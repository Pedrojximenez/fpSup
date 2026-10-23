#!/usr/bin/env python3
"""L7 live steps (notes/L7_14BIT.md §5).  T0: sensor untouched (mode 10, 12-bit stream), BUFA0 re-windowed with the
14-bit format (window struct byte +0xE = 1) into a buffer big enough for it; decode with decode14.

    l7.py t0 OUT
"""
import json, pathlib, struct, sys, time
import numpy as np
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fastsweep as F                                                 # noqa: E402
import bufa_probe as B                                                # noqa: E402
from decode14 import decode14                                         # noqa: E402
from decode12 import decode12                                         # noqa: E402


def rewindow(s, enum):
    import cave
    st = cave.claim('imxl.bufa.struct', 64)
    B.startstop(100)
    stc = bytearray(20); stc[0xE] = enum
    B.P().put(st, bytes(stc), 'window'); B.call(B.F_WINDOW, st)
    h, words = B.P().mem_get(0x30182110, 2)
    fmt = B.P().mem_get(0x3018210C)[0]
    size = h * words * 4
    print(f'BUFA0 window enum {enum}: {h} rows x {words} words, format reg 0x{fmt:X}, {size} B (buffer {s.alloc})')
    if size + 0x200 > s.alloc:
        raise SystemExit('buffer too small: not arming')
    s.h, s.words, s.size = h, words, size
    s.tail = s.buf + size - 16
    s.guard = s.buf + size + 0x100; B.wr(s.guard, 0x5AFE5AFE)
    B.call(B.F_SETADDR, s.scratch)
    B.startstop(10)


def t0(out):
    F.cached_assemble()
    s = F.Session(out, 0, False, 10, min_alloc=24 << 20)
    try:
        s.grab(out / 'frame12')
        rewindow(s, 1)
        ok = s.grab(out / 'frame14')
        print('14-bit frame:', 'ok' if ok else 'NO FRAME')
    finally:
        try:
            rewindow(s, 0)
        except SystemExit:
            pass
        s.close()
    m12 = json.loads((out / 'frame12' / 'frame.json').read_text())
    a12 = decode12((out / 'frame12' / 'frame.raw').read_bytes(), m12['height'], m12['line_words']).astype(float)
    m14 = json.loads((out / 'frame14' / 'frame.json').read_text())
    a14 = decode14((out / 'frame14' / 'frame.raw').read_bytes(), m14['height'], m14['line_words']).astype(float)
    top = m12['window'] >> 16
    print('12-bit: black', round(a12[1:top - 3].mean(), 1), ' median', np.median(a12[top:]))
    print('14-bit: shape', a14.shape, ' black', round(a14[1:top - 3].mean(), 1), ' median', np.median(a14[top:]),
          ' low 2 bits nonzero', round(float(((a14.astype(int) & 3) != 0).mean()), 3))
    w = min(a12.shape[1], a14.shape[1])
    q = (a12[top:, :w] > 300) & (a12[top:, :w] < 3800)
    print('ratio 14/12 on mid tones:', round(float(np.median(a14[top:, :w][q] / a12[top:, :w][q])), 3),
          ' corr', round(float(np.corrcoef(a14[top:, :w][q], a12[top:, :w][q])[0, 1]), 4))


VBIN2 = [(0x0005, 0x03), (0x001C, 0x03), (0x0717, 0x04), (0x071E, 0x05), (0x0720, 0x05), (0x0722, 0x02), (0x0723, 0x02),
         (0x0724, 0x02), (0x0725, 0x02), (0x0726, 0x01), (0x0728, 0x3D), (0x072A, 0xF0), (0x072B, 0x03), (0x072C, 0x04),
         (0x0734, 0x05), (0x0735, 0x05), (0x0737, 0x02), (0x0738, 0x02), (0x0739, 0x02), (0x073A, 0x02), (0x0792, 0x22),
         (0x0793, 0x02), (0x0794, 0x05), (0x079C, 0x3D), (0x0242, 0x2C), (0x0278, 0x04), (0x0279, 0x01), (0x027B, 0x04),
         (0x08B6, 0x01), (0x08B7, 0x68), (0x0003, 0x00), (0x0018, 0x12)]


def batch(regs):
    from armasm import assemble
    import cave
    code = assemble(HERE / 'sensor_read' / 'batch.S')
    at = cave.claim('imxl.batch', 256); tab = cave.claim('imxl.batch.tab', 8 * 128)
    B.P().put(at, code + bytes(-len(code) % 4), 'batch ')
    blob = b''.join(struct.pack('<II', 0x81 | (r >> 8) << 8 | (r & 0xFF) << 16, v) for r, v in regs)
    for k in range(4):                      # a dropped bulk chunk ("cursor diverged") is transient: resend
        try:
            B.P().put(tab, blob, 'table ')
            break
        except SystemExit as e:
            if k == 3 or 'diverged' not in str(e) and 'unavailable' not in str(e):
                raise
            print('table upload retry:', e)
    B.call(B.F_DCACHE)
    return B.call(at, tab, len(regs))


