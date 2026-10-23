"""Real two-sup ARM integration. UI/OS boundaries use the maintained fixtures.
No physical camera, card or storage access. RCD compilation and hooks are real.
"""
import json, os, pathlib, struct, subprocess, sys, tempfile, unittest
HERE=pathlib.Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE/'res-custom')]
import test_v3_reslab as RL
import test_v3_rescustom as RC
import ogc_layout as L
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_SP
T=RL.T
CARD=None
VRC_ABI=2

def built():
    global CARD
    if CARD is None:
        env=os.environ.get('VIRTUAL_RCD_CARD')
        out=pathlib.Path(env) if env else pathlib.Path(tempfile.mkdtemp(prefix='vrc-test-'))/'card'
        if not env:
            subprocess.run([sys.executable,'-B',str(HERE/'build_v3_reslab.py'),'--virtual-rcd','--card','--no-shell','--out',str(out)],check=True,capture_output=True)
        f=json.loads((out/'build.json').read_text())['facts']
        CARD=out,f
    return CARD

class Cam(RL.Cam,RC.Cam):
    fake_uia=RC.Cam.fake_uia
    fake_vr=RC.Cam.fake_vr
    fv_add=RC.Cam.fv_add
    def __init__(self,files,dirs,f,fmt=0,res=2,fr=12,**kw):
        self.cf=f['rescustom']; self.core_block=None; self.pending=[]
        self.uia=[]; self.csv_rows=2; self.uia_fail=set(); self.next_id=RC.STRID0
        self.vr_ids=[]; self.lv_ids=[]; self.fv=[]; self.fv_next=RC.VR_RAM+0x10000
        self.fmt,self.res,self.fr,self.crop=fmt,res,fr,0
        self.sensor=[];self.emitted=[];self.recomputes=[]
        self.qs_seen=[];self.lay_calls=[];self.load_calls=[];self.v_calls=[];self.load_ret=0
        self.lv=[];self.schedule=3;self.running=False;self.inject_busy=False
        self.gui_names=[];self.fail_assets=False;self.busy_on_alloc=False
        self.gui_requests=[];self.view_requests=[];self.request_result=0
        super().__init__(files,dirs,f,core_facts=self.cf,fmt=fmt,res=res,fr=fr,**kw)
        for name,a in RC.FW.items():
            if a in RL.NATIVES: continue
            self.mu.mem_write(a,struct.pack('<I',0xe12fff1e));self.by_addr[a]=name
        for a in (0xC005C024,0xC005BE5C):
            self.mu.mem_write(a,struct.pack('<I',RC.POP456))
            self.by_addr[a]='RESBODY' if a==0xC005C024 else 'FMTBODY'
        self.b25_entry=RL.ENTRIES
        self.test_code.update(int(h['site'],16) for h in self.cf['hooks'])
        self.tables=bytes(self.mu.mem_read(0xC0B00000,0x200000))
        for addr,name in ((0xC054DD38,'GUI_CONTROLLER'),(0xC05DCB40,'VIEW_REQUEST'),(0xC3E80600,'GUI_REQUEST')):
            self.by_addr[addr]=name
            self.mu.mem_write(addr,struct.pack('<I',0xe12fff1e))
        self.put(0xC3E80400,0xC3E80500)
        self.put(0xC3E8050c,0xC3E80600)
    def _alloc(self,n,align=8):
        if self.core_block is not None and self.block is not None and self.get('pages_state')==1:
            if self.fail_assets:return 0
            if self.busy_on_alloc:self.put(0xC35A952c,1)
        p=super()._alloc(n,align)
        if n==self.cf['block'] and self.core_block is None:
            self.core_block=p;uia=p+(self.cf['uia_apply_off']&~1)
            self.by_addr[uia]='UIA';self.pending.append((uia,struct.pack('<H',0x4770)))
        return p
    def _hook(self,mu,addr,size,data):
        name=self.by_addr.get(addr)
        if isinstance(name,tuple) and name[0]=='UI':return RL.Cam._hook(self,mu,addr,size,data)
        # SAVE now coexists with the virtual consumer; keep the producer's
        # modeled directory enumeration and exact readback semantics.
        if name in ('F_OPEN','F_WRITE'):return RL.Cam._hook(self,mu,addr,size,data)
        if name=='RESBODY':
            self.res=self.r(UC_ARM_REG_R1);self.calls.append('SET_RES');return
        if name=='FMTBODY':return
        if name=='GUI_NATIVE':
            self.gui_names.append(self.cstr(self.r(UC_ARM_REG_R1)))
            return self._ret(0x77)
        if name=='GUI_CONTROLLER':return self._ret(0xC3E80400)
        if name=='GUI_REQUEST':
            self.gui_requests.append(self.cstr(self.r(UC_ARM_REG_R1)));return self._ret(1)
        if name=='VIEW_REQUEST':
            self.view_requests.append((self.r(UC_ARM_REG_R0),self.cstr(self.r(UC_ARM_REG_R1))))
            return self._ret(self.request_result)
        if name=='LV_HOLDER':
            self.put(0xC3E80000,0xC3E80100 if self.running else 0)
            self.put(0xC3E80104,1)
            return self._ret(0xC3E80000)
        if name=='CAMSCH1':return self._ret(0xC3E80200)
        if name=='CS_GET':return self._ret(self.schedule)
        if name=='CS_SET':self.schedule=self.r(UC_ARM_REG_R1);self.lv.append(('schedule',self.schedule));return self._ret(0)
        if name in ('LV_STOP','LV_START'):
            self.lv.append(name)
            if name=='LV_STOP' and self.inject_busy:self.put(0xC35A952c,1)
            return self._ret(0)
        if name is None and 0xC0000000<=addr<0xC3000000 and not 0xC072D000<=addr<0xC0740000 and addr not in self.test_code:
            raise AssertionError(f'unmodeled firmware execution {addr:#x}')
        return RC.Cam._hook(self,mu,addr,size,data)
    def s(self):return self.core_block+self.cf['img_off']+L.S_COORD-L.LAYOUT0
    def service(self):return self.w(self.s()+L.S['VRC'])
    def row(self):return self.s()+self.w(self.s()+L.S['ROWS'])+L.ROW['SIZE']*self.w(self.service()+40)
    def apply(self):return self.call(self.fn('sl_menu_apply'),self.m(),thumb=True,sp=T.STACK-0x1000)[0]
    def dispatch(self,op,arg):
        fn=self.core_block+self.cf['virtual_dispatch_off']
        return self.call(fn,self.s(),op,arg,thumb=True,sp=T.STACK-0x1000)[0]
    def blob_provider(self,blob,ident=0x33435256):
        stub=T.HEAP+T.HEAP_SIZE-0x1000
        # Own a separate mapped fixture region for a borrowed producer blob.
        data=0x49000000;desc=data+0x20000
        self.mu.mem_map(data,0x21000);self.mu.mem_write(data,bytes(blob))
        code=(0xe92d4010,0xe1a04002,0xe59f3010,0xe5843000,0xe59f300c,0xe5843004,
              0xe3a00000,0xe8bd8010,data,len(blob))
        self.mu.mem_write(stub,struct.pack('<10I',*code))
        self.mu.mem_write(desc,struct.pack('<8I',32,VRC_ABI,ident,0,0,stub,0,0))
        if self.dispatch(1,desc):raise AssertionError('fixture registration failed')
        return ident
    def snapshot(self):
        st=self.s();return bytes(self.mu.mem_read(st+L.S['BODY'],self.w(st+L.S['S_END'])-L.S['BODY']))
    def assert_tables(self,test):
        expected=bytearray(self.tables)
        if self.tasks and self.w(0xC072F000)==0x4C485356:
            import patches
            for at,value,*_ in patches.IFACE+patches.NOPTP:
                if 0xC0B00000<=at<0xC0D00000:struct.pack_into('<I',expected,at-0xC0B00000,value)
        test.assertEqual(bytes(self.mu.mem_read(0xC0B00000,0x200000)),bytes(expected))

class VirtualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.out,cls.f=built()
    def boot(self,record=None,rcds=None,**kw):
        sups=[(p.name,p.read_bytes()) for p in (self.out/'fpSup').glob('*.BIN') if p.name!='LOADER.BIN']
        if record is not None:
            sups=[(n,b[:32]+record+b[32+L.CFG['BYTES']:]) if n=='32RESCUS.BIN' else (n,b) for n,b in sups]
        files,dirs=T.card(*sups);files['\\fpSup\\LOADER.BIN']=(self.out/'fpSup/LOADER.BIN').read_bytes()
        if rcds is not None:
            dirs['\\fpSup\\RESCUS']=[(n,0x20,len(b)) for n,b in rcds.items()]
            files.update({'\\fpSup\\RESCUS\\'+n:b for n,b in rcds.items()})
        # No .RCD file or even RESCUS directory: the bootstrap is consumer-owned.
        cam=Cam(files,dirs,self.f,**kw)
        for a,v in T.B.loader_words((self.out/'AutoRun.txt').read_bytes()).items():cam.put(a,v)
        cam.boot();self.assertIsNotNone(cam.core_block);self.assertIsNotNone(cam.block)
        if (self.out/'fpSup/00SHELL.BIN').exists():self.assertEqual(len(cam.tasks),1)
        self.assertNotEqual(cam.service(),0)
        cam.written_baseline=dict(cam.written)
        cam.prepare();self.assertEqual(cam.get('pages_state'),1)
        return cam
    def test_apply_without_file_and_live_canvas(self):
        cam=self.boot();cam.geometry();self.assertEqual(cam.apply(),0)
        st=cam.s();row=cam.row()
        self.assertEqual((cam.w(row+L.ROW['AW']),cam.w(row+L.ROW['AH'])),(3008,2000))
        self.assertEqual(cam.w(cam.service()+12),0x42414c52)
        self.assertEqual(cam.w(st+L.S['FLAG']),1)
        self.assertEqual(cam.cstr(cam.m()+self.f['state_fields']['export_text']),'Applied')
        cam.mu.mem_write(RC.KEYBUF,b'VRC00024\0'.ljust(16,b'\0'))
        hit,_=cam.call(RC.PICKER,r1=RC.TAB3,r2=RC.KEYBUF)
        self.assertNotEqual(hit,0);pid=cam.w(hit+4)
        fn=cam.w(st+L.S['FN']+L.FNS.index('CANVAS')*4)
        canvas=RC.CANVAS_IN+0x5c;cam.call(fn,st,canvas,pid,thumb=True,sp=T.STACK-0x1000)
        self.assertEqual((cam.w(canvas+0x24),cam.w(canvas+0x2c)),(3008,2000))
        self.assertEqual(cam.written,cam.written_baseline);cam.assert_tables(self);self.assertEqual(cam.misaligned,[])

    def test_apply_requires_installed_dynamic_menu_row(self):
        cam=self.boot();cam.geometry();cam.put(cam.row()+L.ROW['ON'],0)
        before=cam.snapshot()
        self.assertEqual(cam.apply(),9)
        self.assertEqual(cam.w(cam.service()+16),0)
        self.assertEqual(cam.snapshot(),before)
        self.assertEqual(cam.lv,[])
    def test_mode_and_geometry_updates_keep_one_entry_and_immutable_assets(self):
        cam=self.boot();cam.geometry();self.assertEqual(cam.apply(),0)
        oldpack=cam.w(cam.row()+L.ROW['PACK']);oldlen=cam.w(cam.row()+L.ROW['PACKLEN'])
        old=bytes(cam.mu.mem_read(oldpack,oldlen));menu=cam.w(cam.row()+L.ROW['MROW'])
        for mode,w,h,bh,bv in ((139,2000,1334,1,1),(7,2000,1124,3,1),(98,2000,1000,1,1)):
            cam.geometry(mode,w,h,bh,bv);self.assertEqual(cam.apply(),0)
            self.assertEqual(cam.w(cam.s()+L.S['NROWS']),1)
            self.assertEqual(cam.w(cam.row()+L.ROW['MROW']),menu)
            self.assertEqual(bytes(cam.mu.mem_read(oldpack,oldlen)),old)
            self.assertEqual((cam.w(cam.row()+L.ROW['AW']),cam.w(cam.row()+L.ROW['AH'])),(w,h))
        self.assertEqual(cam.w(cam.service()+16),4);cam.assert_tables(self)
    def test_reapplying_same_recipe_reuses_assets(self):
        cam=self.boot();cam.geometry();self.assertEqual(cam.apply(),0)
        used=cam.w(cam.service()+36);pack=cam.w(cam.row()+L.ROW['PACK'])
        for _ in range(4):self.assertEqual(cam.apply(),0)
        self.assertEqual(cam.w(cam.service()+36),used);self.assertEqual(cam.w(cam.service()+32),1)
        self.assertEqual(cam.w(cam.row()+L.ROW['PACK']),pack)
    def test_recording_guards_preserve_active_recipe(self):
        for addr in (0xC347E08f,0xC358E140,0xC35A952c):
            with self.subTest(addr=addr):
                cam=self.boot();cam.geometry();self.assertEqual(cam.apply(),0);old=cam.snapshot()
                cam.geometry(w=1920,h=1080);cam.put(addr,1);self.assertEqual(cam.apply(),4)
                self.assertEqual(cam.snapshot(),old);self.assertEqual(cam.w(cam.service()+16),1)
    def test_busy_during_stop_restarts_without_commit(self):
        cam=self.boot();cam.geometry();self.assertEqual(cam.apply(),0);old=cam.snapshot()
        cam.running=True;cam.inject_busy=True;cam.geometry(w=1920,h=1080)
        self.assertEqual(cam.apply(),4);self.assertEqual(cam.snapshot(),old)
        self.assertEqual(cam.lv,[('schedule',6),'LV_STOP','LV_START',('schedule',3)])
    def test_live_view_stop_commit_start_and_uhd_setter(self):
        cam=self.boot(res=3);cam.running=True;cam.geometry(w=1920,h=1080)
        self.assertEqual(cam.apply(),0);self.assertEqual(cam.res,2)
        self.assertEqual(cam.lv,[('schedule',6),'LV_STOP','LV_START',('schedule',3)])
        self.assertIn('SET_RES',cam.calls);self.assertEqual(cam.w(cam.s()+L.S['FLAG']),1)
    def test_invalid_geometry_raw14_rate_and_format(self):
        for kw,mode,w,result in (({},98,3007,5),({},100,3008,5),({'fr':7},98,3008,7),({'fmt':1},98,3008,8)):
            with self.subTest(kw=kw,mode=mode,w=w):
                cam=self.boot(**kw);old=cam.snapshot();cam.geometry(mode,w,2000)
                self.assertEqual(cam.apply(),result);self.assertEqual(cam.snapshot(),old)
    def test_registry_supports_more_than_two_providers_without_table_growth(self):
        cam=self.boot();base=T.STACK-0x9000;provider=self.f['functions']['rl_virtual_build']+cam.block
        for i in range(15):
            cam.mu.mem_write(base,struct.pack('<8I',32,VRC_ABI,0x1000+i,0,cam.m(),provider,0,0))
            self.assertEqual(cam.dispatch(1,base),0)
        self.assertEqual(cam.w(cam.service()+28),16);self.assertEqual(cam.w(cam.s()+L.S['NROWS']),1)
        cam.mu.mem_write(base,struct.pack('<8I',32,VRC_ABI,0x7777,0,cam.m(),provider,0,0));self.assertEqual(cam.dispatch(1,base),3)
        cam.geometry(w=1920,h=1080);self.assertEqual(cam.dispatch(2,0x1002),0)
        self.assertEqual(cam.w(cam.service()+12),0x1002);self.assertEqual(cam.w(cam.s()+L.S['NROWS']),1)
        # Existing owner's registration is idempotent; another owner cannot steal it.
        cam.mu.mem_write(base,struct.pack('<8I',32,VRC_ABI,0x1002,0,cam.m()+4,provider,0,0));self.assertEqual(cam.dispatch(1,base),2)
        self.assertEqual(cam.dispatch(2,0xdeadbeef),2)
    def test_static_format_remains_available_after_dynamic_rebuild(self):
        rcd=RC.built()['RESCUS/OG2K.RCD'][0]
        cam=self.boot(rcds={'OG2K.RCD':rcd});st=cam.s();row=st+cam.w(st+L.S['ROWS'])
        fields=('ENUM','LABEL','AW','AH','MROW','QSID','PACK','PACKLEN')
        before=tuple(cam.w(row+L.ROW[x]) for x in fields)
        for mode,w,h in ((98,3008,2000),(139,1920,1080)):
            cam.geometry(mode,w,h);self.assertEqual(cam.apply(),0)
            self.assertEqual(cam.w(st+L.S['NROWS']),2)
            self.assertEqual(tuple(cam.w(row+L.ROW[x]) for x in fields),before)
            cam.mu.mem_write(RC.KEYBUF,b'OG2K60\0'.ljust(16,b'\0'))
            hit,_=cam.call(RC.PICKER,r1=RC.TAB3,r2=RC.KEYBUF)
            self.assertNotEqual(hit,0);self.assertIn(cam.w(hit+4),L.VPID_POOL)
        cam.assert_tables(self)
    def test_memory_budget_failure_and_reentrancy_preserve_recipe(self):
        cam=self.boot();cam.geometry();self.assertEqual(cam.apply(),0);old=cam.snapshot()
        cam.put(cam.service()+32,32);cam.geometry(w=1920,h=1080);self.assertEqual(cam.apply(),3)
        self.assertEqual(cam.snapshot(),old);cam.put(cam.service()+8,1);self.assertEqual(cam.apply(),10)
        self.assertEqual(cam.snapshot(),old)
    def test_allocation_failure_and_busy_at_commit_preserve_recipe(self):
        for failure in ('fail_assets','busy_on_alloc'):
            with self.subTest(failure=failure):
                cam=self.boot();cam.geometry();self.assertEqual(cam.apply(),0);old=cam.snapshot()
                cam.running=True;cam.geometry(w=1920,h=1080);setattr(cam,failure,True)
                self.assertEqual(cam.apply(),3 if failure=='fail_assets' else 4)
                self.assertEqual(cam.snapshot(),old);self.assertEqual(cam.w(cam.service()+16),1)
                self.assertEqual(cam.w(cam.service()+32),1)
                self.assertEqual(cam.lv,[('schedule',6),'LV_STOP','LV_START',('schedule',3)])
    def test_memory_recipe_is_not_restored_from_saved_row_identity(self):
        record=RC.CoreTests.record(self,'VRC000')
        cam=self.boot(record=record)
        self.assertEqual(cam.w(cam.s()+L.S['SEL']),0)
        self.assertEqual(cam.w(cam.service()+16),0)
        cam.geometry();self.assertEqual(cam.apply(),0)
    def test_contract_abi_and_status(self):
        cam=self.boot();arg=T.STACK-0x9000
        cam.mu.mem_write(arg,struct.pack('<8I',32,99,0,0,0,0,0,0))
        self.assertEqual(cam.dispatch(1,arg),1);self.assertEqual(cam.dispatch(3,arg),1)
        self.assertEqual(cam.dispatch(99,0),1)
        cam.geometry();self.assertEqual(cam.apply(),0)
        cam.mu.mem_write(arg,struct.pack('<8I',32,VRC_ABI,0,0,0,0,0,0))
        self.assertEqual(cam.dispatch(3,arg),0)
        got=struct.unpack('<8I',bytes(cam.mu.mem_read(arg,32)))
        self.assertEqual(got[2:7],(0x42414c52,1,0,0,1));self.assertGreater(got[7],0)
    def test_missing_consumer_is_unavailable_and_keeps_stock_page(self):
        sups=[(p.name,p.read_bytes()) for p in (self.out/'fpSup').glob('*.BIN') if p.name not in ('LOADER.BIN','32RESCUS.BIN')]
        files,dirs=T.card(*sups);files['\\fpSup\\LOADER.BIN']=(self.out/'fpSup/LOADER.BIN').read_bytes()
        cam=Cam(files,dirs,self.f)
        for a,v in T.B.loader_words((self.out/'AutoRun.txt').read_bytes()).items():cam.put(a,v)
        cam.boot();self.assertIsNone(cam.core_block);self.assertIsNotNone(cam.block)
        cam.prepare();cam.geometry();self.assertEqual(cam.apply(),9)
        self.assertEqual(cam.w(RL.ENTRIES+8),0x19c130)
        self.assertEqual(cam.cstr(cam.m()+self.f['state_fields']['export_text']),'Unavailable')
    def test_real_apply_key_callback(self):
        cam=self.boot();cam.geometry();desc=cam.vars['SL_O_Key'];cam.put(desc+8,21)
        cam.call(cam.subs['SL_O_Key'],desc,thumb=True,sp=T.STACK-0x1000)
        self.assertEqual(cam.w(desc+8),0);self.assertEqual(cam.w(cam.service()+16),1);self.assertEqual(cam.written,cam.written_baseline)
    def test_bad_checksum_rejected_without_changing_active_tables(self):
        cam=self.boot();cam.geometry();self.assertEqual(cam.apply(),0);old=cam.snapshot()
        size=cam.w(cam.block+self.f['tab_off']+19*4)
        blob=bytearray(cam.mu.mem_read(cam.block+self.f['export_off'],size));blob[0x10]^=1
        ident=cam.blob_provider(blob)
        self.assertEqual(cam.dispatch(2,ident),6)
        self.assertEqual(cam.w(cam.service()+24),L.RCD_WHY['SUM'])
        self.assertEqual(cam.snapshot(),old);self.assertEqual(cam.w(cam.service()+16),1)
    def test_settings_alias_and_recording_page_preservation(self):
        cam=self.boot();entry=cam.w(RL.ENTRIES+8)
        self.assertNotEqual(entry,cam.get('page')-RL.NBU)
        cam.by_addr[0xC0564638]='GUI_NATIVE';cam.mu.mem_write(0xC0564638,struct.pack('<I',0xe12fff1e))
        # The real two-layer GUI hooks resolve the common alias, not a Res Lab
        # specific consumer path. Intercept only the native fallback body.
        names=RL.NAMES+0x200
        for name,expect in (('VRC_SETTINGS',36),('SL_LAB',36)):
            cam.mu.mem_write(names,name.encode()+b'\0');cam.mu.reg_write(UC_ARM_REG_R1,names)
            cam.mu.reg_write(UC_ARM_REG_SP,T.STACK-0x1000)
            cam.mu.emu_start(0xC056461c,0xC0564620,count=20000)
            if cam.error:raise cam.error
            self.assertEqual(cam.r(UC_ARM_REG_R0),expect)
        for name,unavailable in (('OriginalPage',False),('VRC_SETTINGS',True)):
            if unavailable:cam.put(cam.service()+28,0)
            cam.mu.mem_write(names,name.encode()+b'\0');cam.mu.reg_write(UC_ARM_REG_R1,names)
            cam.mu.reg_write(UC_ARM_REG_SP,T.STACK-0x1000)
            cam.mu.emu_start(0xC056461c,0xC0564620,count=20000)
            if cam.error:raise cam.error
            self.assertEqual(cam.r(UC_ARM_REG_R0),0x77)
        self.assertEqual(cam.gui_names,['OriginalPage','SetupHelpMenu'])
        self.assertEqual(cam.w(RL.ENTRIES+8),entry)
    def test_settings_open_uses_both_native_requests_and_preserves_recording(self):
        cam=self.boot();old=cam.snapshot()
        self.assertEqual(cam.dispatch(4,0),0)
        self.assertEqual(cam.gui_requests,['SL_LAB'])
        self.assertEqual(cam.view_requests,[(cam.get('app'),'SL_LAB')])
        self.assertEqual(cam.snapshot(),old)
        cam.put(0xC347E08c,0x01000000)
        self.assertEqual(cam.dispatch(4,0),4)
        self.assertEqual(len(cam.view_requests),1)
    def test_settings_unavailable_and_native_refusal_are_reported(self):
        cam=self.boot();cam.put(cam.m()+self.f['state_fields']['pages_state'],0)
        self.assertEqual(cam.dispatch(4,0),9);self.assertEqual(cam.view_requests,[])
        cam.put(cam.m()+self.f['state_fields']['pages_state'],1);cam.request_result=2
        self.assertEqual(cam.dispatch(4,0),9)
    def test_shutdown_restores_claimed_words(self):
        cam=self.boot();cam.geometry();self.assertEqual(cam.apply(),0);cam.power_off()
        for a in [int(h['site'],16) for h in cam.cf['hooks']]+[0xC05E82f0,0xC06BDA3c]:self.assertEqual(cam.w(a),T.word(cam.img,a))
        cam.assert_tables(self)

