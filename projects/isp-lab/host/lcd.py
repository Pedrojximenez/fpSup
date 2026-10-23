#!/usr/bin/env python3
"""LCD image layer, read straight from the native output ring (stage 0 tool).

Not a screenshot, not HDMI: the firmware's own output descriptors give the
ring handles and geometry (research/imaging-hw/notes/IMAGE_CHANNELS.md, 10-09
correction: the ring is linear Y0 Cb Y1 Cr 8-bit 4:2:2 at descriptor width).
This is the image layer only -- OSD (menus, REC, fps text) is on other display
layers and is not here yet (RESEARCH_PLAN 3.7).

Camera side: reads only. One temporary read-only MEM1 window over exactly the
active bytes of one ring slot, revoked afterwards. Refuses while recording or
outside standby: no USB during recording or playback.

    lcd.py decode RING.bin W H OUT.png        offline
    lcd.py grab OUT_DIR [--descriptor N]      live (camera must be idle)
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
SHELL = ROOT / 'fpSup/fp_usb_shell'
PROBES = ROOT / 'projects/lut-sup/probes'      # Camera: the reviewed text-shell wrapper

# Three SIGSEQ output descriptors, 0x80 apart; which one feeds the LCD is
# itself a stage 0 question, so the tool reads all of them.
OUT_DESC = tuple(0xC30255B4 + i * 0x80 for i in range(3))
DESC_WORDS = 32
WIN_SLOT = 7                 # MEM1 window slot borrowed by lut-sup the same way
STRIDE_PROBE = (960, 1024, 1280, 1920, 2048)   # plus w +-16/+-32 (stride_check); tiny strides
                                               # only compare neighbouring pixels and prove nothing


def parse_descriptor(words):
    """{w, h, slots[addr]} from one output descriptor, or None when unused.
    Layout (lut-sup 10-09, 0xC30255B4): [3] width, [4] height, [8] slot count,
    [9..] handles, address = 0x40000000 + 4*handle."""
    if len(words) < 13 or words[0] != 0:
        return None
    w, h, n = words[3], words[4], words[8]
    if not (0 < w <= 1920 and 0 < h <= 1088 and 1 <= n <= 4):
        return None
    slots = [0x40000000 + 4 * x for x in words[9:9 + n]]
    if any(not x for x in words[9:9 + n]):
        return None
    span = min((b - a for a, b in zip(slots, slots[1:])), default=w * h * 2)
    if span < w * h * 2:          # slots must hold a whole frame each
        return None
    return {'w': w, 'h': h, 'slots': slots}


def y_step(buf, w, h):
    """Mean |Y(row) - Y(row+1)|: the ring's own stride is the minimum."""
    y = np.frombuffer(buf[:w * h * 2], np.uint8)[0::2].reshape(h, w).astype(np.int16)
    return float(np.abs(np.diff(y, axis=0)).mean())


def stride_check(buf, w, h):
    """Our stride must beat every other candidate, otherwise this mode is not
    the packing measured on 10-09 and the decode must not be trusted."""
    own = y_step(buf, w, h)
    other = []
    for s in sorted(set(STRIDE_PROBE) | {w - 32, w - 16, w + 16, w + 32}):
        if s != w and s * h * 2 <= len(buf):
            other.append((s, y_step(buf, s, h)))
    best = min(other, key=lambda t: t[1]) if other else None
    return {'own': own, 'best_other': best, 'ok': best is None or own < best[1]}


