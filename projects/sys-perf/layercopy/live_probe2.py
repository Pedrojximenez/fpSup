"""Read-only probe #2: the waveform painter's box, and what drew last into the 8bpp layer.

    python3 -B live_probe2.py            # CINE standby, waveform on, not recording

Static basis (README §6):
  waveform drawer (slot drawer, vptr C2DF80C4, draw C05A2EE8):
     +5 / [arg+1] set -> memset the WHOLE layer (desc obj +0x10 * +0x14) before drawing;
     +0xC..+0x20 cached layout (6 words, = [+0x28]->vt+0xC() result); +0x24 painter; +0x28 layout source.
  painter draw C05A3728(painter, canvas, src): fill rect painter+8..+0x14 (x,y,w,h) colour +0x18,
     then plot inside origin +0x1C,+0x20 size +0x24 x +0x28 (C05A34B8 / C05A35A0).
  painter vptr must be one of C2DF8F40 / C2DF8FD8 / C2DF9214 (their +0xC == C05A3728).
Only callfn(C05278F8) and mem_get.
"""
import sys
sys.path.insert(0, '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
from putfile import sh, mem_get
from callfn import call

PAINTER_VT = {0xC2DF8F40, 0xC2DF8FD8, 0xC2DF9214}
WAVE_VT = 0xC2DF80C4


def ok_addr(a):
    return 0xC0000000 <= a < 0xC8000000 and a % 4 == 0


def rd(a, n=1):
    for _ in range(4):
        v = mem_get(a, n)
        if v and len(v) == n and None not in v:
            return v
    raise RuntimeError(f'read {a:#x}+{n} kept returning None')


def s32(v):
    return v - (1 << 32) if v & 0x80000000 else v


assert sh('status get is_recording', retries=0).strip() == 'is_recording -> 0', 'recording: stop'
okc, H = call(0xC05278F8, verbose=False)
assert okc and ok_addr(H), 'C05278F8 failed'
ctrl = rd(H + 4)[0]
print(f'DrawController {ctrl:#x}')
d = rd(ctrl, 0x60 // 4)
found = False
for s in range(4):
    for o in d[3 * s:3 * s + 3]:
        if not ok_addr(o) or rd(o)[0] != WAVE_VT:
            continue
        found = True
        w = rd(o, 0x30 // 4)
        print(f'\nslot {s} waveform drawer {o:#x}: flags(+4..+7) {w[1]:08x}  layout(+0xC..+0x20) {w[3:9]}')
        P, Lsrc = w[9], w[10]
        print(f'  painter [+0x24] {P:#x}   layout source [+0x28] {Lsrc:#x}')
        if not ok_addr(P):
            print('  painter address not plausible; skipped'); continue
        p = rd(P, 0x40 // 4)
        print(f'  painter vptr {p[0]:#x}  ' + ('(known C05A3728 class)' if p[0] in PAINTER_VT else '(UNKNOWN class: rects below unverified)'))
        print(f'  fill rect +8..+0x14   x={s32(p[2])} y={s32(p[3])} w={s32(p[4])} h={s32(p[5])}  colour +0x18 {p[6]:#x}')
        print(f'  plot rect +0x1C..+0x28 x={s32(p[7])} y={s32(p[8])} w={s32(p[9])} h={s32(p[10])}')
        print('  painter +00..+3F', ' '.join(f'{x:08x}' for x in p))
        L = d[(0x58 + 8 * s) // 4]
        if ok_addr(L):
            lv = rd(L, 0x54 // 4)
            print(f'  layer {L:#x} fmt {lv[0x1C // 4]}  front desc {lv[0x48 // 4]:#x}  back desc {lv[0x4C // 4]:#x}')
if not found:
    print('no waveform drawer (vptr C2DF80C4) in any slot -- is the waveform on?')
