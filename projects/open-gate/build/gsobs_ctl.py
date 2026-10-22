#!/usr/bin/env python3
"""gsobs 的安裝/讀取(0xC03239C8)。 on / read / off"""
import pathlib, struct, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent.parent / "fpSup" / "fp_usb_shell"))
from armasm import assemble
from putfile import mem_get, mem_set
SITE, STOCK = 0xC03239C8, 0xE92D40F0
CODE, LOG, END = 0xC0732800, 0xC0732880, 0xC07328B0
NAMES = {0:"through(live)",1:"acq(拍照)",2:"through_acq",3:"movie",
         4:"movie_raw",5:"movie_raw_8bit",6:"movie_raw_10bit",
         7:"movie_raw_12bit",8:"digital_off"}
HCG = {0:"OTP",1:"640",2:"640",3:"640",4:"永不",5:"640",6:"640",7:"3200",8:"永不"}
def rd(a,n=1):
    for _ in range(8):
        w=mem_get(a,n)
        if w and all(x is not None for x in w): return w
    raise SystemExit(f"讀不到 0x{a:08X}")
def wr(a,v):
    for _ in range(10):
        if rd(a)[0]==v: return True
        mem_set(a,v)
    return rd(a)[0]==v
cmd = sys.argv[1] if len(sys.argv)>1 else "read"
if cmd=="on":
    blob=assemble(HERE/"gsobs.S")
    if CODE+len(blob)>LOG: raise SystemExit("payload 會蓋到 LOG")
    cur=rd(SITE)[0]
    if cur!=STOCK: raise SystemExit(f"0x{SITE:08X} 是 0x{cur:08X},不是原廠 —— 停手")
    for i,v in enumerate(struct.unpack(f"<{len(blob)//4}I", blob)):
        if not wr(CODE+i*4,v): raise SystemExit(f"寫不進 0x{CODE+i*4:08X}")
    for a in range(LOG,END,4): wr(a,0)
    br=0xEA000000|(((CODE-SITE-8)>>2)&0xFFFFFF)
    if not wr(SITE,br): raise SystemExit("武裝失敗")
    print(f"  payload {len(blob)}B @0x{CODE:08X},已武裝 0x{SITE:08X} = 0x{br:08X}")
elif cmd=="off":
    wr(SITE,STOCK); print(f"  0x{SITE:08X} = 0x{rd(SITE)[0]:08X}(原廠)")
else:
    h=rd(LOG,3); c=rd(LOG+0x10,9)
    print(f"  v30 被呼叫 {h[0]} 次   最後 mode={h[1]}({NAMES.get(h[1],'?')}) rel%={h[2]}")
    print(f"  {'gain_state':<20}{'HCG 門檻':>10}{'次數':>10}")
    for i,n in enumerate(c):
        if n: print(f"    {i} {NAMES.get(i,'?'):<18}{HCG.get(i,'?'):>10}{n:>10}")
