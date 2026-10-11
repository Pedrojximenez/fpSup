#!/usr/bin/env python3
"""把 OG3K 圖塊裝進 QS 的解析度格。

    ./og3ktile.py scan      找出堆裡所有解析後的陣列
    ./og3ktile.py apply     寫圖 + 加第三個槽位
    ./og3ktile.py revert    還原

做三件事,全部執行期寫入,拔電池即還原:

  1. 用新畫的 OG3K(86x49)覆寫 `M_resolution_dci4K` 的 blob。
     那張圖 fp 永遠不會顯示,而且它的槽位有 2896 bytes,我們只要 1564。

  2. 在空白 RAM 蓋一個新的元素物件(照抄元素1,只把 +0x18 的名字指標
     換成 M_resolution_dci4K)和一個三格的指標陣列。

  3. 把每一份解析後陣列的筆數改成 3、+0x0C 指到新陣列。

序列化的那塊資料(0xC22A17xx)完全不碰 —— 實測改它沒有任何作用,
資源記錄是開機時解析一次進活的結構,之後不再回頭讀。
"""
import json, pathlib, struct, sys

sys.path.insert(0, '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
from putfile import mem_get, mem_set, put, read_bulk

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import xci

ORIG = HERE / 'og3ktile_orig.json'

NAME_1S   = 0xC18E92DC          # qs_resolution_1_S 的名字(用來認陣列)
NAME_DCI  = 0xC18DA6C4          # M_resolution_dci4K 的名字 —— 第三個槽位指這裡
BLOB_DCI  = 0xC1359724          # 它的 blob,可用 2896 bytes
BLOB_ROOM = 2896

SCRATCH   = 0xC0733000          # 靜態映像裡的全零區,現有 payload 到 0xC0732980 為止
STRIDE    = 0x40                # 每份副本:元素 0x34 + 陣列 0x0C
ELEM_LEN  = 0x34
POS3      = 0x42                # 第三個元素的位置值(qs_ae 三筆是 0x00/0x21/0x42)

HEAP = [(0xC7000000, 0x1000000)]   # 掃描範圍


def setw(a, v):
    for _ in range(8):
        if mem_get(a)[0] == v:
            return True
        mem_set(a, v)
    return mem_get(a)[0] == v


def scan():
    """在堆裡找出所有 {筆數2, 2, 8, 陣列} 且元素0 指向 qs_resolution_1_S 的表頭。"""
    import re
    found = []
    for base, size in HEAP:
        for off in range(0, size, 0x400000):
            n = min(0x400000, size - off)
            a = base + off
            from putfile import sh
            sh(f'mem save \\scan.bin 0x{a:08X},,0x{n:X}')
            d = fetch_card('\\scan.bin', n)
            for m in re.finditer(re.escape(struct.pack('<I', NAME_1S)), d):
                o = m.start() - 0x30
                if o < 0 or o + 16 > len(d):
                    continue
                cnt, two, eight, arr = struct.unpack('<4I', d[o:o + 16])
                if (cnt, two, eight) == (2, 2, 8):
                    found.append(a + o)
    return found


def fetch_card(remote, size):
    import subprocess, tempfile, os
    fn = tempfile.mktemp(suffix='.bin')
    subprocess.run([sys.executable, str(pathlib.Path(
        '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell/getfile.py')),
        remote, fn, '--size', str(size)], capture_output=True,
        cwd='/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
    d = open(fn, 'rb').read()
    os.unlink(fn)
    return d


def verify(hdr):
    """確認這個表頭現在仍是原廠的兩筆結構,回傳 (陣列, 元素0, 元素1)。"""
    w = mem_get(hdr, 4)
    if tuple(w[:3]) != (2, 2, 8):
        return None
    arr = w[3]
    e = mem_get(arr, 2)
    if mem_get(e[0] + 0x18)[0] != NAME_1S:
        return None
    return arr, e[0], e[1]


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'scan'

    if cmd == 'scan':
        hs = scan()
        print(f"  找到 {len(hs)} 份:")
        for h in hs:
            v = verify(h)
            print(f"    0x{h:08X}  {'✔' if v else '✗ 驗證失敗'}")
        (HERE / 'og3ktile_headers.json').write_text(
            json.dumps([f"0x{h:08X}" for h in hs], indent=1))
        return

    hdrs = [int(x, 16) for x in json.loads(
        (HERE / 'og3ktile_headers.json').read_text())]

    if cmd == 'apply':
        blob = xci.encode(*xci.text_tile('OG3K', lo=0.05, hi=0.95))
        if len(blob) > BLOB_ROOM:
            raise SystemExit(f'blob {len(blob)} 超過 {BLOB_ROOM}')
        orig = {'blob': read_bulk(BLOB_DCI, BLOB_ROOM, 'orig  ').hex(),
                'hdrs': {}}
        # 先把每一份都驗過,有一份不對就整個停手
        info = {}
        for h in hdrs:
            v = verify(h)
            if not v:
                raise SystemExit(f'0x{h:08X} 驗證失敗(堆移動過?) —— 先重跑 scan')
            info[h] = v
        # 1) 覆寫圖
        put(BLOB_DCI, blob + b'\x00' * (-len(blob) % 4), 'tile  ')
        # 2) 蓋新元素 + 新陣列
        tmpl = mem_get(info[hdrs[0]][2], ELEM_LEN // 4)
        for i, h in enumerate(hdrs):
            arr, e0, e1 = info[h]
            ne = SCRATCH + i * STRIDE
            na = ne + ELEM_LEN
            body = list(mem_get(e1, ELEM_LEN // 4))
            body[0] = POS3
            body[0x18 // 4] = NAME_DCI
            for k, val in enumerate(body):
                if not setw(ne + k * 4, val):
                    raise SystemExit(f'元素寫入失敗 0x{ne + k*4:08X}')
            for k, val in enumerate((e0, e1, ne)):
                if not setw(na + k * 4, val):
                    raise SystemExit(f'陣列寫入失敗 0x{na + k*4:08X}')
            orig['hdrs'][f"0x{h:08X}"] = [f"0x{arr:08X}"]
            # 3) 先改指標再改筆數 —— 反過來會讓它讀到舊陣列的第三格(垃圾)
            if not setw(h + 0x0C, na):
                raise SystemExit(f'指標寫入失敗 0x{h+0x0C:08X}')
            if not setw(h, 3):
                raise SystemExit(f'筆數寫入失敗 0x{h:08X}')
        ORIG.write_text(json.dumps(orig))
        print(f"  圖 {len(blob)} bytes 寫入 0x{BLOB_DCI:08X}")
        print(f"  {len(hdrs)} 份陣列已擴充成三筆")
        return

    if cmd == 'revert':
        o = json.loads(ORIG.read_text())
        put(BLOB_DCI, bytes.fromhex(o['blob']), 'back  ')
        for k, v in o['hdrs'].items():
            h = int(k, 16)
            setw(h, 2)
            setw(h + 0x0C, int(v[0], 16))
        for a in range(SCRATCH, SCRATCH + len(o['hdrs']) * STRIDE, 4):
            setw(a, 0)
        print(f"  已還原 {len(o['hdrs'])} 份 + 原圖")
        return

    raise SystemExit(__doc__)


main()
