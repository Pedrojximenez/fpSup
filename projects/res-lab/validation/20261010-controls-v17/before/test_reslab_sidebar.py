"""Sidebar, automatic commit and SAVE: real product ARM, modeled UI/storage."""
import struct
import unittest
import test_virtual_rcd as V
import test_v3_reslab as RL
import rcd


class SidebarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.out, cls.f = V.built()
    def boot(self, **kw):
        # The delivered card includes RESCUS, even before its first saved recipe.
        kw.setdefault('rcds', {})
        return V.VirtualTests.boot(self, **kw)
    test_save_rejects_short_write_corruption_and_tail = RL.CalculatorTests.test_short_write_corruption_and_trailing_bytes_fail
    test_rescustom_loads_saved_geometry = RL.CalculatorTests.test_rescustom_reads_export_and_uses_virtual_geometry

    def change(self, cam, name, value):
        d = cam.vars[name]; cam.put(d+8,value)
        cam.call(cam.subs[name],d,thumb=True,sp=V.T.STACK-0x1000)

    def key(self, cam, value): self.change(cam,'SL_O_Key',value)
    def dimensions(self, cam): return cam.get('out_w'),cam.get('out_h')

    def test_numeric_edit_commits_on_done_without_apply(self):
        c=self.boot();c.geometry(mode=12,w=992,h=662)
        self.key(c,35)
        for _ in range(4):self.key(c,34)
        self.assertEqual(c.w(c.service()+16),0)
        self.key(c,36)
        self.assertEqual(c.w(c.service()+16),1)
        self.assertEqual((c.w(c.row()+V.L.ROW['AW']),c.w(c.row()+V.L.ROW['AH'])),self.dimensions(c))
        for k in (35,31,32,36):self.key(c,k)
        self.assertEqual(c.w(c.service()+16),1,'focus and unchanged dimensions must not reapply')
        self.assertEqual(c.written,c.written_baseline)

    def test_auto_commit_assertion_detects_missing_callback(self):
        c=self.boot();c.geometry(mode=12,w=992,h=662)
        # Isolated emulator mutation, never a source or card modification.
        c.mu.mem_write(c.fn('sl_menu_auto') & ~1,struct.pack('<H',0x4770))
        self.key(c,35);self.key(c,34);self.key(c,36)
        with self.assertRaises(AssertionError):
            self.assertEqual(c.w(c.service()+16),1,'missing automatic commit')

    def test_crop_shape_and_independent_lens_composition(self):
        c=self.boot();c.geometry(mode=12,w=992,h=662)
        self.change(c,'SL_O_Lock',1)
        self.key(c,15)
        for _ in range(6):self.key(c,18)
        self.key(c,16)
        kept=(c.get('ro_w')-c.get('crop_w'),c.get('ro_h')-c.get('crop_h'))
        self.assertAlmostEqual(kept[0]/kept[1],3,delta=.035)
        crop=(c.get('crop_w'),c.get('crop_h'))
        self.change(c,'SL_O_Lens',1)
        w,h=self.dimensions(c);self.assertAlmostEqual(w/h,1.5*1.33,delta=.02)
        self.assertEqual((c.get('crop_w'),c.get('crop_h')),crop)
        self.change(c,'MV_SLScale',1)
        w,h=self.dimensions(c);self.assertAlmostEqual(w/h,3*1.33,delta=.04)
        self.assertEqual((c.get('crop_w'),c.get('crop_h')),crop)
        self.change(c,'SL_O_Lens',0)
        w,h=self.dimensions(c);self.assertAlmostEqual(w/h,3,delta=.03)

    def test_ordinary_mode_lens_and_custom_policy(self):
        c=self.boot();c.geometry(mode=8,w=2000,h=1334)
        self.change(c,'SL_O_Lens',1)
        w,h=self.dimensions(c);self.assertAlmostEqual(w/h,1.995,delta=.015)
        self.assertEqual(c.w(c.vars['SL_O_Warp']+8),0)
        self.change(c,'MV_SLScale',2)
        self.assertEqual(c.get('ratio'),16);self.assertEqual(c.get('lens_on'),0)

    def test_save_exports_current_recipe_and_preserves_active_virtual(self):
        c=self.boot(rcds={});c.geometry(mode=12,w=992,h=662)
        self.change(c,'SL_O_Lens',1)
        generation=c.w(c.service()+16);active=c.snapshot()
        self.key(c,20)
        blob=c.written['\\fpSup\\RESCUS\\LAB001.RCD']
        d=rcd.decode(blob,image=c.img,stock_ids=set(c.modes))
        self.assertEqual(d['act'],self.dimensions(c));self.assertEqual(d['modes'][0][0],12)
        self.assertEqual(d['label'],'LAB001');self.assertEqual(c.w(c.service()+16),generation)
        self.assertEqual([s for n,s in c.text_events if n=='SL_E_Text'][-1],'Saved LAB001.RCD')
        self.assertEqual(c.snapshot(),active)
        self.key(c,20);self.assertIn('\\fpSup\\RESCUS\\LAB002.RCD',list(c.written))
        self.assertEqual([s for n,s in c.text_events if n=='SL_E_Text'][-1],'Saved LAB002.RCD')
        self.assertEqual(c.misaligned,[])

    def test_saved_files_reserve_virtual_row_at_next_boot(self):
        # The actual camera has five existing formats; its first SAVE makes six.
        fixture=RL.RC.built()
        files={n.split('/')[1]:d for n,(d,_) in fixture.items() if n.startswith('RESCUS/')}
        self.assertEqual(len(files),5)
        lab=self.boot();lab.geometry(mode=12,w=992,h=662)
        self.assertEqual(lab.export(),1)
        files['LAB001.RCD']=lab.written['\\fpSup\\RESCUS\\LAB001.RCD']
        c=self.boot(rcds=files);s=c.s()
        self.assertEqual(c.w(s+V.L.S['RCD_OK']),6)
        self.assertEqual(c.w(s+V.L.S['NAVAIL']),6)
        self.assertEqual(c.w(s+V.L.S['NROWS']),6)
        rows=s+c.w(s+V.L.S['ROWS'])
        labels=[c.cstr(rows+i*V.L.ROW['SIZE']+V.L.ROW['LABEL']) for i in range(6)]
        self.assertIn('LAB001',labels);self.assertEqual(labels[-1],'VRC000')
        c.geometry(mode=12,w=992,h=662);self.assertEqual(c.apply(),0)
        self.assertEqual(c.w(c.service()+16),1)

    def test_recording_rejects_auto_commit_and_keeps_old_geometry(self):
        c=self.boot();c.geometry(mode=12,w=992,h=662)
        self.key(c,36);old=c.snapshot()
        c.put(0xC35A952c,1)
        self.change(c,'SL_O_Lens',1)
        self.assertEqual(c.snapshot(),old);self.assertEqual(c.w(c.service()+16),1)
        self.assertIn('busy',c.cstr(c.m()+self.f['state_fields']['export_text']))
        c.put(0xC35A952c,0);self.key(c,36)
        self.assertEqual(c.w(c.service()+16),2)

    def test_native_sidebar_page_and_save_is_third_tab(self):
        import sl_b25_page as P,sl_lab_page as L,sl_lab_sidebar as B,sl_size_page as S
        saved=L.CALC_ONLY;L.CALC_ONLY=True
        try:
            img=V.T.IMAGE.read_bytes();pool=P.Pool(img[P.U.POOL_START-P.B:P.U.POOL_START-P.B+P.U.POOL_SIZE]);refs=[]
            page,ar=S.assemble(L.build_lab_page(img,pool,refs),refs)
            shape=L.check_page(page,pool,img);S.check_refs(page,ar,pool)
            objects=S.objects(P.N.split(page),pool);commands=[];labels=[];owner=0
            for r in P.N.split(page):
                d=r.to_bytes()
                if r.tag==0x10003:owner=P.u32(d,20)
                if r.tag==0x10005 and pool.text(P.u32(d,8))=='drawText':labels.append(pool.text(P.u32(d,32)))
                if r.tag==0x10009 and len(d)==46 and pool.text(P.u32(d,8))=='controlAppVariable' and pool.text(P.u32(d,36))=='SL_O_Key':
                    code=pool.text(P.u32(d,41));commands.append(code)
                    if code=='20':
                        ancestor=owner
                        while objects[ancestor]['parent'] not in (92,93,101):ancestor=objects[ancestor]['parent']
                        self.assertEqual(objects[ancestor]['parent'],101)
            self.assertNotIn('21',commands);self.assertEqual(commands.count('20'),2)
            for text in ('FILTER','OUTPUT','SAVE','Save RCD'):self.assertIn(text,labels)
            self.assertNotIn('Apply',labels);self.assertNotIn('MODES',labels)
            self.assertEqual(len([k for k in pool.added if k.startswith('SL_D_L')]),128)
        finally:L.CALC_ONLY=saved


if __name__=='__main__':unittest.main()
