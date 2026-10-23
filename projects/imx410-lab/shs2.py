#!/usr/bin/env python3
"""0007/0008 retest (user, 2026-10-21: write order and reloading may matter). The firmware writes 0005,0006,0007,0008
every frame in that order (captures/dual/*/bus.json), so a direct write is overwritten: IMXB v2 substitution holds the
value on every firmware write instead.

    shs2.py OUT [--base V1]

Per value: substitution on -> wait (no restart) -> grab set 'n' -> sensor restart (0011) -> grab set 'r' ->
substitution off. Bus log kept per value to prove what went out.
"""
import argparse, json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bufa_probe as B                                                # noqa: E402
import resweep as R                                                   # noqa: E402

VALUES = [('ref1', [])] + [(f'07_{v:02X}', [(0x0007, v), (0x0008, 0)]) for v in (1, 2, 4, 8, 0x10, 0x20, 0x40, 0x80)] \
    + [(f'08_{v:02X}', [(0x0007, 0), (0x0008, v)]) for v in (1, 2, 4, 8, 0x10, 0x20, 0x40, 0x80)] + [('ref2', [])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--base', default='V1')
    a = ap.parse_args()
    out = pathlib.Path(a.out) / a.base; out.mkdir(parents=True, exist_ok=True)
    import fastsweep as F
    F.cached_assemble()
    B.not_recording()
    if ',0008,' not in B.P().sh('imager mode_now'):
        raise SystemExit('start from live view (mode 8)')
    b = R.Base(out, a.base)
    st = B.bus_state()
    try:
        for name, subs in VALUES:
            d = out / name
            if (d / 'r' / 'p' / 'stats.npz').exists():
                continue
            B.bus_on(st)
            B.bus_subs(st, subs); time.sleep(0.2)
            okn = b.grab_set(d / 'n')
            b.restart(); time.sleep(0.1)
            okr = b.grab_set(d / 'r')
            B.bus_subs(st, [])
            log = B.bus_dump(st)
            sent = [(f'{r:04X}', f'{v:02X}') for _, r, v, _ in log if r in (5, 6, 7, 8)][-8:]
            for sub, ok in (('n', okn), ('r', okr)):
                if ok:
                    for q in ('p', 'f10', 'd'):
                        if (d / sub / q / 'frame.json').exists():
                            R.stats(d / sub / q)
            (d / 'res.json').write_text(json.dumps(dict(subs=[f'{r:04X}={v:02X}' for r, v in subs], n=okn, r=okr, sent=sent)))
            print(name, okn, okr, sent[-4:], flush=True)
            b.restart(); time.sleep(0.1)
    finally:
        try:
            B.bus_subs(st, [])
        finally:
            b.close()


if __name__ == '__main__':
    main()
