#!/usr/bin/env python3
"""Unit tests of the master gates in front of inputredraw / iconcache / pagelru / alphalut / waveform.
PERF_WITHOUT=ic,pl runs them on the lean build (left-out gates must be absent).

pf_master = 0 must take the stock path exactly (iconcache: the two replaced
Thumb instructions replayed, registers, memory and flags as stock);
pf_master != 0 must enter the module.  Runs the built body in unicorn with
the reference image mapped; execution stops at the first watched address.

    python3 -B -m unittest test_perf_gates
"""
import os, pathlib, struct, sys, unittest
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R6,
                               UC_ARM_REG_R11, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC,
                               UC_ARM_REG_CPSR)

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_perf as P   # noqa: E402

BODY = 0x45400000
STACK = 0x46000000
IMG = P.IMAGE
WITHOUT = {x for x in os.environ.get('PERF_WITHOUT', '').split(',') if x}


class Gates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.info, cls.sym = P.build(set(), 1, without=WITHOUT)
        cls.body = cls.blob[P.HEADER:]

    def run_gate(self, label, master, regs, mem=()):
        mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        mu.mem_map(0xC0000000, (len(IMG) + 0xFFFF) & ~0xFFFF)
        mu.mem_write(0xC0000000, IMG)
        mu.mem_map(BODY, 0x10000)
        mu.mem_write(BODY, self.body)
        mu.mem_write(BODY + 8, struct.pack('<I', master))
        mu.mem_map(STACK - 0x10000, 0x20000)
        for a, b in mem:
            mu.mem_write(a, b)
        for r, v in regs.items():
            mu.reg_write(r, v)
        mu.reg_write(UC_ARM_REG_SP, regs.get(UC_ARM_REG_SP, STACK))
        mu.reg_write(UC_ARM_REG_LR, 0xC0000004)
        watch = {self.module_entry(label) & ~1: 'module'}
        watch.update({a: 'stock' for a in self.stock_of(label)})
        hit = {}

        def hook(uc, addr, size, _):
            if addr in watch:
                hit['where'] = watch[addr]
                hit['thumb'] = bool(uc.reg_read(UC_ARM_REG_CPSR) & 0x20)
                uc.emu_stop()
        mu.hook_add(UC_HOOK_CODE, hook)
        mu.emu_start(BODY + self.sym[label], 0, count=64)
        return mu, hit

    def module_entry(self, label):
        return BODY + self.sym[{'pf_g_ir': 'ir_enq_hook', 'pf_g_pl_load': 'pl_load',
                                'pf_g_pl_unload': 'pl_unload', 'pf_g_ic1': 'ic_h1',
                                'pf_g_ic2': 'ic_h2', 'pf_g_al': 'al_unpremul',
                                'pf_g_wf': 'wf_method'}[label]]

    def stock_of(self, label):
        return {'pf_g_ir': [0xC055E1E8], 'pf_g_pl_load': [0xC05D90F0],
                'pf_g_pl_unload': [0xC05D91A0], 'pf_g_ic1': [0xC06021A0],
                'pf_g_ic2': [0xC0602350], 'pf_g_al': [0xC0563BA8], 'pf_g_wf': [P.WF_STOCK]}[label]

    def test_simple_gates(self):
        want = [('pf_g_ir', False, 'ir'), ('pf_g_pl_load', True, 'pl'), ('pf_g_pl_unload', True, 'pl'),
                ('pf_g_al', False, 'al'), ('pf_g_wf', False, 'wf')]
        for label, thumb, k in want:
            if k in WITHOUT:
                self.assertNotIn(label, self.sym, f'{label} built although {k} left out')
                continue
            regs = {UC_ARM_REG_R0: 0x1111, UC_ARM_REG_R1: 0x2222, UC_ARM_REG_R2: 0x3333}
            mu, hit = self.run_gate(label, 0, regs)
            self.assertEqual((hit.get('where'), hit.get('thumb')), ('stock', thumb), label)
            self.assertEqual([mu.reg_read(r) for r in regs], list(regs.values()), f'{label} args')
            self.assertEqual(mu.reg_read(UC_ARM_REG_LR), 0xC0000004, f'{label} lr')
            mu, hit = self.run_gate(label, 1, regs)
            self.assertEqual(hit.get('where'), 'module', label)
            self.assertEqual([mu.reg_read(r) for r in regs], list(regs.values()), f'{label} args (on)')
            self.assertEqual(mu.reg_read(UC_ARM_REG_LR), 0xC0000004, f'{label} lr (on)')

    def test_wf_slots_point_at_gate(self):
        rows = [w for w in self.info['writes'] if w['target'] == 'pf_g_wf']
        if 'wf' in WITHOUT:
            self.assertEqual(rows, [])
            return
        self.assertEqual(sorted(int(w['addr'], 16) for w in rows), sorted(P.WF_SLOTS))
        self.assertTrue(all(w['type'] == 'data' for w in rows))

    def test_iconcache_h1_replay(self):
        if 'ic' in WITHOUT:
            self.assertNotIn('pf_g_ic1', self.sym)
            return
        obj = STACK - 0x8000
        regs = {UC_ARM_REG_R6: obj, UC_ARM_REG_R11: 0xABCD0123, UC_ARM_REG_R0: 0, UC_ARM_REG_R1: 0}
        mu, hit = self.run_gate('pf_g_ic1', 0, regs, [(obj + 0x34, struct.pack('<I', 0x5EED5EED))])
        self.assertEqual((hit.get('where'), hit.get('thumb')), ('stock', True))
        # stock: ldr r1, [r6, #0x34]; mov r0, r11
        self.assertEqual((mu.reg_read(UC_ARM_REG_R1), mu.reg_read(UC_ARM_REG_R0)), (0x5EED5EED, 0xABCD0123))
        self.assertEqual(struct.unpack_from('<HH', IMG, 0x0060219C), (0x6B71, 0x4658))
        mu, hit = self.run_gate('pf_g_ic1', 1, regs, [(obj + 0x34, struct.pack('<I', 0x5EED5EED))])
        self.assertEqual(hit.get('where'), 'module')

    def test_iconcache_h2_replay(self):
        if 'ic' in WITHOUT:
            self.assertNotIn('pf_g_ic2', self.sym)
            return
        sp = STACK - 0x200
        for r2 in (5, 0xFFFFFFFC, 0x7FFFFFFE):         # flags: Z/C, N/V cases
            regs = {UC_ARM_REG_R2: r2, UC_ARM_REG_SP: sp}
            mu, hit = self.run_gate('pf_g_ic2', 0, regs)
            self.assertEqual((hit.get('where'), hit.get('thumb')), ('stock', True))
            want = (r2 + 4) & 0xFFFFFFFF
            self.assertEqual(mu.reg_read(UC_ARM_REG_R2), want)
            self.assertEqual(struct.unpack('<I', bytes(mu.mem_read(sp + 0x90, 4)))[0], want)
            n, z = want >> 31, int(want == 0)
            c = int(r2 + 4 > 0xFFFFFFFF)
            v = int(((r2 ^ want) & (4 ^ want)) >> 31)
            nzcv = mu.reg_read(UC_ARM_REG_CPSR) >> 28
            self.assertEqual(nzcv, (n << 3) | (z << 2) | (c << 1) | v, f'flags r2={r2:#x}')
            self.assertEqual(mu.reg_read(UC_ARM_REG_SP), sp)
        self.assertEqual(struct.unpack_from('<HH', IMG, 0x0060234C), (0x3204, 0x9224))
        mu, hit = self.run_gate('pf_g_ic2', 1, {UC_ARM_REG_R2: 5, UC_ARM_REG_SP: sp})
        self.assertEqual(hit.get('where'), 'module')


