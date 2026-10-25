"""Execute the exact SUP bytes under the maintained Loader v4 harness.

Firmware GUI registration, variable queue, screen manager, clock, allocator,
file I/O and the stock observer fallback are explicit service substitutes.
The SUP, portable gesture core, loader, claim/journal and callbacks execute.
"""
from pathlib import Path
import os
import struct
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE),str(ROOT/'fpSup/loader-v4')]
import build as P
import page as PAGE
import test_ui_v4 as U
import test_boot_card_v4 as TB
import test_v4 as T
from test_native_input import relay, private_page, InputProbe

SLOT, STOCK, CLOCK=0xC0CFCCDC,0xC05131A0,0xC002B920
APP_FIND, APP_SHOW = 0xC05E04E8, 0xC05E07C8
DATA=U.F6.FAKE+0x6E00
OBS=DATA+0x40
_artifacts=None


def artifacts():
    global _artifacts
    if _artifacts is None:
        directory=os.environ.get('QST_SUP_ARTIFACTS')
        if directory:
            out=Path(directory)
            _artifacts={str(p.relative_to(out)).replace(os.sep,'/'):p.read_bytes()
                        for p in out.rglob('*') if p.is_file()}
        else:
            with tempfile.TemporaryDirectory(prefix='qst-sup-test-') as d:
                out=Path(d)/'card';P.build(out,card=True)
                _artifacts={str(p.relative_to(out)).replace(os.sep,'/'):p.read_bytes()
                            for p in out.rglob('*') if p.is_file()}
    return _artifacts


