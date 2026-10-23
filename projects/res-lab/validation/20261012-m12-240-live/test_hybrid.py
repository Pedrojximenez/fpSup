"""Exact current loader/shell + old producer + v19 consumer, focused offline check.

The old shell uses BURST15. Its two descriptor writes are independently known
from the existing LOAD.LOG, exact shell bytes and fresh live readback. Keep
full ROM-table equality, accounting only for these intentional shell words.
Other physical optional modules are unchanged but not emulated in this fixture.
"""
import json,pathlib,struct,sys,unittest
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path[:0]=[str(ROOT/'projects/open-gate/build'),str(ROOT/'projects/open-gate/build/res-custom')]
import test_m12_240 as M
import test_virtual_rcd as V
import patches
words=json.loads((HERE/'shell-descriptor-words.json').read_text())
raw=(HERE/'backup/fpSup__00SHELL.BIN').read_bytes()
for address,value,*_ in patches.BURST15:
 assert words[hex(address)]==value
 assert struct.pack('<I',address) in raw and struct.pack('<I',value) in raw

def exact_tables(self,test):
 expected=bytearray(self.tables)
 if self.tasks and self.w(0xC072F000)==0x4C485356:
  for at,value,*_ in patches.IFACE+patches.BURST15+patches.NOPTP:
   if 0xC0B00000<=at<0xC0D00000:struct.pack_into('<I',expected,at-0xC0B00000,value)
 test.assertEqual(bytes(self.mu.mem_read(0xC0B00000,0x200000)),bytes(expected))
V.Cam.assert_tables=exact_tables
suite=unittest.TestSuite(M.M12Tests(n) for n in (
 'test_disk_entry_full_canvas_real_metadata_and_shutdown',
 'test_same_data_through_generic_virtual_service'))
result=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(not result.wasSuccessful())
