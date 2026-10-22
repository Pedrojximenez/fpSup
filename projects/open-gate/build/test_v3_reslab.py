"""Real calculator ARM/loader/encoder, modeled OS/storage/modelCSV, no camera."""
import json,os,pathlib,struct,subprocess,sys,tempfile,unittest
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path[:0]=[str(HERE/'res-custom'),str(ROOT/'fpSup/fp_usb_shell/v3'),str(HERE),str(ROOT/'research/ui/tools')]
import test_v3 as T
import test_v3_rescustom as RC
import ogc_layout as L
import rcd,nbr
from xci import decode as decode_xci
from unicorn import UC_HOOK_MEM_WRITE
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R11,UC_ARM_REG_SP,UC_ARM_REG_LR
UI=0x48000000
APP,SCREEN,READER,ENTRIES,NAMES,DESCS,MODEL,IFACE=[UI+x for x in (0,0x1000,0x2000,0x3000,0x4000,0x8000,0xc000,0xd000)]
NBU=0xC18C0460
NATIVES={0xC05DB418:'lookup',0xC05DB308:'reg',0xC05E0320:'find',0xC05D8BD8:'count',0xC05D8B78:'load',0xC05D8BF8:'get',0xC05D8358:'iface',0xC05D83A8:'notify',0xC05F4860:'rows',0xC05F4878:'current',0xC05F4928:'string',0xC05F4940:'insert',0xC05F4958:'delete',0xC05E84D8:'nbr',0xC0560FB0:'subscribe',0xC0593F30:'post',0xC0593FE0:'text',0xC002B920:'tick'}
_CACHE={}
def calculator_pool():
    """Use the builder's actual preceding B2_5 strings and SL_LAB reservation.

    An empty private pool gives different offsets; one then happens to equal
    an unaligned word in the stock 0x11009 table and trips the bytewise guard.
    Keep the full guard and test the pool layout that is actually delivered.
    """
    import sl_b25_page as P
    names=('WITH_LAB_JUMP','WITH_CLONES','WITH_CUSTOM_LISTS','WITH_PRIVATE_LISTS')
    saved=[getattr(P,n) for n in names]
    try:
        for n,v in zip(names,(False,False,False,True)):setattr(P,n,v)
        pool=P.build()['pool'];pool.intern('SL_LAB');return pool
    finally:
        for n,v in zip(names,saved):setattr(P,n,v)

def built():
    if not _CACHE:
        saved=os.environ.get('RESLAB_V3_CARD')
        out=pathlib.Path(saved) if saved else pathlib.Path(tempfile.mkdtemp(prefix='rlcalc-test-'))/'out'
        if not saved:
            r=subprocess.run([sys.executable,'-B',str(HERE/'build_v3_reslab.py'),'--out',str(out),'--card','--no-shell'],capture_output=True,text=True)
            if r.returncode:raise RuntimeError(r.stdout+r.stderr)
        meta=json.loads((out/'build.json').read_text())
        _CACHE.update(sup=(out/'fpSup'/meta['file']).read_bytes(),facts=meta['facts'],out=out,name=meta['file'])
    return _CACHE['sup'],_CACHE['facts']
