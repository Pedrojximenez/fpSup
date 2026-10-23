#!/usr/bin/env python3
"""Readout planner for the UI (user's design, 2026-10-22): crop -> resolution -> fps -> choice.
Quality is told apart by rolling shutter only for now (user: 品質先用 RS 區分; real image tests later).

    readout_plan.py options --crop HD --out FHD [--fps 119.88] [--bits 12] [--media sd|ssd]
    readout_plan.py matrix  [--list 24,29.97,59.94,119.88,239.76]
    readout_plan.py plan    KEY --crop 6060x3408 --out 1920x1080 --fps 119.88

Sensor side: readout_cfg (IMX410_RULES §42-§58). Recording side: notes/ISP_SIZE_RULES.md --
the recording window is the mode raster; crop = RWZM Z (x1024, 1024..16384, per axis) + a centred DefaultCrop;
active width %16, height even, rec >= active + (16, 10); rec_w = (raster_w*1024//Z) & ~15, rec_h = (rows*1024//Z) & ~1;
recording fps from the fixed list; bits 8/10/12; data rate from the rec matrix; RWZM ratio denominator > 5 = banding.
"""
import argparse, json
from fractions import Fraction
import readout_cfg as C

PITCH_UM = 5.94
REC_FPS = [23.976, 24, 25, 29.97, 48, 50, 59.94, 100, 119.88, 239.76, 279.72]
MEDIA_MBPS = {'sd': 90, 'ssd': 380}          # hard limits; SSD > 220 MB/s sustained not proven for long takes (ISP_SIZE_RULES §4)
MEDIA_SAFE = {'sd': 90, 'ssd': 220}


def _mm(w_mm, h_mm):
    return round(w_mm * 1000 / PITCH_UM / 12) * 12, round(h_mm * 1000 / PITCH_UM / 2) * 2


CROPS = {'OG': (6060, 4040), 'HD': (6060, 3408), 'S35': _mm(24.89, 14.00), 'APS-C': _mm(23.5, 15.6)}
RES = {'1K': 1008, '2K': 2016, '3K': 3024, '3.5K': 3456, '4K': 3840}      # active (DefaultCrop) widths
RES_HD = {'FHD': (1920, 1080), 'UHD': (3840, 2160)}


def resolutions(crop):
    cw, ch = CROPS[crop]
    out = {k: (w, round(w * ch / cw / 2) * 2) for k, w in RES.items()}
    if crop == 'HD':
        out.update(RES_HD)
    return out


def size(text, table):
    if text in table:
        return table[text]
    w, h = text.lower().split('x')
    return int(w), int(h)


