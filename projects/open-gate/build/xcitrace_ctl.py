#!/usr/bin/env python3
"""arm / read / off —— 攔 gui image log 的回呼,抄呼叫端堆疊找 .xci 來源 blob。

    ./xcitrace_ctl.py arm     裝 payload 並把 0xC37CECF8 指過來
    ./xcitrace_ctl.py read    讀回紀錄並解析
    ./xcitrace_ctl.py off     把指標寫回 0xC055FDC8

只換函式指標,不改任何指令。還原一個字就好。
"""
import pathlib, struct, sys

sys.path.insert(0, '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
from armasm import assemble
from putfile import mem_get, mem_set, put, read_bulk

SRC    = pathlib.Path(__file__).resolve().parent / 'xcitrace.S'
CODE   = 0xC0733000
SLOTP  = 0xC07330F0
LOGBEG = 0xC0733100
LOGEND = 0xC0734000
PTR    = 0xC37CECF8             # _DAT_c37cecf8
STOCK  = 0xC055FDC8
SLOT   = 272


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
    # 先確認那塊真的是空的,別壓到別人
    probe = mem_get(CODE, 8)
    if any(probe):
        raise SystemExit(f'0x{CODE:08X} 不是空的:{[hex(x) for x in probe]} —— 停手')
    cur = mem_get(PTR)[0]
    if cur != STOCK:
        raise SystemExit(f'0x{PTR:08X} 是 0x{cur:08X},不是原廠 0x{STOCK:08X} —— 停手')
    put(CODE, code, 'xcitrace')
    for a in range(LOGBEG, LOGBEG + SLOT * 4, 4):
        setw(a, 0)
    if not setw(SLOTP, LOGBEG):
        raise SystemExit('SLOTP 初始化失敗')
    if not setw(PTR, CODE):
        raise SystemExit('指標切換失敗')
    print(f'  armed: 0x{PTR:08X} = 0x{CODE:08X}  ({len(code)} bytes)')

elif cmd == 'off':
    setw(PTR, STOCK)
    print(f'  0x{PTR:08X} = 0x{mem_get(PTR)[0]:08X}  (原廠 0x{STOCK:08X})')

else:
    end = mem_get(SLOTP)[0]
    n = (end - LOGBEG) // SLOT if LOGBEG <= end <= LOGEND else 0
    print(f'  SLOTP = 0x{end:08X}  →  {n} 筆')
    if not n:
        raise SystemExit('  還沒命中')
    raw = read_bulk(LOGBEG, n * SLOT, 'trace ')
    for i in range(n):
        s = raw[i * SLOT:(i + 1) * SLOT]
        r0, r1, r2, lr = struct.unpack('<4I', s[:16])
        stk = struct.unpack("<64I", s[16:272])
        print(f'\n  [{i:2d}] name@0x{r0:08X}  {r1}x{r2}  lr=0x{lr:08X}')
        for j in range(0, 64, 4):
            print('       ' + '  '.join(f'{stk[j+k]:08X}' for k in range(4)))
