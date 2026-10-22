"""Exact consumer data-only four-word preview tap comparison, offline."""
import json
import os
import pathlib
import struct
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
os.environ['VIRTUAL_RCD_CARD'] = str(ROOT/'projects/res-lab/cards/20261011-m12-native30-v40/debug')
sys.path.insert(0, str(ROOT/'projects/open-gate/build'))
import test_virtual_rcd as V
from test_reslab_preview_route import native_route

CHANGES = {0x0c:(2000,1008),0x20:(1984,992),0x60:(1023,2048),0xd8:(2000,1008)}


class MatchingTap(unittest.TestCase):
    def test_four_owned_words_preserve_raw_and_select_native_matching_tap(self):
        out, facts = V.built()
        fixture = V.VirtualTests('test_contract_abi_and_status')
        fixture.out, fixture.f = out, facts
        cam = fixture.boot(fr=3)
        cam.geometry(12,992,662)
        self.assertEqual(cam.apply(),0)
        state = cam.s()
        row = state+cam.w(state+V.L.S['ROWS'])+(cam.w(state+V.L.S['CUR'])-1)*V.L.ROW['SIZE']
        start = state+cam.w(row+V.L.ROW['REC'])
        found = {}
        for n in range(65):
            key = cam.w(start+n*8)
            if key == 0xffffffff:
                break
            if key in CHANGES:
                before, after = CHANGES[key]
                self.assertEqual(cam.w(start+n*8+4),before)
                found[key]=start+n*8+4
        self.assertEqual(set(found),set(CHANGES))
        for key, addr in found.items():
            cam.put(addr,CHANGES[key][1])
        cam.put(state+V.L.S['VRATE'],27972)
        cam.mu.mem_write(V.RC.KEYBUF,b'VRC00030\0'.ljust(16,b'\0'))
        hit,_=cam.call(V.RC.PICKER,r1=V.RC.TAB3,r2=V.RC.KEYBUF)
        self.assertNotEqual(hit,0)
        profiles=json.loads((ROOT/'research/other/external/FP3K-technical-handoff-2026-09-10/analysis/firmware/raw-profiles.json').read_text())
        donor=next(r['words'] for r in profiles['rows'] if 83 in r['profile_ids'])
        canvas=V.RC.CANVAS_IN+0x5c
        cam.mu.mem_write(canvas,struct.pack('<65I',*donor))
        fn=cam.w(state+V.L.S['FN']+V.L.FNS.index('CANVAS')*4)
        self.assertEqual(cam.call(fn,state,canvas,cam.w(hit+4),thumb=True,sp=V.T.STACK-0x1000)[0],1)
        frozen=json.loads((HERE.parent/'20261009-recording-formula/frozen-r78.json').read_text())['canvas']
        effective={int(k,0):cam.w(canvas+int(k,0)) for k in frozen}
        for key, expected in frozen.items():
            off=int(key,0)
            self.assertEqual(effective[off],CHANGES[off][1] if off in CHANGES else expected)
        self.assertEqual(native_route(cam,effective)['enabled'],[0,1,0])
        self.assertEqual(native_route(cam,effective)['mux'],[1,4])
        self.assertEqual(native_route(cam,effective)['record'],0)
        entry=state+cam.w(state+V.L.S['LAST_ENT'])
        self.assertEqual(cam.w(entry+V.L.ENT['W0']),330|(330<<16))
        self.assertEqual(cam.w(entry+V.L.ENT['W1'])&0xffff,780)
        cam.assert_tables(self)
        self.assertEqual(cam.misaligned,[])


if __name__=='__main__':
    unittest.main(verbosity=2)
