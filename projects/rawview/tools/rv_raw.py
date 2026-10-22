#!/usr/bin/env python3
"""rv_raw.py — rawview RAW 模式原型(增益 hook + 依 ISO 自動換 tone 表)。取代 rv_gain_proto / rv_tone_proto。

    python3 rv_raw.py status
    python3 rv_raw.py install     # 放 stub、改兩條指令成 bl;旗標 0,行為與原廠相同
    python3 rv_raw.py load        # 上傳 31 張每 ISO tone 表、插槽、mode 表副本,填 stub 參數(不改畫面)
    python3 rv_raw.py on          # root+0x70 → 副本,旗標 1;下一輪增益計算時依 ISO 選表
    python3 rv_raw.py off         # 旗標 0,root+0x70 寫回;下一輪回到原廠
    python3 rv_raw.py uninstall   # 兩條指令寫回原字

需要色彩模式 OFF。只改 RAM,關機重開一定還原。設計見 README「增益 hook 設計」「決定」。
"""
import argparse, math, pathlib, struct, sys, time

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / 'fpSup' / 'fp_usb_shell'))
from putfile import sh, mem_get, mem_set, put, pool_end  # noqa: E402
from armasm import assemble, symbols                     # noqa: E402
from callfn import call                                  # noqa: E402
import cave                                              # noqa: E402

SRC = HERE / 'rv_raw_hooks.S'
SITES = {'A': (0xC0313244, 0xE595200C, 'stub_gs'),
         'B': (0xC032F728, 0xE59C6000, 'stub_dg')}
DCACHE_CLEAN, ICACHE_INV = 0xC000E91C, 0xC000EABC
ROOT_P70, ROOT_P70_ORIG = 0xC2F1A0D4, 0xC0B3D670
MODE_TAB_N, OFF_ENTRY = 0x24, 35
CURVE_ENTRIES, OFF_TABLE = 0xC0971114, 0xC09C3F34
KEY_CTX0 = 0xC2F19D44
SINGLETON_A0 = 0xC3414470 + 0xA0
IMX = 0xC343B5A0
HELPER_STATE = 0xC343A6A0 + 0x0C
MENU_OFF = 12
ISO_STEPS = [100, 125, 160, 200, 250, 320, 400, 500, 640, 800, 1000, 1250, 1600, 2000,
             2500, 3200, 4000, 5000, 6400, 8000, 10000, 12800, 16000, 20000, 25600,
             32000, 40000, 51200, 64000, 80000, 102400]
REL100 = 117                  # ISO 100 的相對增益;每 1/3 檔 ×2^(1/3)


def word(a, tries=6):
    for _ in range(tries):
        w = mem_get(a)
        if w and w[0] is not None:
            return w[0]
        time.sleep(0.1)
    raise SystemExit(f'read 0x{a:08X} failed')


def set_word(a, v):
    for _ in range(8):
        mem_set(a, v)
        if word(a) == v:
            return
    raise SystemExit(f'write 0x{a:08X} = 0x{v:08X} did not stick')


def publish():
    call(DCACHE_CLEAN, verbose=False)
    call(ICACHE_INV, verbose=False)


def block():
    size = len(assemble(SRC, ['P=0xC072E800']))
    return cave.claim('rawview.raw', size)


def sym(p):
    return symbols(SRC, [f'P=0x{p:08X}'])


def layout():
    """pool 尾端:31 張表(各 4 KiB)、插槽、mode 表副本。"""
    end = pool_end()
    tabs = (end - 0x3000 - len(ISO_STEPS) * 0x1000) & ~0xFFF
    misc = (end - 0x2000) & ~0xFFF
    return {'tabs': tabs, 'slots': misc + 4, 'mode_copy': misc + 0x100}


def bl(site, target):
    off = (target - site - 8) >> 2
    if not -(1 << 23) <= off < (1 << 23):
        raise SystemExit(f'bl 0x{site:08X} → 0x{target:08X} out of range')
    return 0xEB000000 | (off & 0xFFFFFF)


