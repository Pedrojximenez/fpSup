#!/usr/bin/env python3
"""Does a register act row by row during readout? Toggle it on the camera (toggle.S) while BUFA0 writes into the
frame buffer, then look for horizontal bands in the odd/even-row ratio.

    rowlatch.py OUT --reg 0x23A --a 0x01 --b 0x00 [--with 0x738=0x10] [--pairs 40] [--loops 200000]
"""
import argparse, pathlib, sys, time, json
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE)]
import fastsweep as F                                                 # noqa: E402
import bufa_probe as B                                                # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--reg', default='0x23A')
    ap.add_argument('--a', default='0x01'); ap.add_argument('--b', default='0x00')
    ap.add_argument('--with', dest='with_', action='append', default=[])
    ap.add_argument('--pairs', type=int, default=40); ap.add_argument('--loops', type=int, default=200000)
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    from armasm import assemble
    import cave
    F.cached_assemble()
    s = F.Session(out, 0, False, 10)
    reg = int(a.reg, 16)
    try:
        for w in a.with_:
            r, v = (int(x, 16) for x in w.split('='))
            s.write(r, v)
        code = assemble(HERE / 'toggle.S')
        at = cave.claim('imxl.toggle', 256)
        B.P().put(at, code + bytes(-len(code) % 4), 'toggle')
        B.call(B.F_DCACHE)
        time.sleep(0.2)
        hdr = 0x81 | (reg >> 8) << 8 | (reg & 0xFF) << 16
        # steer the DMA into buf, toggle for a while (frames overwrite each other), steer back
        for i in range(4):
            B.wr(s.tail + 4 * i, F.SENT)
        B.wr(0x30182180, B.phys(s.buf) >> 2)
        t0 = time.time()
        n = B.call(at, hdr, int(a.a, 16) | int(a.b, 16) << 8, a.pairs, a.loops)
        dt = time.time() - t0
        B.wr(0x30182180, B.phys(s.scratch) >> 2)
        print(f'{n} pairs in {dt * 1000:.0f} ms host-side (includes the call overhead)')
        time.sleep(0.05)
        B.P().mem_window(B.WIN, s.buf, s.size, 1)
        try:
            raw = B.P().mem_read(s.buf, s.size, label='frame ')
        finally:
            B.P().mem_window(B.WIN, s.buf, s.size, 0)
        (out / 'frame.raw').write_bytes(raw)
        (out / 'frame.json').write_text(json.dumps(dict(height=s.h, line_words=s.words, window=s.base_window,
                                                         reg=a.reg, a=a.a, b=a.b, pairs=a.pairs, loops=a.loops), indent=1))
        s.write(reg, int(a.a, 16))
    finally:
        for w in a.with_:
            r, _ = (int(x, 16) for x in w.split('='))
            s.write(r, 0)
        s.close()
    from decode12 import decode12
    img = decode12(raw, s.h, s.words).astype(float)
    top = s.base_window >> 16
    x = img[top:] - img[1:top - 3].mean()
    gr, gb = x[0::2, 1::2], x[1::2, 0::2]
    ratio = gb.mean(axis=1) / np.maximum(gr.mean(axis=1), 1)
    np.save(out / 'row_ratio.npy', ratio)
    q = np.round(ratio[::16], 2)
    print('Gb/Gr per cell row (every 16th):', q.tolist())


if __name__ == '__main__':
    main()
