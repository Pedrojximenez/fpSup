#!/usr/bin/env python3
"""arm / read / off —— 觀察 0x34-byte 元素物件是誰建的(Thumb hook)。

    ./elemobs_ctl.py arm     裝 payload,把 0xC05EDC40 前 4 bytes 換成 B.W
    ./elemobs_ctl.py read    讀回 (r0, lr) 紀錄
    ./elemobs_ctl.py off     寫回原本那兩道指令

目標是 Thumb-2,所以入口用 B.W(T4)而不是 ARM 的 BL。用 B 不是 BL,
lr 不會被動到,位移的兩道指令可以原樣執行再跳回 0xC05EDC45。
"""
import pathlib, struct, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'fpSup' / 'fp_usb_shell'))
from armasm import assemble
from putfile import mem_get, mem_set, put, read_bulk

SRC    = HERE / 'elemobs.S'
CODE   = 0xC0733000
SLOTP  = 0xC07330F0
LOGBEG = 0xC0733100
LOGEND = 0xC0734000
SLOT   = 64
SITE   = 0xC05EDC40
ORIG   = 0x6B41B530             # push {r4,r5,lr} ; ldr r1,[r0,#0x34]


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
    put(CODE, code, 'elemobs')
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
    end = mem_get(SLOTP)[0]
    if not LOGBEG <= end <= LOGEND or (end - LOGBEG) % SLOT:
        raise SystemExit(f'  SLOTP = 0x{end:08X}(不是有效的 {SLOT}-byte 紀錄邊界)')
    n = (end - LOGBEG) // SLOT
    print(f'  SLOTP = 0x{end:08X} → {n} 筆')
    if not n:
        raise SystemExit('  還沒命中')
    raw = read_bulk(LOGBEG, n * SLOT, 'elem  ')
    import collections
    by = collections.Counter()
    for i in range(n):
        r0, lr = struct.unpack_from('<2I', raw, i * SLOT)
        by[lr] += 1
    print(f'  依呼叫點分佈:')
    for lr, c in by.most_common():
        print(f'    lr=0x{lr:08X}  ×{c}')
    print('  前 12 筆:')
    for i in range(min(12, n)):
        r0, lr = struct.unpack_from('<2I', raw, i * SLOT)
        print(f'    [{i:2d}] r0=0x{r0:08X}  lr=0x{lr:08X}')