class Cam(T.Camera):
    def __init__(self,files,dirs,f,nbr_fail=False,write_fail=False,damage=False,tail=False,**kw):
        super().__init__(files,dirs,**kw);self.f,self.block=f,None
        self.vars,self.subs,self.model,self.cur,self.packs={}, {}, [['']*6],0,[]
        self.text_events=[]
        self.nbr_fail,self.write_fail,self.damage,self.tail=nbr_fail,write_fail,damage,tail
        self.test_code=set()
        RC.Cam.build_descriptor(self);self.mu.mem_map(UI,0x20000)
        for a,v in ((0xC37B7048,APP),(APP+0x80,1),(APP+0x84,512),(APP+0x8c,APP+0x100),(APP+0x100,SCREEN),(APP+0xf8,1),(APP+0xfc,24),(APP+0x888,APP+0x800)):self.put(a,v)
        self.mu.mem_write(NAMES,b'MainB2\0');self.mu.mem_write(NAMES+0x40,b'B2_5\0')
        for off,val in ((4,APP),(8,NAMES),(0x24,READER)):self.put(SCREEN+off,val)
        for off,val in ((8,APP),(0x10,176152),(0x14,NBU+0x14),(0x24,NBU),(0xa8,1),(0xac,ENTRIES)):self.put(READER+off,val)
        self.put(ENTRIES+4,NAMES+0x40);self.put(ENTRIES+8,0x19c130)
        for off,fn in ((0x14,0xC05F4861),(0x18,0xC05F4879),(0x30,0xC05F4929),(0x34,0xC05F4941),(0x38,0xC05F4959)):self.put(IFACE+off,fn)
        for at,name in NATIVES.items():
            self.mu.mem_write(at,struct.pack('<H',0x4770) if at>=0xC05D0000 else struct.pack('<I',0xe12fff1e));self.by_addr[at]=('UI',name)
        self.sensitive=bytes(self.mu.mem_read(0xC0B00000,0x200000))
    def _alloc(self,n,align=8):
        p=super()._alloc(n,align)
        if n==self.f['block']:self.block=p
        return p
    def _hook(self,mu,addr,size,data):
        name=self.by_addr.get(addr)
        if 0xC0000000 <= addr < 0xC3000000 and not 0xC072D000 <= addr < 0xC0740000 and name is None and addr not in self.test_code:
            raise AssertionError(f'unmodeled firmware execution {addr:#x}')
        a=[self.r(r) for r in (UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3)]
        if isinstance(name,tuple) and name[0]=='UI':
            n=name[1];self.calls.append(n)
            if self.r(UC_ARM_REG_SP)&7:self.misaligned.append(n)
            if n=='lookup':self.put(a[2],self.vars.get(self.cstr(a[1]),0))
            elif n=='reg':
                kind,nm,v=struct.unpack('<3I',mu.mem_read(a[2],12));d=DESCS+32*len(self.vars);self.vars[self.cstr(nm)]=d
                for off,x in ((0,kind),(4,nm),(8,v)):self.put(d+off,x)
            elif n=='find':self.put(a[2],MODEL)
            elif n=='count':self.put(a[1],1)
            elif n=='get':self.put(a[1],MODEL)
            elif n=='iface':self.put(a[1],IFACE)
            elif n=='rows':self.put(a[1],len(self.model))
            elif n=='current':self.cur=a[1]
            elif n=='string':self.model[self.cur][a[1]]=self.cstr(a[2])
            elif n=='insert':self.model.insert(a[1],['']*6)
            elif n=='delete':del self.model[a[1]:a[1]+a[2]]
            elif n=='nbr':
                if self.nbr_fail:return self._ret(1)
                self.packs.append(bytes(mu.mem_read(a[1],a[2])));rd=UI+0xe000;self.put(rd+8,APP)
                if a[3]:self.put(a[3],rd)
            elif n=='subscribe':self.subs[self.cstr(a[1])]=a[2]
            elif n in ('post','text'):
                if n=='text':self.text_events.append((self.cstr(a[1]),self.cstr(a[2])))
                if self.cstr(a[1]) in self.vars:self.put(self.vars[self.cstr(a[1])]+8,a[2])
            elif n=='tick':return self._ret(1000)
            return self._ret(0)
        if name=='F_OPEN' and a[2]==1 and self.cstr(a[1]) in self.written:self.files[self.cstr(a[1])]=self.written[self.cstr(a[1])]
        if name=='F_WRITE' and self.fobj[a[0]][0].endswith('.RCD'):
            path=self.fobj[a[0]][0]
            if self.write_fail:return self._ret(0)
            result=super()._hook(mu,addr,size,data);blob=self.written[path]
            if self.damage:blob=blob[:16]+bytes([blob[16]^1])+blob[17:]
            if self.tail:blob+=b'\0'
            self.written[path]=blob;self.dirs['\\fpSup\\RESCUS'].append((path.rsplit('\\',1)[-1],0x20,len(blob)))
            return result
        return super()._hook(mu,addr,size,data)
    def fn(self,name):return self.block+self.f['functions'][name]
    def m(self):return self.block+self.f['state_off']
    def set(self,name,v):self.put(self.m()+self.f['state_fields'][name],v)
    def get(self,name):return self.w(self.m()+self.f['state_fields'][name])
    def prepare(self):self.call(self.fn('rl_prepare'),self.m(),thumb=True,sp=T.STACK-0x1000)
    def geometry(self,mode=98,w=3008,h=2000,bh=1,bv=1):
        for nm,val in (('modes_rows',1),('mode_sel',0),('out_w',w),('out_h',h),('bin_h',bh),('bin_v',bv),('axis_armed',1)):self.set(nm,val)
        self.mu.mem_write(self.m()+self.f['state_fields']['mode_ids'],bytes([mode]));i=self.modes.index(mode);row=0xC0B59DC0+100*i
        for nm,off in (('ro_w',4),('ro_h',8),('ro_sx',0x4c),('ro_sy',0x50)):self.set(nm,self.w(row+off))
        if 'output_policy' in self.f['state_fields']:
            policy=int(self.get('ro_sx')==self.get('ro_sy'))
            for nm,val in (('output_policy',policy),('ratio',policy),('lock_num',w),('lock_den',h)):self.set(nm,val)
            self.put(self.vars['MV_SLScale']+8,policy)
        self.call(self.fn('sl_modes__panel_post'),self.m(),thumb=True,sp=T.STACK-0x1000)
    def export(self):return self.call(self.fn('sl_menu_export'),self.m(),thumb=True,sp=T.STACK-0x1000)[0]
class CalculatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.sup,cls.f=built()
    def boot(self,existing=(),extra=(),**kw):
        shell=_CACHE['out']/'fpSup/00SHELL.BIN'
        extras=list(extra)
        if shell.exists():extras.insert(0,('00SHELL.BIN',shell.read_bytes()))
        files,dirs=T.card(*extras,(_CACHE['name'],self.sup));files['\\fpSup\\LOADER.BIN']=(_CACHE['out']/'fpSup/LOADER.BIN').read_bytes();dirs['\\fpSup\\RESCUS']=list(existing)
        cam=Cam(files,dirs,self.f,**kw)
        for a,v in T.B.loader_words((_CACHE['out']/'AutoRun.txt').read_bytes()).items():cam.put(a,v)
        cam.fw_writes=[]
        cam.mu.hook_add(UC_HOOK_MEM_WRITE,lambda mu,access,a,n,v,d:cam.fw_writes.append((a,n)) if 0xC0000000<=a<0xC3000000 and not 0xC072D000<=a<0xC0740000 else None)
        cam.boot();self.assertEqual(cam.misaligned,[])
        if shell.exists():self.assertEqual(len(cam.tasks),1,'debug shell entry creates its worker and returns')
        return cam
    def test_no_recording_core_and_restoration(self):
        cam=self.boot()
        # A debug shell can deliberately repair stock words during its entry;
        # isolate the calculator's writes after all Sup entries have returned.
        sensitive=bytes(cam.mu.mem_read(0xC0B00000,0x200000))
        if not cam.tasks:self.assertEqual(sensitive,cam.sensitive,'calculator entry leaves sensor tables unchanged')
        cam.prepare();cam.geometry();cam.export()
        self.assertEqual(bytes(cam.mu.mem_read(0xC0B00000,0x200000)),sensitive)
        for a in (0xC043CCF8,0xC005C020,0xC057A6A0,0xC05824D0,0xC032DDF0):self.assertEqual(cam.w(a),T.word(cam.img,a))
        self.assertEqual(self.f['core_hooks'],[]);self.assertEqual(self.f['pointer_pairs'],[])
        covered={a+i for a,n,_ in cam.journal() for i in range(n)}
        self.assertFalse([(a,n) for a,n in cam.fw_writes if any(a+i not in covered for i in range(n))])
        for _ in range(2):
            cam.power_off()
            for a in (0xC056461C,0xC05E82F0):self.assertEqual(cam.w(a),T.word(cam.img,a))
    def test_registers_and_calculates_without_camera_settings(self):
        cam=self.boot();cam.prepare();self.assertEqual(cam.get('pages_state'),1);self.assertEqual(len(cam.packs),2);self.assertGreater(len(cam.model),40)
        self.assertNotIn('SL_RATE',repr(cam.packs));self.assertNotIn('SL_BIT',repr(cam.packs));self.assertIn('SL_O_Key',cam.subs);self.assertNotIn('settings',cam.calls)
    def test_export_and_numbering(self):
        cam=self.boot(existing=[('lab001.rcd',0x20,123)]);cam.prepare();cam.geometry();self.assertEqual(cam.export(),1)
        out=rcd.decode(cam.written['\\fpSup\\RESCUS\\LAB002.RCD'],image=cam.img,stock_ids=set(cam.modes))
        self.assertEqual(out['label'],'LAB002');self.assertEqual(out['act'],(3008,2000));self.assertEqual(out['modes'],[(98,7884,445,0,4)])
        self.assertEqual(out['profile'],83);self.assertEqual(out['enum'],0x524c0002);self.assertEqual(out['maxrate'],7884)
        self.assertEqual(out['bit_depths'],(8,10,12))
        self.assertEqual(dict(out['canvas_rec'])[0x24],3008);self.assertEqual(cam.export(),1);self.assertIn('\\fpSup\\RESCUS\\LAB003.RCD',cam.written)
    def test_geometry_and_assets_at_several_sizes(self):
        for mode,w,h,bh,bv in ((98,1920,1080,1,1),(139,2000,1334,1,1),(7,2000,1124,3,1),(98,992,992,1,1),(98,2000,1000,1,1)):
            with self.subTest(mode=mode,w=w,h=h):
                cam=self.boot();cam.prepare();cam.geometry(mode,w,h,bh,bv);self.assertEqual(cam.export(),1)
                blob=cam.written['\\fpSup\\RESCUS\\LAB001.RCD'];out=rcd.decode(blob,image=cam.img,stock_ids=set(cam.modes));po,ln=out['pack'];pack=blob[po:po+ln];inv=nbr.inspect(pack)
                if (w,h)==(2000,1000):self.assertEqual(out['aspect'],9)
                names={x['name'] for x in inv['resources']};self.assertTrue({'LAB001_QS','LAB001_SET','LAB001_FONT',f'font_S_imageSize_{w}',f'font_S_imageSize_{h}'}<=names)
                for f in inv['files']:
                    iw,ih,l,a=decode_xci(pack[f['offset']:f['offset']+f['bytes']]);self.assertEqual(l.shape,(ih,iw));self.assertGreater(a.sum(),0)
    def test_save_key_callback_exports_and_resets_key(self):
        cam=self.boot();cam.prepare();cam.geometry()
        desc=cam.vars['SL_O_Key'];cam.put(desc+8,20)
        cam.call(cam.subs['SL_O_Key'],r0=desc,thumb=True,sp=T.STACK-0x1000)
        self.assertEqual(cam.w(desc+8),0);self.assertEqual(cam.cstr(cam.m()+self.f['state_fields']['export_text']),'Saved LAB001.RCD')
        self.assertEqual(rcd.decode(cam.written['\\fpSup\\RESCUS\\LAB001.RCD'])['act'],(3008,2000));self.assertEqual(cam.misaligned,[])
    def test_native_calculator_page_and_save_action(self):
        import sl_b25_page as P,sl_lab_page as LAB,sl_size_page as SZ
        LAB.CALC_ONLY=True
        try:
            pool=P.Pool(T.IMAGE.read_bytes()[P.U.POOL_START-P.B:P.U.POOL_START-P.B+P.U.POOL_SIZE]);refs=[]
            page,ar=SZ.assemble(LAB.build_lab_page(T.IMAGE.read_bytes(),pool,refs),refs)
            shape=LAB.check_page(page,pool,T.IMAGE.read_bytes());SZ.check_refs(page,ar,pool)
            self.assertNotIn(LAB.NAME_TAB,shape['objects'])
            seq=[r.to_bytes() for r in P.N.split(page)];owner=None;save_owner=None;saves=[]
            for d in seq:
                if P.u32(d,0)==0x10003:owner=P.u32(d,20)
                if P.u32(d,0)==0x10005 and pool.text(P.u32(d,8))=='drawText' and pool.text(P.u32(d,32))=='Save RCD':save_owner=owner
                if P.u32(d,0)==0x10009 and len(d)==46 and pool.text(P.u32(d,8))=='controlAppVariable' and pool.text(P.u32(d,36))=='SL_O_Key' and pool.text(P.u32(d,41))=='20':saves.append(owner)
            self.assertIsNotNone(save_owner);self.assertEqual(len(saves),2);self.assertEqual(len(set(saves)),1)
        finally:LAB.CALC_ONLY=False
    def test_invalid_geometry_and_missing_directory_fail(self):
        cam=self.boot();cam.prepare();cam.geometry(w=3007);self.assertEqual(cam.export(),4);self.assertFalse(any(p.endswith('.RCD') for p in cam.written))
        cam=self.boot();cam.prepare();cam.geometry();del cam.dirs['\\fpSup\\RESCUS'];self.assertEqual(cam.export(),2)
    def test_raw14_remains_calculable_but_cannot_export(self):
        cam=self.boot();cam.prepare();cam.geometry(mode=100)
        self.assertEqual(cam.get('canvas_valid'),1);self.assertEqual(cam.export(),6)
        self.assertEqual(cam.cstr(cam.m()+self.f['state_fields']['export_text']),'14-bit unsupported')
        cam.geometry(w=3007);self.assertEqual(cam.export(),4)
        self.assertFalse(any(p.endswith('.RCD') for p in cam.written))
    def test_short_write_corruption_and_trailing_bytes_fail(self):
        for kw in ({'write_fail':True},{'damage':True},{'tail':True}):
            with self.subTest(kw=kw):
                cam=self.boot(**kw);cam.prepare();cam.geometry();self.assertEqual(cam.export(),5)
    def test_nbr_refusal_restores_navigation(self):
        cam=self.boot(nbr_fail=True);cam.prepare();self.assertEqual(cam.w(ENTRIES+8),0x19c130);self.assertNotIn('SL_O_Key',cam.subs)
    def test_exclusive_conflict_does_not_arm(self):
        held=T.test_sup('BUSY',[(0xC05E82F0,T.word(T.IMAGE.read_bytes(),0xC05E82F0),2,0)])
        cam=self.boot(extra=[('01BUSY.BIN',held)]);self.assertEqual(cam.w(0xC056461C),T.word(cam.img,0xC056461C));self.assertEqual(cam.w(ENTRIES+8),0x19c130)
    def test_warm_hook_repair_and_real_page_hook_abi(self):
        cam=self.boot(stale={0xC056461C:0xe12fff1e,0xC05E82F0:0xffffffff})
        # Model only the native page body as its matching epilogue. The actual
        # hook, prepare, stock push replay, and register/stack handling run.
        cam.mu.mem_write(0xC05E82F4,struct.pack('<HH',0xe8bd,0x88f0));cam.test_code.update((0xC05E82F0,0xC05E82F4,0xC056461C))
        regs=(UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R11)
        for i,r in enumerate(regs):cam.mu.reg_write(r,0x12340000+i)
        out,sp=cam.call(0xC05E82F0,r0=0x123,r1=0x456,r2=0x789,thumb=True)
        self.assertEqual((out,sp),(0x123,T.STACK-0x1004));self.assertEqual(cam.r(UC_ARM_REG_R1),0x456);self.assertEqual(cam.r(UC_ARM_REG_R2),0x789)
        self.assertEqual([cam.r(r) for r in regs],[0x12340000+i for i in range(len(regs))]);self.assertEqual(cam.get('pages_state'),1);self.assertEqual(cam.misaligned,[])
        # The GUI id layer answers private names; stock names reach the next
        # layer through the real BL site, with its original return address.
        cam.mu.mem_write(0xC0564638,struct.pack('<II',0xe3a00077,0xe12fff1e));cam.test_code.update((0xC0564638,0xC056463C))
        for name,expected in (('SL_LAB',36),('B2_5',0x77)):
            cam.mu.mem_write(NAMES+0x200,name.encode()+b'\0');cam.mu.reg_write(UC_ARM_REG_R1,NAMES+0x200)
            cam.mu.emu_start(0xC056461C,0xC0564620,count=400);self.assertEqual(cam.r(UC_ARM_REG_R0),expected)
        cam.power_off()
        for a in (0xC056461C,0xC05E82F0):self.assertEqual(cam.w(a),T.word(cam.img,a))
    def test_rescustom_reads_export_and_uses_virtual_geometry(self):
        lab=self.boot();lab.prepare();lab.geometry();self.assertEqual(lab.export(),1);data=lab.written['\\fpSup\\RESCUS\\LAB001.RCD']
        core,cf=RC.built()['32RESCUS.BIN'];files,dirs=RC.rcd_card('32RESCUS.BIN',core,{'LAB001.RCD':data});cam=RC.Cam(files,dirs,cf);cam.boot()
        st=cam.core_block+cf['img_off']+L.S_COORD-L.LAYOUT0
        self.assertEqual(cam.w(st+L.S['RCD_OK']),1);self.assertEqual(cam.w(st+L.S['NROWS']),1)
        row=st+cam.w(st+L.S['ROWS']);self.assertEqual(cam.cstr(row+L.ROW['LABEL']),'LAB001');self.assertEqual(cam.w(row+L.ROW['AW']),3008);self.assertEqual(cam.w(row+L.ROW['AH']),2000)
        for off in ('SEL','CUR','FLAG'):cam.put(st+L.S[off],1)
        cam.mu.mem_write(RC.KEYBUF,b'LAB00124\0'.ljust(16,b'\0'));r,_=cam.call(RC.PICKER,r1=RC.TAB3,r2=RC.KEYBUF)
        self.assertNotEqual(r,0);pid=cam.w(r+4);self.assertIn(pid,L.VPID_POOL)
        canvas=RC.CANVAS_IN+0x5c;fn=cam.w(st+L.S['FN']+L.FNS.index('CANVAS')*4);cam.call(fn,r0=st,r1=canvas,r2=pid,thumb=bool(fn&1))
        self.assertEqual(cam.w(canvas+0x24),3008);self.assertEqual(cam.w(canvas+0x2c),2000)
if __name__=='__main__':unittest.main()
