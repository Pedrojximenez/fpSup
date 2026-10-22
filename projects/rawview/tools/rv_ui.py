#!/usr/bin/env python3
"""rv_ui.py — 第三階段 UI 資源的 shell 測試(README「第三階段」)。

    python3 rv_ui.py check    讀兩處,報告是原廠值還是已改
    python3 rv_ui.py m1       里程碑 1:MENU 的 Color 頁出現第 17 列(圖示暫用 OFF)

頁面在第一次開啟時才解析並快取 → 必須在「開機後、還沒開過 Color 頁」時執行,否則要重開機。
  1. MenuText 上限 15.0 → 16.0:C19F5500  0x0070410A → 0x0080410A
  2. List 記錄 C19F4B11 的列表最大索引(+65 起大端 u32)15 → 16:C19F4B54  0x00000F00 → 0x00001000
  3. B1_5_4_Color.cvm 原地改寫(C0F8E2EC,281 B,長度不變):拿掉 BOM、第 5 行起改 LF,加入 `17,set_common_1`
只改 RAM,重開機即還原。
"""
import argparse, pathlib, struct, sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / 'fpSup' / 'fp_usb_shell'))
from putfile import mem_get, mem_set, put  # noqa: E402

ROM = REPO / 'out' / 'MAIN_c0000000.bin'
MAX_AT, MAX_OLD, MAX_NEW = 0xC19F5500, 0x0070410A, 0x0080410A
LIST_AT, LIST_OLD, LIST_NEW = 0xC19F4B54, 0x00000F00, 0x00001000
CSV_AT, CSV_LEN, CSV_SPAN = 0xC0F8E2EC, 281, 284   # 後 3 bytes 是原本的 0 補齊


def stock_csv():
    rom = ROM.read_bytes()
    return rom[CSV_AT - 0xC0000000:CSV_AT - 0xC0000000 + CSV_SPAN]


def new_csv():
    orig = stock_csv()[:CSV_LEN]
    lines = orig[3:].split(b'\r\n')[:-1] + [b'17,set_common_1']
    body = b''.join(l + (b'\r\n' if i < 4 else b'\n') for i, l in enumerate(lines))
    assert len(body) == CSV_LEN, len(body)
    return body + stock_csv()[CSV_LEN:]


