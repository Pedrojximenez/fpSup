#!/usr/bin/env python3
"""Class B of the re-sweep (notes/RESWEEP_DESIGN.md §3): the 161 mode-table registers. A value is never written on
top of a running mode (that left DCLP/receiver/clock inconsistent, §39); instead the base's REG row is rebuilt with
the value and the firmware switches into it (vmode), so every block is programmed for the sensor state it gets.

    resweep_b.py OUT REG[,REG...] [--bases V1,V3,V4] [--values 00,01,...]

Per register and base: the stock row as reference, then one switch per value: grab set (p pair, f10, DCLP off d),
stats, keep raw when it differs. ~10 s per value (switch in and out of magnify).
"""
import argparse, json, pathlib, struct, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bins, vmode, resweep                                            # noqa: E402
import bufa_probe as B                                                 # noqa: E402

TABLE = [int(k[6:], 16) for k in bins.MODES['10'] if k.startswith('reg_')]   # REG row word 1.. in this order


def rows_with(donor, reg, val):
    rows = vmode.donor_rows(donor)
    r = bytearray(rows['REG'])
    struct.pack_into('<I', r, 4 * (1 + TABLE.index(reg)), val)
    rows['REG'] = bytes(r)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('regs')
    ap.add_argument('--bases', default='V1,V2,V3,V4'); ap.add_argument('--values', default=','.join(resweep.VALUES))
    a = ap.parse_args()
    vmode.KEEP_WINDOW = True                    # every round from R2 on: the donor's own sensor window (§7)
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    import fastsweep as F
    F.cached_assemble()
    log = open(out / 'run.log', 'a')
    say = lambda t: (print(t, flush=True), log.write(t + '\n'), log.flush())
    B.not_recording()
    for reg in [int(x, 16) for x in a.regs.split(',') if x]:
        if reg not in TABLE:
            say(f'{reg:04X} not a table register'); continue
        for bname in a.bases.split(','):
            if (out / 'STOP').exists():
                return
            donor = resweep.BASES[bname][0]
            stock = int(bins.MODES[str(donor)][f'reg_0x{reg:04x}'])
            bdir = out / bname / f'{reg:04X}'
            ref = bdir / 'stock'
            if not (ref / 'p' / 'stats.npz').exists():
                b = resweep.Base(out, bname)
                try:
                    if b.grab_set(ref):
                        for sub in ('p', 'f10', 'd'):
                            resweep.stats(ref / sub)
                finally:
                    b.close()
            rs = dict(__import__('numpy').load(ref / 'p' / 'stats.npz'))
            for v in a.values.split(','):
                if (out / 'STOP').exists():
                    return
                val = int(v, 16)
                d = bdir / v
                if val == stock or (d / 'p' / 'stats.npz').exists() or (d / 'nofail').exists():
                    continue
                try:
                    b = resweep.Base(out, bname, rows=rows_with(donor, reg, val))
                except SystemExit as e:
                    d.mkdir(parents=True, exist_ok=True); (d / 'nofail').write_text(f'{e}\n')
                    say(f'{bname} {reg:04X}={v} SWITCH FAILED {e}'); break
                try:
                    if not b.grab_set(d):
                        d.mkdir(parents=True, exist_ok=True); (d / 'nofail').write_text('no frame\n')
                        say(f'{bname} {reg:04X}={v} NO FRAME'); break
                    st = [resweep.stats(d / sub) for sub in ('p', 'f10', 'd') if (d / sub / 'frame.json').exists()]
                    ch = any(resweep.differs(x, rs) for x in st)
                    if not ch:
                        resweep.drop_raw(d)
                    say(f'{bname} {reg:04X}={v} (stock {stock:02X}) {"CHANGED" if ch else "."}')
                finally:
                    b.close()


if __name__ == '__main__':
    main()
