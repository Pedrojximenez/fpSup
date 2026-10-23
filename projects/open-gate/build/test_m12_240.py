"""M12 preset in the real shared ARM parser, virtual tables and native rate path.

Firmware, loader, consumer and producer code execute; UI/OS are fixture boundaries.
No sensor, DMA, scheduling or media throughput is simulated.
"""
import hashlib
import json
from pathlib import Path
import struct
import unittest

import test_virtual_rcd as V
from test_reslab_preview_route import native_engine_gate, native_route
import test_reslab_record_rate as RR

RATE = RR.RATE

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT/'projects/res-lab/validation/20261011-virtual-rate-context-live'


class M12Tests(unittest.TestCase):
    boot = V.VirtualTests.boot
    rate = RR.RecordRateTests.rate

    @classmethod
    def setUpClass(cls):
        cls.out, cls.f = V.built()
        cls.blob = (cls.out/'fpSup/RESCUS/M12240.RCD').read_bytes()
        cls.row = V.RC.rcd.decode(cls.blob)
        source = EVIDENCE/'success-version-audit/historical-h2-profile-difference.json'
        assert hashlib.sha256(source.read_bytes()).hexdigest() == \
            'f7f6b7f9d339b8e537122d58e3c2d1212d5a3ee25c526fe1667d3c2f824e804a'
        reference = json.loads(source.read_text())
        cls.pairs = sorted((int(k,0),v) for k,v in reference['runtime_pairs'].items())
        profiles = json.loads(Path(reference['profiles_source']).read_text())
        cls.base = next(r['words'] for r in profiles['rows'] if 13 in r['profile_ids'])
        cls.expected = cls.base.copy()
        for offset,value in cls.pairs:
            cls.expected[offset//4] = value
        cls.expected[0x30//4] = V.L._f32(240000/1001)

    def camera(self, dynamic=False):
        record = None if dynamic else V.RC.CoreTests.record(
            self,'M12240',enable=('M12240',),vrate=23976)
        cam = self.boot(fr=7,record=record,
                        rcds={} if dynamic else {'M12240.RCD':self.blob})
        if dynamic:
            ident = cam.blob_provider(self.blob)
            self.assertEqual(cam.dispatch(2,ident),0)
            cam.put(cam.s()+V.L.S['VRATE'],23976)
        # Install the real native FrameRate body/getters exactly as the existing
        # metadata regression fixture; only the settings snapshots are modeled.
        cam.mu.mem_write(RATE+4,cam.img[RATE+4-0xC0000000:0xC00C9CF0-0xC0000000])
        cam.test_code.update(range(RATE,0xC00C9CF0,4))
        cam.rate_settings = V.RC.KEYBUF+0x3000
        cam.put(cam.rate_settings+0x14,10)
        for addr in (0xC0021C00,0xC0021C40):
            code = struct.pack('<3I',0xE59F0000,0xE12FFF1E,cam.rate_settings)
            cam.mu.mem_write(addr,code)
            cam.by_addr.pop(addr,None)
            cam.test_code.update(range(addr,addr+len(code),4))
        cam.mu.mem_write(V.RC.KEYBUF,('VRC000120' if dynamic else 'M12240120').encode().ljust(16,b'\0'))
        hit,_ = cam.call(V.RC.PICKER,r1=V.RC.TAB3,r2=V.RC.KEYBUF)
        self.assertNotEqual(hit,0)
        return cam,hit

    def canvas(self,cam,entry):
        address=V.RC.CANVAS_IN+0x5C
        cam.mu.mem_write(address,struct.pack('<65I',*self.base))
        fn=cam.w(cam.s()+V.L.S['FN']+4*V.L.FNS.index('CANVAS'))
        self.assertEqual(cam.call(fn,cam.s(),address,cam.w(entry+V.L.ENT['PID']),
                                 thumb=True,sp=V.T.STACK-0x1000)[0],1)
        return list(struct.unpack('<65I',cam.mu.mem_read(address,260)))

    def check_mode(self,cam,e):
        s=cam.s()
        self.assertEqual((cam.w(e+V.L.ENT['W0']),cam.w(e+V.L.ENT['W1'])),
                         (0x014A014A,0x0006038E))
        self.assertEqual((cam.w(e+V.L.ENT['ENGFPS']),cam.w(e+V.L.ENT['NOMINAL']),
                          cam.w(e+V.L.ENT['VRATE'])),(0x436FC29F,240,23976))
        vm=s+cam.w(s+V.L.S['VMS'])+V.L.VM['SIZE']*cam.w(e+V.L.ENT['VM'])
        self.assertEqual(cam.w(vm+V.L.VM['DONOR']),12)
        idx,_=cam.call(0xC0320BA0,r0=V.L.IMAGER,r1=cam.w(e+V.L.ENT['MODE']))
        timing=(0xC0B59500+idx*32)&0xFFFFFFFF
        self.assertEqual((cam.w(timing+4),cam.w(timing+8)),(0x014A014A,0x0006038E))
        self.assertEqual(self.canvas(cam,e),self.expected)
        self.assertEqual(self.rate(cam),(240000,1001))
        self.assertEqual(native_engine_gate(cam,V.RC.CANVAS_IN+0x5C),1)
        cfg=V.RC.KEYBUF+0x2200
        self.assertEqual((cam.w(cfg+0x68),cam.w(cfg+0x58)),(2,0))
        route=native_route(cam,{i*4:v for i,v in enumerate(self.expected)})
        self.assertEqual((route['enabled'],route['mux']),([0,1,0],[1,4]))
        # p13 owns its native writer batch. The p83 experiment must not apply.
        params=V.RC.KEYBUF+0x3300
        original=struct.pack('<4I',0x4000000,0x49000000,0x40000,0xC03A55D0)
        cam.mu.mem_write(params,original)
        fn=cam.w(s+V.L.S['FN']+4*V.L.FNS.index('BULK'))
        cam.call(fn,s,params,thumb=True,sp=V.T.STACK-0x1000)
        self.assertEqual(bytes(cam.mu.mem_read(params,16)),original)
        self.assertEqual(cam.w(s+V.L.S['BULK_HITS']),0)

    def test_data_matches_independent_archived_pairs_and_stock_timing(self):
        pairs=dict(self.row['canvas_rec'])
        pairs.update(dict(next(r for r in self.row['rate_canvas'] if r['rank']==23976)['pairs']))
        self.assertEqual(pairs,dict(self.pairs))
        self.assertEqual(self.row['profile'],13)
        self.assertEqual(self.row['bit_depths'],(12,))
        self.assertEqual(self.row['modes'],[(12,23976,330,0,6)])
        self.assertNotIn(27972,[e['rank'] for e in self.row['entries']])
        self.assertFalse(self.row.get('capture_timing'))

    def test_disk_entry_full_canvas_real_metadata_and_shutdown(self):
        cam,e=self.camera()
        self.check_mode(cam,e)
        cam.assert_tables(self)
        self.assertEqual(cam.misaligned,[])
        covered={a+i for a,n,_ in cam.journal() for i in range(n)}
        for h in cam.cf['hooks']:
            site=int(h['site'],16)
            self.assertTrue(all(site+i in covered for i in range(4)))
        cam.power_off()
        for h in cam.cf['hooks']:
            site=int(h['site'],16)
            self.assertEqual(cam.w(site),V.T.word(cam.img,site))

    def test_same_data_through_generic_virtual_service(self):
        cam,e=self.camera(dynamic=True)
        self.check_mode(cam,e)
        self.assertEqual(cam.w(cam.row()+V.L.ROW['BITMASK']),4)
        cam.assert_tables(self)
        self.assertEqual(cam.misaligned,[])


if __name__=='__main__':
    unittest.main(verbosity=2)
