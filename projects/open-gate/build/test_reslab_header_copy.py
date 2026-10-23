"""Run the exact inner hook, native caller and ROM CPU copy in Unicorn.

DMA fallback completion is modeled. This proves bytes, ABI, ownership guards
and journal restoration; it cannot establish camera DMA timing/coherency.
"""
import json
import pathlib
import struct
import unittest

import test_virtual_rcd as V
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *

SITE, RESUME, CALL, RETURN = 0xC00FBB90, 0xC00FBB94, 0xC038C77C, 0xC038C780
BULK, CONFIG, CONFIG_RETURN = 0xC03A5144, 0xC0366790, 0xC03A5148
SRC, DST, FRAME, PARAM = 0x49000040, 0x49022040, 0xC3585994, 0x49046000
CACHED = 0xC9000040
SAVED = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
         UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)


class HeaderCopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out, cls.f = V.built()

    boot = V.VirtualTests.boot

    def camera(self):
        cam = self.boot(fr=7)
        cam.geometry(12, 992, 662)
        self.assertEqual(cam.apply(), 0)
        cam.put(cam.s()+V.L.S['VRATE'], 27972)
        cam.mu.mem_write(V.RC.KEYBUF, b'VRC000120\0'.ljust(16, b'\0'))
        self.assertNotEqual(cam.call(V.RC.PICKER, r1=V.RC.TAB3, r2=V.RC.KEYBUF)[0], 0)
        cam.mu.mem_map(0x49000000, 0x50000)
        cam.mu.mem_map(0xC9000000, 0x50000)
        # Real native objects are static BSS, separate from MEM1 image bytes.
        cam.put(0xC351FF48 + 93*4, FRAME)
        # Execute the real ARM CPU-copy implementation, including its tails.
        cam.mu.mem_write(0xC00FBD60, cam.img[0xFBD60:0xFBF58])
        cam.test_code.update(range(0xC00FBD60, 0xC00FBF58, 4))
        # Fallback gets the replayed native push, then modeled completion.
        cam.mu.mem_write(RESUME, struct.pack('<3H', 0x2042, 0xE8BD, 0x8130))
        cam.test_code.update((RESUME, RESUME+2, CALL, RETURN))
        cam.test_code.add(V.T.DONE)
        return cam

    def copy(self, cam, n=0x13400, source=SRC, dest=DST, flags=0,
             owner=None, frame_n=None, frame_end=None, foreign=False,
             member=True):
        params = struct.pack('<4I', source, dest, n, flags)
        cam.mu.mem_write(PARAM, params)
        cam.put(0xC358DBA8, source if owner is None else owner)
        cam.put(0xC358DBA4, n)
        cam.put(FRAME+0x14C, n if frame_n is None else frame_n)
        cam.put(FRAME+0x4C, dest+n if frame_end is None else frame_end)
        cam.put(0xC351FF48 + 93*4, FRAME if member else 0)
        seeds = [0x76540000+i for i in range(8)]
        seeds[1] = FRAME
        for r, v in zip(SAVED, seeds):
            cam.mu.reg_write(r, v)
        seen = []
        def observe(mu, address, size, data):
            if address == RETURN:
                mu.emu_stop()
            if address == RESUME:
                seen.append(bytes(mu.mem_read(mu.reg_read(UC_ARM_REG_R0), 16)))
            if address in (0xC0057AE8, 0xC005C0F0):
                raise AssertionError('interactive settings entered')
        hook = cam.mu.hook_add(UC_HOOK_CODE, observe)
        try:
            if foreign:
                result = cam.call(SITE, r0=PARAM, thumb=True, sp=V.T.STACK-0x1000)[0]
            else:
                result = cam.call(CALL, r0=PARAM, sp=V.T.STACK-0x1000)[0]
        finally:
            cam.mu.hook_del(hook)
        self.assertEqual([cam.r(r) for r in SAVED], seeds)
        self.assertEqual(cam.r(UC_ARM_REG_SP), V.T.STACK-0x1000)
        self.assertEqual(bytes(cam.mu.mem_read(PARAM, 16)), params)
        self.assertEqual(cam.misaligned, [])
        return result, seen

    def test_exact_bytes_uncached_and_original_cached_source(self):
        cam = self.camera()
        for rank, n, source in ((27972, 4, SRC), (27972, 0x13400, SRC),
                                (27972, 0x20000, CACHED)):
            cam.put(cam.s()+V.L.S['VRATE'], rank)
            e = cam.s()+cam.w(cam.s()+V.L.S['LAST_ENT'])
            cam.put(e+V.L.ENT['VRATE'], rank)
            cam.put(e+V.L.ENT['ENGFPS'], 0x438BDC32)
            payload = bytes((i*17+3)&255 for i in range(n))
            cam.mu.mem_write(source, payload)
            cam.mu.mem_write(DST-4, b'\xa5'*(n+8))
            before = cam.w(cam.s()+V.L.S['HDR_COPY_HITS'])
            self.assertEqual(self.copy(cam, n=n, source=source), (0, []))
            self.assertEqual(bytes(cam.mu.mem_read(DST, n)), payload)
            self.assertEqual(bytes(cam.mu.mem_read(DST-4, 4)), b'\xa5'*4)
            self.assertEqual(bytes(cam.mu.mem_read(DST+n, 4)), b'\xa5'*4)
            self.assertEqual(cam.w(cam.s()+V.L.S['HDR_COPY_HITS']), before+1)
        cam.assert_tables(self)

    def test_native_owner_frame_ranges_flags_and_alias_overlap(self):
        cam = self.camera()
        for kw in ({'n':0}, {'n':0x20004}, {'n':7}, {'flags':1},
                   {'owner':SRC+4}, {'frame_n':0x100}, {'frame_end':DST},
                   {'member':False},
                   {'dest':SRC+4}, {'source':CACHED, 'dest':SRC},
                   {'dest':0xC9022040}, {'dest':0x5FFFFFFC},
                   {'source':0x44000040}, {'source':0xDFFFFFFC}):
            with self.subTest(guard=kw):
                result, seen = self.copy(cam, **kw)
                self.assertEqual(result, 0x42)
                self.assertEqual(seen, [struct.pack('<4I',
                    kw.get('source',SRC), kw.get('dest',DST),
                    kw.get('n',0x13400), kw.get('flags',0))])

    def test_inactive_rate_recipe_bit_and_foreign_call_fall_back(self):
        cam = self.camera()
        for key, value in (('VRATE',0), ('PICKOK',0), ('FLAG',0),
                           ('LAST_ENT',0), ('BITLATCH',4)):
            a = cam.s()+V.L.S[key]; old = cam.w(a); cam.put(a,value)
            with self.subTest(state=key):
                self.assertEqual(self.copy(cam)[0], 0x42)
            cam.put(a,old)
        # The policy is the RCD's (SEC_WRITER), not the geometry's: an entry
        # that does not declare it keeps the native DMA header.
        e = cam.s()+cam.w(cam.s()+V.L.S['LAST_ENT']); old = cam.w(e+V.L.ENT['WFLAGS'])
        self.assertEqual(old, V.L.WR_BATCH4M | V.L.WR_HDRCPU | 4 << 8)
        cam.put(e+V.L.ENT['WFLAGS'], old & ~V.L.WR_HDRCPU)
        self.assertEqual(self.copy(cam)[0], 0x42)
        cam.put(e+V.L.ENT['WFLAGS'], old)
        self.assertEqual(self.copy(cam, foreign=True)[0], 0x42)
        cam.assert_tables(self)

    def test_outer_gyro_site_untouched_and_inner_shutdown_journal(self):
        cam = self.camera()
        self.assertEqual(cam.w(CALL), V.T.word(cam.img, CALL))
        covered = {a+i for a,n,_ in cam.journal() for i in range(n)}
        self.assertTrue(all(SITE+i in covered for i in range(4)))
        self.assertTrue(all(BULK+i in covered for i in range(4)))
        self.assertFalse(any(CALL+i in covered for i in range(4)))
        self.assertNotEqual(cam.w(SITE), V.T.word(cam.img,SITE))
        cam.power_off()
        self.assertEqual(cam.w(SITE), V.T.word(cam.img,SITE))
        self.assertEqual(cam.w(BULK), V.T.word(cam.img,BULK))

    def test_local_bulk_descriptor_before_native_configuration(self):
        cam = self.camera()
        cam.mu.mem_write(CONFIG, struct.pack('<2I',0xE3A00055,0xE12FFF1E))
        cam.test_code.update((BULK,CONFIG,CONFIG+4,CONFIG_RETURN))
        source = [0x4000000, 0x49048000, 0x40000, 0xC03A55D0]
        def run(words, expected):
            cam.mu.mem_write(PARAM,struct.pack('<4I',*words))
            seen = []
            seeds = [0x76540000+i for i in range(8)]
            for r,v in zip(SAVED,seeds): cam.mu.reg_write(r,v)
            def observe(mu,address,size,data):
                if address == CONFIG:
                    self.assertEqual(mu.reg_read(UC_ARM_REG_R0),FRAME)
                    self.assertEqual(mu.reg_read(UC_ARM_REG_R1),PARAM)
                    seen.append(list(struct.unpack('<4I',mu.mem_read(PARAM,16))))
                if address == CONFIG_RETURN: mu.emu_stop()
            hook=cam.mu.hook_add(UC_HOOK_CODE,observe)
            try: result=cam.call(BULK,r0=FRAME,r1=PARAM,sp=V.T.STACK-0x1000)[0]
            finally: cam.mu.hook_del(hook)
            self.assertEqual(result,0x55)
            self.assertEqual(seen,[[expected,*words[1:]]])
            self.assertEqual([cam.r(r) for r in SAVED],seeds)
            self.assertEqual(cam.r(UC_ARM_REG_SP),V.T.STACK-0x1000)
            self.assertEqual(cam.misaligned,[])
        e = cam.s()+cam.w(cam.s()+V.L.S['LAST_ENT'])
        cam.put(e+V.L.ENT['ENGFPS'], 0x436FC29F)   # 239.76p: native 64 MiB
        run(source,source[0])
        cam.put(e+V.L.ENT['ENGFPS'], 0x438BDC32)
        run(source,0x400000)
        for words in ([0x100000,*source[1:]], [source[0],0,*source[2:]],
                       [*source[:2],0x80000,source[3]], [*source[:3],0xDEADBEEF]):
            run(words,words[0])
        cam.put(cam.s()+V.L.S['VRATE'],0)
        run(source,source[0])
        cam.put(cam.s()+V.L.S['VRATE'],27972)
        cam.put(BULK,V.T.word(cam.img,BULK))
        cam.mu.ctl_remove_cache(BULK,BULK+4)
        with self.assertRaises(AssertionError): run(source,0x400000)
        run(source,source[0])
        self.assertEqual(bytes(cam.mu.mem_read(0xC0B9E5D8,16)),
                         cam.img[0xB9E5D8:0xB9E5E8])

    def test_missing_hook_mutation_is_detected(self):
        cam = self.camera()
        cam.put(SITE, V.T.word(cam.img,SITE))
        cam.mu.ctl_remove_cache(SITE,SITE+4)
        with self.assertRaises(AssertionError):
            self.assertEqual(self.copy(cam)[0], 0)
        self.assertEqual(self.copy(cam)[0], 0x42)


