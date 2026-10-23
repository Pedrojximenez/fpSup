"""Instructions per icon load (C0602184..C060235E): stock vs miss vs hit."""
import sys
from unicorn import UC_HOOK_CODE
import test_iconcache as T
ents = T.icons()
pick = [ents[i] for i in (0, 100, 500, 1000, 1500)] + [max(ents, key=lambda e: e[2] * e[3])]
stock, pat = T.Rig(False), T.Rig(True, arena=4 << 20)
n = [0]
def cnt(uc, a, s, u): n[0] += 1
for r in (stock, pat):
    r.mu.hook_add(UC_HOOK_CODE, cnt)
tot = [0, 0, 0, 0]
for e in pick:
    size = e[2] * e[3] * 2
    n[0] = 0; stock.load(e); s = n[0]
    n[0] = 0; pat.load(e); m = n[0]
    n[0] = 0; pat.load(e); h = n[0]
    tot = [tot[0] + s, tot[1] + m, tot[2] + h, tot[3] + size]
    print(f'{e[0]:#x} {e[2]}x{e[3]} out {size:7d} B  stock {s:9d} ({s/size:5.2f}/B)  miss {m:9d}  hit {h:8d} ({h/size:4.2f}/B)')
print(f'total: stock {tot[0]/tot[3]:.2f} instr/B, hit {tot[2]/tot[3]:.2f} instr/B (x{tot[0]/tot[2]:.1f}), miss overhead {100*(tot[1]-tot[0])/tot[0]:.1f}%')
