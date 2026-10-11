#!/usr/bin/env python3
"""rv_gain_proto.py — rawview 原型二:待機 LV 用錄影的類比增益、RAW_CORR 數位增益維持 1×。

兩個 hook(README「增益 hook 設計」,stub 在 rv_gain_hooks.S):
  A 0xC0313244  E595200C  ldr r2,[r5,#0xc]   gain_state:待機且旗標開 → 7(movie_raw_12bit)
  B 0xC032F728  E59C6000  ldr r6,[ip]        RAW_CORR 最終數位增益:旗標開且 bank 0 → 0x400(1×)

    python3 rv_gain_proto.py status
    python3 rv_gain_proto.py install     # 放 stub、改兩條指令成 bl;旗標為 0,行為與原廠相同
    python3 rv_gain_proto.py on          # 旗標 = 1;之後轉一次 ISO 才生效
    python3 rv_gain_proto.py off         # 旗標 = 0;之後轉一次 ISO
    python3 rv_gain_proto.py uninstall   # 兩條指令寫回原字

每次改指令都做 D-cache clean(0xC000E91C)+ I-cache invalidate(0xC000EABC)。
全部改動只在 RAM,關機重開一定還原。
"""
import argparse, pathlib, sys, time

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / 'fpSup' / 'fp_usb_shell'))
from putfile import mem_get, mem_set, put  # noqa: E402
from armasm import assemble, symbols        # noqa: E402
from callfn import call                     # noqa: E402
import cave                                 # noqa: E402

SRC = HERE / 'rv_gain_hooks.S'
SITES = {'A': (0xC0313244, 0xE595200C, 'stub_gs'),
         'B': (0xC032F728, 0xE59C6000, 'stub_dg')}
DCACHE_CLEAN = 0xC000E91C
ICACHE_INV = 0xC000EABC
HELPER_STATE = 0xC343A6A0 + 0x0C
IMX = 0xC343B5A0          # +0 rel gain, +8 analog code, +0x14 ratio, +0x1C HCG, +0x20 digital ×100


def word(a, tries=6):
    for _ in range(tries):
        w = mem_get(a)
        if w and w[0] is not None:
            return w[0]
        time.sleep(0.1)
    raise SystemExit(f'read 0x{a:08X} failed')


def block():
    size = len(assemble(SRC, ['P=0xC072E800']))
    return cave.claim('rawview.gain', size), size


def bl(site, target):
    off = (target - site - 8) >> 2
    if not -(1 << 23) <= off < (1 << 23):
        raise SystemExit(f'bl 0x{site:08X} → 0x{target:08X} out of range')
    return 0xEB000000 | (off & 0xFFFFFF)


def publish():
    call(DCACHE_CLEAN, verbose=False)
    call(ICACHE_INV, verbose=False)


def set_word(a, v):
    for _ in range(8):
        mem_set(a, v)
        if word(a) == v:
            return
    raise SystemExit(f'write 0x{a:08X} = 0x{v:08X} did not stick')


def status():
    p, _ = block()
    print(f'stub block 0x{p:08X}  flag = {word(p)}')
    for n, (site, orig, sym) in SITES.items():
        w = word(site)
        state = 'original' if w == orig else ('hooked' if (w & 0xFF000000) == 0xEB000000 else 'UNKNOWN')
        print(f'  site {n} 0x{site:08X} = 0x{w:08X}  {state}')
    im = mem_get(IMX, 9)
    print(f'gain_state {word(HELPER_STATE)}  rel {im[0]}  analog code {im[2]}  ratio {im[5]}  hcg {im[7] & 0xFF}  digital×100 {im[8]}')


def install():
    for n, (site, orig, _) in SITES.items():
        w = word(site)
        if w != orig:
            raise SystemExit(f'site {n} 0x{site:08X} is 0x{w:08X}, expected 0x{orig:08X}; refusing')
    p, _ = block()
    code = assemble(SRC, [f'P=0x{p:08X}'])
    sym = symbols(SRC, [f'P=0x{p:08X}'])
    put(p, code, 'gainhk')                     # flag word is 0 in the image: hooks start inert
    back = mem_get(p, len(code) // 4)
    if bytes(b for x in back for b in x.to_bytes(4, 'little')) != code:
        raise SystemExit('stub readback mismatch; not touching the sites')
    publish()
    for n, (site, _, s) in SITES.items():
        set_word(site, bl(site, p + sym[s]))
    publish()
    print('installed (flag 0: behaviour unchanged)')
    status()


def uninstall():
    for n, (site, orig, _) in SITES.items():
        set_word(site, orig)
    publish()
    print('uninstalled')
    status()


def flag(v):
    p, _ = block()
    if any(word(site) == orig for site, orig, _ in SITES.values()):
        raise SystemExit('hooks not installed; run install first')
    set_word(p, v)
    print(f'flag = {v}; turn the ISO dial once so the gain is recomputed')
    time.sleep(0.3)
    status()


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['status', 'install', 'on', 'off', 'uninstall'])
    a = ap.parse_args()
    {'status': status, 'install': install, 'uninstall': uninstall,
     'on': lambda: flag(1), 'off': lambda: flag(0)}[a.cmd]()
