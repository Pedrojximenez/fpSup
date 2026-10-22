"""Exact archived r10 profile versus current candidate's actual ARM canvas.

The historical reference was obtained by running the old binary, not by
copying candidate constants. Native translator/publication and >99 predicate
execute actual ROM; OS services are declared fixture stubs. No DMA/media proof.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0,str(ROOT/'projects/open-gate/build'))
import test_virtual_rcd as V
from test_reslab_preview_route import OFFSETS, native_engine_gate, native_route


class SensorLabCanvas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out,cls.f = V.built()
        cls.ref = json.loads((HERE/'sensorlab-r10-exact-reference.json').read_text())
        card = Path(cls.ref['card'])/'fpSup.BIN'
        assert hashlib.sha256(card.read_bytes()).hexdigest() == cls.ref['bin_sha256']
        cls.old = [cls.ref['cases'][0]['canvas'][hex(i*4)] for i in range(65)]
        cls.r78 = json.loads((HERE.parent/'20261009-recording-formula/frozen-r78.json').read_text())

    boot = V.VirtualTests.boot

    def camera(self):
        cam = self.boot(fr=7)
        cam.geometry(12,992,662)
        self.assertEqual(cam.apply(),0)
        profiles=json.loads((ROOT/'research/other/external/FP3K-technical-handoff-2026-09-10/analysis/firmware/raw-profiles.json').read_text())
        self.base=next(r['words'] for r in profiles['rows'] if 83 in r['profile_ids'])
        return cam

    def pick(self,cam,rank,token='120'):
        cam.put(cam.s()+V.L.S['VRATE'],rank)
        cam.mu.mem_write(V.RC.KEYBUF,('VRC000'+token).encode().ljust(16,b'\0'))
        hit,_=cam.call(V.RC.PICKER,r1=V.RC.TAB3,r2=V.RC.KEYBUF)
        self.assertNotEqual(hit,0)
        return cam.w(hit+4)

    def canvas(self,cam,pid):
        native=V.RC.CANVAS_IN+0x5c
        cam.mu.mem_write(native,struct.pack('<65I',*self.base))
        fn=cam.w(cam.s()+V.L.S['FN']+V.L.FNS.index('CANVAS')*4)
        result=cam.call(fn,cam.s(),native,pid,thumb=True,sp=V.T.STACK-0x1000)[0]
        self.assertEqual(result,1)
        return list(struct.unpack('<65I',cam.mu.mem_read(native,260)))

    def test_full_old_240_profile_and_280_geometry(self):
        cam=self.camera()
        for rank,nominal,vmax in ((23976,240,910),(27972,280,780)):
            pid=self.pick(cam,rank)
            got=self.canvas(cam,pid)
            want=self.old.copy()
            want[0x30//4]=struct.unpack('<I',struct.pack('<f',nominal*1000/1001))[0]
            differences=[(hex(i*4),a,b) for i,(a,b) in enumerate(zip(want,got)) if a!=b]
            self.assertEqual(differences,[],'candidate differs from actual archived r10 canvas')
            e=cam.s()+cam.w(cam.s()+V.L.S['LAST_ENT'])
            self.assertEqual(cam.w(e+V.L.ENT['W0']),330|(330<<16))
            self.assertEqual(cam.w(e+V.L.ENT['W1']),vmax|(6<<16))
            self.assertEqual(native_engine_gate(cam,V.RC.CANVAS_IN+0x5c),1)
            cfg=V.RC.KEYBUF+0x2200
            self.assertEqual((cam.w(cfg+0x68),cam.w(cfg+0x58),cam.w(cfg+0x14)),(2,4,1))
            route=native_route(cam,{i*4:v for i,v in enumerate(got)})
            self.assertEqual(route['enabled'],[0,1,0])
            self.assertEqual(route['mux'],[1,4])
            print('archived r10 full65 words reproduced',rank,'native configuration',
                  {'class':cam.w(cfg+0x68),'field58':cam.w(cfg+0x58),'flag14':cam.w(cfg+0x14)},'route',route,flush=True)
        cam.assert_tables(self)
        self.assertEqual(cam.misaligned,[])

    def test_low_rates_and_rejected_entries_keep_existing_profile(self):
        cam=self.camera()
        for rank,token,engine in ((0,'120',60.0),(0,'30',30.0)):
            cam.fr=7 if token=='120' else 3
            pid=self.pick(cam,rank,token)
            got=self.canvas(cam,pid)
            want=self.r78['row'].copy()
            for o,v in self.r78['recipe_canvas'].items():want[int(o,0)//4]=v
            want[0x30//4]=struct.unpack('<I',struct.pack('<f',engine))[0]
            if token == '120':
                # r78 evidence was captured at30p. Its >60 per-entry flag is
                # independently present in the archived native120 recipe.
                want[0xB0//4]=self.ref['cases'][1]['canvas']['0xb0']
            for off in (0x60,0x64,0xd0,0xd4):
                want[off//4]=max(1024,want[off//4]);got[off//4]=max(1024,got[off//4])
            self.assertEqual(got,want)
        cam.fr=7
        pid=self.pick(cam,23976)
        e=cam.s()+cam.w(cam.s()+V.L.S['LAST_ENT'])
        # Build the unchanged non-legacy output through the real canvas itself.
        guard=cam.s()+V.L.S['PICKOK'];cam.put(guard,0)
        before=self.canvas(cam,pid);cam.put(guard,1)
        cases=[(guard,0),(cam.s()+V.L.S['VR_UI'],0),(cam.s()+V.L.S['BITLATCH'],3),
               (e+V.L.ENT['W0'],330|(331<<16)),(e+V.L.ENT['W1'],911|(6<<16)),
               (e+V.L.ENT['PID'],pid+1)]
        for address,value in cases:
            original=cam.w(address);cam.put(address,value)
            got=self.canvas(cam,pid)
            # Depth deliberately changes only the native pixel-type fields.
            if address==cam.s()+V.L.S['BITLATCH']:
                got[0x80//4]=before[0x80//4];got[0x84//4]=before[0x84//4]
            self.assertEqual(got,before,'rejected legacy guard changed the recording profile')
            cam.put(address,original)
        cam.assert_tables(self)
        self.assertEqual(cam.misaligned,[])

    def test_current_unified_encoder_rejects_archived_recording_profile(self):
        """Demonstrate the model gap; this is not permission to bypass guards."""
        cam = self.camera()
        label = V.RC.KEYBUF + 0x1200
        cam.mu.mem_write(label, b'VRC000\0')
        current = cam.call(cam.fn('rl_encode'), cam.m(), label,
                           thumb=True, sp=V.T.STACK-0x1000)[0]
        self.assertGreater(current, 0)
        address = cam.m() + self.f['state_fields']['canvas']
        for index, offset in enumerate(OFFSETS):
            cam.put(address + index*4, self.old[offset//4])
        archived = cam.call(cam.fn('rl_encode'), cam.m(), label,
                            thumb=True, sp=V.T.STACK-0x1000)[0]
        self.assertEqual(archived, 0)
        print('Actual current encoder accepts its calculated M12 canvas but '
              'rejects the independently archived r10 recording canvas. '
              'The exporter is not a general model of all native paths.', flush=True)
        cam.assert_tables(self)
        self.assertEqual(cam.misaligned, [])


if __name__=='__main__':unittest.main(verbosity=2)
