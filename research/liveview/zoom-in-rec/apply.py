#!/usr/bin/env python3
"""錄影中放大 —— 實驗 A:把 canZoom 路徑上的兩道守門拆掉。

    ./apply.py            裝上(兩個字改成 mov r0,#0)
    ./apply.py --revert    還原成原廠的兩個 BL
    ./apply.py --check     只回讀,不寫

只改兩個字,都在 `FUN_c04a5650` / `FUN_c04a5790` 自己的呼叫點上,被呼叫的
函式本體不動 —— 錄影中其他也在問它們的程式碼行為不變。

寫完由相機端的 stub 做 D-cache clean + I-cache invalidate;少了那一步,回讀
會給你新值而畫面照舊擋,是最會騙人的一種失敗。

相機要在跑帶 USB shell 的卡(`fpshd` 起著、`fpsh ping` 有回應)。
"""
import argparse, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
SHELL = HERE.parents[2] / 'fpSup/fp_usb_shell'
sys.path.insert(0, str(SHELL))

from armasm import assemble                                   # noqa: E402
from putfile import mem_get, put                              # noqa: E402
import cave, callfn                                           # noqa: E402

# (位址, 原廠值, patch 後的值, 這道門是什麼)
GATES = [
    (0xC04A569C, 0xEBFFFE05, 0xE3A00000,
     'canZoom: BL FUN_c04a4eb8 —— 「正在錄影」'),
    (0xC04A579C, 0xEB00079D, 0xE3A00000,
     'canZoom wrapper: BL FUN_c04a7618 —— 會跳 3 秒提示的那道'),
    (0xC04827A0, 0xEB0089C4, 0xE3A00000,
     'StandbyEventHandler::v16 前置: BL FUN_c04a4eb8 —— 按鍵層的「正在錄影」'),
    (0xC048276C, 0xEB0093A9, 0xE3A00000,
     'StandbyEventHandler::v16 前置: BL FUN_c04a7618'),
    (0xC04A56B8, 0xEB00227E, 0xE3A00000,
     'canZoom: BL FUN_c04ae0b8 —— ★實測錄影中 0→1 的那道'),
]


def read_words():
    return [mem_get(a)[0] for a, _, _, _ in GATES]


def show(words):
    for (a, orig, new, what), w in zip(GATES, words):
        state = 'stock' if w == orig else 'patched' if w == new else '?????'
        print(f'  0x{a:08X}  {w:08X}  {state:<7} {what}')
    return words


def run(want):
    """want: 每個位址要變成的值。stub 一次吃兩對,所以分批。"""
    for i in range(0, len(GATES), 2):
        pair = GATES[i:i + 2]
        vals = want[i:i + 2]
        while len(pair) < 2:                      # 奇數收尾:第二對指回自己,寫原值
            pair = pair + [pair[0]]
            vals = vals + [vals[0]]
        code = assemble(HERE / 'zoom_gate.S', [
            f'A1=0x{pair[0][0]:08X}', f'V1=0x{vals[0]:08X}',
            f'A2=0x{pair[1][0]:08X}', f'V2=0x{vals[1]:08X}',
        ])
        at = cave.claim('zoom_gate', len(code))
        put(at, code, 'zoom_gate')
        ok, _ = callfn.call(at, verbose=False)
        if not ok:
            raise SystemExit('stub 沒有回來 —— 不要再下指令,拔電池')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--revert', action='store_true')
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args()

    print('現在:')
    before = show(read_words())

    if a.check:
        return

    want = [g[1] if a.revert else g[2] for g in GATES]
    if before == want:
        print('已經是要的樣子,沒有動作。')
        return

    # 守衛:每一項都必須是原廠值或 patch 值之一。中間值代表位址或韌體版本不對,
    # 那種情況下再寫一次只會蓋掉證據。混合狀態是允許的 —— 加了新的門之後,
    # 先前那幾個本來就已經裝好了。
    bad = [f'0x{g[0]:08X}={w:08X}' for g, w in zip(GATES, before)
           if w not in (g[1], g[2])]
    if bad:
        raise SystemExit('這些位址不是原廠值也不是 patch 值,先弄清楚再動:'
                         + ', '.join(bad))

    run(want)

    print('之後:')
    after = show(read_words())
    if after != want:
        raise SystemExit('回讀對不上 —— mem set 會掉寫入,再跑一次,確認前不要上機測。')
    print('好了。' + ('已還原。' if a.revert else
                     '注意:這只改了 UI 的許可判斷,畫面會不會真的放大是另一回事。'))


if __name__ == '__main__':
    main()
