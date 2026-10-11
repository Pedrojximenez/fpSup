#!/usr/bin/env python3
"""掃描 fp 韌體映像,列出四個 DNG ColorMatrix ROM 常數的每一個引用點。

兼作補丁驗證器:對已補丁的映像跑一次,OFF 的兩個點應該指向 normal 常數。

位址用 movw+movt 組出來,不在文字池裡,所以要配對掃描而不是找 4-byte 字面值。
"""
import sys
import numpy as np

BASE = 0xC0000000
CONSTS = {0xC096FD2C: 'normal CM1 (Std A)',
          0xC096FD74: 'OFF    CM1 (Std A)',
          0xC096FC9C: 'normal CM2 (D65)',
          0xC096FCE4: 'OFF    CM2 (D65)'}
# 已知的兩個 OFF 取值點(Ver.5.02.0.V91)
PATCH_SITES = {0xC02C4BE4: (0xFD74, 0xFD2C, 'CM1'),
               0xC02C4C98: (0xFCE4, 0xFC9C, 'CM2')}


def scan(path):
    rom = np.fromfile(path, dtype='<u4')
    top = rom & np.uint32(0xFFF00000)
    rd = (rom >> 12) & np.uint32(0xF)
    imm16 = (((rom >> 16) & np.uint32(0xF)).astype(np.uint32) << 12) | (rom & np.uint32(0xFFF))
    is_movw = top == np.uint32(0xE3000000)
    is_movt = top == np.uint32(0xE3400000)

    found = {}
    for i in np.nonzero(is_movw)[0]:
        lo = int(imm16[i])
        addr = 0xC0960000 | lo
        if addr not in CONSTS:
            continue
        r = int(rd[i])
        for k in range(1, 6):                       # movt 通常緊接在後
            j = i + k
            if j < len(rom) and is_movt[j] and int(rd[j]) == r and int(imm16[j]) == 0xC096:
                found.setdefault(addr, []).append((BASE + int(i) * 4, r))
                break
    return rom, found


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else \
        '/Users/dido/Developer.localized/SIGMAfp_re/out/MAIN_c0000000.bin'
    rom, found = scan(path)
    print(path)
    for addr, nm in CONSTS.items():
        hits = found.get(addr, [])
        print('  %-20s 0x%08X → %d 處  %s' % (nm, addr, len(hits),
                                              [(hex(a), 'r%d' % r) for a, r in hits]))
    print('\n  補丁狀態:')
    for site, (orig, new, tag) in PATCH_SITES.items():
        w = int(rom[(site - BASE) // 4])
        imm = ((w >> 16) & 0xF) << 12 | (w & 0xFFF)
        state = ('未補丁(仍指 OFF 常數)' if imm == orig else
                 '已補丁(指向 normal)' if imm == new else '⚠ 不認得的值')
        print('    0x%08X  %s  movw r%d,#0x%04X  → %s'
              % (site, tag, (w >> 12) & 0xF, imm, state))
    print('\n  最小補丁:改 movw 的 imm12 低位元組')
    for site, (orig, new, tag) in PATCH_SITES.items():
        print('    檔案位移 0x%06X : 0x%02X → 0x%02X   (%s)'
              % (site - BASE, orig & 0xFF, new & 0xFF, tag))


if __name__ == '__main__':
    main()
