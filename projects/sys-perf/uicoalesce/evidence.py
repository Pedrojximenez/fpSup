"""Static evidence (no camera): the UI queue already coalesces same-name
variable sets per draw cycle, and timecode digits use span idx 7.
Run: python3 -B evidence.py   (asserts; prints the checked facts)
"""
import struct, capstone
R = '/Users/dido/Developer.localized/SIGMAfp_re/out/'
rom = open(R + 'seg0_c0000000.bin', 'rb').read()
s1 = open(R + 'seg1_c2ef6e00.bin', 'rb').read()
B = 0xC0000000
arm = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
def ins(a, n=1):
    return [f'{i.mnemonic} {i.op_str}' for i in arm.disasm(rom[a - B:a - B + 4 * n], a)]
def w(a):
    if a >= 0xC2EF6E00: return struct.unpack_from('<I', s1, a - 0xC2EF6E00)[0]
    return struct.unpack_from('<I', rom, a - B)[0]
def bl_target(a):
    v = w(a); imm = v & 0xFFFFFF
    if imm & 0x800000: imm -= 1 << 24
    return a + 8 + imm * 4

facts = [
    # consumer: message type 2 (variable set) -> C0563F40 (pending table)
    ('type-2 case calls C0563F40', bl_target(0xC055E600) == 0xC0563F40),
    # C0563F40 looks up existing entry by name (C0564068) and overwrites in place
    ('lookup by name', bl_target(0xC0563F58) == 0xC0564068),
    ('overwrite slot, count++ only when new', ins(0xC0563FC0) == ['cmp r5, r3']),
    ('flush at 64 distinct names', ins(0xC0563FD8) == ['cmp r3, #0x40']),
    # end of batch: flush once -> C055F8F0 -> C05DC778 (one tree walk per flush)
    ('batch end flushes once', bl_target(0xC055E7D0) == 0xC0563FF0),
    ('flush applies via C055F8F0', bl_target(0xC0564014) == 0xC055F8F0),
    # batch = whole queue, processed from the per-cycle Gui update C0561198
    ('Gui update processes queue', bl_target(0xC0561260) == 0xC0560868),
    # timecode digits: span table 1 idx 7 (ARGB4444 src) is C06FBCD9, not replaced by neonblit
    ('table1 idx7 = C06FBCD9', w(0xC2EB3F78) == 0xC06FBCD9),
    ('table1 idx3 = C06FBC09 (lut8 blend, neonblit covers)', w(0xC2EB3F68) == 0xC06FBC09),
]
for name, ok in facts:
    print(('OK  ' if ok else 'FAIL') + '  ' + name)
assert all(ok for _, ok in facts)
