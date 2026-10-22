#!/usr/bin/env python3
"""rv_imglog.py — 診斷:找出誰在載入 font_menu_LB 字形(COLOR 選單右側框的 SA/GA 研究)。

    python3 rv_imglog.py arm      圖檔載入紀錄回呼 [0xC37CECF8] → 常駐 stub_il
    python3 rv_imglog.py read     讀 2 筆環:呼叫者 lr、字形名、呼叫者堆疊中像程式位址的字
    python3 rv_imglog.py disarm   [0xC37CECF8] = 0(原廠預設;`gui image log 1` 會設成 FUN_c055fdc8)

stub_il 只記 font_menu_LB*;字形有快取,只有第一次載入(或快取釋放後)才會觸發。
"""
import pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'fpSup' / 'fp_usb_shell'))
sys.path.insert(0, str(HERE.parent / 'build'))
from putfile import mem_get, mem_set  # noqa: E402
from armasm import symbols             # noqa: E402
import rv_card as C                    # noqa: E402

PTR = 0xC37CECF8


def main(cmd):
    p = C.params()
    if cmd == 'arm':
        rs = symbols(HERE.parent / 'build' / 'rv_resident.S')
        mem_set(PTR, p + rs['stub_il'] - rs['params'])
        print(f'[0x{PTR:08X}] = 0x{C.word(PTR):08X}')
    elif cmd == 'disarm':
        mem_set(PTR, 0)
        print(f'[0x{PTR:08X}] = 0x{C.word(PTR):08X}')
    else:
        log = p + 0x2A00
        n = C.word(log)
        print('次數', n)
        for j in range(max(0, n - 2), n):
            e = log + 4 + 276 * (j & 1)
            words = []
            for k in range(0, 69, 16):
                words += mem_get(e + 4 * k, min(16, 69 - k))
            name = b''.join(w.to_bytes(4, 'little') for w in words[1:5]).split(b'\0')[0]
            code = [(i, w) for i, w in enumerate(words[5:]) if 0xC0000000 <= w < 0xC0A00000]
            print(f'#{j} {name.decode()}  lr {words[0]:08X}')
            print('   堆疊中的程式位址:', ' '.join(f'[{i}]{w:08X}' for i, w in code))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'read')