def read(a, n):
    for _ in range(4):
        w = mem_get(a, n // 4)
        if all(x is not None for x in w):
            return b''.join(x.to_bytes(4, 'little') for x in w)
    raise SystemExit(f'read 0x{a:08X} failed')


def check():
    mx = struct.unpack('<I', read(MAX_AT, 4))[0]
    ls = struct.unpack('<I', read(LIST_AT, 4))[0]
    csv = read(CSV_AT, CSV_SPAN)
    print(f'max  0x{MAX_AT:08X} = 0x{mx:08X}  ' + ('原廠' if mx == MAX_OLD else '已改' if mx == MAX_NEW else '未知'))
    print(f'list 0x{LIST_AT:08X} = 0x{ls:08X}  ' + ('原廠' if ls == LIST_OLD else '已改' if ls == LIST_NEW else '未知'))
    print(f'csv  0x{CSV_AT:08X}      ' + ('原廠' if csv == stock_csv() else '已改' if csv == new_csv() else '未知'))
    return mx, ls, csv


def m1():
    mx, ls, csv = check()
    for cur, old, new, what in ((mx, MAX_OLD, MAX_NEW, 'max'), (ls, LIST_OLD, LIST_NEW, 'list')):
        if cur not in (old, new):
            raise SystemExit(f'{what} 既非原廠也非目標值,不寫')
    if csv not in (stock_csv(), new_csv()):
        raise SystemExit('csv 既非原廠也非目標值,不寫')
    if csv != new_csv():
        put(CSV_AT, new_csv(), 'csv   ')
    mem_set(MAX_AT, MAX_NEW)
    mem_set(LIST_AT, LIST_NEW)
    check()


# ---------------------------------------------------------------- 里程碑 2
# COLOR 鍵的畫面是 ColorButtonMenu(實測 2026-09-24,MENU 路徑也是它),model = ListColorButtonMenu{,_EXCL,_EXCL2}.cvm。
# CSV 加一列會比原檔長 → 不能原地改;改 heap 檔案表(reader 0xC6902940 +0xB0,每筆 {hash, name ptr, offset, size} LE)
# 那三筆的 offset/size,指向我們放在 pool 的新版(韌體取檔 = base + offset)。
NBR_BASE = 0xC0D22400
BTN = [  # (名稱, 原廠位址, 原廠大小, hash, 改法)
    ('ListColorButtonMenu', 0xC0D566EC, 453, 0x08C7EA7B,
     {1: b'1,set_color_01,0,16,1,0', 16: b'16,set_common_1,0,14,16,15'}, b'17,set_common_1,0,15,0,16'),
    ('_EXCL', 0xC0D568B4, 483, 0x75550E26, {}, b'17,set_common_1,1,15,15,15'),
    ('_EXCL2', 0xC0D56A98, 452, 0xB0264BF0, {}, b'17,set_common_1,1,14,0,15'),
]
PAGE = [  # ColorButtonMenu 頁(大端值跨 word;在頁面下次解析時生效)
    (0xC1D63010, 0x00000070, 0x00000080),   # 列表上限 15.0 → 16.0
    (0xC1D631AC, 0x70410000, 0x80410000),   # 動畫 t=0 上限 15.0 → 16.0
    (0xC1D66CBC, 0xF4010000, 0x15020000),   # 文字群組終點 500 → 533
]


def btn_csv(at, size, edits, extra):
    rom = ROM.read_bytes()
    orig = rom[at - 0xC0000000:at - 0xC0000000 + size]
    lines = orig[3:].split(b'\r\n')
    lines = [l for l in lines if l]
    for i, l in edits.items():
        assert lines[i].split(b',')[0] == str(i).encode(), (i, lines[i])
        lines[i] = l
    return b'\n'.join(lines + [extra]) + b'\n'


def nbr_table():
    ctx = struct.unpack('<I', read(0xC37B7048, 4))[0]
    reader = 0xC6902940
    base, cnt, tab = (struct.unpack('<I', read(reader + o, 4))[0] for o in (0x24, 0xAC, 0xB0))
    if base != NBR_BASE or not 0 < cnt < 5000:
        raise SystemExit(f'reader 0x{reader:08X} 不是原廠 NBR(base 0x{base:08X} count {cnt})')
    return tab, cnt


def find_entries():
    tab, cnt = nbr_table()
    want = {at - NBR_BASE: name for name, at, *_ in BTN}
    found = {}
    for i0 in range(0, cnt, 64):
        n = min(64, cnt - i0)
        blob = read(tab + 16 * i0, 16 * n)
        for j in range(n):
            h, _, off, size = struct.unpack_from('<4I', blob, 16 * j)
            key = next((nm for nm, at, s, hh, *_ in BTN if hh == h), None)
            if key:
                found[key] = (tab + 16 * (i0 + j), off, size)
    return found


def m2_blobs():
    blobs = [(name, btn_csv(at, size, ed, ex)) for name, at, size, h, ed, ex in BTN]
    return blobs


def m2_buf():
    from putfile import pool_end
    return (pool_end() - 0x2000) & ~0xFF


def m2(undo=False):
    ents = find_entries()
    if set(ents) != {b[0] for b in BTN}:
        raise SystemExit(f'檔案表只找到 {sorted(ents)}')
    buf = m2_buf()
    if undo:
        for name, at, size, *_ in BTN:
            e, _, _ = ents[name]
            mem_set(e + 8, at - NBR_BASE); mem_set(e + 12, size)
        for a, old, new in PAGE:
            mem_set(a, old)
    else:
        for name, at, size, *_ in BTN:
            e, off, sz = ents[name]
            if (off, sz) != (at - NBR_BASE, size) and not (buf - NBR_BASE) & 0xFFFFFFFF <= off < (buf - NBR_BASE + 0x2000) & 0xFFFFFFFF:
                raise SystemExit(f'{name} 檔案表是 offset 0x{off:X} size {sz},非原廠也非本工具;不寫')
        for a, old, new in PAGE:
            cur = struct.unpack('<I', read(a, 4))[0]
            if cur not in (old, new):
                raise SystemExit(f'0x{a:08X} = 0x{cur:08X},非原廠也非目標;不寫')
        p = buf
        for name, data in m2_blobs():
            pad = data + b'\0' * (-len(data) % 4)
            put(p, pad, name[:6].ljust(6))
            e, _, _ = ents[name]
            mem_set(e + 8, (p - NBR_BASE) & 0xFFFFFFFF)
            mem_set(e + 12, len(data))
            p += len(pad) + 16
        for a, old, new in PAGE:
            mem_set(a, new)
    for name, (e, off, sz) in find_entries().items():
        print(f'  {name:20s} entry 0x{e:08X}  → 0x{(NBR_BASE + off) & 0xFFFFFFFF:08X}  size {sz}')
    for a, old, new in PAGE:
        cur = struct.unpack('<I', read(a, 4))[0]
        print(f'  0x{a:08X} = 0x{cur:08X}  ' + ('原廠' if cur == old else '已改' if cur == new else '未知'))


# ---------------------------------------------------------------- 實驗:其他 enum→GUI 呼叫點
# C06C0768 的五個呼叫點:ST_COLBKT C0594FB0、CM_COLFIX C0595734(卡上已接 stub_mb)、CM_DNGDEV C0597504、
# CM_CHGMOD C0597E3C、LV_ColorMode C059DA1C(不接:16–25 是單色調色圖示)。
MB_SITE = 0xC0595734
EXTRA_MB = {'chgmod': (0xC0597E3C,), 'dngdev': (0xC0597504,), 'colbkt': (0xC0594FB0,)}


def bl_target(site, w):
    return site + 8 + ((((w & 0xFFFFFF) ^ 0x800000) - 0x800000) * 4)


def patch_mb(which, undo=False):
    from callfn import call
    ven = bl_target(MB_SITE, struct.unpack('<I', read(MB_SITE, 4))[0])
    if struct.unpack('<I', read(ven, 4))[0] != 0xE51FF004:
        raise SystemExit(f'CM_COLFIX 呼叫點沒有接到 veneer(0x{ven:08X}):卡上的 rawview 沒裝?')
    for site in EXTRA_MB[which]:
        w = struct.unpack('<I', read(site, 4))[0]
        stock = 0xEB000000 | (((0xC06C0768 - site - 8) >> 2) & 0xFFFFFF)
        new = 0xEB000000 | (((ven - site - 8) >> 2) & 0xFFFFFF)
        if w not in (stock, new):
            raise SystemExit(f'0x{site:08X} = 0x{w:08X},非原廠也非本工具')
        mem_set(site, stock if undo else new)
        print(f'  0x{site:08X}: 0x{w:08X} → 0x{(stock if undo else new):08X}')
    call(0xC000E91C, verbose=False)
    call(0xC000EABC, verbose=False)


# ---------------------------------------------------------------- 實驗:其餘 15.0 上限
# ColorButtonMenu 頁面裡與列表上限(C1D62FEF,已由卡片改)同結構的控制值記錄,+0x20 是大端 float 15.0。
# 位元組 +1 由 0x70 改 0x80(15.0 → 16.0)。頁面關閉即釋放、下次開啟重新解析 → RAM 改了下次開啟生效。
EXTRA_CAPS = [0xC1D5F1FF, 0xC1D62A7C, 0xC1D63F8B, 0xC1D65B26]


def caps(undo=False):
    for a in EXTRA_CAPS:
        b = a + 1
        wa = b & ~3
        w = struct.unpack('<I', read(wa, 4))[0]
        sh_ = (b - wa) * 8
        cur = (w >> sh_) & 0xFF
        want, other = (0x70, 0x80) if undo else (0x80, 0x70)
        hi = struct.unpack('>I', read(a & ~3, 8)[(a & 3):(a & 3) + 4])[0]
        if cur not in (0x70, 0x80) or (hi >> 24) != 0x41:
            raise SystemExit(f'0x{a:08X} 不是 15.0/16.0(byte 0x{cur:02X});不寫')
        mem_set(wa, (w & ~(0xFF << sh_)) | (want << sh_))
        print(f'  0x{a:08X}: {"15.0" if cur == 0x70 else "16.0"} → {"15.0" if want == 0x70 else "16.0"}')


def expr(undo=False):
    """UI 條件式 `ColorMode :v() == 15` → `>= 15`(資料在 build/rv_uidata.EXPR)。每個字先核對原廠或已改,才寫。"""
    sys.path.insert(0, str(HERE.parent / 'build'))
    import rv_uidata
    for wa, old, new in rv_uidata.expr_words():
        cur = struct.unpack('<I', read(wa, 4))[0]
        want = old if undo else new
        if cur not in (old, new):
            raise SystemExit(f'0x{wa:08X} = 0x{cur:08X},不是原廠 0x{old:08X} 也不是 0x{new:08X};停止')
        if cur != want:
            mem_set(wa, want)
        got = struct.unpack('<I', read(wa, 4))[0]
        print(f'  0x{wa:08X}: 0x{cur:08X} → 0x{got:08X} {"OK" if got == want else "失敗"}')


# OFF 列上下框(Effect)灰字的條件 CBM_BKTMonochrome:`CM_COLAJ_ColorMode :v() == 15`(三處,位址 = '==' 的位置)。
# 改成 `== 99`(永不成立、等長)→ OFF 的框可操作。fs2-6 卡把 '==' 改成 '>=',也接受。
OFFBOX = (0xC2D9FD47, 0xC2DAF097, 0xC2DAF0DA)


def offbox(undo=False):
    want = b'== 15' if undo else b'== 99'
    ok = (b'== 15', b'>= 15', b'== 99')
    for a in OFFBOX:
        wa = a & ~3
        raw = bytearray(read(wa, 12))
        o = a - wa
        cur = bytes(raw[o:o + 5])
        if cur not in ok:
            raise SystemExit(f'0x{a:08X} = {cur!r},不是預期的條件式;停止')
        raw[o:o + 5] = want
        for k in range(0, 12, 4):
            old = struct.unpack_from('<I', read(wa + k, 4))[0]
            new = struct.unpack_from('<I', raw, k)[0]
            if old != new:
                mem_set(wa + k, new)
        print(f'  0x{a:08X}: {cur.decode()} → {bytes(read(wa, 12)[o:o + 5]).decode()}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['check', 'm1', 'm2', 'm2-undo', 'm2-show', 'mb', 'mb-undo', 'caps', 'caps-undo', 'expr', 'expr-undo', 'offbox', 'offbox-undo'])
    ap.add_argument('which', nargs='?', default='chgmod', choices=sorted(EXTRA_MB))
    a = ap.parse_args()
    c = a.cmd
    if c in ('mb', 'mb-undo'):
        patch_mb(a.which, c == 'mb-undo')
        raise SystemExit(0)
    if c in ('caps', 'caps-undo'):
        caps(c == 'caps-undo')
        raise SystemExit(0)
    if c in ('expr', 'expr-undo'):
        expr(c == 'expr-undo')
        raise SystemExit(0)
    if c in ('offbox', 'offbox-undo'):
        offbox(c == 'offbox-undo')
        raise SystemExit(0)
    if c == 'm2-show':
        for name, data in m2_blobs():
            print(f'== {name} ({len(data)} B)\n{data.decode()}')
    else:
        {'check': check, 'm1': m1, 'm2': m2, 'm2-undo': lambda: m2(True)}[c]()
