#!/usr/bin/env python3
"""Defect-table generator for generated modes (SMC G7, route B; notes/DEFECT_CORRECTION.md).

Host port of the firmware's own translation FUN_c0310740 (+ c0310e90 sort, c0310ce0 stream build, c0310ac0 same-colour
flags, c03111e8 coordinate types), so a generated mode gets its table the way the stock firmware derives 98 / 139 /
131 from table 97. Input: the flash defect buffer (partition 0xF, 0x40000 B, dumped from *0xC343A71C).

    defect_tables.py dir  BUF                 list the directory
    defect_tables.py selftest BUF             97 -> 98 / 139 / 131 with the stock R68 rows must equal the stored tables
Library: parse(buf), table(buf, id) -> u16 list, translate(src_u16, win, types, offs, W, H) -> (u16 stream, point list)
"""
import pathlib, struct, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

DIR = 0x16000
SIZE = 0x40000
CONV = {1: 0, 2: 7, 3: 2}                  # merge factor -> coordinate type (stock: h2/v2 7, h3 2, v3 1, v6 3)
CONV_V = {1: 0, 2: 7, 3: 1, 6: 3}


def parse(buf):
    valid, n = struct.unpack_from('<II', buf, DIR)
    ids = struct.unpack_from(f'<{n}H', buf, DIR + 8)
    sizes = struct.unpack_from(f'<{n}H', buf, DIR + 0x88)
    tabs, at = {}, DIR + 0x400
    for i, (t, sz) in enumerate(zip(ids, sizes)):
        tabs[t] = (at, sz * 4, SIZE - 0x100 * (i + 1))
        at += sz * 4
    return dict(valid=valid, n=n, tables=tabs)


def table(buf, tid):
    at, nb, lst = parse(buf)['tables'][tid]
    u16 = list(struct.unpack_from(f'<{nb // 2}H', buf, at))
    pts = []
    for k in range(64):
        w = struct.unpack_from('<I', buf, lst + 4 * k)[0]
        if w == 0xFFFFFFFF:
            break
        pts.append(w)
    return u16, pts


def conv(t, off, c):
    """FUN_c03111e8"""
    u2 = (c + off) & 0xFFFFFFFF
    u1 = u2 & 0xFFFF
    if t == 1:
        return 0xFFFF if u1 % 3 == 1 else u1 // 3
    if t == 2:
        return u1 // 3 + (1 if u1 % 3 == 1 else 0)
    if t == 3:
        if u2 & 1 == 0:
            return u1 // 6 if u1 % 6 in (0, 2, 4) else 0xFFFF
        return u1 // 6 if (u1 + 1) % 6 in (0, 2, 4) else 0xFFFF
    if t == 7:
        return (u1 & 1) + (u1 >> 2) * 2
    return u1


def points(u16):
    """stream -> [(x, y)] including the same-colour neighbours the flags stand for (they are entries themselves)"""
    out, y = [], None
    for w in u16:
        if w == 0xFFFF:
            break
        if w & 0x8000:
            y = w & 0x1FFF
        else:
            out.append((w & 0x1FFF, y))
    return out


def translate(src, win, types, offs, W, H, size_words=0x10000):
    """FUN_c0310740 for one table. win = (x0, y0, w, h) in source coordinates; types = (xt, yt); offs = (xo, yo);
    W, H = output (META) size. Returns (u16 stream, point list u32[128])."""
    x0, y0, w, h = win
    xt, yt = types
    xo, yo = offs
    pts = []
    i, ffs, ny = 0, 0, 0
    n2 = size_words * 2
    k = 0
    while k < n2 and i < len(src):
        v = src[i]
        if v == 0xFFFF:
            i += 1; ffs += 1
            if ffs == 4:
                break
            k += 1
            continue
        if not v & 0x8000 or (v & 0x1FFF) < y0 or (v & 0x1FFF) >= y0 + h:
            i += 1; k += 1
            continue
        ny = conv(yt, yo, ((v & 0x1FFF) - y0) & 0xFFFF)
        i += 1
        while i < len(src) and not src[i] & 0x8000:
            x = src[i] & 0x1FFF
            if x0 <= x < x0 + w:
                nx = conv(xt, xo, (x - x0) & 0xFFFF)
                if nx < W and ny < H:
                    pts.append(nx | ny << 16)
            i += 1
        k += 1
    pts.sort(key=lambda p: (p >> 16, p & 0xFFFF))            # c0310e90: y, then x (stable)
    # c0310ce0: stream build
    out, lst, last_y, cnt = [], [], 0xFFFF, 0
    for j, p in enumerate(pts):
        x, y = p & 0xFFFF, p >> 16
        if y == last_y:
            if x != pts[j - 1] & 0xFFFF:
                if cnt < 4:
                    out.append(x); cnt += 1
                elif (x - (pts[j - 4] & 0xFFFF)) & 0xFFFFFFFF < 12:
                    if len(lst) < 0x7F:
                        lst.append(p)
                else:
                    out.append(x); cnt += 1
        else:
            last_y = y
            out += [y | 0x8000, x]; cnt = 1
    n = len(out)
    out += [0xFFFF] * 4
    # c0310ac0: same-colour neighbour flags (x +- 2 in the same row)
    for j in range(n + 3):
        if out[j] == 0xFFFF:
            break
        if out[j] & 0x8000:
            continue
        prev_pt = j > 0 and not out[j - 1] & 0x8000
        next_pt = not out[j + 1] & 0x8000 and out[j + 1] != 0xFFFF
        if not (prev_pt or next_pt):
            continue
        x = out[j] & 0x1FFF
        if prev_pt:
            if next_pt and x + 2 == out[j + 1] & 0x1FFF:
                out[j] = x | 0x2000
            elif x - 2 == out[j - 1] & 0x1FFF:
                out[j] = x | 0x4000
        elif x + 2 == out[j + 1] & 0x1FFF:
            out[j] = x | 0x2000
    return out, lst + [0xFFFFFFFF] * (128 - len(lst))


def main():
    buf = pathlib.Path(sys.argv[2]).read_bytes()
    d = parse(buf)
    if sys.argv[1] == 'dir':
        print('valid', d['valid'], 'tables', d['n'])
        for t, (at, nb, lst) in d['tables'].items():
            u16, pts = table(buf, t)
            print(f'  id {t:3d}  {nb // 4:6d} words  {len(points(u16)):6d} points  list {len(pts)}')
    elif sys.argv[1] == 'selftest':
        import struct as S
        img = pathlib.Path(__file__).resolve().parents[3].joinpath('out', 'MAIN_c0000000.bin').read_bytes()
        import reconstruct as RC                                       # stock output sizes (META width/height)
        at = RC.load()[1]
        meta = {m: (at[m]['width'], at[m]['height']) for m in (98, 139, 131)}
        src, _ = table(buf, 97)
        for m in (98, 139, 131):
            for i in range(70):
                w = S.unpack_from('<26I', img, 0xB5DB00 + i * 0x68)
                if w[0] == m:
                    break
            got, lst = translate(src, w[4:8], (w[8], w[9]), (w[10], w[11]), *meta[m])
            want, wl = table(buf, m)
            ok = got[:len(want)] == want[:len(got)] and len(got) == len(want)
            print(f'97 -> {m}: generated {len(points(got))} points, stored {len(points(want))}; identical={ok}')


if __name__ == '__main__':
    main()
