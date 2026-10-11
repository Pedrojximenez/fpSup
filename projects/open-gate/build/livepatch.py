#!/usr/bin/env python3
"""趁 QS 開著的時候把第三個槽位接上去,再強制重繪,看圖會不會載入。

這是決定性的測試,不是解法:元素物件是 QS 開啟時才建的,所以這樣 patch
撐不過下一次開關。目的只是證明「三個槽位 + 我們的圖」這條路本身成立,
再決定要不要投資去做 Thumb hook。

流程:
  1. 把 QS 正規化成關閉,然後開啟
  2. 掃堆找出現在存在的解析後陣列
  3. 寫圖 + 加第三個槽位
  4. 改一個無關的設定強制重繪(QS 保持開著)
  5. 讀 image log
"""
import json, pathlib, re, struct, subprocess, sys, tempfile, os, time

SHELL = '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell'
sys.path.insert(0, SHELL)
from putfile import sh, mem_get, mem_set, put

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import xci

NAME_1S  = 0xC18E92DC
NAME_DCI = 0xC18DA6C4
BLOB_DCI = 0xC1359724
BLOB_ROOM = 2896
SCRATCH  = 0xC0733000
STRIDE   = 0x40
ELEM_LEN = 0x34
POS3     = 0x42
SWEEP    = range(0xC6000000, 0xC8000000, 0x400000)


def k(cmd, wait=0.8):
    try:
        sh(cmd)
    except Exception:
        pass
    time.sleep(wait)


def setw(a, v):
    for _ in range(8):
        if mem_get(a)[0] == v:
            return True
        mem_set(a, v)
    return mem_get(a)[0] == v


def grab(a, n=0x400000):
    sh(f'mem save \\s.bin 0x{a:08X},,0x{n:X}')
    fn = tempfile.mktemp(suffix='.bin')
    subprocess.run([sys.executable, 'getfile.py', '\\s.bin', fn, '--size', str(n)],
                   capture_output=True, cwd=SHELL)
    d = open(fn, 'rb').read()
    os.unlink(fn)
    return d


def scan():
    out = []
    for base in SWEEP:
        d = grab(base)
        if len(d) < 0x400000:
            continue
        for m in re.finditer(re.escape(struct.pack('<I', NAME_1S)), d):
            o = m.start() - 0x30
            if o < 0:
                continue
            w = struct.unpack('<4I', d[o:o + 16])
            if (w[0], w[1], w[2]) == (2, 2, 8):
                out.append(base + o)
    return out


def loads():
    out, prev = [], None
    for l in sh('log out GUI').splitlines():
        if '0xc055fdf4' in l:
            prev = l.split('0xc055fdf4,')[-1].strip()
        elif '0xc055fe14' in l and prev is not None:
            out.append(prev)
            prev = None
    return out


def main():
    sh('gui image log 1')
    sh('log act GUI')

    print('  QS 正規化成關閉…')
    k('key QSON', 1.0)
    k('key QSON', 1.0)
    print(f'  關閉時堆裡的陣列: {len(scan())} 份')

    print('  開啟 QS…')
    k('key QSON', 1.5)
    hs = scan()
    print(f'  開啟時堆裡的陣列: {len(hs)} 份 {[hex(x) for x in hs[:4]]}')
    if not hs:
        print('  找不到 —— 物件不在掃描範圍內,測試無法進行')
        k('key QSON', 1.0)
        return

    blob = xci.encode(*xci.text_tile('OG3K', lo=0.05, hi=0.95))
    put(BLOB_DCI, blob + b'\x00' * (-len(blob) % 4), 'tile  ')
    print(f'  圖 {len(blob)} bytes 已寫入')

    for i, h in enumerate(hs):
        w = mem_get(h, 4)
        arr = w[3]
        e0, e1 = mem_get(arr, 2)
        ne = SCRATCH + i * STRIDE
        na = ne + ELEM_LEN
        body = list(mem_get(e1, ELEM_LEN // 4))
        body[0] = POS3
        body[0x18 // 4] = NAME_DCI
        for j, v in enumerate(body):
            setw(ne + j * 4, v)
        for j, v in enumerate((e0, e1, ne)):
            setw(na + j * 4, v)
        setw(h + 0x0C, na)
        setw(h, 3)
    print(f'  {len(hs)} 份已擴充成三筆(QS 仍開著)')

    sh('log clear')
    print('  改一個無關設定強制重繪…')
    cur = sh('menu SetShutterSpeed').strip().split()[0]
    sh(f'menu SetShutterSpeed {int(cur) + 1}')
    time.sleep(1.5)
    got = loads()
    res = [x for x in got if 'resolution' in x]
    print(f'  重繪載入 {len(got)} 張,resolution 相關: {res}')
    sh(f'menu SetShutterSpeed {cur}')
    k('key QSON', 1.0)


main()
