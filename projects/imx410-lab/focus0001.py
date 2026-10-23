#!/usr/bin/env python3
"""Second look at the 0001 values that gave an image in sweep0001 (or alternated): per value, 3 frame pairs a few
frames apart, all raws kept, so frame-to-frame alternation and the image content can be checked offline.

    focus0001.py OUT V1 01,03,15,...
"""
import json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bufa_probe as B                                                # noqa: E402
import resweep as R                                                   # noqa: E402
import ramp14                                                         # noqa: E402
from sweep0001 import DONOR, status                                   # noqa: E402


def main():
    out = pathlib.Path(sys.argv[1]) / sys.argv[2]; out.mkdir(parents=True, exist_ok=True)
    vals = [int(x, 16) for x in sys.argv[3].split(',')]
    stock = ramp14.table_value(DONOR[sys.argv[2]], 0x0001)
    import fastsweep as F
    F.cached_assemble()
    B.not_recording()
    if ',0008,' not in B.P().sh('imager mode_now'):
        raise SystemExit('start from live view (mode 8)')
    b = R.Base(out, sys.argv[2])
    s = b.s
    try:
        for v in [stock] + vals:
            d = out / f'{v:02X}'
            if (d / 'res.json').exists():
                continue
            s.write(0x0001, v); b.restart(); time.sleep(0.2)
            res = dict(value=f'{v:02X}', grabs=[])
            s.pair = True
            for k in range(3):
                st = status()
                ok = s.grab(d / f'g{k}')
                res['grabs'].append(dict(ok=ok, status=st))
                time.sleep(0.1)
            s.pair = False
            s.write(0x0001, stock); b.restart(); time.sleep(0.15)
            res['recovered'] = s.grab(out / 'back')
            (d / 'res.json').write_text(json.dumps(res))
            print(f'{v:02X}', [g['ok'] for g in res['grabs']], 'recovered' if res['recovered'] else 'NOT RECOVERED', flush=True)
            if not res['recovered']:
                break
    finally:
        b.close()


if __name__ == '__main__':
    main()
