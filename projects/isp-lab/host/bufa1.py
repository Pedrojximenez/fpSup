#!/usr/bin/env python3
"""RWZM output (BUFA1) in standby, read only -- no recording, nothing armed.

In live view BUFA1 is already running: it feeds the preview (BUFA_FRONT_TAP.md:
"待機時 BUFA1 是開著的", 0x30002060 bit4).  Its ISR (blk_c01.c ~32784) rotates
the slots and leaves the frame it just finished in [0xC31D96D4] (register
units: address = value*4 + 0x40000000, as 0x30182280 = 0x02A400E0 ->
0x4A900380 on 10-20).  So this tool only reads: the BUFA1 register block,
that pointer, and one frame through a temporary read-only MEM1 window.

Geometry is not assumed: by analogy with BUFA0 (0x30182110 rows, 0x30182114
words per row) the candidates are 0x30182210/0x30182214; the tool saves the
raw words and every register so the layout can be checked offline, and
scores the 12-bit decode the way lcd.py scores a stride.

    bufa1.py grab OUT_DIR
"""
import argparse, datetime as dt, hashlib, json, pathlib, sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SHELL = ROOT / 'fpSup' / 'fp_usb_shell'
IMXL = ROOT / 'projects' / 'imx410-lab'

REG0, REG_N = 0x30182200, 0xA8 // 4         # 0x30182200..0x301822A4 (FUN_c0149ff0 writes these)
LAST = 0xC31D96D4                           # the frame the BUFA1 ISR finished last (register units)
EN = 0x30002060                             # bit4 = BUFA1 running
WIN_SLOT = 7


def addr(v):
    return (v & 0x3FFFFFFF) * 4 + 0x40000000


def smooth(img):
    """Same-colour neighbour step (dx2, dy2): small for a real CFA image."""
    a = img.astype(np.int32)
    return float(np.abs(a[:, 2:] - a[:, :-2]).mean()), float(np.abs(a[2:] - a[:-2]).mean())


def decode12(raw, rows, wpr):
    sys.path.insert(0, str(IMXL))
    from decode12 import decode12 as d
    return d(raw, rows, wpr)


def regs(p):
    out = {}
    for i in range(0, REG_N, 8):
        vals = p.mem_get(REG0 + 4 * i, min(8, REG_N - i))
        for k, v in enumerate(vals):
            out[REG0 + 4 * (i + k)] = v
    return out


def grab(out):
    sys.path.insert(0, str(SHELL))
    import putfile as p
    if not p.sh('status get is_recording').strip().endswith('0'):
        raise SystemExit('recording: no USB during recording')
    en = p.mem_get(EN)[0]
    if not (en >> 4) & 1:
        raise SystemExit(f'BUFA1 not running (0x30002060 = {en:#x}): not in live view?')
    r = regs(p)
    last = p.mem_get(LAST)[0]
    # 10-24 on camera: [0xC31D96D4] is 0 in standby; the one standby buffer is
    # 0x30182280 (static, not rotated): 8-bit Bayer, 0x30182214 words a row
    if not last:
        last = r[0x30182280]
    rows, wpr = r[0x30182210] & 0x3FFF, r[0x30182214]
    n = rows * wpr * 4
    if not last or not (0 < rows <= 8192 and 0 < wpr <= 8192) or n > (16 << 20):
        raise SystemExit(f'unexpected geometry: last {last:#x} rows {rows} wpr {wpr}')
    at = addr(last)
    caps = p.mem_caps(refresh=True)
    if tuple(caps['windows'][WIN_SLOT]) != (0, 0, 0):
        raise SystemExit('MEM1 window slot already owned')
    grant = (at, n, 1)
    try:
        p.mem_window(WIN_SLOT, *grant)
        raw = p.mem_read(at, n, sync=False, label='bufa1 ')
    finally:
        if tuple(p.mem_caps(refresh=True)['windows'][WIN_SLOT]) == grant:
            p.mem_window(WIN_SLOT, 0, 0, 0)
    last_after = p.mem_get(LAST)[0]
    out.mkdir(parents=True, exist_ok=False)
    (out / 'bufa1.raw').write_bytes(raw)
    rep = {'date_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'atomic': False,
           'en': en, 'regs': {f'{a:#010x}': v for a, v in r.items()},
           'last': last, 'last_after': last_after, 'frame_at': at, 'rows': rows, 'wpr': wpr,
           'sha256': hashlib.sha256(raw).hexdigest(),
           'tool_sha256': hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()}
    img8 = np.frombuffer(raw, np.uint8).reshape(rows, wpr * 4)
    rep['bayer8'] = {'shape': list(img8.shape), 'dx2_dy2': smooth(img8),
                     'phase_means': [float(img8[y::2, x::2].mean()) for y in (0, 1) for x in (0, 1)]}
    try:
        img = decode12(raw, rows, wpr)
        rep['decode12'] = {'shape': list(img.shape), 'min': int(img.min()), 'max': int(img.max()),
                           'dx2_dy2': smooth(img)}
        np.save(out / 'bufa1_12.npy', img)
        from PIL import Image
        v = img.astype(np.float32)
        v = np.clip((v - np.percentile(v, 1)) / max(np.percentile(v, 99.5) - np.percentile(v, 1), 1), 0, 1)
        Image.fromarray((v ** 0.45 * 255).astype(np.uint8)).save(out / 'bufa1_12.png')
    except Exception as e:                                   # noqa: BLE001 -- the raw is kept regardless
        rep['decode12_error'] = str(e)
    (out / 'report.json').write_text(json.dumps(rep, indent=1) + '\n')
    print(json.dumps({k: rep[k] for k in ('rows', 'wpr', 'frame_at', 'last', 'last_after') if k in rep}),
          rep['bayer8'])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    g = sub.add_parser('grab'); g.add_argument('out', type=pathlib.Path)
    a = ap.parse_args()
    grab(a.out)


if __name__ == '__main__':
    main()
