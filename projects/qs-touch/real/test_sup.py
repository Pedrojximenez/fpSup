"""Exact Loader v4 / native QS SUP execution; no camera connection.

Native variable registry/queue and final NBU construction are explicit
substitutes. Native settings instructions and full page parsing have their
own separate tests. This suite does not call a private FT_ test page.
"""
from pathlib import Path
import json
import os
import struct
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(ROOT/'fpSup/loader-v4')]
import build as B
import test_ui_v4 as U
import test_boot_card_v4 as TB
import test_v4 as T
from unicorn.arm_const import (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,
    UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,
    UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11,UC_ARM_REG_SP,UC_ARM_REG_PC)

RECORD=0xC05E6400
LAYOUT=0xC05D90F0
TOUCH=0xC0CFCCDC
STOCK_TOUCH=0xC05131A0
LOOKUP=0xC05DCA88
NOTIFY=0xC05DC7C8
READER=U.F6.FAKE+0x18000
DATA=READER+0x100
SAVED=(UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,
       UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11)
ARTIFACTS=None


def artifacts():
    global ARTIFACTS
    if ARTIFACTS is None:
        path=os.environ.get('QSN_ARTIFACTS')
        if path:out=Path(path)
        else:
            temp=Path(tempfile.mkdtemp(prefix='native-qs-test-'));out=temp/'card';B.build(out,card=True)
        ARTIFACTS={str(p.relative_to(out)):p.read_bytes() for p in out.rglob('*') if p.is_file()}
    return ARTIFACTS


class Camera(U.Cam):
    def __init__(self,stale=None):
        a=artifacts();files={'\\'+n.replace('/','\\'):v for n,v in a.items() if n.startswith('fpSup/')}
        entries=[(n.removeprefix('\\fpSup\\'),0x20,len(v)) for n,v in files.items()
                 if n.startswith('\\fpSup\\') and '\\' not in n.removeprefix('\\fpSup\\')]
        entries.append(('UI',0x10,0))
        self.native_writes=[];self.parsed=[];self.descs={};self.stock_touches=[]
        super().__init__(files,{'\\fpSup':entries})
        for at in (LOOKUP,NOTIFY):self.put(at,0x47704770)
        self.put(STOCK_TOUCH,0xE12FFF1E)
        for at,v in (stale or {}).items():self.put(at,v)
        self.by_addr[TB.POP]='AR_POP';self.put(TB.POP,0xE12FFF1E)
        self.put(TB.TABLE+0x21C,2);self.put(TB.TABLE+36+4,0xC03DA158)
        self.put(TB.TABLE+72+4,TB.LINE);self.put(TB.TABLE+72+12,TB.CTX)
        self.put(TB.CTX+0x90,1);self.put(TB.CTX+0x94,TB.FOBJ)
        self.put(T.T3.DRAW,T.T3.DRAW_PAUSED)
        for name,value in zip(B.P.NATIVE,(1,0,0,0,0,0,0,20,17,21,22,1,2,3,4)):
            self.vars[name]=(0,value)
        TB.run_autorun(self,a['AutoRun.txt'])
        if self.error:raise AssertionError(self.error)

    def _hook(self,mu,address,size,data):
        if address==TB.POP:self.put(TB.TABLE+0x21C,self.w(TB.TABLE+0x21C)-1);return self._ret(0)
        if address==STOCK_TOUCH:
            self.stock_touches.append(1);return self._ret(1)
        if address==LOOKUP:
            name=self.cstr(self.r(UC_ARM_REG_R1));out=self.r(UC_ARM_REG_R2)
            if name not in self.vars:self.put(out,0);return self._ret(0)
            if name not in self.descs:self.descs[name]=U.F6.FAKE+0x10000+32*len(self.descs)
            desc=self.descs[name];self.put(desc,self.vars[name][0]);self.put(desc+8,self.vars[name][1]);self.put(out,desc)
            return self._ret(0)
        if address==NOTIFY:
            assignment=self.r(UC_ARM_REG_R3)
            kind,name,value=self.w(assignment),self.cstr(self.w(assignment+4)),self.w(assignment+8)
            assert kind==0 and name in B.P.NATIVE
            self.vars[name]=(0,value);self.native_writes.append((name,value))
            if name=='QS_FocusPos':self.vars['QS_QSMode']=(0,self.vars[B.P.NATIVE[7+value]][1])
            return self._ret(0)
        if address==RECORD+4:
            # Original prologue has run; simulate one constructed record and
            # its matching epilogue without skipping our real wrapper.
            reader=self.r(UC_ARM_REG_R0);pos=self.w(reader+4);base=self.w(reader+36)
            at=base+pos;tag,n=struct.unpack('>II',bytes(mu.mem_read(at,8)))
            self.parsed.append((base,pos,bytes(mu.mem_read(at,n))))
            self.put(reader+4,pos+n)
            sp=self.r(UC_ARM_REG_SP);saved=struct.unpack('<9I',bytes(mu.mem_read(sp,36)))
            for reg,value in zip(SAVED,saved):mu.reg_write(reg,value)
            mu.reg_write(UC_ARM_REG_SP,sp+36);mu.reg_write(UC_ARM_REG_R0,1 if tag==0xFFFF else 0)
            mu.reg_write(UC_ARM_REG_PC,saved[8]);return
        return super()._hook(mu,address,size,data)

    def notify(self,name,value):
        callbacks=[fn for _,n,fn in self.subs if n==name];assert len(callbacks)==1,(name,callbacks)
        self.vars[name]=(0,value);desc=U.F6.FAKE+0x1A000;self.put(desc,0);self.put(desc+8,value)
        self.call(callbacks[0]&~1,r0=desc,thumb=bool(callbacks[0]&1),sp=T.T3.STACK-0x1000)

    def touch(self,x=-1,y=-1):
        mu=self.mu;mu.mem_write(DATA,struct.pack('<6i',x,y,-1,-1,0,0));before=len(self.posts)
        fn=self.w(TOUCH);self.call(fn&~1,r0=DATA+64,r1=DATA,thumb=bool(fn&1),sp=T.T3.STACK-0x1000)
        for name,value in self.posts[before:]:
            if name=='QSN_Raw':self.notify('QSN_Input',value)

    def tap(self,x,y):self.touch(x,y);self.touch()


