"""Real ARM UI installer + two-Sup recipes and native FPS commit/picker hooks.

Only the OS, GUI model and storage boundaries are modeled. Unlike the broad
integration fixture, the core's complete uia_apply/ui_pool code runs here.
"""
import json, pathlib, struct, unittest
import test_virtual_rcd as V
from ui import chain


class RealUICam(V.Cam):
    def _alloc(self, n, align=8):
        p = super()._alloc(n, align)
        if n == self.cf['block']:
            uia = p + (self.cf['uia_apply_off'] & ~1)
            self.by_addr.pop(uia)
            self.pending = []
        return p

    def csvs(self, sources):
        ven = chain.bw_target(V.RC.FV_SITE, self.w(V.RC.FV_SITE))
        assert ven and self.w(ven) == 0xf000f8df
        head = self.w(ven + 4) - 16
        assert self.w(head) == 0x4b485346
        table = self.w(head + 8)
        files = {self.w(table + 16 + 12*i):
                 (self.w(table + 20 + 12*i), self.w(table + 24 + 12*i))
                 for i in range(self.w(table + 8))}
        out = []
        for stock, _, _ in sources:
            at, size = files[stock]
            out.append(bytes(self.mu.mem_read(at, size)).decode('utf-8-sig').splitlines())
        return out

    def rate_csvs(self):
        return self.csvs(V.RC.rcd.RATE_CSV)

    def bit_csvs(self):
        return [[','.join(row.split(',')[-2:]) for row in lines[1:]]
                for lines in self.csvs(V.RC.rcd.BIT_CSV)]

    def choose_rate(self, rank):
        """the service's VRC_RATE_SET, as a UI sup of someone else's calls it"""
        return self.dispatch(6, rank)


class RateUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out, cls.f = V.built()

    def boot(self, rcds=None):
        sups = [(p.name, p.read_bytes()) for p in (self.out/'fpSup').glob('*.BIN')
                if p.name != 'LOADER.BIN']
        files, dirs = V.T.card(*sups)
        files['\\fpSup\\LOADER.BIN'] = (self.out/'fpSup/LOADER.BIN').read_bytes()
        # The actual camera has five static formats before the shared dynamic row.
        data = pathlib.Path(__file__).resolve().parents[2]/'res-lab/validation/20261009-oncamera/v6-complete-readback'
        if rcds is None:
            rcds = {p.name:p.read_bytes() for p in data.glob('*.RCD')}
        assert len(rcds) == 5
        dirs['\\fpSup\\RESCUS'] = [(n, 0x20, len(b)) for n, b in rcds.items()]
        files.update({'\\fpSup\\RESCUS\\'+n:b for n,b in rcds.items()})
        cam = RealUICam(files, dirs, self.f)
        for a,v in V.T.B.loader_words((self.out/'AutoRun.txt').read_bytes()).items():
            cam.put(a,v)
        # Native callback bodies are UI boundaries, as in the maintained core fixture.
        for a in (V.RC.CMT_SET+4, V.RC.CMT_QS+4):
            cam.mu.mem_write(a, struct.pack('<I', V.RC.POP4567))
            cam.test_code.add(a)
        cam.boot()
        self.assertIsNotNone(cam.core_block)
        self.assertIsNotNone(cam.block)
        self.assertEqual(cam.w(cam.s()+V.L.S['RATE_UI']), 1)
        self.assertEqual(cam.w(cam.s()+V.L.S['RATE_WHY']), 1)
        self.assertEqual(cam.w(cam.s()+V.L.S['UI_OK']), 0x3f)
        cam.written_baseline = dict(cam.written)
        cam.prepare()
        return cam

    def check_csvs(self, cam, offered, dynamic=False):
        stock_text = lambda a, n: cam.img[a-0xC0000000:a-0xC0000000+n].decode('utf-8-sig').splitlines()
        for lines, (stock,size,_) in zip(cam.rate_csvs(), V.RC.rcd.RATE_CSV):
            # the copy: the stock nine, no row of the core's own
            self.assertEqual(len(lines), 10)
            self.assertEqual([int(line.split(',')[0]) for line in lines[1:]], list(range(1,10)))
            for j,line in enumerate(lines[1:]):
                expected = ('1,2' if dynamic else ','.join(stock_text(stock,size)[j+1].split(',')[-2:])) if j in offered else '0,0'
                self.assertEqual(','.join(line.split(',')[-2:]),expected,(stock,j))

    def check_native_limits(self, cam, fastest, rate_class):
        # Execute the actual five-site greying/normalizer hooks, including the
        # restrictive incoming SD/FHD classes observed on the physical camera.
        V.RC.CoreTests.stub_gates(self,cam)
        cam.test_code.update((0xc04a1790,0xc04a1794,0xc00a87e8,0xc00a87ec,
                              0xc04a1220,0xc04a1224,0xc043b6a8,0xc043b6ac,0xc043b6b0))
        gates=V.RC.CoreTests.gates(self,cam)
        self.assertEqual(gates['frmax'],dict.fromkeys((7,6,5,3,2),fastest))
        self.assertEqual(gates['frclass'],dict.fromkeys((0,5,3,1,4,2),rate_class))

    def test_real_installer_dynamic_declared_rates_and_stock_restore(self):
        cam = self.boot()
        self.check_csvs(cam,set(range(9)))
        for mid in (12,9):
            cam.fr=12
            cam.put(cam.s()+V.L.S['VRATE'],0)
            cam.geometry(mid,2000,660)
            self.assertEqual(cam.apply(),0)
            self.check_native_limits(cam,7,0)
            self.check_csvs(cam,set(range(9)),dynamic=True)
            for site in ('service', 'again'):
                for rank,numerator in ((23976,240000),(27972,280000)):
                    cam.fr=12
                    self.assertEqual(cam.choose_rate(rank),0)
                    cam.fr=7
                    self.assertEqual(cam.w(cam.s()+V.L.S['VRATE']),rank)
                    cam.mu.mem_write(V.RC.KEYBUF,b'VRC000120\0'.ljust(16,b'\0'))
                    e,_=cam.call(V.RC.PICKER,r1=V.RC.TAB3,r2=V.RC.KEYBUF)
                    self.assertNotEqual(e,0)
                    self.assertEqual(cam.w(e+V.L.ENT['VRATE']),rank)
                    self.assertEqual(cam.w(e+V.L.ENT['NOMINAL']),numerator//1000)
                    self.assertEqual(cam.w(e+V.L.ENT['ENGFPS']),V.L._f32(numerator/1001))
                    vm=cam.s()+cam.w(cam.s()+V.L.S['VMS'])+V.L.VM['SIZE']*cam.w(e+V.L.ENT['VM'])
                    self.assertEqual(cam.w(vm+V.L.VM['DONOR']),mid)
                    w0,w1=cam.w(e+V.L.ENT['W0']),cam.w(e+V.L.ENT['W1'])
                    self.assertEqual((w0&0xffff)*((w1&0xffff)-1)+(w0>>16),72000000*1001//numerator)
                    fn=cam.w(cam.s()+V.L.S['FN']+V.L.FNS.index('CANVAS')*4)
                    canvas=V.RC.CANVAS_IN+0x5c
                    cam.call(fn,cam.s(),canvas,cam.w(e+4),thumb=True,sp=V.T.STACK-0x1000)
                    self.assertEqual(cam.w(canvas+0xb0),1)
                    self.assertEqual((cam.w(canvas+0x24),cam.w(canvas+0x2c)),(2000,660))
                    print('M%d %s %.2fp: service, timing, canvas passed'%(mid,site,rank/100),flush=True)
        cam.fr=12
        cam.put(cam.s()+V.L.S['VRATE'],0)
        cam.geometry(98,3008,2000)
        self.assertEqual(cam.apply(),0)
        self.check_native_limits(cam,5,3)
        self.check_csvs(cam,set(range(7)),dynamic=True)
        self.assertEqual(cam.choose_rate(23976),7)       # VRC_RATE: M98 does not reach 239.76
        self.assertEqual(cam.w(cam.s()+V.L.S['VRATE']),0)
        # Core transition back to native FHD restores each stock exclusion variant.
        var=V.RC.KEYBUF+0x800;cam.put(var+8,1)
        cam.call(V.RC.CMT_SET,r0=var)
        cam.call(V.RC.SETTER,r1=2,r2=1)
        self.assertEqual(cam.w(cam.s()+V.L.S['FLAG']),0)
        self.check_csvs(cam,set(range(9)))
        gates=V.RC.CoreTests.gates(self,cam)
        self.assertEqual(gates['frmax'],{7:7,6:6,5:5,3:3,2:2})
        self.assertEqual(gates['frclass'],{0:0,5:5,3:3,1:1,4:4,2:2})
        cam.assert_tables(self)
        self.assertEqual(cam.misaligned,[])

    def test_real_installer_static_and_applied_rcd_depths_restore(self):
        rcds = {name.removeprefix('RESCUS/'): blob for name, (blob, _) in V.RC.built().items()
                if name.startswith('RESCUS/')}
        cam = self.boot(rcds=rcds)
        original = [['1,2'] * 3, ['1,2','0,0','0,0']]
        self.assertEqual(cam.bit_csvs(), original)
        for label in ('OG35K', 'OG4K', 'S16'):
            st = cam.s()
            row = next(st+cam.w(st+V.L.S['ROWS'])+V.L.ROW['SIZE']*i
                       for i in range(cam.w(st+V.L.S['NROWS']))
                       if cam.cstr(st+cam.w(st+V.L.S['ROWS'])+V.L.ROW['SIZE']*i+V.L.ROW['LABEL']) == label)
            var = V.RC.KEYBUF+0x800
            cam.put(var+8, cam.w(row+V.L.ROW['MROW']))
            cam.call(V.RC.CMT_SET,r0=var)
            cam.call(V.RC.SETTER,r1=cam.w(row+V.L.ROW['STOCK']),r2=1)
            self.assertEqual(cam.bit_csvs(), [['1,2'] * 3] * 2)
            self.check_native_limits(cam, 6 if label=='S16' else 3, 5 if label=='S16' else 1)
        cam.fr=12
        cam.geometry(98,3008,2000)
        self.assertEqual(cam.apply(),0)
        self.assertEqual(cam.w(cam.row()+V.L.ROW['BITMASK']),7)
        self.assertEqual(cam.bit_csvs(), [['1,2'] * 3] * 2)
        # A second generic producer supplies a restrictive policy. Apply updates
        # the same shared row and the real uia_apply copies, without format tests.
        blob=rcds['OG3K.RCD']; row=V.RC.rcd.decode(blob)
        off,n=row['pack']
        ident=cam.blob_provider(V.RC.rcd.encode(dict(row,bit_depths=(12,)),blob[off:off+n]))
        self.assertEqual(cam.dispatch(2,ident),0)
        self.assertEqual(cam.w(cam.row()+V.L.ROW['BITMASK']),4)
        self.assertEqual(cam.bit_csvs(), [['0,0','0,0','1,2']] * 2)
        cam.call(V.RC.FMTSET,r1=V.RC.MOV,r2=1)
        self.assertEqual(cam.bit_csvs(),original)
        cam.assert_tables(self)
        self.assertEqual(cam.misaligned,[])


if __name__=='__main__': unittest.main()
