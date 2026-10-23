#!/usr/bin/env python3
"""FAST_READOUT: how short can the line be with the 14-bit AD (PARAM_STATUS #11, CAPABILITY_MAP P0-FAST_READOUT).

    half14.py OUT [--hmax 911,850,...] [--base V2]

Virtual 14-bit base (donor's own sensor window kept), then the SoC line length HMAX (0x30100004, both halves) is
stepped down by direct write; per step a frame pair + DCLP-off frame (resweep.Base.grab_set). Stops at the first
step that gives no frame. HMAX goes back to the base value before leaving; fastreboot afterwards anyway.
Read offline with offline/half14_eval.py (clipping of the top code, blank alternate lines, noise, black).
"""
import argparse, json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bufa_probe as B                                                # noqa: E402
import resweep as R                                                   # noqa: E402
import vmode                                                          # noqa: E402

HREG = 0x30100004


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--base', default='V2')
    ap.add_argument('--hmax', default='911,850,800,750,700,650,600,550,500,450')
    ap.add_argument('--word', help='readout format 0001 written after entering the base (e.g. 2B = 4160 wide)')
    ap.add_argument('--rxw', type=int, help='receiver width in pixels (0x3010000C low half = width/12)')
    a = ap.parse_args()
    out = pathlib.Path(a.out) / (a.base + (f'_w{a.word}' if a.word else '')); out.mkdir(parents=True, exist_ok=True)
    import fastsweep as F
    F.cached_assemble()
    B.not_recording()
    if ',0008,' not in B.P().sh('imager mode_now'):
        raise SystemExit('start from live view (mode 8)')
    vmode.KEEP_WINDOW = True
    b = R.Base(out, a.base)
    h0 = B.P().mem_get(HREG)[0]
    rx0 = B.P().mem_get(0x3010000C)[0]
    log = dict(hmax0=f'0x{h0:08X}', rx0=f'0x{rx0:08X}', word=a.word, rxw=a.rxw, steps=[])
    try:
        if a.word:
            b.s.write(0x0001, int(a.word, 16))
            if a.rxw:
                B.wr(0x3010000C, (rx0 & 0xFFFF0000) | a.rxw // 12)
            b.restart(); time.sleep(0.2)
            import l7
            l7.rewindow(b.s, 1 if b.bits == 14 else 0)
        for h in [int(x) for x in a.hmax.split(',')]:
            B.wr(HREG, (h << 16) | h); time.sleep(0.15)
            d = out / f'h{h:04d}'
            ok = b.grab_set(d)
            if ok:
                for sub in ('p', 'f10', 'd'):
                    if (d / sub / 'frame.json').exists():
                        R.stats(d / sub)
            log['steps'].append(dict(hmax=h, ok=ok))
            print(h, 'ok' if ok else 'NO FRAME', flush=True)
            if not ok:
                break
    finally:
        try:
            B.wr(HREG, h0); B.wr(0x3010000C, rx0)
        finally:
            b.close()
            (out / 'steps.json').write_text(json.dumps(log, indent=1))


if __name__ == '__main__':
    main()
