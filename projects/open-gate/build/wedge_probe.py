#!/usr/bin/env python3
"""卡住現場取證。

    ./wedge_probe.py arm     錄影前:把所有計數器歸零
    ./wedge_probe.py read    卡住之後:讀回來,看它停在哪一步

卡住的是 UI/寫入側,shell 仍然活著,所以這些計數器讀得到。
重點是 canvas 的「最後 pid」與 og3kout 的拒絕環:
  最後 pid = 13  -> 還在錄影 profile,沒走到 live view
  最後 pid = 5   -> 已經在配置 live view 了,死在那之後
  拒絕環有 16:9  -> live view 的描述子沒被換成 3:2
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ogdev import rd
try:
    from ogdev import wr
except ImportError:
    from putfile import mem_set as _ms
    def wr(a, v): _ms(a, v); return True

CANVAS_LOG = 0xC0732A00     # +0 錄影命中 +4 回放命中 +8 最後 pid +C/+10 要求尺寸
OUT_HITS   = 0xC0732060
OUT_REJ    = 0xC0732070     # +0 筆數,之後每筆 12B {idx, W, H},最多 6
SEL_LOG    = 0xC0731C00
GS_LOG     = 0xC07328C0
FMT_HITS   = 0xC0730700
FLAG, PBFLAG, BITLATCH = 0xC0731C08, 0xC0731C0C, 0xC0731C14

def arm():
    for a in (CANVAS_LOG, CANVAS_LOG+4, CANVAS_LOG+8, CANVAS_LOG+0xC, CANVAS_LOG+0x10,
              OUT_HITS, OUT_REJ, SEL_LOG, SEL_LOG+4, GS_LOG, FMT_HITS):
        wr(a, 0)
    print("計數器已歸零。現在錄影。卡住之後跑 ./wedge_probe.py read")

def read():
    c = rd(CANVAS_LOG, 5)
    print("canvas  錄影命中 %d  回放命中 %d  最後 pid %d  要求尺寸 %dx%d"
          % (c[0], c[1], c[2], c[3], c[4]))
    print("fmttable 命中 %d   og3kout 命中 %d" % (rd(FMT_HITS)[0], rd(OUT_HITS)[0]))
    s = rd(SEL_LOG, 2); print("og3ksel  次數 %d  最後 enum %d" % (s[0], s[1]))
    print("og3kgs   %d" % rd(GS_LOG)[0])
    print("FLAG %d  PBFLAG %d  BITLATCH %d"
          % (rd(FLAG)[0], rd(PBFLAG)[0], rd(BITLATCH)[0]))
    n = rd(OUT_REJ)[0]
    print("og3kout 拒絕環 %d 筆" % n)
    if 0 < n <= 6:
        w = rd(OUT_REJ + 4, n * 3)
        for i in range(n):
            idx, W, H = w[i*3:i*3+3]
            print("   idx %d  %dx%d%s" % (idx, W, H, "  <- 16:9,沒被換成 3:2" if H and W*9 == H*16 else ""))

{"arm": arm, "read": read}[sys.argv[1] if len(sys.argv) > 1 else "read"]()
