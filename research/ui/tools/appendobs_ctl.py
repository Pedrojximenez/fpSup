#!/usr/bin/env python3
"""arm / read / off —— 觀察 image array 容器接上的元素(Thumb hook)。

    ./appendobs_ctl.py arm     裝 payload,把 0xC05E2CA8 前 4 bytes 換成 B.W
    ./appendobs_ctl.py read    讀回 (container, element, name) 紀錄
    ./appendobs_ctl.py off     寫回原本那兩道指令

目標是 Thumb-2,所以入口用 B.W(T4)而不是 ARM 的 BL。用 B 不是 BL,
lr 不會被動到,位移的兩道指令可以原樣執行再跳回 0xC05E2CAD。
"""
import pathlib, struct, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'fpSup' / 'fp_usb_shell'))
from armasm import assemble
from putfile import mem_get, mem_set, put, read_bulk

SRC    = HERE / 'appendobs.S'
CODE   = 0xC0733000
SLOTP  = 0xC07330F0
LOGBEG = 0xC0733100
LOGEND = 0xC0734000
SLOT   = 12
SITE   = 0xC05E2CA8
ORIG   = 0x4605B530             # push {r4,r5,lr} ; mov r5,r0
NAME1  = 0xC18E92DC             # qs_resolution_1_S
NAME2  = 0xC18E92F0             # qs_resolution_2_S


def bw(site, target):
    """Thumb-2 B.W (T4)。回傳放進記憶體的那個 32-bit 字。"""
    off = target - (site + 4)
    if not -(1 << 24) <= off < (1 << 24) or off & 1:
        raise SystemExit('B.W 跳不到')
    s  = (off >> 24) & 1
    i1 = (off >> 23) & 1
    i2 = (off >> 22) & 1
    j1 = (~i1 ^ s) & 1
    j2 = (~i2 ^ s) & 1
    hw1 = 0xF000 | (s << 10) | ((off >> 12) & 0x3FF)
    hw2 = 0x9000 | (j1 << 13) | (j2 << 11) | ((off >> 1) & 0x7FF)
    return hw1 | (hw2 << 16)


def setw(a, v):
    for _ in range(8):
        if mem_get(a)[0] == v:
            return True
        mem_set(a, v)
    return mem_get(a)[0] == v


cmd = sys.argv[1] if len(sys.argv) > 1 else 'read'

if cmd == 'arm':
    code = assemble(SRC)
    if CODE + len(code) > SLOTP:
        raise SystemExit(f'payload {len(code)} bytes 會蓋到 SLOTP')
    if any(mem_get(CODE, (SLOTP - CODE) // 4)):
        raise SystemExit(f'0x{CODE:08X} 不是空的 —— 停手')
    cur = mem_get(SITE)[0]
    if cur != ORIG:
        raise SystemExit(f'掛點是 0x{cur:08X},不是原廠 0x{ORIG:08X} —— 停手')
    put(CODE, code, 'appendobs')
    setw(SLOTP, LOGBEG)
    word = bw(SITE, CODE)
    print(f'  B.W 0x{SITE:08X} → 0x{CODE:08X} = 0x{word:08X}')
    if not setw(SITE, word):
        raise SystemExit('掛點寫入失敗')
    print('  armed')

elif cmd == 'off':
    setw(SITE, ORIG)
    print(f'  0x{SITE:08X} = 0x{mem_get(SITE)[0]:08X}  (原廠 0x{ORIG:08X})')

else:
    code = assemble(SRC)
    expected_words = struct.unpack(f'<{len(code) // 4}I', code)
    actual_words = tuple(mem_get(CODE, len(expected_words)))
    bad = [i for i, (expected, actual) in enumerate(zip(expected_words, actual_words))
           if expected != actual]
    hook = mem_get(SITE)[0]
    expected_hook = bw(SITE, CODE)
    if bad or hook != expected_hook:
        detail = []
        if bad:
            detail.append(f'payload 有 {len(bad)} 字不符(首筆 +0x{bad[0] * 4:X})')
        if hook != expected_hook:
            detail.append(f'hook=0x{hook:08X},預期 0x{expected_hook:08X}')
        raise SystemExit('  觀察器沒有完整裝上:' + '；'.join(detail))

    end = mem_get(SLOTP)[0]
    if not LOGBEG <= end <= LOGEND or (end - LOGBEG) % SLOT:
        raise SystemExit(f'  SLOTP = 0x{end:08X}(不是有效的 {SLOT}-byte 紀錄邊界)')
    n = (end - LOGBEG) // SLOT
    print(f'  payload {len(code)} bytes 與 hook 0x{hook:08X} 完整')
    print(f'  SLOTP = 0x{end:08X} → {n} 筆')
    if not n:
        print('  判定:觀察器在開機時沒有看到 resolution image array 建構')
        raise SystemExit(0)
    raw = read_bulk(LOGBEG, n * SLOT, 'append')
    import collections
    labels = {NAME1: 'qs_resolution_1_S', NAME2: 'qs_resolution_2_S'}
    by_name = collections.Counter()
    by_container = collections.Counter()
    rows = []
    for i in range(n):
        container, elem, name = struct.unpack_from('<3I', raw, i * SLOT)
        if name not in labels:
            raise SystemExit(f'  第 {i} 筆名稱指標 0x{name:08X} 不在過濾清單內')
        rows.append((container, elem, name))
        by_name[name] += 1
        by_container[container] += 1
    print('  依圖示分佈:')
    for name, count in by_name.most_common():
        print(f'    {labels[name]:24s} ×{count}')
    print(f'  不同容器:{len(by_container)}')
    print('  前 12 筆:')
    for i, (container, elem, name) in enumerate(rows[:12]):
        print(f'    [{i:2d}] container=0x{container:08X}  elem=0x{elem:08X}  '
              f'name={labels[name]}')
