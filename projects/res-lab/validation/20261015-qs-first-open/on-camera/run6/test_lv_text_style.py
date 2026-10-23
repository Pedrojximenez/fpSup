"""FPS typography, resource boundaries, original parser; no actual GUI render."""
from pathlib import Path
import struct
import sys
import unittest
import tempfile
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE.parent)]
import vr_ui as L
import imx410_rate_lv as V
import native_ui_audit as A
import nbu_format as N
IMAGE=(L.ROOT/'out/MAIN_c0000000.bin').read_bytes()
POOL=L._pool(IMAGE)

def candidate(spec):
    raw=bytearray(IMAGE[spec['start']-L.BASE:spec['end']-L.BASE])
    for a,_,data in L.lv(IMAGE)[0]:
        lo,hi=max(a,spec['start']),min(a+len(data),spec['end'])
        if lo<hi:raw[lo-spec['start']:hi-spec['start']]=data[lo-a:hi-a]
    pool=bytearray(POOL);ids=[]
    for label in L.LV_LABELS:
        ids.append(len(pool));pool+=label.encode()+b'\0'
    replacements={r['address']:r for r in L.lv_records(IMAGE)};out=[]
    for rec in N.split(bytes(raw)):
        row=replacements.get(spec['start']+rec.offset)
        if row is None:out.append(rec);continue
        data=bytearray(row['data'])
        for off,index in row['marks']:struct.pack_into('>I',data,off,ids[index])
        out+=N.split(bytes(data)+struct.pack('>2I',0xFFFFFFFF,8))[:-1]
    return N.join(out),bytes(pool)

class StyleTests(unittest.TestCase):
    def test_parts_and_integer_rates(self):
        self.assertEqual((len(L.LV_VALUES),len(L.LV_LABELS)),(14,29))
        for i,value in enumerate(L.LV_VALUES):
            self.assertEqual(L.LV_LABELS[i]+L.LV_LABELS[14+i].strip(),value)
        self.assertEqual(L.LV_LABELS[-1],'FPS');self.assertEqual(L.LV_TIMES[-1],433)

    def test_pins_program_and_journal_bounds(self):
        blob=L.lv_record_blob(IMAGE)
        self.assertEqual(struct.unpack_from('<2I',blob),(16,len(blob)))
        self.assertLessEqual(len(blob),0x16000)
        self.assertLess(sum(len(n) for _,_,n in L.lv(IMAGE)[0]),0x1800)
        for r in L.lv_records(IMAGE):
            self.assertLessEqual(len(r['data']),0x2800)
            for off,index in r['marks']:
                self.assertLessEqual(off+4,len(r['data']));self.assertLess(index,29)
        for spec in V.SETS:
            im=bytearray(IMAGE);im[spec['draw']-L.BASE]^=1
            with self.assertRaisesRegex(ValueError,'LV set differs'):L.lv(im)

    def test_style_and_preserved_objects_all_four_layouts(self):
        for spec in V.SETS:
            with self.subTest(layout=spec['name']):
                data,pool=candidate(spec);rs=N.split(data)
                original=N.split(IMAGE[spec['start']-L.BASE:spec['end']-L.BASE])
                old={r.words(4)[3]:r for r in original if r.tag==0x10003}
                new={r.words(4)[3]:r for r in rs if r.tag==0x10003}
                self.assertEqual(set(new),set(old))
                for oid in old:
                    if oid!=spec['owner']:self.assertEqual(old[oid].to_bytes(),new[oid].to_bytes())
                self.assertEqual(new[spec['owner']].words(1)[0],old[spec['owner']].words(1)[0]+26)
                texts=[r for r in rs if r.tag==0x10005 and r.words(4)[3]==spec['owner']]
                self.assertEqual(len(texts),27)
                self.assertEqual(len({r.words(5)[4] for r in texts}),27)
                for r in texts:
                    self.assertEqual(r.words(6)[5],0x4000203F)
                    self.assertEqual(N.string_at(pool,struct.unpack_from('>I',r.body,29)[0]),'Other_fontsetting')
                self.assertEqual([struct.unpack_from('>I',r.body,49)[0] for r in texts], [0xFF]*24+[0xFFFFFFFF]*3)
                for part in range(3):
                    black=texts[8*part:8*part+8];white=texts[24+part]
                    rect=lambda r:struct.unpack_from('>4f',r.body,53)
                    x,y,w,h=rect(white)
                    self.assertEqual({(rect(r)[0]-x,rect(r)[1]-y) for r in black},{(-2,0),(2,0),(0,-2),(0,2),(-1,-1),(1,-1),(-1,1),(1,1)})
                    self.assertEqual(len({r.body[24:28] for r in black+[white]}),1)
                c=next(r for r in rs if r.tag==0x1000A and r.words(5)[3:5]==(spec['owner'],4))
                d=A.parse_clip(A.Record(0,c.to_bytes()),lambda x:N.string_at(pool,x))
                self.assertEqual(len(d['properties']),45)
                self.assertEqual(sum(p['name']=='text' for p in d['properties']),18)
                for p in d['properties']:self.assertEqual([k['time'] for k in p['keys']],list(L.LV_TIMES))
                h=A.parse_header(A.Record(0,rs[0].to_bytes()),lambda x:N.string_at(pool,x))
                self.assertEqual(h['component_counts']['drawText'],spec['texts']+27)
                self.assertEqual(h['component_counts']['drawImage'],spec['images']-1)
                self.assertEqual(h['clip_property_counts'][-1],45)
                self.assertEqual(h['property_key_counts'][-45:],[14]*45)

    def test_native_parser_all_four_layouts(self):
        import nbu_probe as P
        for spec in V.SETS:
            with self.subTest(layout=spec['name']):
                data,pool=candidate(spec);im=bytearray(IMAGE[:P.SEG0_SIZE]);a=spec['start']-L.BASE
                im[a:a+len(data)]=data
                p=P.NbuProbe(bytes(im));p.install_arena();p.allow(*p.OBJECT_FACTORY,'stock object factory')
                for addr in V._stock_services(spec['name']):p.stub(addr,'stock UI construction service')
                pool_at=p._allocate(len(pool));p.write(pool_at,pool)
                p.open(base=spec['start'],size=len(data),magic=False,cursor=0,pool=(len(pool),pool_at),owner=True)
                for rec in N.split(data):
                    t=p.record();self.assertEqual((t.token,t.cursor_in,t.consumed),(rec.tag,rec.offset,rec.size))
                    self.assertEqual(p.error_flag(),0)
                self.assertEqual(p.traces[-1].result,1);self.assertFalse(p.survey);self.assertFalse(p.discovered)

