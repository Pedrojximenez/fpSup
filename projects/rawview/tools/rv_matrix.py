#!/usr/bin/env python3
"""rv_matrix.py — 上機驗證:OFF 的色彩矩陣換成 fp 校色矩陣(RAM 副本 + 換 root+0x08 指標)。

    python3 rv_matrix.py show        讀 root+0x08、OFF 那筆、live RGBLMAT(0x30210CB0..)
    python3 rv_matrix.py on          在 rawview 配置區的空白處(T0 + 0x20000)放表副本,OFF 那筆換成校色矩陣,
                                     root+0x08 指過去,再 `menu SetColorMode 12` 觸發 PQ 更新
    python3 rv_matrix.py off         root+0x08 寫回原廠 0xC0B39CC8,再 `menu SetColorMode 12`

表(README「RAW 模式色彩矩陣」):35 筆 × 0x18 {mode, 9 × s16, pad},512 = 1.0;
每列對角在前:R(R,G,B)、G(G,R,B)、B(B,R,G)。第 34 筆 = OFF(0x24)= 單位矩陣。
矩陣來源:非 OFF DNG 的 ColorMatrix2(D65)→ cam→709,列和 512。
只寫 RAM;重開機即還原。T0 + 0x20000 在 fs2-4 的 0x22000 配置內、常駐之後(常駐止於 T0 + 0x1FC50)。
"""
import pathlib, struct, sys, time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'fpSup' / 'fp_usb_shell'))
from putfile import sh, mem_get, mem_set  # noqa: E402
import rv_card                            # noqa: E402

ROOT_P08 = 0xC2F1A06C
TAB = 0xC0B39CC8
N, REC, OFF_IDX = 35, 0x18, 34
# cam→709(D65),×512;表內順序 R(R,G,B)、G(G,R,B)、B(B,R,G)
MAT = (706, -298, 104, 627, -50, -65, 706, 31, -225)
RGBLMAT = 0x30210CB0


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


def show():
    p, cnt = words(ROOT_P08, 2)
    print(f'root+0x08 = 0x{p:08X}  count {cnt}  ({"原廠" if p == TAB else "已換"})')
    rec = struct.pack(f'<{REC // 4}I', *words(p + OFF_IDX * REC, REC // 4))
    print(f'  第 {OFF_IDX} 筆 mode 0x{struct.unpack_from("<I", rec)[0]:X}  {struct.unpack_from("<9h", rec, 4)}')
    w = words(RGBLMAT, 12)
    s11 = lambda v: (v & 0x7FF) - 0x800 if v & 0x400 else v & 0x7FF
    print('  RGBLMAT 組 1:', [s11(x) for x in w[0:6]], [s11(x >> 16) for x in w[0:6]])
    print('  RGBLMAT 組 2:', [s11(x) for x in w[6:12]], [s11(x >> 16) for x in w[6:12]])


def on():
    p, cnt = words(ROOT_P08, 2)
    if p != TAB or cnt != N:
        raise SystemExit(f'root+0x08 = 0x{p:08X} / {cnt},不是原廠;不寫')
    par = rv_card.params()
    tab = rv_card.word(par + 0x10)
    dst = tab + 0x20000
    if par != tab + 0x1F200:                # fs2-4 版面:配置 0x22000,T0 − 基址 ≤ 0xFFF → T0 + 0x20000..+0x348 在配置內
        raise SystemExit(f'params 0x{par:08X} 不是 fs2-4 版面(tables 0x{tab:08X});不寫')
    src = words(TAB, N * REC // 4)
    raw = bytearray(struct.pack(f'<{len(src)}I', *src))
    o = OFF_IDX * REC
    assert struct.unpack_from('<I', raw, o)[0] == 0x24 and struct.unpack_from('<9h', raw, o + 4) == (512, 0, 0) * 3
    struct.pack_into('<9h', raw, o + 4, *MAT)
    new = struct.unpack(f'<{len(src)}I', raw)
    for i, v in enumerate(new):
        mem_set(dst + 4 * i, v)
    if words(dst, len(new)) != list(new):
        raise SystemExit('副本讀回不符;不換指標')
    mem_set(ROOT_P08, dst)
    print(f'副本 0x{dst:08X},root+0x08 → 副本')
    print(sh('menu SetColorMode 12').strip())
    time.sleep(1.5)
    show()


def off():
    mem_set(ROOT_P08, TAB)
    print(sh('menu SetColorMode 12').strip())
    time.sleep(1.5)
    show()


if __name__ == '__main__':
    {'show': show, 'on': on, 'off': off}[sys.argv[1]]()
