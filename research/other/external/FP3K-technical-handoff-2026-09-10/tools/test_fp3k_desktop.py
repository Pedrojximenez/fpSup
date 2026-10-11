"""Exercise media-management behavior against temporary directories, never real disks."""
import importlib.util,unittest,tempfile,shutil,json,struct,contextlib,io
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];spec=importlib.util.spec_from_file_location('fp3k',ROOT/'prototype/fp3k-0.1/fp3k.py');fp=importlib.util.module_from_spec(spec);spec.loader.exec_module(fp)
class Desktop(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.package=self.base/'package';shutil.copytree(fp.ROOT,self.package,ignore=shutil.ignore_patterns('backups','__pycache__'));self.override=patch.object(fp,'ROOT',self.package);self.override.start();self.media={}
  for label in ('SD','SSD'):
   p=self.base/label;p.mkdir();self.media[label]={'path':p,'disk':'fake-'+label,'uuid':fp.UUIDS[label]};(p/'keep.DNG').write_bytes(b'preserve this clip')
 def tearDown(self):self.override.stop();self.tmp.cleanup()
 def run_action(self,a):
  with contextlib.redirect_stdout(io.StringIO()):return fp.manage(a,self.media)
 def test_enable_disable_reenable_preserves_data_and_diagnostics(self):
  self.run_action('install');sd=self.media['SD']['path'];ssd=self.media['SSD']['path'];body=(sd/'AutoRun.txt').read_bytes();self.assertEqual(fp.digest(body),fp.AUTORUN_HASH);self.assertFalse((ssd/'AutoRun.txt').exists());(ssd/'FP3KF1/STATUS.BIN').write_bytes(b'old diagnostics')
  backup=self.run_action('disable');self.assertFalse((sd/'AutoRun.txt').exists());self.assertEqual((backup/'SSD/FP3KF1/STATUS.BIN').read_bytes(),b'old diagnostics')
  self.run_action('install');self.assertEqual((sd/'AutoRun.txt').read_bytes(),body);self.assertTrue(list(ssd.glob('FP3KF1-before-*/STATUS.BIN')))
  for m in self.media.values():self.assertEqual((m['path']/'keep.DNG').read_bytes(),b'preserve this clip')
 def test_unknown_autorun_blocks_before_any_media_change(self):
  (self.media['SD']['path']/'AutoRun.txt').write_bytes(b'other project')
  with self.assertRaises(ValueError):self.run_action('install')
  self.assertFalse((self.media['SSD']['path']/'FP3KF1').exists())
 def test_ssd_autorun_blocks(self):
  (self.media['SSD']['path']/'AutoRun.txt').write_bytes((self.package/'card/AutoRun.txt').read_bytes())
  with self.assertRaises(ValueError):self.run_action('install')
  self.assertFalse((self.media['SD']['path']/'AutoRun.txt').exists())
 def test_missing_ssd_blocks_install_but_not_disable(self):
  self.run_action('install');del self.media['SSD']
  with self.assertRaises(ValueError):self.run_action('install')
  self.run_action('disable');self.assertFalse((self.media['SD']['path']/'AutoRun.txt').exists())
 def test_tampered_package_blocks(self):
  (self.package/'card/AutoRun.txt').write_bytes(b'corrupt')
  with self.assertRaises(ValueError):self.run_action('install')
  self.assertFalse((self.media['SD']['path']/'AutoRun.txt').exists())
 def test_symlink_diagnostics_rejected(self):
  (self.media['SD']['path']/'FP3KF1').symlink_to(self.media['SSD']['path'],target_is_directory=True)
  with self.assertRaises(ValueError):self.run_action('install')
 def test_diagnostic_success_already_present_and_incomplete(self):
  p=self.base/'logs';shutil.copytree(ROOT/'diagnostics/three-k-coldstart30-return/SSD/FP3KF1',p);m,_=fp.load_package();self.assertTrue(fp.diagnose(p,m).startswith('PASS:'))
  (p/'STATUS.BIN').write_bytes(struct.pack('<4I',0x3146334b,4,0xc0be3f54,3032));self.assertTrue(fp.diagnose(p,m).startswith('ALREADY PRESENT:'))
  (p/'WORD3.BIN').unlink();self.assertTrue(fp.diagnose(p,m).startswith('Incomplete'))
 def test_check_is_read_only_on_media(self):
  self.run_action('install');before={str(p):p.read_bytes() for v in self.media.values() for p in v['path'].rglob('*') if p.is_file()};self.run_action('check');after={str(p):p.read_bytes() for v in self.media.values() for p in v['path'].rglob('*') if p.is_file()};self.assertEqual(before,after)
if __name__=='__main__':unittest.main()
