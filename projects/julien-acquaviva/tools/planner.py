#!/usr/bin/env python3
"""R168 output-size calculation on a host, without firmware or emulation.

The binary supplies allowed settings, nominal windows and per-setting width
ceilings. This code implements its integer output-size/RWZM calculation. It
does not calculate sensor registers, throughput guarantees or new frame rates.
"""
from functools import lru_cache
from pathlib import Path
import argparse
import json

DATA = Path(__file__).resolve().parent.parent / 'extracted/planner-data.json'


def resolution(window, width_limit, ratio):
    width, height = window
    numerator, denominator = map(int, ratio.split(':'))
    if min(width, height, width_limit, numerator, denominator) <= 0:
        raise ValueError('positive dimensions, limit and ratio required')
    if width <= width_limit:
        return dict(output=[width, height], rwzm_raw=1023, rwzm_effective=1024, one=True)
    out_h = width_limit * denominator // numerator
    k = (width * 1024 + width_limit - 1) // width_limit
    return dict(output=[width_limit, out_h], rwzm_raw=k, rwzm_effective=k, one=False)


@lru_cache(maxsize=1)
def model():
    doc = json.loads(DATA.read_text())
    return doc, {tuple(r[:4]): tuple(r[4:]) for r in doc['settings']}


def plan(media='SSD', ratio='3:2', crop=1.0, fps=24):
    doc, settings = model()
    ci = round(float(crop) * 10) - 10
    if abs(float(crop) - (ci + 10) / 10) > 1e-8:
        raise ValueError('R168 crop must be a step of 0.1')
    try:
        key = doc['media'].index(media), doc['ratios'].index(ratio), ci, doc['fps'].index(float(fps))
        w, h, limit = settings[key]
    except (ValueError, KeyError):
        raise ValueError('setting is outside the published R168 modes') from None
    return dict(media=media, ratio=ratio, crop=float(crop), fps=float(fps),
                nominal_window=[w, h], output_width_limit=limit,
                **resolution((w, h), limit, ratio))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--media', choices=('SSD', 'v90', 'v60', 'v30'), default='SSD')
    p.add_argument('--ratio', choices=('3:2', '16:9', '2:1'), default='3:2')
    p.add_argument('--crop', type=float, default=1)
    p.add_argument('--fps', type=float, default=24)
    args = p.parse_args()
    print(json.dumps(plan(args.media, args.ratio, args.crop, args.fps), indent=2))


if __name__ == '__main__':
    main()
