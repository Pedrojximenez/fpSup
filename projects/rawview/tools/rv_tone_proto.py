#!/usr/bin/env python3
"""rv_tone_proto.py — rawview 原型一:在 OFF 色彩模式下換上 RAW tone 表(只寫資料,不注入程式)。

做法(README「決定」與追查結果):
  所有色彩模式共用 FUN_c02d29e0;mode→tone 編號查 root(0xC2F1A064)+0x70 的 {mode, base} 表,
  位址 = *(0xC0971114 + idx*8 + 4),idx 不做範圍檢查。所以:
    S  = 88-byte 插槽陣列(S ≡ 4 mod 8),S[k*8+4] = 我們的表(k = 0..10,涵蓋對比 ±5)
    N  = ((S − 0xC0971114) >> 3) + 5  (mod 2^32)
    M  = +0x70 表的 RAM 副本,OFF(0x24,第 35 筆)的 base 改成 N
  開:寫表 → 寫插槽 → 寫 M → root+0x70 指向 M → 清 ctx0 快取鍵 0xC2F19D44 → 等 singleton+0xA0 == 表
  關:root+0x70 寫回原值 → 清快取鍵 → 等 +0xA0 回到原廠表
所有東西放在 worker pool 的尾端(本工具自己的區域),只改一個 RAM 指標與一個快取鍵;關機重開一定還原。

    python3 rv_tone_proto.py status
    python3 rv_tone_proto.py on  [--iso N]    # 不給 --iso 就依目前相對增益選
    python3 rv_tone_proto.py off
"""
import argparse, json, math, pathlib, sys, time

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / 'fpSup' / 'fp_usb_shell'))
from putfile import sh, mem_get, mem_set, put, pool_end  # noqa: E402

ROOT_P70 = 0xC2F1A0D4          # root 0xC2F1A064 + 0x70
ROOT_P70_ORIG = 0xC0B3D670
MODE_TAB_N = 0x24              # {mode, base} pairs
OFF_ENTRY = 35                 # mode 0x24 → base 82
CURVE_ENTRIES = 0xC0971114
OFF_TABLE = 0xC09C3F34
KEY_CTX0 = 0xC2F19D44
SINGLETON_A0 = 0xC3414470 + 0xA0
REL_GAIN = 0xC343B5A0
MENU_OFF = 12                  # menu SetColorMode: OFF

ISO_STEPS = [100, 125, 160, 200, 250, 320, 400, 500, 640, 800, 1000, 1250, 1600, 2000,
             2500, 3200, 4000, 5000, 6400, 8000, 10000, 12800, 16000, 20000, 25600,
             32000, 40000, 51200, 64000, 80000, 102400]
STATE = HERE.parent / 'captures' / 'tone_proto_state.json'


def layout():
    """本工具在 pool 尾端的區域:表 A、插槽 S、副本 M。"""
    end = pool_end()
    base = (end - 0x3000) & ~0xFFF
    tab = base                      # 4096 B, 4 KiB 對齊
    s = base + 0x1000 + 4           # ≡ 4 mod 8
    m = base + 0x1100
    return {'table': tab, 'slots': s, 'mode_copy': m, 'end': end}


def word(a, tries=5):
    # USB 偶爾整個回覆掉(2026-09-24 on 時讀 +A0 掉過一次),重試而不是中止
    for _ in range(tries):
        w = mem_get(a)
        if w and w[0] is not None:
            return w[0]
        time.sleep(0.1)
    raise SystemExit(f'read 0x{a:08X} failed')


def pick_iso(rel):
    iso = rel / 1.17
    return min(ISO_STEPS, key=lambda s: abs(math.log2(s / iso)))


def wait_a0(want, tries=20):
    for _ in range(tries):
        if word(SINGLETON_A0) == want:
            return True
        mem_set(KEY_CTX0, 0xFFFFFFFF)
        time.sleep(0.15)
    return False


def status():
    L = layout()
    print(f"color mode {sh('menu SetColorMode').strip()}  rel gain {word(REL_GAIN)}")
    print(f"root+0x70 = 0x{word(ROOT_P70):08X}  (原廠 0x{ROOT_P70_ORIG:08X})")
    print(f"singleton+A0 = 0x{word(SINGLETON_A0):08X}  (OFF 表 0x{OFF_TABLE:08X}, 本工具表 0x{L['table']:08X})")
    print(f"hw 30200094 = 0x{word(0x30200094):08X}")


def on(iso):
    if sh('menu SetColorMode').strip().split()[-1] != str(MENU_OFF):
        raise SystemExit('色彩模式不是 OFF(12);原型只在 OFF 下運作')
    p70 = word(ROOT_P70)
    if p70 != ROOT_P70_ORIG:
        raise SystemExit(f'root+0x70 是 0x{p70:08X},不是原廠值;先 off 或重開機')
    orig = mem_get(ROOT_P70_ORIG, MODE_TAB_N * 2)
    if orig[OFF_ENTRY * 2] != 0x24 or orig[OFF_ENTRY * 2 + 1] != 82:
        raise SystemExit(f'mode 表第 35 筆不是 (0x24, 82): {orig[70:72]}')
    L = layout()
    iso = iso or pick_iso(word(REL_GAIN))
    tab = (HERE.parent / 'curves' / f'tone2048_iso{iso}.u16le').read_bytes()
    assert len(tab) == 4096

    put(L['table'], tab, 'tone  ')
    n = ((L['slots'] - CURVE_ENTRIES) >> 3) + 5 & 0xFFFFFFFF
    slots = b''.join((0).to_bytes(4, 'little') + L['table'].to_bytes(4, 'little') for _ in range(11))
    put(L['slots'], slots, 'slots ')
    m = list(orig); m[OFF_ENTRY * 2 + 1] = n
    put(L['mode_copy'], b''.join(x.to_bytes(4, 'little') for x in m), 'modes ')
    # 位址換算自檢:韌體算出的位址 = *(entries + idx*8 + 4),idx 取 N-5..N+5
    for k in (-5, 0, 5):
        a = (CURVE_ENTRIES + ((n + k) & 0xFFFFFFFF) * 8 + 4) & 0xFFFFFFFF
        if word(a) != L['table']:
            raise SystemExit(f'插槽自檢失敗 idx N{k:+d} → 0x{a:08X}')

    STATE.write_text(json.dumps({'iso': iso, 'N': n, **{k: f'0x{v:08X}' for k, v in L.items()}}, indent=2))
    mem_set(ROOT_P70, L['mode_copy'])
    mem_set(KEY_CTX0, 0xFFFFFFFF)
    ok = wait_a0(L['table'])
    print(f"RAW tone ISO {iso}: {'已載入' if ok else '未載入(已寫入,但 +A0 沒有切到本表)'}")
    status()


def off():
    mem_set(ROOT_P70, ROOT_P70_ORIG)
    mem_set(KEY_CTX0, 0xFFFFFFFF)
    ok = wait_a0(OFF_TABLE)
    print('已還原原廠 OFF 表' if ok else '指標已寫回,但 +A0 沒回到 OFF 表(若對比非 0 屬正常);請切一次色彩模式確認')
    status()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['status', 'on', 'off'])
    ap.add_argument('--iso', type=int)
    a = ap.parse_args()
    {'status': status, 'on': lambda: on(a.iso), 'off': off}[a.cmd]()
