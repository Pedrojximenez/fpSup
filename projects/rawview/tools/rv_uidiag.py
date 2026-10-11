#!/usr/bin/env python3
"""rv_uidiag.py — 唯讀診斷:Color 清單的版面與 CSV model 狀態(照 OG enum_ui_instances.py 的結構)。

    python3 rv_uidiag.py

只讀、不寫。依序:
  1. 里程碑 1 的三處修改是否還在
  2. ctx = [0xC37B7048](UicCont);目前畫面 [ctx+0x84C]/[ctx+0x850] 的名稱
  3. 版面清單 n=[ctx+0x80]、陣列 [ctx+0x8C]:B1_5_4／ColorButtonMenu／B1_5 的樹 [s+0xC]
  4. NB 實例 sub=[ctx+0x888]、n=[sub+0x30]、陣列 [sub+0x3C]:B1_5_4_Color 與 ListColorButtonMenu*
     child=[inst+0x18];已解析時 data=[child+0x34]:列數 [data+0x18]、文字長度 [data+0x10]
"""
import pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'fpSup' / 'fp_usb_shell'))
from putfile import mem_get  # noqa: E402
import rv_ui                # noqa: E402

LAYOUTS = ('B1_5_4', 'ColorButtonMenu', 'B1_5')
MODELS = ('B1_5_4_Color', 'ListColorButtonMenu')


def words(a, n):
    out = []
    while n > 0:
        k = min(n, 16)
        for _ in range(6):
            got = mem_get(a, k)
            if all(w is not None for w in got):
                break
        else:
            raise SystemExit(f'read 0x{a:08X} failed')
        out += got; a += 4 * k; n -= k
    return out


def w(a):
    return words(a, 1)[0]


def cstr(a, limit=40):
    if not a:
        return ''
    raw = b''.join(x.to_bytes(4, 'little') for x in words(a & ~3, (limit + 7) // 4))[a & 3:]
    return raw.split(b'\0', 1)[0].decode('latin-1')


def name_at(field):
    """名稱欄位可能是指標或內嵌字串:兩種都試。"""
    v = w(field)
    if 0x40000000 <= v < 0xE0000000:
        s = cstr(v)
        if s and s.isprintable():
            return s
    return cstr(field)


def main():
    rv_ui.check()
    ctx = w(0xC37B7048)
    print(f'ctx 0x{ctx:08X}')
    for off in (0x84C, 0x850):
        s = w(ctx + off)
        print(f'  目前畫面 [ctx+0x{off:X}] = 0x{s:08X}  {name_at(s + 8) if s else ""}')
    n, arr = w(ctx + 0x80), w(ctx + 0x8C)
    print(f'版面清單 {n} 個 @0x{arr:08X}')
    if 0 < n < 1000:
        for s in words(arr, n):
            nm = name_at(s + 8)
            if nm in LAYOUTS:
                print(f'  {nm:18s} 0x{s:08X}  tree [s+0xC] = 0x{w(s + 0xC):08X}')
    sub = w(ctx + 0x888)
    n, arr = w(sub + 0x30), w(sub + 0x3C)
    print(f'NB 實例 {n} 個 @0x{arr:08X}')
    if not 0 < n < 20000:
        raise SystemExit('實例數不合理,停止')
    for i, inst in enumerate(words(arr, n)):
        nm = cstr(w(inst + 8), 32)
        if any(nm.startswith(m) for m in MODELS):
            child, flags = w(inst + 0x18), w(inst + 0x28)
            line = f'  #{i} {nm:28s} inst 0x{inst:08X} child 0x{child:08X} flags 0x{flags:X}'
            if child:
                data = w(child + 0x34)
                rows, cols, tlen = w(data + 0x18), w(data + 0x1C), w(data + 0x10)
                line += f' ref {w(child + 0xC)} | rows {rows} cols {cols} textlen {tlen}'
            print(line)


CSV_FILES = {'ListColorButtonMenu': 0xC0D566EC, '_EXCL': 0xC0D568B4, '_EXCL2': 0xC0D56A98,
             'B1_5_4_Color': 0xC0F8E2EC}


def nbr():
    """唯讀:找原廠 NBR reader 的 heap 檔案表({hash, name ptr, offset, size} LE),列出四個 CSV 那幾筆。"""
    ctx = w(0xC37B7048)
    sub = w(ctx + 0x888)
    n, arr = w(sub + 0x30), w(sub + 0x3C)
    readers = {}
    for inst in words(arr, min(n, 600)):
        esz, vcnt, vdata = w(inst + 0x30), w(inst + 0x34), w(inst + 0x40)
        if 0 < vcnt < 64 and esz >= 16:
            r = w(vdata + 8)
            if r and r not in readers:
                readers[r] = w(r + 0x24)
        if len(readers) >= 2:
            break
    for r, base in readers.items():
        cnt, tab, b2 = w(r + 0xAC), w(r + 0xB0), w(r + 0xB4)
        print(f'reader 0x{r:08X}  [+0x24] base 0x{base:08X}  [+0xAC] count {cnt}  [+0xB0] table 0x{tab:08X}  [+0xB4] 0x{b2:08X}')
        if base != 0xC0D22400 or not 0 < cnt < 5000:
            continue
        want = {a - base: k for k, a in CSV_FILES.items()}
        ent = words(tab, cnt * 4)
        for i in range(cnt):
            h, np_, off, size = ent[4 * i:4 * i + 4]
            if off in want:
                print(f'  #{i} @0x{tab + 16 * i:08X}  {want[off]:20s} hash 0x{h:08X} name {cstr(np_, 40)!r} '
                      f'offset 0x{off:X} size {size}')


if __name__ == '__main__':
    nbr() if sys.argv[1:] == ['nbr'] else main()