class Camera(U.Cam):
    def journal(self):
        # The exact AutoRun has both an outer stage2 callback and v4's own
        # callback. Select v4 by its service-table version, not list order.
        owners={o for o,_ in self.registered if self.w(o-T.SVC_BYTES)==P.B.SL4_LOADER_SVC}
        assert len(owners)==1,owners
        e=self.w(owners.pop()+8);out=[]
        while self.w(e):
            at,n=self.w(e),self.w(e+4)
            assert 0<n<=0x10000 and len(out)<256
            out.append((at,n,bytes(self.mu.mem_read(e+8,n))));e+=8+n
        return out

    def __init__(self,*,extra=(),no_gui=False,stale=None):
        a=artifacts()
        files={'\\'+name.replace('/','\\'):data for name,data in a.items() if name.startswith('fpSup/')}
        for name,data in extra:files['\\fpSup\\'+name]=data
        entries=[(path.removeprefix('\\fpSup\\'),0x20,len(data)) for path,data in files.items()
                 if path.startswith('\\fpSup\\') and '\\' not in path.removeprefix('\\fpSup\\')]
        entries.append(('UI',0x10,0))
        super().__init__(files,{'\\fpSup':entries})
        self.clock=1000;self.stock_calls=[]
        self.mu.mem_write(STOCK,struct.pack('<I',0xE12FFF1E))
        self.mu.mem_write(CLOCK,struct.pack('<I',0xE12FFF1E))
        for at,value in (stale or {}).items():self.put(at,value)
        if no_gui:self.put(U.F6.GUI_OBJECT,0)
        self.by_addr[TB.POP]='AR_POP';self.put(TB.POP,0xE12FFF1E)
        self.put(TB.TABLE+0x21C,2)
        self.put(TB.TABLE+36+4,0xC03DA158)
        self.put(TB.TABLE+72+4,TB.LINE);self.put(TB.TABLE+72+12,TB.CTX)
        self.put(TB.CTX+0x90,1);self.put(TB.CTX+0x94,TB.FOBJ)
        self.put(T.T3.DRAW,T.T3.DRAW_PAUSED)
        self.fallback=None
        TB.run_autorun(self,a['AutoRun.txt'])
        if self.error:raise AssertionError(self.error)

    def _hook(self,mu,addr,size,data):
        services={CLOCK,STOCK,APP_FIND,APP_SHOW,U.F6.NBR_LOAD,U.F6.VAR_REGISTER,U.F6.VAR_SUBSCRIBE,
                  U.F6.POST_INT,U.F6.POST_STR,U.F6.F_RENAME,U.SCREENS,U.SHOW}
        if 0xC0000000<=addr<0xC3000000 and not 0xC072D000<=addr<0xC0735000:
            if addr not in self.by_addr and addr not in services:
                raise AssertionError(f'Unmodeled firmware execution at {addr:#x}')
        if addr in (CLOCK,STOCK,APP_FIND,APP_SHOW,U.F6.NBR_LOAD,U.F6.VAR_REGISTER,U.F6.VAR_SUBSCRIBE,
                    U.F6.POST_INT,U.F6.POST_STR,U.SCREENS,U.SHOW):
            if self.r(T.T3.UC_ARM_REG_SP)&7:raise AssertionError(f'Unaligned native call at {addr:#x}')
        if addr==CLOCK:return self._ret(self.clock)
        if addr==APP_FIND:
            assert self.r(T.T3.UC_ARM_REG_R0)==self.w(U.F6.GUI_OBJECT)
            self.requested_page=self.cstr(self.r(T.T3.UC_ARM_REG_R1))
            return self._ret(0 if getattr(self,'reject_page',False) else U.F6.FAKE+0x7D00)
        if addr==APP_SHOW:
            assert self.r(T.T3.UC_ARM_REG_R0)==self.w(U.F6.GUI_OBJECT)
            assert self.r(T.T3.UC_ARM_REG_R1)==U.F6.FAKE+0x7D00
            self.shown.append((self.r(T.T3.UC_ARM_REG_R0),self.requested_page))
            return self._ret(getattr(self,'show_result',0))
        if addr==STOCK:
            self.stock_calls.append((self.r(T.T3.UC_ARM_REG_R0),self.r(T.T3.UC_ARM_REG_R1)))
            return self._ret(1)
        if addr==TB.POP:
            self.put(TB.TABLE+0x21C,self.w(TB.TABLE+0x21C)-1);return self._ret(0)
        if addr==U.F6.NBR_LOAD:
            pack=bytes(mu.mem_read(self.r(T.T3.UC_ARM_REG_R1),self.r(T.T3.UC_ARM_REG_R2)))
            if PAGE.MACHINE.encode() in pack:
                n=len(self.machine_names);self.machine_names.append(PAGE.MACHINE)
                machine=U.F6.FAKE+0x9000+0x40*n;name=U.F6.FAKE+0x9800+0x20*n
                mu.mem_write(name,PAGE.MACHINE.encode()+b'\0');self.put(machine+8,name)
                self.new_machine=machine
                return U.F6.Cam._hook(self,mu,addr,size,data)
        return super()._hook(mu,addr,size,data)

    def open(self):
        k,= [k for k in range(6) if self.vars[f'FT_N{k}'][1]=='QS Touch test']
        self.notify('FT_Key',41+k)
        assert self.shown[-1][1]==PAGE.PAGE,self.shown
        self.notify('QST_Active',1)               # native page's loaded event

    def notify(self,var,value):
        self.vars[var] = (self.vars[var][0], value)
        callbacks=[f for _o,name,f in self.subs if name==var]
        assert len(callbacks)==1, f'{var} must have exactly one operation subscriber: {callbacks}'
        fn,=callbacks
        desc=U.F6.FAKE+0x7800;self.put(desc,0);self.put(desc+8,value)
        # GUI callbacks follow AAPCS, unlike AutoRun's special echo entry.
        self.call(fn&~1,r0=desc,thumb=bool(fn&1),sp=T.T3.STACK-0x1000)

    def deliver_touch(self, value):
        # POST_INT is silent: never call its subscriber directly. The exact
        # page must contain a change-event/action relay to a separate variable.
        route = relay(artifacts()['fpSup/QSTOUCH.BIN'])
        self.assert_relay(route)
        self.notify(route['destination'], value)

    @staticmethod
    def assert_relay(route):
        assert route == dict(event='QST_Touch', destination='QST_Input',
                             source='QST_Touch', source_type=0), route

    def touch(self,x=-1,y=-1,*,second=(-1,-1),ms=20,deliver=True):
        self.clock+=ms
        self.mu.mem_write(DATA,struct.pack('<6i',x,y,*second,self.clock,0))
        before=len(self.posts);fn=self.w(SLOT)
        from unicorn.arm_const import UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11
        saved=[UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11]
        initial=[self.r(r) for r in saved]
        ret,sp=self.call(fn&~1,r0=OBS,r1=DATA,thumb=bool(fn&1),sp=T.T3.STACK-0x1000)
        assert sp==T.T3.STACK-0x1000,hex(sp)
        assert [self.r(r) for r in saved]==initial,'observer damaged callee-saved registers'
        # The actual firmware queue is substituted, with explicit delivery.
        queued=[value for name,value in self.posts[before:] if name=='QST_Touch']
        if deliver:
            for value in queued:self.deliver_touch(value)
        return ret if deliver else queued

    def tap(self,x,y):self.touch(x,y);self.touch()
    def swipe(self,x,y,x2,y2):self.touch(x,y);self.touch(x2,y2);self.touch()


class SupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if T.Uc is None or not T.T3.IMAGE.exists():raise RuntimeError('Unicorn and firmware image are required; no skipped success')

    def test_real_boot_installs_a_resident_sup_and_borrowed_ui(self):
        cam=Camera();a=artifacts();blob=a['fpSup/QSTOUCH.BIN'];h=struct.unpack_from('<12I',blob)
        self.assertEqual((h[0],h[1],h[2],h[7],h[8]),(P.B.SL4_MAGIC,48,len(blob),6,1))
        base=T.blocks(cam)['QSTOUCH.BIN'];self.assertEqual(base%64,0);self.assertGreaterEqual(base,0xC0000000)
        self.assertTrue(base<=cam.w(SLOT)<base+len(blob))
        self.assertTrue(cam.w(SLOT)&1)
        state_off,ui_off=struct.unpack_from('<II',blob,52)
        self.assertEqual(cam.w(base+state_off),0x31545351)
        self.assertEqual(cam.w(base+state_off+4),0)
        self.assertEqual(cam.w(base+state_off+8),1)
        self.assertIn(PAGE.MACHINE,cam.machines())
        self.assertEqual(cam.page_id(PAGE.PAGE),21)
        self.assertIn(SLOT,[a for a,_,_ in cam.journal()])
        self.assertEqual(cam.misaligned,[])
        self.assertTrue(cam.freed,'loader staging must have been released')
        cam.open()
        self.assertEqual([cam.vars[f'QST_N{k}'][1] for k in range(4)],['FORMAT','DC','RES','FPS'])
        self.assertEqual(cam.vars['QST_Status'][1],'QS TOUCH TEST')
        self.assertEqual(cam.vars['QST_D0'][1],'UI values only')
        self.assertGreater(base+ui_off,base+h[4])

    def test_inactive_touch_passthrough_and_owned_contact_drain(self):
        cam=Camera();cam.tap(100,120)
        self.assertEqual(cam.stock_calls,[(OBS,DATA)]*2)
        cam.open();cam.stock_calls.clear();cam.touch(300,150)
        self.assertFalse(cam.stock_calls)
        cam.notify('QST_Active',0)               # MENU/other screen closed it
        cam.touch(330,160);cam.touch()
        self.assertFalse(cam.stock_calls,'release must not leak into touch AF')
        cam.tap(500,200);self.assertEqual(len(cam.stock_calls),2)

    def test_select_adjust_double_tap_and_inline_option_grid(self):
        cam=Camera();cam.open();start=len(cam.posts)
        cam.tap(300,150)
        self.assertEqual(cam.vars['QST_X'][1],256)
        self.assertEqual(cam.vars['QST_Footer'][1],'OG')
        cam.tap(820,640)
        self.assertEqual(cam.vars['QST_V1'][1],'HD')
        cam.touch(700,640);cam.touch(570,640);cam.touch()
        self.assertEqual(cam.vars['QST_V1'][1],'APS-C')
        cam.tap(100,150);cam.tap(100,150)
        self.assertEqual(cam.vars['QST_Status'][1],'FORMAT options')
        self.assertEqual(cam.vars['QST_V3'][1],'CDNG 12bit')
        cam.tap(800,150)
        cam.swipe(800,450,800,300)
        self.assertEqual(cam.vars['QST_Status'][1],'QS TOUCH TEST')
        self.assertEqual(cam.vars['QST_V0'][1],'CDNG 12bit')
        self.assertTrue(all(name.startswith('QST_') for name,_ in cam.posts[start:]),'no recording/exposure variable may be written')

    def test_long_press_reorders_on_release_without_motion_frames(self):
        cam=Camera();cam.open();cam.touch(800,150)
        cam.touch(400,150,ms=600)
        self.assertEqual(cam.vars['QST_X'][1],256)
        self.assertEqual(cam.vars['QST_N1'][1],'DC')
        cam.touch()
        self.assertEqual([cam.vars[f'QST_N{k}'][1] for k in range(4)],['FORMAT','FPS','DC','RES'])

    def test_multi_contact_cancels_without_applying_and_stable_moves_do_not_repaint(self):
        cam=Camera();cam.open();cam.touch(500,640)
        applied=[cam.vars[f'QST_V{k}'][1] for k in range(4)]
        before=len(cam.posts)
        for _ in range(8):cam.touch(500,640)
        self.assertEqual([name for name,_ in cam.posts[before:]],['QST_Touch']*8)
        cam.touch(300,640,second=(700,300));cam.touch(200,640);cam.touch()
        self.assertEqual([cam.vars[f'QST_V{k}'][1] for k in range(4)],applied)

    def test_swipe_up_and_back_target_return_to_parent(self):
        for button in (False,True):
            with self.subTest(back_button=button):
                cam=Camera();cam.open()
                if button:cam.tap(950,30)
                else:cam.swipe(800,450,800,300)
                self.assertEqual(cam.shown[-1][1],'FT_Y6')
                cam.stock_calls.clear();cam.tap(300,200)
                self.assertEqual(len(cam.stock_calls),2)

    def test_unknown_touch_owner_is_not_overwritten(self):
        cam=Camera(stale={SLOT:0x12345678})
        self.assertNotIn('QSTOUCH.BIN',T.blocks(cam))
        self.assertEqual(cam.w(SLOT),0x12345678)
        self.assertNotIn('QST_Touch',cam.vars)

    def test_claim_conflict_releases_sup_without_private_ui(self):
        other=P.B.test_sup(T.cfg(claims=[(SLOT,STOCK,2,STOCK)]),'OTHR')
        cam=Camera(extra=[('A_OWNER.BIN',other)])
        self.assertNotIn('QSTOUCH.BIN',T.blocks(cam))
        self.assertNotIn('QST_Touch',cam.vars)

    def test_old_queued_packets_do_not_change_a_reopened_page(self):
        cam=Camera();cam.open()
        queued=cam.touch(820,640,deliver=False)+cam.touch(deliver=False)
        cam.notify('QST_Active',0);cam.open()
        for packet in queued:cam.deliver_touch(packet)
        self.assertEqual(cam.vars['QST_V0'][1],'MOV')

    def test_missing_gui_keeps_pointer_lifetime_but_does_not_arm(self):
        cam=Camera(no_gui=True)
        self.assertIn('QSTOUCH.BIN',T.blocks(cam))
        self.assertEqual(cam.w(SLOT),STOCK)
        base=T.blocks(cam)['QSTOUCH.BIN']
        off=struct.unpack_from('<I',artifacts()['fpSup/QSTOUCH.BIN'],52)[0]
        self.assertNotEqual(cam.w(base+off+4),0)
        self.assertEqual(cam.w(base+off+8),0)

    def test_power_off_restores_touch_word_after_idle_and_interaction(self):
        for interact in (False,True):
            with self.subTest(interact=interact):
                cam=Camera()
                if interact:cam.open();cam.tap(300,150);cam.tap(820,640)
                self.assertNotEqual(cam.w(SLOT),STOCK)
                TB.Camera.power_off_all(cam)
                self.assertEqual(cam.w(SLOT),STOCK)

    def test_private_page_has_no_animation_or_stock_settings(self):
        p=PAGE.Page((ROOT/'out/MAIN_c0000000.bin').read_bytes());raw,refs,info=p.build_private()
        records=PAGE.B.Q.N.split(raw)
        self.assertEqual(info['own_objects'],13)
        self.assertGreater(info['native_focus_objects'],0)
        self.assertEqual(info['animation_requests'],0)
        self.assertFalse(any(r.tag==0x10009 and p.pool.text(PAGE.B.u32(r.to_bytes(),8))=='controlAnimation' for r in records))
        self.assertFalse(any(name.startswith(('CM_','MV_','MENU_','QS_')) for _,name in refs))
        self.assertEqual(PAGE.B.Q.SL.duplicate_local_ids(raw),[])
        # Lifecycle values come directly from the real QS page, not a guessed 0/1.
        events=[r for r in records if r.tag==0x10006 and p.pool.text(PAGE.B.u32(r.to_bytes(),8))=='screenEvent']
        private=[r for r in events if PAGE.B.u32(r.to_bytes(),24)==40001]
        self.assertEqual([PAGE.B.u32(r.to_bytes(),36) for r in private],[1,2])

    def test_native_focus_has_a_visible_private_initial_target(self):
        data,info=PAGE.data_file();h=struct.unpack_from('<17I',data)
        variables={}
        for k in range(h[7]):
            kind,name,first=struct.unpack_from('<3I',data,h[8]+12*k)
            name=data[name:data.index(b'\0',name)].decode()
            variables[name]=(kind,first)
        focus=variables['QTG_Focus'][1]
        self.assertIn(focus,info['shape']['objects'])
        self.assertLess(focus,40000,'native focus must not point at an unfocusable drawing tile')
        self.assertEqual(variables['QTG_Visible0'][1],1)
        self.assertEqual(variables['QTG_Title'][1],0)
        self.assertNotIn('FT_Key',variables,'test frame must not drive the real fpSup menu')
        self.assertNotIn('FT_Focus',variables)

    def test_native_silent_post_requires_relay_and_preserves_all_packet_bits(self):
        route = relay(artifacts()['fpSup/QSTOUCH.BIN'])
        Camera.assert_relay(route)
        p = InputProbe(route)
        self.addCleanup(p.close)
        words = [0x00400001, 0x80400001, 0x7FFFFFFF, 0xFFFFFFFF,
                 0x80A25B03, 0x00BFFFFF, 0, 1]
        for word in words:
            before = list(p.events)
            p.post_silent(word)
            self.assertEqual(p.events, before, 'the old direct-watch path must stay silent')
            self.assertEqual(p.words(p.descs[route['source']]+8)[0], word)
            p.run_action()
            self.assertEqual(p.events, before+[word])
            self.assertEqual(p.words(p.descs[route['destination']]+8)[0], word)
        self.assertIn(0xC05F15E0, p.native_pcs)

    def test_private_paint_order_places_tiles_above_native_frame_and_fill(self):
        records, _, _ = private_page(artifacts()['fpSup/QSTOUCH.BIN'])
        objects = [r.to_bytes() for r in records if r.tag == 0x10003]
        children = [PAGE.B.u32(r,20) for r in objects if PAGE.B.u32(r,24) == 1]
        self.assertEqual(children[0], 40001)
        own = [PAGE.B.u32(r,20) for r in objects if PAGE.B.u32(r,24) == 40001]
        self.assertEqual(own[-1], 40002)
        self.assertGreater(own.index(40002), own.index(40003))


if __name__=='__main__':unittest.main(verbosity=2)
