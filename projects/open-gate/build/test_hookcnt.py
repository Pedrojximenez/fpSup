"""OGC_HOOKCNT diagnostic build: hooks enter through counting stubs; counters at S - 0x100."""
import unittest
import test_virtual_rcd as V
import ogc_layout as L

class HookCount(unittest.TestCase):
    def test_counters_move_and_hooks_still_work(self):
        self.assertTrue(L.HOOKCNT)
        out, f = V.built(); t = V.VirtualTests('test_contract_abi_and_status'); t.out, t.f = out, f
        cam = t.boot(); cam.geometry(); self.assertEqual(cam.apply(), 0)
        base = cam.s() - L.HOOKCNT_BACK
        counts = {n: cam.w(base + 4*i) for i, (n, _, _) in enumerate(L.HOOKS)}
        print({n: c for n, c in counts.items() if c})
        self.assertGreater(sum(counts.values()), 0)

    def test_stub_preserves_every_register(self):
        from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_SP, UC_ARM_REG_LR,
                                       UC_ARM_REG_PC, UC_ARM_REG_CPSR)
        out, f = V.built(); t = V.VirtualTests('test_contract_abi_and_status'); t.out, t.f = out, f
        import json
        facts = json.loads((out/'build.json').read_text())['facts']
        rc = facts.get('rescustom', facts)
        cam = t.boot(); mu = cam.mu
        origin = cam.s() - L.SHIMS_MAX
        regs = [UC_ARM_REG_R0 + i for i in range(13)]
        for i, (n, _, _) in enumerate(L.HOOKS):
            stub, target = origin + rc['shims'][n + '_cnt'], origin + rc['shims'][n]
            before_cnt = cam.w(cam.s() - L.HOOKCNT_BACK + 4 * i)
            vals = [0x11110000 + 0x111 * k for k in range(13)]
            for r, v in zip(regs, vals): mu.reg_write(r, v)
            sp0 = mu.reg_read(UC_ARM_REG_SP); mu.reg_write(UC_ARM_REG_LR, 0xC0DE0001)
            cpsr0 = (mu.reg_read(UC_ARM_REG_CPSR) & ~0xF0000020) | 0xA0000000   # ARM state, N and C set
            mu.reg_write(UC_ARM_REG_CPSR, cpsr0)
            mu.emu_start(stub, target, count=64)
            with self.subTest(hook=n):
                self.assertEqual(mu.reg_read(UC_ARM_REG_PC), target)
                self.assertEqual([mu.reg_read(r) for r in regs], vals)
                self.assertEqual(mu.reg_read(UC_ARM_REG_SP), sp0)
                self.assertEqual(mu.reg_read(UC_ARM_REG_LR), 0xC0DE0001)
                self.assertEqual(mu.reg_read(UC_ARM_REG_CPSR) & 0xF0000020, 0xA0000000)
                self.assertEqual(cam.w(cam.s() - L.HOOKCNT_BACK + 4 * i), before_cnt + 1)

if __name__ == '__main__':
    unittest.main()
