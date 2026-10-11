"""Consumer-owned native page allocation, bindings and Return route."""
import struct, sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'res-custom'))
import rc_files_page as C


class FilePage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob,cls.info=C.build();h=struct.unpack_from('<10I',cls.blob)
        cls.pack=bytearray(cls.blob[h[6]:h[6]+h[7]])
        cls.img,cls.pool=C.F.stock_pool()
        strings=cls.info['strings']
        for i in range(h[2]):
            off,index=struct.unpack_from('<2I',cls.blob,h[4]+8*i)
            name=strings[index];at=cls.pool.find(name)
            if at is None:at=cls.pool.intern(name)[0]
            C.F.put(cls.pack,off,at)
        rows=list(C.SL.native_rows(bytes(cls.pack)))
        cls.page=bytes(cls.pack[rows[0][1]:])

    def test_native_allocation_graph_and_dynamic_text_components(self):
        F=C.F;shape=F.check_page(self.page,self.img,self.pool)
        self.assertEqual(shape['objects'][F.ROWS_PARENT]['child_count'],6)
        self.assertFalse(F.Lab.duplicate_local_ids(self.page))
        objects=F.SZ.objects(F.N.split(self.page),self.pool)
        draws={};binds=[]
        for r in F.N.split(self.page):
            d=r.to_bytes()
            if r.tag==0x10005 and self.pool.text(F.u32(d,8))=='drawText':
                draws[F.u32(d,20)]=F.u32(d,24)
            if r.tag==0x10006 and self.pool.text(F.u32(d,8))=='appVariableEvent' and len(d)==58:
                name=self.pool.text(F.u32(d,40))
                if dict(C.VARIABLES).get(name)==2:
                    binds.append((name,F.u32(d,24),F.u32(d,45)))
        self.assertTrue({'RC_N1','RC_N5','RC_R1','RC_E5','RC_Count','RC_Status','RC_Restart','RC_Title'} <= {n for n,_,_ in binds})
        for name,owner,component in binds:self.assertEqual(component,draws[owner],name)

    def test_return_to_manager_uses_original_state_matcher(self):
        got=C.SL.native_switch(bytes(self.pack),[('FT_LIST','RC_FILES'),('RC_FILES','Return')])
        self.assertEqual(got[('FT_LIST','RC_FILES')][0],'RC_FILES')
        self.assertEqual(got[('RC_FILES','Return')][0],'FT_LIST')

    def test_only_consumer_variables_are_written_by_file_controls(self):
        names=set()
        for r in C.F.N.split(self.page):
            d=r.to_bytes()
            if r.tag==0x10009 and len(d)>40 and self.pool.text(C.F.u32(d,8))=='controlAppVariable':
                name=self.pool.text(C.F.u32(d,36))
                if name:names.add(name)
        self.assertTrue('RC_Key' in names)
        self.assertFalse(any(n.startswith(('SL_','FT_')) for n in names),names)

    def test_five_native_popups_with_private_choices_and_numbered_pages(self):
        F=C.F;recs=[r.to_bytes() for r in F.N.split(self.page)]
        writes=[];labels=set()
        for d in recs:
            if F.u32(d,0)==0x10009 and len(d)>40 and self.pool.text(F.u32(d,8))=='controlAppVariable':
                name=self.pool.text(F.u32(d,36))
                if name:writes.append(name)
            if F.u32(d,0)==0x10005 and self.pool.text(F.u32(d,8))=='drawText':
                schemas=C.F.P.load_schemas(self.img)
                field=F.text_field(d,self.pool,schemas)
                if field:labels.add(self.pool.text(F.u32(d,field[0])))
        for k in range(1,6):self.assertIn(f'RC_Choice{k}',writes)
        self.assertTrue({'Enable','Disable'}<=labels)
        self.assertEqual(C.VISIBLE,5);self.assertEqual(C.TABS,4)
        self.assertEqual(len(C.VARIABLES),84)
        self.assertEqual(len(set(n for n,_ in C.VARIABLES)),84)
        self.assertLessEqual(len(self.info['strings']),128)
        self.assertFalse(any(n.startswith('FT_') for n in writes))


if __name__=='__main__':unittest.main()