def status():
    p = block()
    s = sym(p)
    print(f'stub 0x{p:08X}  flag {word(p)}  last_rel {word(p + 4)}  tab_base 0x{word(p + 8):08X}')
    for n, (site, orig, name) in SITES.items():
        w = word(site)
        st = 'original' if w == orig else ('hooked→rv_raw' if w == bl(site, p + s[name]) else 'OTHER')
        print(f'  site {n} 0x{site:08X} = 0x{w:08X}  {st}')
    im = mem_get(IMX, 9)
    print(f'color {sh("menu SetColorMode").strip()}  gain_state {word(HELPER_STATE)}  rel {im[0]}  '
          f'analog {im[2]}  ratio {im[5]}  hcg {im[7] & 0xFF}  digital×100 {im[8]}')
    a0 = word(SINGLETON_A0)
    L = layout()
    which = f'ISO {ISO_STEPS[(a0 - L["tabs"]) >> 12]} 表' if L['tabs'] <= a0 < L['tabs'] + 0x1F000 else \
        ('原廠 OFF 表' if a0 == OFF_TABLE else '其他')
    print(f'root+0x70 0x{word(ROOT_P70):08X}  tone +A0 0x{a0:08X} ({which})  hw 0x{word(0x30200094):08X}')


def install():
    for n, (site, orig, _) in SITES.items():
        w = word(site)
        if w != orig:
            raise SystemExit(f'site {n} is 0x{w:08X}, expected 0x{orig:08X} '
                             '(rv_gain_proto 的 hook 還在?先 rv_gain_proto.py uninstall)')
    p = block()
    code = assemble(SRC, [f'P=0x{p:08X}'])
    put(p, code, 'rawhk ')
    back = mem_get(p, len(code) // 4)
    if b''.join(x.to_bytes(4, 'little') for x in back) != code:
        raise SystemExit('stub readback mismatch; not touching the sites')
    publish()
    s = sym(p)
    for n, (site, _, name) in SITES.items():
        set_word(site, bl(site, p + s[name]))
    publish()
    print('installed (flag 0)')
    status()


def load():
    L = layout()
    blob = b''.join((HERE.parent / 'curves' / f'tone2048_iso{i}.u16le').read_bytes() for i in ISO_STEPS)
    assert len(blob) == len(ISO_STEPS) * 0x1000
    put(L['tabs'], blob, 'tables')
    orig = mem_get(ROOT_P70_ORIG, MODE_TAB_N * 2)
    if orig[OFF_ENTRY * 2] != 0x24 or orig[OFF_ENTRY * 2 + 1] != 82:
        raise SystemExit(f'mode 表第 35 筆不是 (0x24, 82): {orig[70:72]}')
    first = L['tabs'] + ISO_STEPS.index(100) * 0x1000
    put(L['slots'], b''.join(struct.pack('<II', 0, first) for _ in range(11)), 'slots ')
    n = ((L['slots'] - CURVE_ENTRIES) >> 3) + 5 & 0xFFFFFFFF
    m = list(orig); m[OFF_ENTRY * 2 + 1] = n
    put(L['mode_copy'], b''.join(x.to_bytes(4, 'little') for x in m), 'modes ')
    for k in (-5, 0, 5):
        a = (CURVE_ENTRIES + ((n + k) & 0xFFFFFFFF) * 8 + 4) & 0xFFFFFFFF
        if word(a) != first:
            raise SystemExit(f'插槽自檢失敗 idx N{k:+d}')
    p = block()
    thr = [round(REL100 * 2 ** ((k + 0.5) / 3)) for k in range(len(ISO_STEPS) - 1)]
    put(p + 8, struct.pack('<II', L['tabs'], L['slots']) + struct.pack(f'<{len(thr)}I', *thr), 'params')
    publish()                      # 表經 DMA 讀取:D-cache 清一次
    print(f'loaded 31 tables at 0x{L["tabs"]:08X}, slots 0x{L["slots"]:08X}, N 0x{n:08X}')


def on():
    if sh('menu SetColorMode').strip().split()[-1] != str(MENU_OFF):
        raise SystemExit('色彩模式不是 OFF(12)')
    p = block()
    if word(p + 8) == 0:
        raise SystemExit('先 load')
    set_word(p + 4, 0)                          # 強制下一輪重新選表
    set_word(ROOT_P70, layout()['mode_copy'])
    set_word(p, 1)
    mem_set(KEY_CTX0, 0xFFFFFFFF)
    time.sleep(1.0)
    status()


def off():
    p = block()
    set_word(p, 0)
    set_word(ROOT_P70, ROOT_P70_ORIG)
    mem_set(KEY_CTX0, 0xFFFFFFFF)
    time.sleep(1.0)
    status()
    print('轉一次 ISO 讓增益回到原廠計算(旗標 0 時 hook 不動作)')


def uninstall():
    for site, orig, _ in SITES.values():
        set_word(site, orig)
    publish()
    status()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['status', 'install', 'load', 'on', 'off', 'uninstall'])
    a = ap.parse_args()
    {'status': status, 'install': install, 'load': load, 'on': on, 'off': off,
     'uninstall': uninstall}[a.cmd]()
