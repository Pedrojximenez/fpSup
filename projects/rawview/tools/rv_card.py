#!/usr/bin/env python3
"""rv_card.py — 操作卡片開機載入的 rawview(build/build_rawview.py 的產物)。

    python3 rv_card.py status
    python3 rv_card.py on        # flag = 1(是否生效由 stub 依色彩模式 OFF／CinemaDNG／12-bit 判斷)
    python3 rv_card.py off       # flag = 0
    python3 rv_card.py select-raw   # 模擬在 Color 清單選第 17 列(R1):pend = 17,再 menu SetColorMode 12(經 setter 的 stub_mc)
    python3 rv_card.py select-off   # 模擬選 OFF:pend = 16,再 menu SetColorMode 12
    python3 rv_card.py dbg          # 讀選單事件紀錄環(8 筆)
    python3 rv_card.py lat SA|GA    # 曲線:SA = Latitude — Stop Aligned(每檔等寬)、GA = Gray Aligned(中灰對 709)
    python3 rv_card.py sat N        # 矩陣程度(AEL 飽和度 0 = 不套、1 = 完整校色)
    python3 rv_card.py con N        # 曲線做法(AEL 對比 0 = 12.5 檔鋪到預覽 10.9 檔、1 = 原做法)
    python3 rv_card.py shot NAME    # 截圖(CAPTURE 鍵)並取回到 captures/<今天>/NAME.JPG

常駐參數區經 site A 的 bl → veneer(ldr pc,[pc,#-4])→ stub_gs 位址 − STUB_GS 找到,並核對 'RVW1'。
開關只寫 flag;下一次增益計算(待機時頻繁發生)stub 自己切換 root 指標、選表、增益。
"""
import argparse, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'fpSup' / 'fp_usb_shell'))
sys.path.insert(0, str(HERE.parent / 'build'))
from putfile import sh, mem_get, mem_set  # noqa: E402
from armasm import symbols               # noqa: E402

SITE_A = 0xC0313244
ISO_STEPS = [100, 125, 160, 200, 250, 320, 400, 500, 640, 800, 1000, 1250, 1600, 2000,
             2500, 3200, 4000, 5000, 6400, 8000, 10000, 12800, 16000, 20000, 25600,
             32000, 40000, 51200, 64000, 80000, 102400]


def word(a):
    for _ in range(6):
        w = mem_get(a)
        if w and w[0] is not None:
            return w[0]
    raise SystemExit(f'read 0x{a:08X} failed')


def params():
    w = word(SITE_A)
    if w >> 24 != 0xEB:
        raise SystemExit(f'site A = 0x{w:08X}: rawview 未安裝')
    off = ((w & 0xFFFFFF) ^ 0x800000) - 0x800000
    ven = SITE_A + 8 + off * 4
    if word(ven) != 0xE51FF004:
        raise SystemExit(f'site A 指向 0x{ven:08X},不是 veneer(可能是 rv_raw.py 原型)')
    stub = word(ven + 4)
    magic = int.from_bytes(b'RVW1', 'little')
    p = stub - symbols(HERE.parent / 'build' / 'rv_resident.S')['stub_gs']
    if word(p) == magic:
        return p
    for d in range(4, 0x600, 4):            # 卡上是別版常駐(參數區長度不同):往附近找
        for q in (p + d, p - d):
            if word(q) == magic:
                return q
    raise SystemExit(f'0x{p:08X} 附近沒有 RVW1')


P_DBGI, P_DBG, P_LAT, P_MAT, P_SAT, P_SATF = 0x120, 0x124, 0x1A4, 0x1A8, 0x1B0, 0x1B4   # fs2-7 起(單列 RAW + 調整)
P_CON, P_CONF = 0x1C4, 0x1C8                                                          # fs2-21 起(對比 0/1)


def new_layout(p):
    return word(p + P_MAT) != 0 and (word(p + P_MAT) & 0x7FF) == 0


def status():
    p = params()
    flag, eff, last, tab, slots, mode = mem_get(p + 4, 6)
    a0 = word(0xC3414470 + 0xA0)
    off = (a0 - tab) >> 12 if a0 >= tab and (a0 - tab) & 0xFFF == 0 else -1
    k = off if 0 <= off < 62 else off - 4 if 66 <= off < 128 else None   # 表 62 起在常駐區之後(rv_tables.table_addr_off)
    sets = ('SA 對比0', 'GA 對比0', 'SA 對比1(原做法)', 'GA 對比1(原做法)')
    which = f'{sets[k // 31]} ISO {ISO_STEPS[k % 31]} 表' if k is not None else \
        ('原廠 OFF 表' if a0 == 0xC09C3F34 else f'0x{a0:08X}')
    im = mem_get(0xC343B5A0, 9)
    s32 = lambda a: word(a) - (1 << 32) if word(a) & 0x80000000 else word(a)
    var = (f'{"SA GA".split()[word(p + P_LAT) & 1]}  對比 {s32(p + P_CON):+d}(確認 {s32(p + P_CONF):+d})'
           f'  飽和度 {s32(p + P_SAT):+d}(確認 {s32(p + P_SATF):+d})'
           f'  矩陣 0x{word(0xC2F1A06C):08X}') if new_layout(p) else '舊版常駐'
    print(f'params 0x{p:08X}  flag {flag}  eff {eff}  last_rel {last}  tables 0x{tab:08X}  {var}')
    print(f'root+0x70 0x{word(0xC2F1A0D4):08X} (副本 0x{mode:08X})  tone {which}')
    print(f'color {sh("menu SetColorMode").strip()}  fmt {sh("menu SetMovRecFormat").strip()}  '
          f'qual {sh("menu SetMovCinemaDNGQuality").strip()}  iso {sh("menu SetIso").strip()}')
    print(f'rel {im[0]}  analog {im[2]}  ratio {im[5]}  hcg {im[7] & 0xFF}  digital×100 {im[8]}')


