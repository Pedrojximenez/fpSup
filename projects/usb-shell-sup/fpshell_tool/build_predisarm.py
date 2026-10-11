#!/usr/bin/env python3
"""Assemble camera/predisarm_hook.S (Thumb-2), place at CAVE, compute the B.W patch
at FUN_c01e62a8, and emit the AutoRun mem-set lines that install it.

  python3 build_predisarm.py    # prints the install block
"""
import sys, subprocess, tempfile, pathlib, struct
sys.path.insert(0, '/Users/dido/Developer.localized/SIGMAfp_re/codex')
from build_stage5_autorun import extract_and_relocate
HERE = pathlib.Path('/Users/dido/Developer.localized/SIGMAfp_re/codex/fpshell_tool')
CAVE = 0xC0727380          # stub load addr (free rodata cave, past builder stub @..2F8)
SITE = 0xC01E62A8          # FUN_c01e62a8 entry (Thumb PUSH.W e92d4df0)
ORIG = 0xE92D4DF0          # displaced instruction (for a sanity note)

def assemble():
    with tempfile.TemporaryDirectory() as d:
        obj = pathlib.Path(d)/'p.o'
        r = subprocess.run(['clang','-target','thumbv7-none-eabi','-mthumb','-c',
                            str(HERE/'camera/predisarm_hook.S'),'-o',str(obj)],
                           capture_output=True, text=True)
        if r.returncode: sys.stderr.write(r.stderr); sys.exit(1)
        return extract_and_relocate(obj)

def bw_encode(site, target):
    """Thumb-2 B.W (T4) at `site` branching to `target`. Returns 32-bit LE word."""
    off = target - (site + 4)
    assert -(1<<24) <= off < (1<<24), "B.W out of range"
    u = off & 0xFFFFFFFF
    S  = (u >> 24) & 1
    I1 = (u >> 23) & 1
    I2 = (u >> 22) & 1
    imm10 = (u >> 12) & 0x3FF
    imm11 = (u >> 1)  & 0x7FF
    J1 = (I1 ^ 1) ^ S    # J1 = NOT(I1) XOR S
    J2 = (I2 ^ 1) ^ S
    hw1 = 0xF000 | (S << 10) | imm10
    hw2 = 0x9000 | (J1 << 13) | (J2 << 11) | imm11
    return hw1 | (hw2 << 16)

def main():
    code = assemble()
    # sanity: the displaced Thumb PUSH.W (e92d 4df0 -> bytes 2d e9 f0 4d) must be present
    assert bytes([0x2d,0xe9,0xf0,0x4d]) in code, "stub missing displaced PUSH.W (encoding check!)"
    if len(code) % 4: code += b'\x00' * (4 - len(code)%4)   # pad to word
    words = list(struct.unpack('<%dI' % (len(code)//4), code))
    patch = bw_encode(SITE, CAVE)
    end = CAVE + len(code)
    print(f"# pre-disarm hook: stub {len(words)}w @0x{CAVE:08X}..0x{end:08X}")
    print(f"# install: FUN_c01e62a8 PUSH.W -> B.W 0x{CAVE:08X}; fires EndTransfer(4/5) on param_1==0")
    for i, w in enumerate(words):
        print(f"mem set 0x{CAVE+i*4:08X} 0x{w:08X}")
    print(f"# patch site 0x{SITE:08X}: e92d4df0 (PUSH.W) -> B.W 0x{CAVE:08X}")
    print(f"mem set 0x{SITE:08X} 0x{patch:08X}")

if __name__ == '__main__':
    main()