class StringInstallerTests(unittest.TestCase):
    """Use the real C applier; the boot harness substitutes this function."""
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0,str(L.ROOT/'fpSup/uishare'))
        import test_ui_apply as U
        import rcd
        from ui import fpui
        cls.U,cls.fpui=U,fpui
        cls.tmp=tempfile.TemporaryDirectory(prefix='lv-strings-')
        cls.lib=U.build(cls.tmp.name)
        blob=bytearray(rcd.vr_template(IMAGE));ns,nw=struct.unpack_from('<2I',blob,16)
        cur=32
        for _ in range(ns):cur+=(8+struct.unpack_from('<I',blob,cur+4)[0]+1+3)&~3
        cls.targets=[]
        i=0
        while i<nw:
            head=struct.unpack_from('<I',blob,cur+4*i)[0];n=head&0xffffff
            if head>>24==fpui.OP_STRBASE:
                at=cur+4*i+8;target=struct.unpack_from('<I',blob,at)[0]+0x10080000
                struct.pack_into('<I',blob,at,target);cls.targets.append(target)
            i+=1+n
        struct.pack_into('<I',blob,12,fpui.fnv(blob[32:]))
        cls.blob=bytes(blob)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def check_labels(self,lib):
        cam=self.U.Camera(lib);result,out=cam.apply(self.blob)
        self.assertEqual(result,self.U.OK,out)
        self.assertEqual(len(self.targets),L.K+len(L.LV_LABELS))
        labels=[v[-1] for v in L.VRATES]+list(L.LV_LABELS)
        self.assertEqual([cam.text(cam.peek(a)) for a in self.targets],labels)
        self.assertTrue(cam.pool_untouched());self.assertEqual(cam.get(self.U.OOB),0)

    def test_all_33_labels_are_installed_by_the_real_applier(self):self.check_labels(self.lib)

    def test_old_eight_label_limit_is_detected(self):
        lib=self.U.build(self.tmp.name,('#define MAX_STRBASE    MAX_STRINGS',
                                      '#define MAX_STRBASE    8u'),'old-limit.dylib')
        cam=self.U.Camera(lib);result,_=cam.apply(self.blob)
        self.assertEqual(result,self.U.OP)
        self.assertEqual([cam.peek(a) for a in self.targets],[0]*len(self.targets))
        self.assertEqual(cam.layers(),[])
        with self.assertRaises(AssertionError):self.check_labels(lib)

if __name__=='__main__':unittest.main(verbosity=2)
