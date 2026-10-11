"""Exact diagnostic BIN, real ARM consumer/producer and native ISP gate.

OS/menu-setter bodies are fixture boundaries; this does not emulate DMA or
establish the real sensor cadence, recording picture or clean hardware stop.
"""
import json
import os
import pathlib
import struct
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BUILD = ROOT / 'projects/open-gate/build'
os.environ.setdefault('VIRTUAL_RCD_CARD', str(ROOT / 'projects/res-lab/cards/20261011-m12-native30-v40/debug'))
sys.path[:0] = [str(BUILD), str(BUILD / 'res-custom')]
import test_virtual_rcd as V
from test_reslab_preview_route import OFFSETS, native_engine_gate
from unicorn.arm_const import UC_ARM_REG_R3


class Native30Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out, cls.f = V.built()

    def test_high_rate_carrier_preserves_timing_and_geometry(self):
        fixture = V.VirtualTests('test_contract_abi_and_status')
        fixture.out, fixture.f = self.out, self.f
        cam = fixture.boot(fr=3)
        cam.geometry(12, 992, 662)
        self.assertEqual(cam.apply(), 0)
        state = cam.s()
        frozen = json.loads((HERE.parent / '20261009-recording-formula/frozen-r78.json').read_text())['canvas']
        values = struct.unpack('<29I', cam.mu.mem_read(cam.m() + self.f['state_fields']['canvas'], 116))
        self.assertEqual(dict(zip(map(hex, OFFSETS), values)), frozen)
        profiles = json.loads((ROOT / 'research/other/external/FP3K-technical-handoff-2026-09-10/analysis/firmware/raw-profiles.json').read_text())
        donor = next(row['words'] for row in profiles['rows'] if 83 in row['profile_ids'])
        # Restore only the modeled callback continuation. The hook and replay
        # prologue still execute from the actual consumer artifact.
        cam.test_code.update((0xC057A6FC, 0xC05821BC))
        reference = None
        for menu_row, rank, nominal, vmax in ((9, 23976, 240, 910), (10, 27972, 280, 780)):
            with self.subTest(rank=rank):
                var = V.RC.KEYBUF + 0x900
                cam.put(var + 8, menu_row)
                cam.call(0xC057A6F8, r0=var)
                self.assertEqual(cam.w(state + V.L.S['VRATE']), rank)
                pairs = state + V.L.S['RPAIRS']
                self.assertEqual((cam.w(pairs), cam.w(pairs + 4)), (3, menu_row), 'menu must commit native 29.97 carrier')
                cam.mu.mem_write(V.RC.KEYBUF, b'VRC00030\0'.ljust(16, b'\0'))
                hit, _ = cam.call(V.RC.PICKER, r1=V.RC.TAB3, r2=V.RC.KEYBUF)
                self.assertNotEqual(hit, 0)
                entry = state + cam.w(state + V.L.S['LAST_ENT'])
                self.assertEqual(cam.w(entry + V.L.ENT['VRATE']), rank)
                self.assertEqual(cam.w(entry + V.L.ENT['NOMINAL']), nominal)
                self.assertEqual(cam.w(entry + V.L.ENT['W0']), 330 | (330 << 16))
                self.assertEqual(cam.w(entry + V.L.ENT['W1']) & 0xffff, vmax)
                canvas = V.RC.CANVAS_IN + 0x5c
                cam.mu.mem_write(canvas, struct.pack('<65I', *donor))
                fn = cam.w(state + V.L.S['FN'] + V.L.FNS.index('CANVAS') * 4)
                self.assertEqual(cam.call(fn, state, canvas, cam.w(hit + 4), thumb=True, sp=V.T.STACK - 0x1000)[0], 1)
                self.assertEqual(native_engine_gate(cam, canvas), 0)
                self.assertEqual(cam.w(canvas + 0x30), V.L._f32(60.0))
                for offset, expected in frozen.items():
                    self.assertEqual(cam.w(canvas + int(offset, 0)), expected)
                data = bytes(cam.mu.mem_read(canvas, 260))
                if reference is None:
                    reference = data
                else:
                    self.assertEqual(data, reference)
                vtv = cam.w(state + V.L.S['FN'] + V.L.FNS.index('VTV') * 4)
                # Camera.call's fifth positional argument is LR, not r3.
                cam.mu.reg_write(UC_ARM_REG_R3, 3)
                self.assertEqual(cam.call(vtv, state, 0, 0, thumb=True, sp=V.T.STACK - 0x1000)[0], nominal)
        cam.put(var + 8, 3)
        cam.call(0xC05821B8, r0=var)
        self.assertEqual(cam.w(state + V.L.S['VRATE']), 0)
        self.assertEqual(cam.w(state + V.L.S['VR_COMMITS']), 3)
        self.assertEqual(cam.misaligned, [])
        cam.assert_tables(self)


if __name__ == '__main__':
    suite = unittest.TestSuite()
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(Native30Tests))
    for name in ('test_contract_abi_and_status', 'test_apply_without_file_and_live_canvas',
                 'test_invalid_geometry_raw14_rate_and_format'):
        suite.addTest(V.VirtualTests(name))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