class ThumbBranch(unittest.TestCase):
    """perf_core.S thumb_branch(site, veneer, blx?) encodes T2 blx / T4 b.w for
    any offset within +-16 MiB, including negative ones (S = 1), which the real
    layout (cave above the sites) never produces."""
    @classmethod
    def setUpClass(cls):
        cls.blob, cls.info, cls.sym = P.build(set(), 1)
        cls.body = cls.blob[P.HEADER:]

    def encode(self, site, ven, blx):
        mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        mu.mem_map(BODY, 0x10000)
        mu.mem_write(BODY, self.body)
        mu.mem_map(STACK - 0x10000, 0x20000)
        mu.mem_map(site & ~0xFFF, 0x2000)
        mu.mem_write(site, b'\xAA' * 4)
        mu.reg_write(UC_ARM_REG_R0, site)
        mu.reg_write(UC_ARM_REG_R1, ven)
        mu.reg_write(UC_ARM_REG_R2, int(blx))
        mu.reg_write(UC_ARM_REG_SP, STACK)
        mu.reg_write(UC_ARM_REG_LR, 0xDEAD0000)
        mu.emu_start(BODY + self.sym['thumb_branch'], 0xDEAD0000, count=200)
        h1, h2 = struct.unpack('<HH', bytes(mu.mem_read(site, 4)))
        return h1, h2

    def test_offsets_both_signs(self):
        import test_perf_loader as TL
        site0 = 0xC0602000
        for d in (8, 0x1000, 0x3FFFF0, 0x7FFFF8, 0xFFFFF0, -8, -0x1000, -0x3FFFF0, -0x7FFFF8, -0xFFFFF0):
            for blx in (True, False):
                site = site0 + (2 if blx else 0)            # blx sites may be only 2-aligned
                ven = (site0 + d) & ~7
                h1, h2 = self.encode(site, ven, blx)
                t, kind = TL.thumb_to(site, h1, h2)
                self.assertEqual((t, kind), (ven, 'blx' if blx else 'b.w'), f'd={d:#x} blx={blx}')


if __name__ == '__main__':
    unittest.main()
