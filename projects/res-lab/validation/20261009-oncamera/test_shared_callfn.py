"""Offline regression for getfile/callfn sharing the execution area."""
import importlib.util,pathlib,sys,types,unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[4]
SOURCE=ROOT/'fpSup/fp_usb_shell/callfn.py'

class SharedCode(unittest.TestCase):
 def fixture(self):
  mem={};state={'code':None,'uploads':0,'echoes':0,'handler':0x1000}
  pf=types.ModuleType('putfile')
  pf.CODE=0x2000;pf.CODE_END=0x3000;pf.P=0x4000
  pf.ECHO_SLOT=0x5000;pf.ECHO_ORIG=0x1000;pf.HERE=SOURCE.parent
  pf.mem_set=lambda a,v:mem.__setitem__(a,v)
  pf.mem_get=lambda a,n=1:[mem.get(a+4*i,0) for i in range(n)]
  def upload(a,b,label):
   assert a==pf.CODE
   state['code']=b;state['uploads']+=1
  pf.put=upload
  pf.set_echo_handler=lambda p:state.__setitem__('handler',p)
  def sh(cmd,**kwargs):
   assert cmd=='echo' and kwargs.get('retries')==0
   assert state['handler']==pf.CODE
   if state['code']!=b'CALLFN':raise RuntimeError('executed stale getfile code')
   state['echoes']+=1;mem[pf.P+0x18]=123;mem[pf.P+0x1c]=0xd09e0000
   return 'OK'
  pf.sh=sh
  asm=types.ModuleType('armasm');asm.assemble=lambda *a:b'CALLFN'
  spec=importlib.util.spec_from_file_location('shared_callfn_fixture',SOURCE)
  module=importlib.util.module_from_spec(spec)
  with patch.dict(sys.modules,{'putfile':pf,'armasm':asm}):spec.loader.exec_module(module)
  return module,state,pf

 def test_each_call_restores_code_after_getfile_overwrites_it(self):
  module,state,pf=self.fixture()
  self.assertEqual(module.call(0xc001d7a0,verbose=False),(True,123))
  state['code']=b'GETFILE'
  self.assertEqual(module.call(0xc001d7a0,verbose=False),(True,123))
  self.assertEqual(state['uploads'],2)
  self.assertEqual(state['echoes'],2)
  self.assertEqual(state['handler'],pf.ECHO_ORIG)

 def test_omitting_second_upload_reproduces_stale_code_failure(self):
  module,state,pf=self.fixture()
  module.call(0xc001d7a0,verbose=False)
  state['code']=b'GETFILE'
  with patch.object(module,'put',lambda *a:None):
   with self.assertRaisesRegex(RuntimeError,'stale getfile'):
    module.call(0xc001d7a0,verbose=False)
  self.assertEqual(state['echoes'],1)
  self.assertEqual(state['handler'],pf.ECHO_ORIG)

if __name__=='__main__':unittest.main()
