"""Exact v39 ARM consumer, reduced isotropic preview and real ROM selector.

No camera, DMA or hardware timing is modeled; this only validates the scoped
data changes and the native route they request before a bounded camera trial.
"""
import hashlib
import json
import os
import pathlib
import struct
import sys
import unittest
from unittest.mock import patch

from preview_half_spec import CHANGES, EXPECTED_SHA
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CARD = ROOT/'projects/res-lab/cards/20261011-m12-engine60-v39/debug'
assert hashlib.sha256((CARD/'fpSup/32RESCUS.BIN').read_bytes()).hexdigest() == EXPECTED_SHA
os.environ['VIRTUAL_RCD_CARD'] = str(CARD)
sys.path.insert(0, str(ROOT/'projects/open-gate/build'))
import imx410_profile as P
import test_virtual_rcd as V
from test_reslab_preview_route import native_route


class PreviewHalf(unittest.TestCase):
    def test_scoped_preview_formula_and_native_route(self):
        out, facts = V.built()
        fixture = V.VirtualTests('test_contract_abi_and_status')
        fixture.out, fixture.f = out, facts
        cam = fixture.boot(fr=7)
        cam.geometry(12, 992, 662)
        self.assertEqual(cam.apply(), 0)
        state = cam.s()
        row = state+cam.w(state+V.L.S['ROWS'])+(cam.w(state+V.L.S['CUR'])-1)*V.L.ROW['SIZE']
        start = state+cam.w(row+V.L.ROW['REC'])
        before = {}
        for i in range(65):
            key = cam.w(start+i*8)
            if key == 0xffffffff:
                break
            before[key] = cam.w(start+i*8+4)
            if key in CHANGES:
                self.assertEqual(before[key], CHANGES[key][0])
                cam.put(start+i*8+4, CHANGES[key][1])
        self.assertTrue(set(CHANGES) <= set(before))
        profiles = json.loads((ROOT/'research/other/external/FP3K-technical-handoff-2026-09-10/analysis/firmware/raw-profiles.json').read_text())
        donor = next(r['words'] for r in profiles['rows'] if 83 in r['profile_ids'])
        want = P.Want((2016, 672), (1008, 672), (992, 662), (2048, 1023),
                      bits=12, hirate=True, scale=(3, 6))
        with patch.object(P, 'preview_factors', return_value=(2048, 2048)):
            declared = P.declare(want, donor)
        for key, (_, value) in CHANGES.items():
            self.assertEqual(declared[key//4], value)
        reference = None
        for rank, nominal, vmax in ((23976, 240, 910), (27972, 280, 780)):
            cam.put(state+V.L.S['VRATE'], rank)
            cam.mu.mem_write(V.RC.KEYBUF, b'VRC000120\0'.ljust(16, b'\0'))
            hit, _ = cam.call(V.RC.PICKER, r1=V.RC.TAB3, r2=V.RC.KEYBUF)
            self.assertNotEqual(hit, 0)
            entry = state+cam.w(state+V.L.S['LAST_ENT'])
            canvas = V.RC.CANVAS_IN+0x5c
            cam.mu.mem_write(canvas, struct.pack('<65I', *donor))
            fn = cam.w(state+V.L.S['FN']+V.L.FNS.index('CANVAS')*4)
            self.assertEqual(cam.call(fn, state, canvas, cam.w(hit+4), thumb=True,
                                     sp=V.T.STACK-0x1000)[0], 1)
            effective = {key: cam.w(canvas+key) for key in before}
            for key, value in before.items():
                self.assertEqual(effective[key], CHANGES[key][1] if key in CHANGES else value)
            self.assertEqual((effective[0], effective[4], effective[0x24], effective[0x2c]),
                             (1008, 672, 992, 662))
            self.assertEqual((effective[0x64], effective[0xd4], effective[0x5c], effective[0xc8]),
                             (2048, 1023, 0, 0))
            self.assertEqual(cam.w(canvas+0x30), V.L._f32(60.0))
            self.assertEqual(cam.w(entry+V.L.ENT['W0']), 330|(330<<16))
            self.assertEqual(cam.w(entry+V.L.ENT['W1']) & 0xffff, vmax)
            self.assertEqual(cam.w(entry+V.L.ENT['NOMINAL']), nominal)
            route = native_route(cam, effective)
            print('M12', rank, 'isotropic half preview; native route', route, flush=True)
            self.assertNotEqual(route['enabled'], [0, 1, 0], 'must not recreate unequal-axis matching C')
            if reference is None:
                reference = route
            else:
                self.assertEqual(route, reference)
        cam.assert_tables(self)
        self.assertEqual(cam.misaligned, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
