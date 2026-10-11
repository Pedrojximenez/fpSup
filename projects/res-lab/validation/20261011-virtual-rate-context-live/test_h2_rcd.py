"""Real current ARM loader, RCD parser, timing lookup and native ISP selector.

Fixture OS/UI services are explicit; no live sensor, DMA or storage claims.
"""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest
from unicorn.arm_const import UC_ARM_REG_R3

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT/'projects/open-gate/build'),
               str(ROOT/'projects/open-gate/build/res-custom')]
import test_virtual_rcd as V
import rcd
from test_reslab_preview_route import native_engine_gate, native_route


class H2Rcd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out,cls.f = V.built()
        cls.manifest = json.loads((HERE/'h2-success-rcd/manifest.json').read_text())
        cls.blob = (HERE/'h2-success-rcd/H2S240.RCD').read_bytes()
        assert hashlib.sha256(cls.blob).hexdigest() == cls.manifest['sha256']
        cls.row = rcd.decode(cls.blob)
        profiles = json.loads((ROOT/'research/other/external/FP3K-technical-handoff-2026-09-10/analysis/firmware/raw-profiles.json').read_text())
        cls.base = next(r['words'] for r in profiles['rows'] if 13 in r['profile_ids'])

    boot = V.VirtualTests.boot

    def camera(self,blob=None):
        record = V.RC.CoreTests.record(self,'H2S240',enable=('H2S240',))
        cam=self.boot(fr=3,record=record,rcds={'H2S240.RCD':self.blob if blob is None else blob})
        return cam

    def pick(self,cam,suffix):
        cam.mu.mem_write(V.RC.KEYBUF,('H2S240'+suffix).encode().ljust(16,b'\0'))
        entry,_ = cam.call(V.RC.PICKER,r1=V.RC.TAB3,r2=V.RC.KEYBUF)
        self.assertNotEqual(entry,0)
        return entry

    def test_archived_geometry_sensor240_native30_and_original_writer(self):
        cam=self.camera();s=cam.s()
        self.assertEqual(cam.w(s+V.L.S['RCD_OK']),1)
        self.assertEqual(cam.w(s+V.L.S['FLAG']),1)
        self.assertEqual(cam.w(s+V.L.S['VRATE']),0)
        e=self.pick(cam,'30');pid=cam.w(e+4);vid=cam.w(e+8)
        self.assertEqual(cam.w(e+V.L.ENT['W0']),330|(330<<16))
        self.assertEqual(cam.w(e+V.L.ENT['W1']),910|(6<<16))
        self.assertEqual(cam.w(e+V.L.ENT['ENGFPS']),self.manifest['expected_canvas'][12])
        self.assertEqual(cam.w(e+V.L.ENT['NOMINAL']),240)
        self.assertEqual(cam.w(e+V.L.ENT['VRATE']),0)
        idx,_=cam.call(0xc0320ba0,r0=V.L.IMAGER,r1=vid)
        tim=(0xc0b59500+idx*0x20)&0xffffffff
        self.assertEqual((cam.w(tim+4),cam.w(tim+8)),(330|(330<<16),910|(6<<16)))
        address=V.RC.CANVAS_IN+0x5c
        cam.mu.mem_write(address,struct.pack('<65I',*self.base))
        def fn(name):return cam.w(s+V.L.S['FN']+4*V.L.FNS.index(name))
        self.assertEqual(cam.call(fn('CANVAS'),s,address,pid,thumb=True,sp=V.T.STACK-0x1000)[0],1)
        got=list(struct.unpack('<65I',cam.mu.mem_read(address,260)))
        self.assertEqual(got,self.manifest['expected_canvas'])
        self.assertEqual(native_engine_gate(cam,address),1)
        cfg=V.RC.KEYBUF+0x2200
        self.assertEqual((cam.w(cfg+0x68),cam.w(cfg+0x58)),(2,0))
        route=native_route(cam,{i*4:v for i,v in enumerate(got)})
        self.assertEqual((route['enabled'],route['mux']),([0,1,0],[1,4]))
        rational=V.RC.KEYBUF+0x3100
        cam.mu.mem_write(rational,struct.pack('<2I',30000,1001))
        self.assertEqual(cam.call(fn('RECRATE'),s,rational,thumb=True,sp=V.T.STACK-0x1000)[0],0)
        self.assertEqual(bytes(cam.mu.mem_read(rational,8)),struct.pack('<2I',30000,1001))
        params=V.RC.KEYBUF+0x3200
        descriptor=struct.pack('<4I',0x4000000,0x49000000,0x40000,0xc03a55d0)
        cam.mu.mem_write(params,descriptor)
        cam.call(fn('BULK'),s,params,thumb=True,sp=V.T.STACK-0x1000)
        self.assertEqual(bytes(cam.mu.mem_read(params,16)),descriptor)
        cam.mu.reg_write(UC_ARM_REG_R3,0xc038c780)
        self.assertEqual(cam.call(fn('HDRCOPY'),r0=s,r1=params,r2=0xc3585994,
                       thumb=True,sp=V.T.STACK-0x1000)[0],0)
        for key in ('M12_LEGACY_HITS','HDR_COPY_HITS','BULK_HITS'):
            self.assertEqual(cam.w(s+V.L.S[key]),0)
        # Only the explicit30 carrier changes. Subsequent ordinary25 lookup
        # must update the already-cached donor clone to its own generated timing.
        e25=self.pick(cam,'25')
        expected=next(e for e in V.L.gen_entries('H2S240',self.row['modes'],0) if e['rank']==2500)
        self.assertEqual((cam.w(e25+V.L.ENT['W0']),cam.w(e25+V.L.ENT['W1'])),
                         (expected['w0'],expected['w1']))
        self.assertEqual((cam.w(tim+4),cam.w(tim+8)),(expected['w0'],expected['w1']))
        cam.assert_tables(self);self.assertEqual(cam.misaligned,[])
        print('H2 RCD: real parser/lookup preserves p13 full65 canvas; '
              'sensor239.76, engine239.76, native30 rational, native header/64MiB writer; '
              '25p cache retiming and ABI/table canaries verified.',flush=True)

    def test_invalid_timing_rejected_before_publication(self):
        bad=bytearray(self.blob)
        ns,so=struct.unpack_from('<2I',bad,V.L.RCD['NSEC'])
        section=next(struct.unpack_from('<4I',bad,so+16*i) for i in range(ns)
                     if struct.unpack_from('<I',bad,so+16*i)[0]==V.L.SEC_CAPTURE_TIMING)
        struct.pack_into('<I',bad,section[1]+12,331|(330<<16))
        bad=rcd.reseal(bad)
        with self.assertRaises(rcd.RcdError) as exc:rcd.decode(bad)
        self.assertEqual(exc.exception.why,'ENTRY')
        cam=self.camera(bad);s=cam.s()
        self.assertEqual(cam.w(s+V.L.S['RCD_OK']),0)
        self.assertEqual(cam.w(s+V.L.S['RCD_BAD'])&1,1)
        self.assertEqual(cam.w(s+V.L.S['RCD_WHY'])&0xffff,V.L.RCD_WHY['ENTRY'])
        labels=[cam.cstr(s+cam.w(s+V.L.S['ROWS'])+i*V.L.ROW['SIZE']+V.L.ROW['LABEL'])
                for i in range(cam.w(s+V.L.S['NROWS']))]
        self.assertNotIn('H2S240',labels)
        cam.assert_tables(self);self.assertEqual(cam.misaligned,[])

    def test_prior_v15_core_rejects_required_capture_section(self):
        prior=ROOT/'projects/res-lab/cards/20261011-virtual-header-inner/plain-sensorlab-profile-v15'
        self.out=prior
        self.f=json.loads((prior/'build.json').read_text())['facts']
        self.assertEqual(hashlib.sha256((prior/'fpSup/32RESCUS.BIN').read_bytes()).hexdigest(),
                         '51cd29c8f7eea3e6ff78f6398b82d5b0bffa2033f6afc875047c2217606a297f')
        cam=self.camera();s=cam.s()
        self.assertEqual(cam.w(s+V.L.S['RCD_OK']),0)
        self.assertEqual(cam.w(s+V.L.S['RCD_BAD'])&1,1)
        self.assertEqual(cam.w(s+V.L.S['RCD_WHY'])&0xffff,V.L.RCD_WHY['UNKNOWN'])
        cam.assert_tables(self);self.assertEqual(cam.misaligned,[])
        print('Frozen v15 rejects the required capture section before publishing H2S240.',flush=True)

    def test_python_parser_rejects_malformed_and_optional_capture_section(self):
        ns,so=struct.unpack_from('<2I',self.blob,V.L.RCD['NSEC'])
        index=next(i for i in range(ns) if struct.unpack_from('<I',self.blob,so+16*i)[0]==V.L.SEC_CAPTURE_TIMING)
        offset=struct.unpack_from('<I',self.blob,so+16*index+4)[0]
        for delta,value in ((0,0),(4,0),(8,1),(12,0),(16,1),(20,0x7fc00000),(24,0)):
            b=bytearray(self.blob);struct.pack_into('<I',b,offset+delta,value)
            with self.subTest(delta=delta),self.assertRaises(rcd.RcdError):rcd.decode(rcd.reseal(b))
        b=bytearray(self.blob);struct.pack_into('<I',b,so+16*index+12,0)
        with self.assertRaises(rcd.RcdError):rcd.decode(rcd.reseal(b))


if __name__=='__main__':unittest.main(verbosity=2)
