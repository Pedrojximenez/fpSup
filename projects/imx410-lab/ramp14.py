#!/usr/bin/env python3
"""FAST_READOUT: which Family A registers hold the 14-bit line time (IMX410_RULES §42, CAPABILITY_MAP).

    ramp14.py OUT GROUP [--hmax 911,800,700,600,500,445] [--src 10]

Virtual 14-bit base V2 (donor mode 6, own sensor window). GROUP's registers are written with the value of mode
--src (10 = 12-bit normal, 8 = 12-bit fast), the sensor restarted, then the SoC HMAX is stepped down as in
half14.py. Table registers only: the mode switch back rewrites them, so no reboot is needed for the sensor;
fastreboot anyway between groups (HMAX and DCLP state). Groups:
  timing  counters that shrink with the line time (14-bit > normal > fast)
  res     the 14-bit-only settings (0042/0403, 007F, 008C/057A, 0453, 0089, 0571, 04F1, 06D9)
  all     both
"""
import argparse, json, pathlib, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bins                                                           # noqa: E402
import bufa_probe as B                                                # noqa: E402
import resweep as R                                                   # noqa: E402
import vmode                                                          # noqa: E402

HREG = 0x30100004
GROUPS = {
    'timing': [0x007E, 0x0081, 0x0083, 0x0084, 0x0085, 0x0086, 0x042A, 0x042D, 0x0430, 0x0441, 0x0482, 0x0484, 0x0487,
               0x0489, 0x048B, 0x04DC, 0x04DF, 0x04E1, 0x04E4, 0x0511, 0x0525, 0x0575, 0x0576, 0x0577, 0x0578,
               0x0585, 0x05D8],
    'res': [0x0042, 0x0403, 0x007F, 0x008C, 0x057A, 0x0453, 0x0089, 0x0571, 0x04F1, 0x06D9],
}
GROUPS['all'] = GROUPS['timing'] + GROUPS['res']


def table_value(mode, reg):
    m = bins.MODES[str(mode)]
    return int(m[next(k for k in m if k.lower() == f'reg_0x{reg:04x}')])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('group', choices=sorted(GROUPS))
    ap.add_argument('--hmax', default='911,800,700,600,500,445'); ap.add_argument('--src', default='10')
    a = ap.parse_args()
    out = pathlib.Path(a.out) / f'{a.group}_m{a.src}'; out.mkdir(parents=True, exist_ok=True)
    writes = [(r, table_value(a.src, r)) for r in GROUPS[a.group]]
    import fastsweep as F
    F.cached_assemble()
    B.not_recording()
    if ',0008,' not in B.P().sh('imager mode_now'):
        raise SystemExit('start from live view (mode 8)')
    vmode.KEEP_WINDOW = True
    b = R.Base(out, 'V2')
    h0 = B.P().mem_get(HREG)[0]
    log = dict(hmax0=f'0x{h0:08X}', writes=[f'{r:04X}={v:02X}' for r, v in writes], steps=[])
    try:
        b.restart(); time.sleep(0.05)
        if b.grab_set(out / 'ref'):                     # the untouched 14-bit base, same boot
            for sub in ('p', 'f10', 'd'):
                R.stats(out / 'ref' / sub)
        for r, v in writes:
            b.s.write(r, v)
        b.restart(); time.sleep(0.05)
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
            B.wr(HREG, h0)
        finally:
            b.close()
            (out / 'steps.json').write_text(json.dumps(log, indent=1))


if __name__ == '__main__':
    main()
