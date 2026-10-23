"""Instruction counts: our dc_clean per round vs stock C000E91C (unicorn, CCSIDR as the
A7 model reports it -- the camera's L2 size is not known, see README)."""
import sys
from unicorn import UC_HOOK_CODE
from unicorn import arm_const as A
import test_dirtyclean as T

def ours(rect, fmt=1):
    g = T.Rig(fmt=fmt); g.set_drawers(0, ['uic'])
    n = [0]
    lo, hi = T.CODE, T.CODE + 0x1000
    g.mu.hook_add(UC_HOOK_CODE, lambda mu, a, s, _: n.__setitem__(0, n[0] + 1), begin=lo, end=hi)
    g.round(1, {0: {'uic': rect}})
    return n[0], g.cr(0x1C)

def stock():
    g = T.Rig(patched=False)
    mu = g.mu
    mu.hooks = None
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM
    u = Uc(UC_ARCH_ARM, UC_MODE_ARM); u.ctl_set_cpu_model(A.UC_CPU_ARM_CORTEX_A7)
    u.mem_map(0xC0000000, 0x04000000); u.mem_write(0xC0000000, T.SEG0.read_bytes())
    n = [0]; dc = [0]
    def h(mu, a, s, _):
        n[0] += 1
        w = int.from_bytes(mu.mem_read(a, 4), 'little')
        if (w & 0x0FFF0FFF) == 0x0E070F5E: dc[0] += 1      # mcr p15,0,Rt,c7,c14,2 DCCISW
    u.hook_add(UC_HOOK_CODE, h)
    u.reg_write(A.UC_ARM_REG_SP, 0xC3F00000); u.reg_write(A.UC_ARM_REG_CPSR, 0x1D3)
    u.reg_write(A.UC_ARM_REG_LR, 0xC3FFF000)
    u.emu_start(0xC000E91C, 0xC3FFF000, count=10_000_000)
    return n[0], dc[0]

if __name__ == '__main__':
    for name, rect in (('timecode FF digits', T.TC), ('seconds+frames 4 digits', (193, 600, 116, 47)),
                       ('menu row 1024x80', (0, 300, 1024, 80)), ('full layer', (0, 0, 1024, 682))):
        print(f'ours  {name:26s} insns={ours(rect)[0]:7d} lines={ours(rect)[1]:6d}  IRQs stay on')
    i, d = stock()
    print(f'stock C000E91C              insns={i:7d} set/way ops={d:6d}  IRQ+FIQ off throughout')