class CaptureCarrierHeaderTests(unittest.TestCase):
    """Same archived H2 canvas/carrier; only the header-copy path changes."""
    boot = V.VirtualTests.boot
    copy = HeaderCopyTests.copy

    @classmethod
    def setUpClass(cls):
        cls.out, cls.f = V.built()
        evidence = pathlib.Path(__file__).resolve().parents[2] / 'res-lab/validation/20261011-virtual-rate-context-live'
        cls.blob = (evidence/'h2-success-rcd/H2S240.RCD').read_bytes()
        cls.manifest = json.loads((evidence/'h2-success-rcd/manifest.json').read_text())

    def camera(self):
        record = V.RC.CoreTests.record(self, 'H2S240', enable=('H2S240',))
        cam = self.boot(fr=3, record=record, rcds={'H2S240.RCD':self.blob})
        cam.mu.mem_write(V.RC.KEYBUF, b'H2S24030\0'.ljust(16, b'\0'))
        entry, _ = cam.call(V.RC.PICKER, r1=V.RC.TAB3, r2=V.RC.KEYBUF)
        self.assertNotEqual(entry, 0)
        cam.mu.mem_map(0x49000000, 0x50000)
        cam.put(0xC351FF48 + 93*4, FRAME)
        cam.mu.mem_write(0xC00FBD60, cam.img[0xFBD60:0xFBF58])
        cam.test_code.update(range(0xC00FBD60, 0xC00FBF58, 4))
        cam.mu.mem_write(RESUME, struct.pack('<3H', 0x2042, 0xE8BD, 0x8130))
        cam.test_code.update((RESUME, RESUME+2, CALL, RETURN, V.T.DONE))
        return cam, entry

    def test_native30_capture240_exact_header_and_h2_canvas(self):
        cam, entry = self.camera()
        s = cam.s()
        self.assertEqual(cam.w(s+V.L.S['VRATE']), 0)
        payload = bytes((i*17+3)&255 for i in range(0x13400))
        cam.mu.mem_write(SRC, payload)
        cam.mu.mem_write(DST-4, b'\xa5'*(len(payload)+8))
        # 239.76p keeps the native DMA header (A001_193): no CPU copy.
        self.assertEqual(self.copy(cam)[0], 0x42)
        self.assertEqual(cam.w(s+V.L.S['HDR_COPY_HITS']), 0)
        # Seed the independently archived p13 canvas. Every65 word must stay
        # exact; in particular the later p83 processing field+88 stays absent.
        expected = self.manifest['expected_canvas']
        address = V.RC.CANVAS_IN+0x5C
        cam.mu.mem_write(address, struct.pack('<65I', *expected))
        fn = lambda name: cam.w(s+V.L.S['FN']+4*V.L.FNS.index(name))
        cam.call(fn('CANVAS'), s, address, cam.w(entry+V.L.ENT['PID']),
                 thumb=True, sp=V.T.STACK-0x1000)
        self.assertEqual(list(struct.unpack('<65I', cam.mu.mem_read(address, 260))), expected)
        descriptor = struct.pack('<4I', 0x4000000, 0x49048000, 0x40000, 0xC03A55D0)
        cam.mu.mem_write(PARAM, descriptor)
        cam.call(fn('BULK'), s, PARAM, thumb=True, sp=V.T.STACK-0x1000)
        self.assertEqual(bytes(cam.mu.mem_read(PARAM, 16)), descriptor)
        rational = PARAM+0x100
        cam.mu.mem_write(rational, struct.pack('<2I', 30000, 1001))
        self.assertEqual(cam.call(fn('RECRATE'), s, rational, thumb=True, sp=V.T.STACK-0x1000)[0], 0)
        self.assertEqual(bytes(cam.mu.mem_read(rational, 8)), struct.pack('<2I', 30000, 1001))
        cam.assert_tables(self)

    def test_carrier280_follows_the_declared_policy_and_inactive_falls_back(self):
        cam, entry = self.camera()
        s = cam.s()
        # The archived file declares no writer policy: native header at any rate.
        self.assertEqual(cam.w(entry+V.L.ENT['WFLAGS']), 0)
        for nom, fps in ((240, 0x436FC29F), (280, 0x438BDC32)):
            cam.put(entry+V.L.ENT['NOMINAL'], nom)
            cam.put(entry+V.L.ENT['ENGFPS'], fps)
            cam.put(s+V.L.S['FPSLATCH'], fps)
            self.assertEqual(self.copy(cam)[0], 0x42)
        # Declared (as SEC_WRITER compiles it): 12-bit CPU header copy.
        cam.put(entry+V.L.ENT['WFLAGS'], V.L.WR_HDRCPU | 4 << 8)
        self.assertEqual(self.copy(cam)[0], 0)
        row = s+cam.w(s+V.L.S['ROWS'])+(cam.w(s+V.L.S['CUR'])-1)*V.L.ROW['SIZE']
        for address, value in ((s+V.L.S['FLAG'],0), (s+V.L.S['PICKOK'],0),
                               (s+V.L.S['BITLATCH'],4), (s+V.L.S['FPSLATCH'],0),
                               (row+V.L.ROW['ON'],0), (entry+V.L.ENT['WFLAGS'],V.L.WR_BATCH4M | 4 << 8),
                               (entry+V.L.ENT['WFLAGS'],V.L.WR_HDRCPU | 3 << 8)):
            old = cam.w(address)
            cam.put(address, value)
            with self.subTest(address=hex(address), value=value):
                self.assertEqual(self.copy(cam)[0], 0x42)
            cam.put(address, old)
        cam.mu.mem_write(V.RC.KEYBUF, b'H2S24025\0'.ljust(16, b'\0'))
        self.assertNotEqual(cam.call(V.RC.PICKER, r1=V.RC.TAB3, r2=V.RC.KEYBUF)[0], 0)
        self.assertEqual(self.copy(cam)[0], 0x42)
        cam.assert_tables(self)


if __name__ == '__main__':
    unittest.main(verbosity=2)