class NativeSupTests(unittest.TestCase):
    def test_exact_boot_adds_no_demo_page_and_keeps_real_setting_owners(self):
        cam=Camera();base=T.blocks(cam)['ZQS.BIN'];blob=artifacts()['fpSup/ZQS.BIN']
        state=struct.unpack_from('<I',blob,52)[0]
        self.assertEqual(cam.w(base+state),B.MAGIC)
        self.assertEqual(cam.w(base+state+8),1)
        self.assertNotIn('QST_Touch',cam.vars)
        self.assertFalse(any(name in B.P.NATIVE for _,name,_ in cam.subs))
        self.assertTrue(base<=cam.w(TOUCH)<base+len(blob))
        self.assertEqual(cam.native_writes,[],'boot must not change any recording setting')
        cam.notify('QSN_Active',1)
        self.assertEqual(cam.vars['FPQS_FormatText'],(2,'MOV'))
        self.assertEqual(cam.vars['FPQS_ResText'],(2,'UHD'))
        cam.tap(300,150);cam.tap(800,640)
        self.assertIn(('CM_DCCrop',1),cam.native_writes)
        self.assertEqual(cam.vars['FPQS_DCText'],(2,'ON'))
        self.assertFalse(cam.shown,'the native QS page must not switch to FT_QSTOUCH')

    def test_sparse_arm_stream_preserves_original_coordinates(self):
        cam=Camera();patches,_,_,_=B.P.resources()
        for patch in (patches[0],next(p for p in patches if p['records']>5),patches[-1]):
            before=len(cam.parsed);pos=patch['address']-B.P.B.Q.NBU_BASE
            cam.put(READER+36,B.P.B.Q.NBU_BASE);cam.put(READER+4,pos)
            _,sp=cam.call(RECORD,r0=READER,thumb=True,sp=T.T3.STACK-0x1004)
            self.assertEqual(sp,T.T3.STACK-0x1004)
            self.assertEqual(cam.w(READER+36),B.P.B.Q.NBU_BASE)
            self.assertEqual(cam.w(READER+4),pos+len(patch['old']))
            self.assertEqual(len(cam.parsed)-before,patch['records'])
            # Relocated string identifiers differ; record sizes and tag order
            # still have to match exactly, including inserted action records.
            wanted=B.P.B.Q.N.split(patch['data']+bytes.fromhex('ffffffff00000008'))[:-1]
            self.assertEqual([(struct.unpack_from('>I',r[2])[0],len(r[2])) for r in cam.parsed[before:]],
                             [(r.tag,r.size) for r in wanted])

    def test_inactive_touch_passes_through_and_no_demo_values_are_committed(self):
        cam=Camera();cam.tap(300,150)
        self.assertEqual(len(cam.stock_touches),2)
        cam.notify('QSN_Active',1)
        cam.tap(100,150);cam.tap(800,640)
        # MOV is already the last native choice: no invented five-entry
        # FORMAT list may send a diagnostic CDNG index to the camera.
        self.assertEqual(cam.native_writes,[])
        cam.tap(20,640)
        self.assertEqual(cam.vars['MV_RecordingFormat'],(0,0))
        self.assertEqual(cam.vars['FPQS_FormatText'],(2,'CinemaDNG'))
        cam.tap(600,150);cam.tap(800,640)
        self.assertEqual(cam.vars['MV_Resolution'],(0,1))
        self.assertEqual(cam.vars['FPQS_ResText'],(2,'FHD'))
        cam.tap(800,150);cam.tap(800,640)
        self.assertEqual(cam.vars['MV_FrameRate'],(0,1))
        self.assertEqual(cam.vars['FPQS_FPSText'],(2,'24p'))

    def test_unknown_touch_owner_is_left_alone(self):
        cam=Camera(stale={TOUCH:0x12345678})
        self.assertNotIn('ZQS.BIN',T.blocks(cam));self.assertEqual(cam.w(TOUCH),0x12345678)
        self.assertNotIn('QSN_Raw',cam.vars)

    def test_idle_and_interaction_power_off_restore_all_three_words(self):
        for interact in (False,True):
            cam=Camera()
            if interact:cam.notify('QSN_Active',1);cam.tap(300,150)
            TB.Camera.power_off_all(cam)
            self.assertEqual(cam.w(TOUCH),STOCK_TOUCH)
            self.assertEqual(cam.w(RECORD),0x4FF0E92D)
            self.assertEqual(cam.w(LAYOUT),0x4CF0E92D)


if __name__=='__main__':unittest.main(verbosity=2)