def record(p, bits, fps, media):
    """ISP_SIZE_RULES §6: Z per axis so the active area is the requested output, rec matrix, margins, data rate."""
    raster_w, raster_h = p['fmt_w'], p['out_h']
    ow, oh = p['out']
    # Z from the crop, but never so large that the rec matrix loses the 16/10 margin: when the crop fills the
    # raster, the margin trims it by ~1 % (the recorded field is then (act/(act+16)) of the crop)
    zh = max(1024, min(16384, round(1024 * p['rwzm'][0]), raster_w * 1024 // (ow + 16)))
    zv = max(1024, min(16384, round(1024 * p['rwzm'][1]), raster_h * 1024 // (oh + 10)))
    rec_w = (raster_w * 1024 // zh) & ~15
    rec_h = (raster_h * 1024 // zv) & ~1
    issues = []
    if ow % 16:
        issues.append('width %16')
    if oh % 2:
        issues.append('height odd')
    if ow + 16 > rec_w or oh + 10 > rec_h:
        issues.append('no 16/10 margin (crop a little more or enlarge raster)')
    if bits not in (8, 10, 12):
        issues.append(f'{bits}-bit not recordable')
    if fps and not any(abs(fps - f) < 0.01 for f in REC_FPS):
        issues.append('fps not in the recording list')
    mbps = (rec_w * rec_h * bits / 8 + 79e3) * (fps or p['fps']) / 1e6
    if mbps > MEDIA_MBPS[media]:
        issues.append(f'{mbps:.0f} MB/s > {media} {MEDIA_MBPS[media]}')
    warn = []
    if mbps > MEDIA_SAFE[media] and mbps <= MEDIA_MBPS[media]:
        warn.append(f'{mbps:.0f} MB/s: long takes not proven on {media}')
    if rec_w * rec_h * bits / 8 < 714e3:
        warn.append('frame < 714 KB (descriptor pool risk)')
    zf = [Fraction(z, 1024).limit_denominator(64) for z in (zh, zv)]
    return dict(Z=[zh, zv], rec=[rec_w, rec_h], origin=[(rec_w - ow) // 2, (rec_h - oh) // 2], mbps=mbps,
                banding=any(f.denominator > 5 for f in zf if f != 1), issues=issues, warnings=warn)


def options(cw, ch, ow, oh, fps=None, bits=12, media='sd'):
    done = C.validated()
    out = []
    for r in C.READOUTS:
        try:
            p = C.plan(r['key'], cw, ch, ow, oh, fps)
        except ValueError:
            continue
        p['record'] = record(p, min(bits, 12), fps, media)
        p['verified'] = done.get(p['id'], {}).get('PASS')
        out.append(p)
    return sorted(out, key=lambda p: p['rolling_ms'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=('options', 'matrix', 'plan'))
    ap.add_argument('key', nargs='?')
    ap.add_argument('--crop', default='HD'); ap.add_argument('--out', default='FHD'); ap.add_argument('--fps', type=float)
    ap.add_argument('--bits', type=int, default=12); ap.add_argument('--media', default='sd', choices=sorted(MEDIA_MBPS))
    ap.add_argument('--list', default='23.976,29.97,59.94,100,119.88,239.76')
    a = ap.parse_args()
    if a.cmd == 'matrix':
        fl = [float(x) for x in a.list.split(',')]
        print('crop   res   out        ' + ''.join(f'{f:>8g}' for f in fl) + '   (readouts possible on the sensor / of those recordable on ' + a.media + ')')
        for crop in CROPS:
            for rn, (ow, oh) in resolutions(crop).items():
                cw, ch = CROPS[crop]
                cells = []
                for f in fl:
                    ops = options(cw, ch, ow, oh, f, a.bits, a.media)
                    rec = sum(1 for p in ops if not p['record']['issues'])
                    cells.append(f'{len(ops)}/{rec}' if ops else '.')
                print(f'{crop:6s} {rn:5s} {ow}x{oh:<6d}' + ''.join(f'{c:>8s}' for c in cells))
        return
    cw, ch = size(a.crop, CROPS)
    ow, oh = resolutions(a.crop)[a.out] if a.crop in CROPS and a.out in resolutions(a.crop) else size(a.out, {})
    if a.cmd == 'plan':
        p = C.plan(a.key, cw, ch, ow, oh, a.fps); p['record'] = record(p, min(a.bits, 12), a.fps, a.media)
        print(json.dumps(p, indent=1, default=str)); return
    ops = options(cw, ch, ow, oh, a.fps, a.bits, a.media)
    if not ops:
        raise SystemExit('nothing can deliver this')
    for p in ops:
        v = {True: 'verified', False: 'FAILED', None: 'untested'}[p['verified']]
        rc = p['record']
        print(f"{p['key']:8s} RS {p['rolling_ms']:6.2f} ms  max {p['fps_max']:6.1f} fps  raster {p['fmt_w']}x{p['out_h']}"
              f"  Z {rc['Z'][0]}/{rc['Z'][1]}  rec {rc['rec'][0]}x{rc['rec'][1]} {rc['mbps']:.0f} MB/s"
              f"{'  banding' if rc['banding'] else ''}  {'REC OK' if not rc['issues'] else 'no rec: ' + '; '.join(rc['issues'])}{' (' + '; '.join(rc['warnings']) + ')' if rc['warnings'] else ''}  [{v}; {p['ev']}]")


if __name__ == '__main__':
    main()
