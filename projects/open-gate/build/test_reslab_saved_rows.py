"""Saved-file selection, full-list refusal, reboot and real native UI/QS."""
import pathlib, struct, tempfile, unittest
import test_virtual_rcd as V
import test_reslab_save_names as N
import test_virtual_rcd_rates as R


class SavedRows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.out,cls.f=V.built()
    boot=N.SaveNameTests.boot
    change=N.SaveNameTests.change
    key=N.SaveNameTests.key
    name=N.SaveNameTests.name
    geometry=N.SaveNameTests.geometry
    def originals(self):
        p=pathlib.Path(__file__).resolve().parents[2]/'res-lab/validation/20261009-oncamera/v6-complete-readback'
        files={p.name:p.read_bytes() for p in p.glob('*.RCD')}
        self.assertEqual(len(files),5);return files
    def rows(self,c):
        s=c.s();p=s+c.w(s+V.L.S['ROWS'])
        return [c.cstr(p+i*V.L.ROW['SIZE']+V.L.ROW['LABEL']) for i in range(c.w(s+V.L.S['NROWS']))]
    def saved_record(self,c):
        return c.written['\\fpSup\\32RESCUS.BIN'][32:32+V.L.CFG['BYTES']]

    def open_files(self,c):
        fn=c.core_block+c.cf['files_button_off']
        return c.call(fn,c.s(),thumb=True,sp=V.T.STACK-0x1000)[0]
    def file_key(self,c,key):self.change(c,'RC_Key',key)
    def choice(self,c,row,on):self.change(c,f'RC_Choice{row}',0 if on else 1)
    def text(self,c,name):return c.cstr(c.w(c.vars[name]+8))
    def test_full_list_save_then_rescustom_chooses_and_reboots_into_native_qs(self):
        files=self.originals();c=self.boot(rcds=files);c.geometry(12,992,662);self.key(c,36)
        active=c.snapshot();geometry=self.geometry(c);registry=bytes(c.mu.mem_read(c.service(),44))
        self.name(c,'ZNEW');self.assertEqual(c.export(),1)
        self.assertEqual(self.text(c,'SL_E_Text'),'Saved ZNEW.RCD')
        self.assertNotIn('\\fpSup\\32RESCUS.BIN',c.written,'SAVE never manages the enable list')
        self.assertEqual(self.open_files(c),0)
        self.assertEqual(self.text(c,'RC_Title'),'RES-CUSTOM (5/5)')
        self.assertEqual(c.gui_requests[-1],'RC_FILES')
        self.assertEqual(c.w(c.s()+V.L.S['NAVAIL']),6)
        self.file_key(c,11)
        self.assertEqual(self.text(c,'RC_File'),'RCD ZNEW')
        self.assertEqual(self.text(c,'RC_On'),'Enabled OFF')
        self.assertEqual(self.text(c,'RC_G1'),'ZNEW.RCD')
        self.assertEqual(c.w(c.vars['RC_Visible2']+8),0)
        self.choice(c,1,True)
        self.assertEqual(self.text(c,'RC_Status'),'List full: disable one')
        self.assertNotIn('\\fpSup\\32RESCUS.BIN',c.written)
        self.file_key(c,10)
        self.choice(c,1,False)
        self.assertEqual(self.text(c,'RC_Title'),'RES-CUSTOM (4/5)')
        self.assertEqual(self.text(c,'RC_Status'),'Restart to apply')
        self.file_key(c,11)
        self.choice(c,1,True)
        self.assertEqual(self.text(c,'RC_On'),'Enabled ON')
        self.assertEqual(self.text(c,'RC_Title'),'RES-CUSTOM (5/5)')
        self.assertEqual(self.text(c,'RC_Status'),'Restart to apply')
        self.assertEqual(c.snapshot(),active);self.assertEqual(self.geometry(c),geometry)
        self.assertEqual(bytes(c.mu.mem_read(c.service(),44)),registry)
        files['ZNEW.RCD']=c.written['\\fpSup\\RESCUS\\ZNEW.RCD']
        original=V.Cam
        try:
            V.Cam=R.RealUICam;loaded=self.boot(rcds=files,record=self.saved_record(c))
        finally:V.Cam=original
        self.assertIn('ZNEW',self.rows(loaded));self.assertNotIn('OG2K',self.rows(loaded))
        self.assertEqual(self.rows(loaded)[-1],'VRC000')
        self.assertEqual(loaded.w(loaded.s()+V.L.S['UI_OK']),0x3f)
        C=V.RC.CoreTests;loaded.S=loaded.s()
        class QSCheck(C):
            def boot(self,*a,**kw):raise AssertionError('reuse the verified saved-file boot')
        q=QSCheck();got=q.run_recipe(loaded,8);ids=q.qs_ids(loaded)
        self.assertEqual(sorted(ids),list(range(2,8)))
        for row in V.RC.QS.recipe()['records']:
            old=V.RC.QS.stock(row);want=V.RC.rcd.qs_target(row,old,8,ids)
            self.assertEqual(got[row['address']],old if want is None else want)
        self.assertEqual(c.misaligned,[]);self.assertEqual(loaded.misaligned,[])

    def test_empty_selection_persists_and_rescustom_needs_no_producer(self):
        c=self.boot();c.geometry(12,992,662);self.name(c,'MY240');self.assertEqual(c.export(),1)
        self.assertNotIn('\\fpSup\\32RESCUS.BIN',c.written)
        self.assertEqual(self.open_files(c),0);self.choice(c,1,True)
        blob=c.written['\\fpSup\\RESCUS\\MY240.RCD']
        loaded=self.boot(rcds={'MY240.RCD':blob},record=self.saved_record(c))
        self.assertEqual(self.rows(loaded),['MY240','VRC000'])
        self.choice(c,1,False);empty=self.boot(rcds={'MY240.RCD':blob},record=self.saved_record(c))
        self.assertEqual(self.rows(empty),['VRC000'])
        empty.put(empty.service()+28,0) # all registered producers removed in this fixture
        self.assertEqual(self.open_files(empty),0)
        self.assertEqual(self.text(empty,'RC_On'),'Enabled OFF')

    def test_failed_persistence_and_recording_do_not_change_selection(self):
        files=self.originals();c=self.boot(rcds=files);self.assertEqual(self.open_files(c),0)
        s=c.s();cfg=c.w(s+V.L.S['CFG']);before=bytes(c.mu.mem_read(cfg,V.L.CFG['BYTES']))
        c.seek_ok=False;self.choice(c,1,False)
        self.assertEqual(bytes(c.mu.mem_read(cfg,V.L.CFG['BYTES'])),before)
        self.assertEqual(self.text(c,'RC_Status'),'Write failed')
        c.seek_ok=True;c.put(0xC35A952c,1);self.choice(c,1,False)
        self.assertEqual(bytes(c.mu.mem_read(cfg,V.L.CFG['BYTES'])),before)
        self.assertEqual(c.misaligned,[])

    def test_enable_assertion_detects_disconnected_consumer_callback(self):
        c=self.boot();c.geometry(12,992,662);self.name(c,'MUTATE');self.assertEqual(c.export(),1)
        self.assertEqual(self.open_files(c),0)
        c.mu.mem_write(c.subs['RC_Choice1']&~1,b'\x00\x20\x70\x47') # movs r0,0; bx lr
        self.choice(c,1,True)
        with self.assertRaises(AssertionError):self.assertEqual(self.text(c,'RC_On'),'Enabled ON')

    def test_paginated_choices_do_not_alias_hidden_files_or_more_settings(self):
        c=self.boot(rcds=self.originals());c.geometry(12,992,662);self.name(c,'ZNEW')
        self.assertEqual(c.export(),1);self.assertEqual(self.open_files(c),0)
        self.assertEqual(self.text(c,'RC_N1'),'OG2K.RCD')
        self.assertEqual(self.text(c,'RC_E1'),'Enabled')
        self.assertEqual(c.w(c.vars['RC_TabVisible2']+8),1)
        self.assertEqual(c.w(c.vars['RC_TabWidth1']+8),512)
        self.file_key(c,11)
        self.assertEqual(self.text(c,'RC_G1'),'ZNEW.RCD')
        self.assertEqual(self.text(c,'RC_R1'),'Disabled')
        self.assertEqual(c.w(c.vars['RC_TabActive2']+8),1)
        self.assertEqual(c.w(c.vars['RC_Lock2']+8),1)
        cfg=c.w(c.s()+V.L.S['CFG']);before=bytes(c.mu.mem_read(cfg,V.L.CFG['BYTES']))
        self.choice(c,2,True)                  # hidden slot never aliases row 1
        self.change(c,'RC_Choice1',2)         # inherited More action does nothing
        self.assertEqual(bytes(c.mu.mem_read(cfg,V.L.CFG['BYTES'])),before)
        self.assertNotIn('\\fpSup\\32RESCUS.BIN',c.written)
        self.file_key(c,10)
        self.assertEqual(self.text(c,'RC_N1'),'OG2K.RCD')
        self.assertEqual(c.misaligned,[])

    def test_standalone_all_files_off_keeps_manager_and_stock_recording(self):
        import build_v3_rescustom as B,rcd
        with tempfile.TemporaryDirectory(prefix='rc-files-only-') as d:
            core,cf,_=B.build_core(pathlib.Path(d),virtual=False)
        cfg=bytearray(V.L.CFG['BYTES'])
        for name,value in [('MAGIC',V.L.CFG_MAGIC),('VERSION',V.L.CFG_VERSION),('NEN',1)]:
            struct.pack_into('<I',cfg,V.L.CFG[name],value)
        cfg[V.L.CFG['EN']:V.L.CFG['EN']+8]=b'VRC000\0\0'
        struct.pack_into('<I',cfg,V.L.CFG['SUM'],rcd.fnv(cfg[:V.L.CFG['SUM']]))
        core=core[:32]+cfg+core[32+len(cfg):]
        sups=[('32RESCUS.BIN',core)]
        if (self.out/'fpSup/00SHELL.BIN').exists():sups.append(('00SHELL.BIN',(self.out/'fpSup/00SHELL.BIN').read_bytes()))
        files,dirs=V.T.card(*sups)
        files['\\fpSup\\LOADER.BIN']=(self.out/'fpSup/LOADER.BIN').read_bytes()
        originals=self.originals();dirs['\\fpSup\\RESCUS']=[(n,0x20,len(b)) for n,b in originals.items()]
        files.update({'\\fpSup\\RESCUS\\'+n:b for n,b in originals.items()})
        c=V.Cam(files,dirs,dict(self.f,rescustom=cf));c.tables=bytes(c.mu.mem_read(0xC0B00000,0x200000))
        for a,v in V.T.B.loader_words((self.out/'AutoRun.txt').read_bytes()).items():c.put(a,v)
        before={int(h['site'],16):c.w(int(h['site'],16)) for h in cf['hooks']}
        c.boot();self.assertIsNone(c.block);self.assertIsNotNone(c.core_block)
        self.assertEqual(c.w(c.s()+V.L.S['NROWS']),0)
        for h in cf['hooks']:
            address=int(h['site'],16)
            if address!=0xC056461c:self.assertEqual(c.w(address),before[address],hex(address))
        self.assertEqual(self.open_files(c),0);self.assertEqual(self.text(c,'RC_Count'),'0/6')
        self.assertEqual(self.text(c,'RC_Title'),'RES-CUSTOM (0/6)')
        self.assertEqual(self.text(c,'RC_On'),'Enabled OFF');self.choice(c,1,True)
        self.assertEqual(self.text(c,'RC_On'),'Enabled ON')
        self.assertIn('\\fpSup\\32RESCUS.BIN',c.written)
        self.assertEqual(c.misaligned,[])


if __name__=='__main__':unittest.main()
