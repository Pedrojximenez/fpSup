"""Execute the installed DNG header call and the firmware's CPU memcpy.

The original DMA function is modeled only on the unchanged fallback path.
This proves bytes/ABI/guards, not camera timing or device coherency.
"""
import struct
import unittest

import test_virtual_rcd as V
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import *

SITE, NEXT, DMA = 0xC038C77C, 0xC038C780, 0xC00FBB90
SRC, DST, PARAM = 0x49000040, 0x49022040, 0x49045000
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
        cam.mu.mem_write(V.RC.KEYBUF,b'VRC000120\0'.ljust(16,b'\0'))
        self.assertNotEqual(cam.call(V.RC.PICKER,r1=V.RC.TAB3,r2=V.RC.KEYBUF)[0],0)
        cam.mu.mem_map(0x49000000,0x50000)
        cam.mu.mem_write(0xC00FBD60,cam.img[0xFBD60:0xFBF58])
        cam.test_code.update(range(0xC00FBD60,0xC00FBF58,4))
        cam.mu.mem_write(DMA,struct.pack('<2H',0x2042,0x4770))
        cam.test_code.add(DMA)
        cam.test_code.add(DMA+2)
        cam.test_code.add(NEXT)
        return cam

    def copy(self,cam,n=0x13500,source=SRC,dest=DST,flags=0,owner=None):
        params=struct.pack('<4I',source,dest,n,flags)
        cam.mu.mem_write(PARAM,params)
        cam.put(0xC358DBA8,source if owner is None else owner)
        cam.put(0xC358DBA4,n)
        seeds=[0x76540000+i for i in range(8)]
        for r,v in zip(SAVED,seeds):cam.mu.reg_write(r,v)
        dma=[]
        def observe(mu,a,size,data):
            if a==NEXT:mu.emu_stop()
            if a==DMA:dma.append(list(struct.unpack('<4I',mu.mem_read(mu.reg_read(UC_ARM_REG_R0),16))))
            if a in (0xC0057AE8,0xC005C0F0):raise AssertionError('interactive settings entered')
        hook=cam.mu.hook_add(UC_HOOK_CODE,observe)
        try:
            result=cam.call(SITE,r0=PARAM,sp=V.T.STACK-0x1000)[0]
        finally:cam.mu.hook_del(hook)
        self.assertEqual([cam.r(r) for r in SAVED],seeds)
        self.assertEqual(cam.r(UC_ARM_REG_SP),V.T.STACK-0x1000)
        self.assertEqual(bytes(cam.mu.mem_read(PARAM,16)),params)
        self.assertEqual(cam.misaligned,[])
        return result,dma

    def test_native_cpu_copy_exact_bytes_and_fallback_guards(self):
        cam=self.camera()
        for rank,n in ((23976,4),(27972,0x13500),(27972,0x20000)):
            cam.put(cam.s()+V.L.S['VRATE'],rank)
            entry=cam.s()+cam.w(cam.s()+V.L.S['LAST_ENT'])
            cam.put(entry+V.L.ENT['VRATE'],rank)
            payload=bytes((i*17+3)&255 for i in range(n))
            cam.mu.mem_write(SRC,payload)
            cam.mu.mem_write(DST-4,b'\xa5'*(n+8))
            before=cam.w(cam.s()+V.L.S['HDR_COPY_HITS'])
            self.assertEqual(self.copy(cam,n),(0,[]))
            self.assertEqual(bytes(cam.mu.mem_read(DST,n)),payload)
            self.assertEqual(bytes(cam.mu.mem_read(DST-4,4)),b'\xa5'*4)
            self.assertEqual(bytes(cam.mu.mem_read(DST+n,4)),b'\xa5'*4)
            self.assertEqual(cam.w(cam.s()+V.L.S['HDR_COPY_HITS']),before+1)
        for kwargs in ({'n':0},{'n':0x20004},{'n':7},{'flags':1},
                       {'owner':SRC+4},{'source':0xC5000040},
                       {'dest':SRC+4},{'dest':0x5FFFFFFC}):
            with self.subTest(guard=kwargs):
                result,dma=self.copy(cam,**kwargs)
                self.assertEqual(result,0x42)
                self.assertEqual(len(dma),1)
        for key,value in (('VRATE',0),('PICKOK',0),('FLAG',0),('LAST_ENT',0),('VR_UI',0)):
            addr=cam.s()+V.L.S[key];old=cam.w(addr);cam.put(addr,value)
            with self.subTest(state=key):self.assertEqual(self.copy(cam)[0],0x42)
            cam.put(addr,old)
        cam.assert_tables(self)

    def test_new_call_site_is_owned_by_shutdown_journal(self):
        cam=self.camera()
        installed=cam.w(SITE)
        self.assertNotEqual(installed,struct.unpack_from('<I',cam.img,SITE-0xC0000000)[0])
        self.assertEqual(installed&0xFF000000,0xEB000000)
        self.assertIn(SITE,cam.written)
        cam.restore()
        self.assertEqual(cam.w(SITE),struct.unpack_from('<I',cam.img,SITE-0xC0000000)[0])


if __name__=='__main__':unittest.main(verbosity=2)