def decode(buf, w, h):
    """(Y, RGB) from Y0 Cb Y1 Cr. RGB uses BT.709 full range: the matrix and
    range are NOT verified (lut-sup analysis.json); use Y for geometry checks."""
    a = np.frombuffer(buf[:w * h * 2], np.uint8).reshape(h, w // 2, 4).astype(np.float32)
    y = np.empty((h, w), np.float32)
    y[:, 0::2], y[:, 1::2] = a[..., 0], a[..., 2]
    cb = np.repeat(a[..., 1], 2, axis=1) - 128
    cr = np.repeat(a[..., 3], 2, axis=1) - 128
    r = y + 1.5748 * cr
    g = y - 0.1873 * cb - 0.4681 * cr
    b = y + 1.8556 * cb
    rgb = np.clip(np.stack([r, g, b], -1), 0, 255).astype(np.uint8)
    return y.astype(np.uint8), rgb


def save_png(path, rgb):
    from PIL import Image
    Image.fromarray(rgb).save(path)


# ---- live -------------------------------------------------------------------

def _camera():
    sys.path.insert(0, str(SHELL))
    sys.path.insert(0, str(PROBES))
    import putfile
    from native_mode_trial import Camera
    return Camera(putfile.mem_line), putfile


def _idle(cam):
    cam.status()
    if cam.integer('status get is_recording') != 0:
        raise RuntimeError('recording: no USB during recording')


def descriptors(cam):
    return [(hex(a), cam.words(a, DESC_WORDS)) for a in OUT_DESC]


def grab(cam, api, which=None):
    """Read one slot of every valid descriptor (or only `which`). Returns a list
    of {index, desc, slot, raw, before, after}. Not atomic: the producer keeps
    running; before/after descriptor words are kept so tearing is visible."""
    _idle(cam)
    before = descriptors(cam)
    caps = api.mem_caps(refresh=True)
    if not caps or len(caps['windows']) != 8:
        raise RuntimeError('MEM1 required')
    if tuple(caps['windows'][WIN_SLOT]) != (0, 0, 0):
        raise RuntimeError('MEM1 window slot already owned; refusing to borrow')
    out = []
    for i, (addr, words) in enumerate(before):
        if which is not None and i != which:
            continue
        d = parse_descriptor(words)
        if not d:
            continue
        slot = d['slots'][0]
        n = d['w'] * d['h'] * 2
        if n > caps['xfer']:
            raise RuntimeError('frame larger than one MEM1 transfer')
        grant = (slot, n, 1)
        try:
            api.mem_window(WIN_SLOT, *grant)
            if tuple(api.mem_caps(refresh=True)['windows'][WIN_SLOT]) != grant:
                raise RuntimeError('window grant mismatch')
            _idle(cam)
            raw = api.mem_read(slot, n, sync=False, label='isp lcd')
        finally:
            now = api.mem_caps(refresh=True)
            if now is None:
                raise RuntimeError('window state uncertain')
            if tuple(now['windows'][WIN_SLOT]) == grant:      # revoke only our own tuple
                api.mem_window(WIN_SLOT, 0, 0, 0)
            if tuple(api.mem_caps(refresh=True)['windows'][WIN_SLOT]) != (0, 0, 0):
                raise RuntimeError('window revocation not verified')
        if len(raw) != n:
            raise RuntimeError('short ring read')
        out.append({'index': i, 'desc': addr, 'w': d['w'], 'h': d['h'], 'slot': slot, 'raw': raw})
    after = descriptors(cam)
    for r in out:
        r['descriptor_changed'] = before[r['index']] != after[r['index']]
    return out, before, after


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    d = sub.add_parser('decode')
    d.add_argument('raw', type=Path); d.add_argument('w', type=int); d.add_argument('h', type=int)
    d.add_argument('png', type=Path)
    g = sub.add_parser('grab')
    g.add_argument('out', type=Path)
    g.add_argument('--descriptor', type=int, choices=range(len(OUT_DESC)))
    a = ap.parse_args()

    if a.cmd == 'decode':
        buf = a.raw.read_bytes()
        chk = stride_check(buf, a.w, a.h)
        _, rgb = decode(buf, a.w, a.h)
        save_png(a.png, rgb)
        print(json.dumps(chk))
        return 0 if chk['ok'] else 1

    a.out.mkdir(parents=True, exist_ok=False)
    cam, api = _camera()
    report = {'date_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'atomic': False,
              'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    try:
        frames, before, after = grab(cam, api, a.descriptor)
        report.update(before=before, after=after, frames=[])
        for f in frames:
            stem = f'desc{f["index"]}'
            (a.out / f'{stem}.yuyv').write_bytes(f['raw'])
            chk = stride_check(f['raw'], f['w'], f['h'])
            _, rgb = decode(f['raw'], f['w'], f['h'])
            save_png(a.out / f'{stem}.png', rgb)
            report['frames'].append({k: v for k, v in f.items() if k != 'raw'} | {
                'slot': hex(f['slot']), 'sha256': hashlib.sha256(f['raw']).hexdigest(), 'stride': chk})
        report['status'] = 'ok' if frames else 'no valid descriptor'
    except Exception as e:                                  # noqa: BLE001 -- the report keeps the reason
        report.update(status='failed', error=str(e))
    finally:
        report['transcript'] = cam.transcript
        (a.out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n')
    print(report['status'])
    return 0 if report['status'] == 'ok' else 1


if __name__ == '__main__':
    raise SystemExit(main())
