"""Live minimal check of the Fill DMA driver C00DB188 (README §6 steps 1-3).

Not recording. One driver call on a 1 KiB test buffer, then read back.
Buffer is 0x500 B from cave.claim (the arena is too small for README's 0x20000).
Cache: clean+invalidate (C000EA54) before, invalidate (C000EB28) after.
"""
import sys, struct
sys.path.insert(0, '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
from putfile import sh, put, mem_get
from callfn import call
import cave

assert sh('status get is_recording', retries=0).strip() == 'is_recording -> 0'

# step 1: runtime checks
w = mem_get(0xC31D25B4)[0], mem_get(0xC301FEC4)[0], mem_get(0xC301FEC0)[0]
print('init flag / sems', [hex(x) for x in w])
assert w[0] == 1 and w[1] and w[2], 'driver not initialised; stop'

# tool check: harmless getter
print('getter', call(0xC0407E20))

raw = cave.claim('filldma.test', 0x500)
B = (raw + 63) & ~63
assert B + 0x480 <= raw + 0x500
D = cave.claim('filldma.desc', 0x40)
print('B', hex(B), 'D', hex(D))

put(B, b'\x5a' * 0x480, 'testbuf')
desc = bytearray(0x28)
struct.pack_into('<7I', desc, 0x0C, (B - 0xC0000000) >> 2, 0, 0x100, 1, 0x100, 0x11223344, 0x11223344)
put(D, bytes(desc), 'desc')

print('clean+inv', call(0xC000EA54, r0=B, r1=B + 0x47F))
ok, rv = call(0xC00DB188 | 1, r0=D)
print('driver returned', ok, hex(rv) if rv is not None else rv)
print('inv', call(0xC000EB28, r0=B, r1=B + 0x47F))

got = mem_get(B, 0x480 // 4)
assert None not in got, 'missing words, re-read'
fill = got[:0x100]
tail = got[0x100:]
print('fill words != 0x11223344:', sum(1 for x in fill if x != 0x11223344),
      ' first', hex(fill[0]), ' last', hex(fill[-1]))
print('guard words != 0x5A5A5A5A:', sum(1 for x in tail if x != 0x5A5A5A5A))
