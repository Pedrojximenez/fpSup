"""Offline checks for diagnostic validation; synthetic data is not a camera test."""
import unittest,tempfile,json,struct
from pathlib import Path
from check_diagnostic import check,ROOT
from unpack_fp import decompress
class DiagnosticTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=Path(self.tmp.name)
  m=json.loads((ROOT/'diagnostics/fp-state-v001/manifest.json').read_text());main=(ROOT/'analysis/firmware/MAIN_c0000000.bin').read_bytes()
  for f in m['expected_files']:
   b=bytearray(f['size'])
   if f['name']=='GEOM.BIN':b[:]=main[0xb59dc0:0xb59dc0+f['size']]
   elif f['name']=='DONE.BIN':
    b[:]=main[:64];b[0x20:0x24]=main[0x76c:0x770]
   elif f['name'].startswith('S'):
    struct.pack_into('<5I',b,0,0xc2f1e654,218,218,66,66);struct.pack_into('<I',b,0xd0,0xc0b5fcc0)
   (self.p/f['name']).write_bytes(b)
 def tearDown(self):self.tmp.cleanup()
 def test_complete(self):
  r=check(self.p);self.assertEqual(r['status'],'PASS');self.assertEqual(len(r['samples']),24);self.assertEqual(r['samples'][0]['known_raster'],[3032,1708])
 def test_missing(self):
  (self.p/'DONE.BIN').unlink();self.assertNotEqual(check(self.p)['status'],'PASS')
 def test_wrong_firmware(self):
  (self.p/'GEOM.BIN').write_bytes(bytes(7000));self.assertTrue(any('fingerprint' in x for x in check(self.p)['errors']))
 def test_bad_runtime_vector(self):
  b=bytearray((self.p/'DONE.BIN').read_bytes());b[0x20]^=1;(self.p/'DONE.BIN').write_bytes(b)
  self.assertTrue(any('fingerprint' in x for x in check(self.p)['errors']))
 def test_bad_size(self):
  (self.p/'S000.BIN').write_bytes(b'bad');self.assertTrue(any('expected' in x for x in check(self.p)['errors']))
 def test_bad_pointer(self):
  (self.p/'S000.BIN').write_bytes(bytes(256));self.assertTrue(any('descriptor' in x for x in check(self.p)['errors']))
 def test_lzss_overlap(self):
  out,used,extra=decompress(bytes([1,65,0xee,0xf2]),6);self.assertEqual(out,b'AAAAAA');self.assertEqual(used,4);self.assertEqual(extra,'')
 def test_lzss_truncation(self):
  with self.assertRaises(ValueError):decompress(bytes([1]),1)
if __name__=='__main__':unittest.main()