def t1(out, word='0x29', yend=1500, rx14=True, fam14=True, geom=None, soc=()):
    """14-bit ADC + vertical-only 2:1 from mode 10; receiver/BUFA in 14 bit (rx14) or kept at 12."""
    F.cached_assemble()
    s = F.Session(out, yend, False, 10, min_alloc=24 << 20)
    regs = [(r, v) for r, v in json.loads((HERE / 'captures' / 'l7' / 'fam14.json').read_text()) if r != 0x0001] if fam14 else []
    regs += (geom if geom is not None else VBIN2) + [(0x0001, int(word, 16))]
    try:
        s.grab(out / 'before')
        B.startstop(100)
        n = batch(regs)
        vm = B.P().mem_get(0x30100020)[0]
        B.wr(0x30100004, 0x038E038E if fam14 else 0x01BC01BC)          # HMAX 911 with the 14-bit ADC
        pass                                                        # VMAX kept: the AE shutter is computed for it
        for ad, va in soc:
            B.wr(ad, va)
        if rx14:
            B.wr(0x30100800, 0x00112013); B.wr(0x300E10B4, 3)
        print(f'batch {n} regs; HMAX {"911" if fam14 else "445"}; receiver {"14" if rx14 else "12"}-bit')
        time.sleep(0.3)
        rewindow(s, 1 if rx14 else 0)
        time.sleep(0.2)
        ok = s.grab(out / 'after')
        print('after:', 'ok' if ok else 'NO FRAME')
    finally:
        s.close()
    import sweep
    sweep.KEEP = None
    sweep.fastreboot()
    if (out / 'after' / 'frame.raw').exists():
        m = json.loads((out / 'after' / 'frame.json').read_text())
        dec = decode14 if rx14 else decode12
        a = dec((out / 'after' / 'frame.raw').read_bytes(), m['height'], m['line_words']).astype(float)
        np.save(out / 'after.npy', a[:, ::4].astype(np.float32))
        print('after: shape', a.shape, ' first 50 row means', np.round(a[:50, 100:-100].mean(1)).astype(int).tolist()[::5],
              ' median', np.median(a[60:]), ' max', a.max(), ' low2 nonzero', round(float(((a.astype(int) & 3) != 0).mean()), 3))
        same = a[60:, 0:-4:2]; nb = a[60:, 2::2][:, :same.shape[1]]
        print('same-colour neighbour |diff| median', np.median(np.abs(same - nb)))


if __name__ == '__main__':
    if sys.argv[1] == 't1':
        o = pathlib.Path(sys.argv[2]); o.mkdir(parents=True, exist_ok=True)
        t1(o, *(sys.argv[3:4] or ['0x29']))
    if sys.argv[1] == 't2':
        o = pathlib.Path(sys.argv[2]); o.mkdir(parents=True, exist_ok=True)
        word, rx = sys.argv[3], sys.argv[4] == '14'
        geom = [tuple(x) for x in json.loads((HERE / 'captures' / 'l7' / 'to98.json').read_text())] + [(0x0018, 0x12)]
        fam = (sys.argv[5] if len(sys.argv) > 5 else '14') == '14'
        t1(o, word, yend=1500, rx14=rx, fam14=fam, geom=geom, soc=[(0x3010000C, 0xFC)])
    if sys.argv[1] == 't3':                                            # 14-bit 1x1 (+ optional checkerboard HDR)
        o = pathlib.Path(sys.argv[2]); o.mkdir(parents=True, exist_ok=True)
        v = int(sys.argv[3], 16)
        geom = [(0x0242, 0x01 if v else 0x00), (0x0738, v)]
        t1(o, '0x29', yend=0, rx14=True, fam14=True, geom=geom)
        m = json.loads((o / 'after' / 'frame.json').read_text()); m['bits'] = 14
        (o / 'after' / 'frame.json').write_text(json.dumps(m, indent=1))
    if sys.argv[1] == 'vhdr':                                          # vertical 2:1 + checkerboard HDR, 12-bit
        o = pathlib.Path(sys.argv[2]); o.mkdir(parents=True, exist_ok=True)
        v = int(sys.argv[3], 16)
        geom = [(r, x) for r, x in VBIN2 if r not in (0x0242, 0x0738)] + [(0x0242, 0x2D if v else 0x2C), (0x0738, v if v else 0x02)]
        t1(o, '0x2A', yend=1500, rx14=False, fam14=False, geom=geom)
    if sys.argv[1] == 't0':
        o = pathlib.Path(sys.argv[2]); o.mkdir(parents=True, exist_ok=True); t0(o)