class NativeUI(unittest.TestCase):
    def test_save_command_is_not_bound_to_button_value(self):
        import sl_b25_page as P, sl_lab_page as LAB, sl_size_page as SZ
        saved=LAB.CALC_ONLY,LAB.VIRTUAL_APPLY
        LAB.CALC_ONLY=LAB.VIRTUAL_APPLY=True
        try:
            image=T.IMAGE.read_bytes()
            pool=RL.calculator_pool()
            refs=[]
            page,ar=SZ.assemble(LAB.build_lab_page(image,pool,refs),refs)
            SZ.check_refs(page,ar,pool)
            records=[r.to_bytes() for r in P.N.split(page)]
            owners=[];owner=None
            for d in records:
                if P.u32(d,0)==0x10003:owner=P.u32(d,20)
                if P.u32(d,0)==0x10009 and len(d)==46 and pool.text(P.u32(d,8))=='controlAppVariable' and pool.text(P.u32(d,36))=='SL_O_Key' and pool.text(P.u32(d,41))=='20':owners.append(owner)
            self.assertEqual(len(owners),2);self.assertEqual(len(set(owners)),1)
            objects=SZ.objects(P.N.split(page),pool)
            root=owners[0]
            while objects[root]['parent']!=LAB.OUTPUT_TAB:root=objects[root]['parent']
            subtree=SZ.subtree(objects,root);bound=False
            schemas=P.load_schemas(image)
            for d in records:
                if P.u32(d,0)==0x10003:owner=P.u32(d,20)
                if owner not in subtree:continue
                texts=[pool.text(P.u32(d,o)) for o,k in P.typed_fields(d,pool,schemas) if k in ('str','text')]
                bound |= 'SL_E_Button' in texts
                if 'SL_O_Key' in texts:
                    self.assertEqual(P.u32(d,0),0x10009)
                    self.assertEqual(pool.text(P.u32(d,8)),'controlAppVariable')
            self.assertTrue(bound)
        finally:LAB.CALC_ONLY,LAB.VIRTUAL_APPLY=saved

    """Production ui_apply.c on the stock page, compared to the typed model.
    This tests the common Help action that the ARM fixture abstracts out.
    """
    def test_tool_settings_return_to_manager_with_native_state_machine(self):
        import sl_pages as PG
        card, facts = built()
        blob = (card/'fpSup'/json.loads((card/'build.json').read_text())['file']).read_bytes()
        at = facts['area_off'] + 4096
        menu = blob[at:at + facts['slmp_bytes']]
        header = struct.unpack_from('<9I', menu)
        pages_at = (36 + header[2] + header[3] + header[4]*8 + 3) & ~3
        pages_at = (pages_at + header[7] + 3) & ~3
        pages = menu[pages_at:pages_at + header[8]]
        queries = [('FT_LIST','SL_LAB'), ('FT_Y6','SL_LAB'),
                   ('SL_LAB','Return'), ('FT_LIST','Return')]
        matches = PG.native_switch(pages, queries)
        self.assertEqual(matches[queries[0]], ('SL_LAB',0))
        self.assertEqual(matches[queries[1]], ('SL_LAB',0))
        self.assertEqual(matches[queries[2]], ('FT_LIST',0))
        self.assertIsNone(matches[queries[3]])

    def test_settings_page_matches_reference_and_keeps_rate_variants(self):
        sys.path.insert(0,str(RC.UISHARE))
        import test_ui_apply as U
        import sl_b25_page as SP
        from ui import fpui,options as O
        with tempfile.TemporaryDirectory(prefix='vrc-ui-') as tmp:
            cam=U.Camera(U.build(tmp));img=O.image();a,off,n=O.resource_set('B2_5')
            pool=fpui.Strings(img[SP.U.POOL_START-SP.B:SP.U.POOL_START-SP.B+SP.U.POOL_SIZE])
            pages={'B2_5':fpui.PageCopy(O.at(img,a,n),n,1)}
            files=fpui.Files(lambda at,ln:O.at(img,at,ln))
            tpl,_=RC.rcd.ui_template(virtual=True)
            # Exercise real ui_apply on five ordinary rows plus Custom.
            # A fixed Help guard previously let only the first row install.
            for i in range(6):
                title='Custom' if i==5 else 'Static'+str(i)
                label='VRC000' if i==5 else 'F'+str(i)
                blob=RC.rcd.ui_block(tpl,{'row_text':title,'summary':title,'label':label},0xC072EE00+4*i)
                fpui.apply(blob,pages,pool,files)
                code,out=cam.apply(blob);self.assertEqual(code,0);self.assertEqual(out[5],2+i)
                data,hdr,p=cam.page('B2_5');self.assertEqual(data,bytes(pages['B2_5'].data))
            self.assertTrue(cam.pool_untouched());self.assertEqual(cam.get(U.NBU_WRITES),0)
            owner=None;actions=[];stock_actions=[]
            for records,target,resolve in ((SP.N.split(data),actions,lambda i:cam.text(i) or pool.text(i)),(SP.N.split(O.at(img,a,n)),stock_actions,lambda i:pool.text(i))):
                for rec in records:
                    d=rec.to_bytes()
                    if SP.u32(d,0)==0x10003:owner=SP.u32(d,20)
                    if SP.u32(d,0)==0x10009 and len(d)==41 and resolve(SP.u32(d,8))=='controlAppState':
                        if SP.u32(d,36)==0xffffffff:continue
                        value=resolve(SP.u32(d,36))
                        if owner==SP.HELP_ROW and SP.u32(d,24)==SP.HELP_KEY:
                            target.append(('help',value))
                        elif value.startswith('B2_5_5'):target.append(('rate',value))
            self.assertEqual([x for x in actions if x[0]=='help'],[x for x in stock_actions if x[0]=='help'])
            self.assertEqual([x for x in actions if x[0]=='rate'],[x for x in stock_actions if x[0]=='rate'])

if __name__=='__main__':unittest.main()
