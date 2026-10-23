"""Read-only probe of DrawController slots, layers, non-UIC drawers, uicMgr records.

    python3 -B live_probe.py            # CINE standby, not recording

Only callfn(C05278F8) (a getter; its static is already constructed) and mem_get.
Offsets (static, see README §5):
  C05278F8() -> holder H (= 0xC3782FC8 live); DrawController = [H+4] (C0527D88: ldr r0,[r4,#4]).
  DrawController (C05281B0 init): +0x00 drawers[4][3]; +0x34 event flag; +0x38 clear[4];
     +0x48 drawer count[4]; +0x58 layer[4] (8 B each, +5 = flag byte read by C0528700); +0x78 lock.
  layer: [+0] vptr, +0x1C fmt, +0x3C/40/44 descs, +0x48 front desc, +0x4C back desc;
     desc +4 base, desc +8 -> {w, h}.
  uicMgr 0xC37B7034 +0x18: 10 records x 0x20: +4 base, +8 x, +12 y, +16 w, +20 h.
"""
import sys
sys.path.insert(0, '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
from putfile import sh, mem_get
from callfn import call

UIC_VT = {0xC0D17780: 'UIC', 0xC2E45DF8: 'UIC2'}
FMT = {0: '32bpp', 1: '16bpp', 2: '4bpp', 3: '8bpp'}


def ok_addr(a):
    return 0xC0000000 <= a < 0xC8000000 and a % 4 == 0


def rd(a, n=1):
    for _ in range(4):
        v = mem_get(a, n)
        if v and len(v) == n and None not in v:
            return v
    raise RuntimeError(f'read {a:#x}+{n} kept returning None')


def word(a):
    return rd(a)[0]


def hexs(ws):
    return ' '.join(f'{w:08x}' for w in ws)


assert sh('status get is_recording', retries=0).strip() == 'is_recording -> 0', 'recording: stop'
okc, H = call(0xC05278F8, verbose=False)
print(f'C05278F8 -> {H:#x}' if okc else 'callfn failed'); assert okc and ok_addr(H)
ctrl = word(H + 4)
print(f'DrawController = [H+4] = {ctrl:#x}')
if not ok_addr(ctrl):
    sys.exit('DrawController address not plausible; stop')

d = rd(ctrl, 0x80 // 4)
print('ctrl +00..7F:', hexs(d))
counts = d[0x48 // 4:0x48 // 4 + 4]
clears = d[0x38 // 4:0x38 // 4 + 4]
print('drawer counts', counts, ' pending clear', clears)

nonuic = []
for s in range(4):
    drs = d[3 * s:3 * s + 3]
    L = d[(0x58 + 8 * s) // 4]
    flag = d[(0x5C + 8 * s) // 4]
    print(f'\nslot {s}: layer {L:#x}  word+4 {flag:#x}')
    for i, o in enumerate(drs):
        if not o:
            continue
        if not ok_addr(o):
            print(f'  drawer{i} {o:#x} (not a RAM address, skipped)'); continue
        vp = word(o)
        kind = UIC_VT.get(vp, 'other')
        line = f'  drawer{i} {o:#x} vptr {vp:#x} [{kind}]'
        if ok_addr(vp):
            v = rd(vp, 8)
            line += f'  vt+0xC {v[3]:#x}  vt+0x1C {v[7]:#x}'
        print(line)
        if kind == 'other':
            nonuic.append((s, o))
    if ok_addr(L):
        lv = rd(L, 0x54 // 4)
        print(f'  layer vptr {lv[0]:#x} fmt {lv[0x1C // 4]} ({FMT.get(lv[0x1C // 4], "?")})')
        front, back = lv[0x48 // 4], lv[0x4C // 4]
        for nm, ds in [('desc0', lv[0x3C // 4]), ('desc1', lv[0x40 // 4]), ('desc2', lv[0x44 // 4])]:
            if ok_addr(ds):
                dd = rd(ds, 3)
                wh = rd(dd[2], 2) if ok_addr(dd[2]) else (None, None)
                tag = (' FRONT' if ds == front else '') + (' BACK' if ds == back else '')
                print(f'  {nm} {ds:#x} base {dd[1]:#x} wh {wh}{tag}')
            else:
                print(f'  {nm} {ds:#x} (skipped)')

for s, o in nonuic:
    print(f'\nnon-UIC drawer slot {s} {o:#x}: +00..+3F', hexs(rd(o, 16)))
    f = rd(o + 0x1C, 4)
    print(f'  +0x1C..+0x28 (x y w h if this is the waveform object): {f}')

print('\nuicMgr 0xC37B7034+0x18 records:')
recs = rd(0xC37B7034 + 0x18, 10 * 8)
for i in range(10):
    r = recs[8 * i:8 * i + 8]
    x, y, w, h = [v - (1 << 32) if v & 0x80000000 else v for v in r[2:6]]
    print(f'  [{i}] raw {hexs(r)}  base {r[1]:#x}  rect x={x} y={y} w={w} h={h}')
