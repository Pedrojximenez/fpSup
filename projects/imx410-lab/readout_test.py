#!/usr/bin/env python3
"""Synthesised-readout tests (PROJECT_FEASIBILITY.md L2/L3/L7): from a base mode, batch-write a set of sensor
registers (sensor_read/batch.S, one call), optionally adjust the SoC receiver window / VMAX, grab frames.

    readout_test.py OUT --set zcam:MODE21 [--from zcam:MODE1] [--extra 0x0003=0x00] [--yend N] [--vmax N]

--set zcam:NAME     every register of that Z CAM readout column (offline/zcam/zcam_readout_regs.csv) that differs
                    from --from (default: the fp mode-10 equivalent, Z CAM MODE1)
Captures: OUT/before (stock), OUT/after (with the set). The sensor is reset (poff 1) at the end: the batch is
not undone register by register.
"""
import argparse, csv, json, pathlib, struct, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / 'sensor_read')]
import fastsweep as F                                                 # noqa: E402
import bufa_probe as B                                                # noqa: E402
import sweep                                                          # noqa: E402


def zcam_set(name, base):
    rows = list(csv.DictReader(open(HERE / 'offline' / 'zcam' / 'zcam_readout_regs.csv')))
    cols = list(rows[0])
    pick = lambda tag: next(c for c in cols if c.startswith('r') and tag in c)
    a, b = pick(base), pick(name)
    out = []
    for r in rows:
        if r[a] != r[b] and r[b] not in ('', '-'):
            out.append((int(r['addr'], 16), int(r[b], 16)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--set', required=True); ap.add_argument('--from', dest='base', default='MODE1_')
    ap.add_argument('--extra', action='append', default=[]); ap.add_argument('--yend', type=int, default=0)
    ap.add_argument('--vmax', type=int, default=0)
    ap.add_argument('--soc', action='append', default=[], help='ADDR=VAL SoC register written after the batch')
    ap.add_argument('--rewindow', action='store_true', help='after the SoC writes, stop BUFA0, redo its window from the '
                    'receiver (new width/height), restart it')
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    regs = zcam_set(a.set.split(':', 1)[1], a.base) if a.set.startswith('zcam:') else []
    regs += [tuple(int(x, 16) for x in e.split('=')) for e in a.extra]
    (out / 'regs.json').write_text(json.dumps([f'{r:04X}={v:02X}' for r, v in regs]))
    print(len(regs), 'registers:', ' '.join(f'{r:04X}={v:02X}' for r, v in regs))
    from armasm import assemble
    import cave
    F.cached_assemble()
    s = F.Session(out, a.yend, False, 10)
    try:
        s.grab(out / 'before')
        code = assemble(HERE / 'sensor_read' / 'batch.S')
        at = cave.claim('imxl.batch', 256)
        tab = cave.claim('imxl.batch.tab', 8 * 128)
        B.P().put(at, code + bytes(-len(code) % 4), 'batch ')
        B.P().put(tab, b''.join(struct.pack('<II', 0x81 | (r >> 8) << 8 | (r & 0xFF) << 16, v) for r, v in regs), 'table ')
        B.call(B.F_DCACHE)
        n = B.call(at, tab, len(regs))
        print('written', n)
        for e in a.soc:
            ad, va = (int(x, 0) for x in e.split('='))
            print(f'SoC 0x{ad:08X}: 0x{B.P().mem_get(ad)[0]:08X} -> 0x{va:08X}')
            B.wr(ad, va)
        if a.rewindow:
            import cave as _cave
            st = _cave.claim('imxl.bufa.struct', 64)
            B.startstop(100)
            B.P().put(st, bytes(20), 'window'); B.call(B.F_WINDOW, st)
            s.h, s.words = B.P().mem_get(0x30182110, 2)
            s.size = s.h * s.words * 4
            s.tail = s.buf + s.size - 16
            B.wr(s.guard, 0); s.guard = s.buf + s.size + 0x100; B.wr(s.guard, 0x5AFE5AFE)
            B.call(B.F_SETADDR, s.scratch)
            B.startstop(10)
            print(f'rewindow: {s.h} rows x {s.words} words')
        if a.vmax:
            vm = B.P().mem_get(0x30100020)[0]
            B.wr(0x30100020, ((a.vmax - 1) << 16) | (vm & 0xFFFF))
        time.sleep(0.4)
        ok = s.grab(out / 'after')
        print('after frame:', 'ok' if ok else 'NO FRAME')
    finally:
        s.close()
    sweep.KEEP = None
    sweep.fastreboot()                                                # the batch is undone by a sensor reset


if __name__ == '__main__':
    main()
