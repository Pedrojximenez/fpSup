"""Real ARM filename editing/export, stable filtering and native SAVE navigation."""
import unittest
import test_virtual_rcd as V
import test_v3_reslab as RL
import rcd, nbr
from xci import decode as decode_xci
from unicorn.arm_const import UC_ARM_REG_R1, UC_ARM_REG_R2


class SaveNameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.out,cls.f=V.built()
    def boot(self,**kw):return V.VirtualTests.boot(self,rcds=kw.pop('rcds',{}),**kw)
    def key(self,c,k):self.change(c,'SL_O_Key',k)
    def change(self,c,name,v):
        d=c.vars[name];c.put(d+8,v);c.call(c.subs[name],d,thumb=True,sp=V.T.STACK-0x1000)
    def name(self,c,s):c.mu.mem_write(c.m()+self.f['state_fields']['save_name'],s.encode().ljust(8,b'\0'))
    def geometry(self,c):
        fields=('mode_sel','out_w','out_h','crop_w','crop_h','bin_h','bin_v','bin_kh','bin_kv','bin_mode','output_policy','ratio','lock_num','lock_den')
        return {n:c.get(n) for n in fields}

    def test_name_keys_and_save_do_not_change_geometry_or_active_consumer(self):
        c=self.boot();c.geometry(12,992,662);self.key(c,36)
        before=self.geometry(c);active=c.snapshot();gen=c.w(c.service()+16)
        for k in (65,63,62,64,66):self.key(c,k)  # A9, native editor keys
        self.assertEqual(c.cstr(c.w(c.vars['SL_E_Name']+8)),'A9.RCD')
        self.key(c,20)
        blob=c.written['\\fpSup\\RESCUS\\A9.RCD'];d=rcd.decode(blob,image=c.img,stock_ids=set(c.modes))
        self.assertEqual((d['label'],d['act'],d['modes'][0][0]),('A9',(992,662),12))
        self.assertEqual(c.snapshot(),active);self.assertEqual(c.w(c.service()+16),gen)
        self.assertEqual(self.geometry(c),before);self.assertEqual(c.misaligned,[])
        old=dict(c.written);self.key(c,20)
        self.assertEqual(c.written,old);self.assertEqual(c.cstr(c.w(c.vars['SL_E_Text']+8)),'Name exists')
        self.name(c,'B');c.dirs['\\fpSup\\RESCUS'].append(('b.rcd',0x20,100))
        self.assertEqual(c.export(),7);self.assertEqual(c.written,old)

    def test_short_and_seven_character_names_resources_and_consumer_load(self):
        c=self.boot();c.geometry(12,992,662);files={}
        for name in ('Q','VWXQZ09'):
            self.name(c,name);self.assertEqual(c.export(),1)
            blob=c.written['\\fpSup\\RESCUS\\'+name+'.RCD'];files[name+'.RCD']=blob
            d=rcd.decode(blob,image=c.img,stock_ids=set(c.modes));self.assertEqual(d['label'],name)
            at,n=d['pack'];pack=blob[at:at+n];inv=nbr.inspect(pack)
            self.assertTrue({name+'_'+s for s in ('QS','SET','FONT')} <= {r['name'] for r in inv['resources']})
            for f in inv['files']:
                w,h,l,a=decode_xci(pack[f['offset']:f['offset']+f['bytes']]);self.assertGreater(a.sum(),0)
            self.assertEqual(c.cstr(c.w(c.vars['SL_E_Text']+8)),'Saved '+name+'.RCD')
        loaded=self.boot(rcds=files)
        self.assertEqual(loaded.w(loaded.s()+V.L.S['RCD_OK']),2)
        rows=loaded.s()+loaded.w(loaded.s()+V.L.S['ROWS'])
        labels=[loaded.cstr(rows+i*V.L.ROW['SIZE']+V.L.ROW['LABEL']) for i in range(3)]
        self.assertEqual(set(labels),{'Q','VWXQZ09','VRC000'})
        self.assertEqual(c.misaligned,[]);self.assertEqual(loaded.misaligned,[])

    def test_empty_name_uses_auto_and_invalid_or_reserved_name_never_writes(self):
        c=self.boot();c.geometry(12,992,662)
        for s,reason in (('BAD/..',8),('VRC000',9)):
            self.name(c,s);old=dict(c.written);self.assertEqual(c.export(),reason);self.assertEqual(c.written,old)
        self.name(c,'');self.assertEqual(c.export(),1);self.assertEqual(c.export(),1)
        self.assertIn('\\fpSup\\RESCUS\\LAB001.RCD',c.written)
        self.assertIn('\\fpSup\\RESCUS\\LAB002.RCD',c.written)

    def test_filter_expansion_publishes_range_before_stable_selection(self):
        original=V.Cam
        class Clamped(original):
            def _hook(self,mu,addr,size,data):
                if self.by_addr.get(addr)==('UI','post') and self.cstr(self.r(UC_ARM_REG_R1))=='SL_M_Sel':
                    value=self.r(UC_ARM_REG_R2);limit=self.w(self.vars['SL_ModeMax']+8)
                    result=super()._hook(mu,addr,size,data)
                    self.put(self.vars['SL_M_Sel']+8,min(value,limit));return result
                return super()._hook(mu,addr,size,data)
        try:
            V.Cam=Clamped;c=self.boot()
        finally:V.Cam=original
        ids=lambda:list(c.mu.mem_read(c.m()+self.f['state_fields']['mode_ids'],c.get('modes_rows')))
        self.change(c,'SL_F_Fps',11);self.change(c,'SL_M_Sel',ids().index(12))
        before=self.geometry(c);gen=c.w(c.service()+16)
        self.change(c,'SL_F_Fps',0)
        self.assertEqual(ids()[c.get('mode_sel')],12)
        self.assertEqual(c.w(c.vars['SL_M_Sel']+8),ids().index(12))
        after=self.geometry(c);before.pop('mode_sel');after.pop('mode_sel')
        self.assertEqual(after,before);self.assertEqual(c.w(c.service()+16),gen)

    def test_save_page_has_only_name_and_save_controls_mode_is_read_only(self):
        import sl_b25_page as P,sl_lab_page as L,sl_size_page as S,sl_lab_sidebar as B
        saved=L.CALC_ONLY;L.CALC_ONLY=True
        try:
            img=V.T.IMAGE.read_bytes();pool=RL.calculator_pool();refs=[]
            page,ar=S.assemble(L.build_lab_page(img,pool,refs),refs)
            L.check_page(page,pool,img);S.check_refs(page,ar,pool)
            objects=S.objects(P.N.split(page),pool);owner=0;actions=[]
            for r in P.N.split(page):
                d=r.to_bytes()
                if r.tag==0x10003:owner=P.u32(d,20)
                ancestor=owner
                while ancestor in objects and ancestor not in (92,93,101):ancestor=objects[ancestor]['parent']
                if ancestor==101 and r.tag==0x10009 and pool.text(P.u32(d,8)) in ('controlAppVariable','controlValue'):
                    names=[pool.text(P.u32(d,o)) for o,k in P.typed_fields(d,pool,P.load_schemas(img)) if k in ('str','text')]
                    actions+=names
            self.assertNotIn('SL_M_Sel',actions)
            self.assertEqual([r['key'] for r in B.specs()[101]],['NAME','SAVE'])
            self.assertLessEqual(B.MODE_Y+48,B.Y)
            self.assertNotIn(b'Sensor 6064x4042',pool.data)
        finally:L.CALC_ONLY=saved


if __name__=='__main__':unittest.main()