def flag(v):
    p = params()
    mem_set(p + 4, v)
    if word(p + 4) != v:
        raise SystemExit('flag write did not stick')
    import time; time.sleep(1.0)
    status()


def setp(off, v):
    p = params()
    if not new_layout(p):
        raise SystemExit('卡上是舊版常駐')
    mem_set(p + off, v & 0xFFFFFFFF)                   # stub_gs 下次增益計算時偵測變更、換表與矩陣
    import time; time.sleep(1.0)
    status()


def select(raw):
    p = params()
    mem_set(p + 0x94, (17 if raw else 16) if new_layout(p) else (1 if raw else 2))   # pend(fs2-4 以前:1 / 2)
    print(sh('menu SetColorMode 12').strip())
    import time; time.sleep(1.0)
    status()
    print('GUI 顯示(CM_COLFIX_ColorMode):', sh('gui geti CM_COLFIX_ColorMode').strip())


def dbg():
    p = params()
    di, db = (P_DBGI, P_DBG) if new_layout(p) else (0x120, 0x124)
    n = word(p + di)
    print(f'事件數 {n}')
    for k in range(max(0, n - 8), n):
        tag, a, b, f = mem_get(p + db + 16 * (k & 7), 4)
        if tag & 0xFF == 0x4D:
            site = {0xC0568950: 'COLOR 鍵 COLFIX', 0xC05689A8: 'COLOR 鍵預覽 COLAJ', 0xC056D028: '選單頁',
                    0xC05818B8: 'QS'}.get(0xC0000000 + (tag >> 8) - 4, f'0x{0xC0000000 + (tag >> 8) - 4:08X}') if tag >> 8 else '?'
            print(f'  #{k} GUI→enum  gui {a}  pend {b}  flag {f}  ← {site}')
        else:
            print(f'  #{k} setter    old {tag >> 8}  new {a}  生效列 {b} → {f}')


def shot(name, existing=None):
    import datetime, re, subprocess, time
    if existing:
        listing, new = sh(r'dir \DCIM\100SIGMA'), [existing]
        return fetch(name, new[-1], listing)
    before = set(re.findall(r'SS__\d{4}\.JPG', sh(r'dir \DCIM\100SIGMA')))
    sh('key CAPTUREON'); sh('key CAPTUREOFF')
    for _ in range(10):
        time.sleep(1.5)
        listing = sh(r'dir \DCIM\100SIGMA')
        new = sorted(set(re.findall(r'SS__\d{4}\.JPG', listing)) - before)
        if new:
            break
    else:
        raise SystemExit('沒有新的截圖')
    fetch(name, new[-1], listing)
    time.sleep(4)   # 截圖後相機會回放幾秒


def fetch(name, f, listing):
    import datetime, re, subprocess
    size = int(re.search(r'(\d+) +' + re.escape(f), listing).group(1))
    out = HERE.parent / 'captures' / str(datetime.date.today()) / f'{name}.JPG'
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, '-B', 'getfile.py', rf'\DCIM\100SIGMA\{f}', str(out), '--size', str(size)],
                   cwd=HERE.parents[2] / 'fpSup' / 'fp_usb_shell', check=True)
    print(f'{f} → {out}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['status', 'on', 'off', 'select-raw', 'select-off', 'dbg', 'shot', 'lat', 'sat', 'con'])
    ap.add_argument('name', nargs='?', default='shot')
    ap.add_argument('--existing', help='取回已存在的 SS__nnnn.JPG')
    a = ap.parse_args(); c = a.cmd
    {'status': status, 'on': lambda: flag(1), 'off': lambda: flag(0),
     'select-raw': lambda: select(True), 'select-off': lambda: select(False), 'dbg': dbg,
     'shot': lambda: shot(a.name, a.existing), 'lat': lambda: setp(P_LAT, 'SA GA'.split().index(a.name.upper())),
     'sat': lambda: setp(P_SAT, max(0, min(1, int(a.name)))),
     'con': lambda: setp(P_CON, max(0, min(1, int(a.name))))}[c]()
