"""Re-checks the static/emulated facts behind layercopy/README.md (no camera).

    python3 -B evidence.py
"""
import pathlib, struct, sys
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'projects/sys-perf/dirtyclean'))
import test_dirtyclean as T                                   # noqa: E402
from unicorn import UC_HOOK_CODE                              # noqa: E402

img = (ROOT / 'out/seg0_c0000000.bin').read_bytes()
word = lambda a: struct.unpack_from('<I', img, a - 0xC0000000)[0]
ok = []

def chk(name, cond):
    ok.append(cond); print(('ok  ' if cond else 'BAD ') + name)

# 1. both UIC drawer vtables: +0x1C = C05757F8, which returns 0 (no whole-layer copy)
for vt in (0xC0D17780, 0xC2E45DF8):
    chk(f'UIC vt {vt:#x} +0x1C == C05757F8', word(vt + 0x1C) == 0xC05757F8)
chk('C05757F8 = mov ip,r0; mov r1,#0; mov r0,r1; bx lr',
    [word(0xC05757F8 + 4 * i) for i in range(4)] == [0xE1A0C000, 0xE3A01000, 0xE1A00001, 0xE12FFF1E])
# 2. the default drawer +0x1C C03E05A0 returns 1 (non-UIC drawers ask for the copy)
chk('C03E05A0 = mov ip,r0; mov r1,#1; mov r0,r1; bx lr',
    [word(0xC03E05A0 + 4 * i) for i in range(4)] == [0xE1A0C000, 0xE3A01001, 0xE1A00001, 0xE12FFF1E])
chk('drawer vt C2DF7F68 (C05A26C8 registers it) +0x1C == C03E05A0', word(0xC2DF7F68 + 0x1C) == 0xC03E05A0)
# 3. C0528BA0 copies front(vt+0xC desc+4) -> back(vt+0x10 desc+4), stride*height, via memcpy
chk('C0528BA0 ends in bl C001510C (memcpy)', word(0xC0528C1C) == T.bl(0xC0528C1C, 0xC001510C))

# 4. emulated real C0528700: copy calls per 5 rounds
def copies(kinds, other_copy):
    g = T.Rig(patched=False); g.set_drawers(0, kinds); g.other_copy = other_copy
    n = [0]
    g.mu.hook_add(UC_HOOK_CODE, lambda *a: n.__setitem__(0, n[0] + 1), begin=0xC0528BA0, end=0xC0528BA0)
    for _ in range(5):
        g.round(1, {0: {'uic': T.TC}})
    return n[0], g.commits
chk('UIC-only slot: 0 copies in 5 commits', copies(['uic'], False) == (0, 5))
chk('slot with a non-UIC drawer (+0x1C=1): 5 copies in 5 commits', copies(['uic', 'other'], True) == (5, 5))
print('all facts hold' if all(ok) else 'SOME FACTS FAILED')
sys.exit(0 if all(ok) else 1)
