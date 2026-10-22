"""Exact artifact boot/entry/journal check, no physical camera or card access."""
import hashlib
import json
import pathlib
import re
import struct
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT/'projects/open-gate/build'), str(ROOT/'projects/open-gate/build/res-custom')]
import test_virtual_rcd as V


class BootCam(V.Cam):
    def __init__(self, files, dirs, facts, autorun):
        super().__init__(files, dirs, facts, autorun=autorun)
        # Same modeled active AutoRun context as maintained test_boot_options.
        self.put(0xC2F20FC0+0x21C, 2)
        self.put(0xC2F20FC0+36+4, 0xC03DA158)
        self.put(0xC2F20FC0+72+4, 0xC03DA7A8)
        self.put(0xC2F20FC0+72+12, 0xC3010000)
        self.put(0xC3010000+0x90, 1)
        self.put(0xC3010000+0x94, 0xC3010200)
        self.put(0xC0420D90, 0xE12FFF1E)
        for a, w in re.findall(rb'^mem set (0x[0-9A-Fa-f]+) (0x[0-9A-Fa-f]+)', autorun, re.M):
            a, w = int(a,16), int(w,16)
            if 0xC072F700 <= a < 0xC072F800:
                self.put(a,w)

    def _hook(self, mu, addr, size, data):
        if addr == 0xC0420D90:
            self.put(0xC2F20FC0+0x21C, self.w(0xC2F20FC0+0x21C)-1)
            return self._ret(0)
        return super()._hook(mu,addr,size,data)


test = unittest.TestCase()
report = []
for name in ('virtual-card','virtual-debug','virtual-fast-debug'):
    card = HERE/'final'/name
    rcds = {p.name:p.read_bytes() for p in (card/'fpSup/RESCUS').glob('*.RCD')}
    test.assertEqual(len(rcds),5)
    meta = json.loads((card/'build.json').read_text())
    sups = [(p.name,p.read_bytes()) for p in (card/'fpSup').glob('*.BIN') if p.name!='LOADER.BIN']
    files,dirs = V.T.card(*sups)
    files.update({'\\fpSup\\'+str(p.relative_to(card/'fpSup')).replace('/','\\'):p.read_bytes()
                  for p in (card/'fpSup').rglob('*') if p.is_file()})
    dirs['\\fpSup\\RESCUS'] = [(n,0x20,len(b)) for n,b in rcds.items()]
    files.update({'\\fpSup\\RESCUS\\'+n:b for n,b in rcds.items()})
    cam = BootCam(files,dirs,meta['facts'],(card/'AutoRun.txt').read_bytes())
    r,sp = cam.boot()
    test.assertEqual(sp,V.T.STACK-0x1004)
    test.assertIsNotNone(cam.core_block)
    test.assertIsNotNone(cam.block)
    test.assertEqual(len(cam.tasks),int(name!='virtual-card'))
    cam.prepare()
    cam.geometry()
    test.assertEqual(cam.apply(),0)
    test.assertEqual(cam.w(cam.row()+V.L.ROW['BITMASK']),7)
    for a,_,_ in V.RC.rcd.BIT_CSV:
        _,copy,size = next(f for f in cam.fv if f[0]==a)
        flags = [','.join(line.split(',')[-2:]) for line in bytes(cam.mu.mem_read(copy,size)).decode('utf-8-sig').splitlines()[1:]]
        test.assertEqual(flags,['1,2']*3)
    coverage = {a+i for a,n,_ in cam.journal() for i in range(n)}
    for site in (0xC04A13E4,0xC00A7FFC):
        test.assertTrue(all(site+i in coverage for i in range(4)))
    if name == 'virtual-fast-debug':
        # The common Fast envelope owns this active-script abort word. The
        # product-table check still compares every other byte independently.
        test.assertEqual(cam.w(0xC0BAC2F8),0xC072F080)
        native=bytearray(cam.tables)
        struct.pack_into('<I',native,0xC0BAC2F8-0xC0B00000,0xC072F080)
        cam.tables=bytes(native)
    cam.assert_tables(test)
    cam.power_off()
    for h in cam.cf['hooks']:
        site=int(h['site'],16)
        test.assertEqual(cam.w(site),V.T.word(cam.img,site))
    test.assertEqual(cam.misaligned,[])
    hashes = {str(p.relative_to(card)):hashlib.sha256(p.read_bytes()).hexdigest()
              for p in card.rglob('*') if p.is_file()}
    report.append({'variant':name,'passed':True,'checks':['returning entries','static plus dynamic RCD','depth CSV copies','journal coverage','power-off restore','ABI alignment'], 'sha256':hashes})
    print('PASS',name,flush=True)
(HERE/'boot-variants.json').write_text(json.dumps(report,indent=2)+'\n')
