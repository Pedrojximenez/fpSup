"""Offline checks for recording toggles and uncertain file-transfer ownership."""
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import spatial_hdr_live as L


class FakeRecording(L.Live):
    def __init__(self,state='is_recording -> 0',mode=102):
        self.state=state;self.mode=mode;self.keys=[];self.events=[];self.names=0
    def idle(self):pass
    def clip_names(self):
        self.names+=1
        return {'A001_001'} if self.names==1 else {'A001_001','A001_002'}
    def shell(self,cmd,ms=1000):
        if cmd.startswith('key '):self.keys.append(cmd);return ''
        if cmd=='status get is_recording':return self.state
        raise AssertionError(cmd)
    def words(self,addr,n=1):
        if addr==0xC30338C8:return [0,0,0]
        return [{0xC343B58C:self.mode,0xC343A6AC:7,
                 0xC343B5A8:985,0xC343B5BC:0,0xC343B5B8:100}[addr]]
    def event(self,row):self.events.append(row)


class HostTests(unittest.TestCase):
    @patch.object(L.time,'sleep')
    def test_self_stopped_clip_is_not_restarted(self,_):
        cam=FakeRecording()
        self.assertEqual(cam.record('baseline'),'A001_002')
        self.assertEqual(cam.keys,['key MOVON','key MOVOFF'])

    @patch.object(L.time,'sleep')
    def test_active_clip_is_stopped_with_one_pair(self,_):
        cam=FakeRecording(state='is_recording -> 1')
        cam.record('baseline')
        self.assertEqual(cam.keys,['key MOVON','key MOVOFF']*2)

    @patch.object(L.time,'sleep')
    def test_wrong_mode_is_rejected_after_stopping(self,_):
        cam=FakeRecording(state='is_recording -> 1',mode=6)
        with self.assertRaisesRegex(RuntimeError,'recorded mode/gain context'):
            cam.record('baseline')
        self.assertEqual(cam.keys,['key MOVON','key MOVOFF']*2)
        self.assertEqual(cam.last_record['clip'],'A001_002')

    def test_uncertain_mem1_stages_retain_buffer_and_do_not_retry(self):
        for fault in ('grant','read','revoke'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as tmp:
                cam=object.__new__(L.Live)
                cam.memory=dict(parm=0xC072E500,code=0xC072E600,fobj=0x45010000)
                cam.file_blob=b'code';cam.events=[];cam.freed=[]
                cam.init_memory=lambda:None;cam.write=lambda *a:None
                cam.publish=lambda:None;cam.echo=lambda *a:None
                cam.words=lambda addr,n=1: [64,2,1,1] if n==4 else [0x46000000]
                cam.event=cam.events.append
                cam.native=lambda *a:cam.freed.append(a)
                cam.io=types.SimpleNamespace(transport_faulted=False)
                cam.io._latch_transport_fault=lambda:setattr(cam.io,'transport_faulted',True)
                calls=[]
                def window(i,base,size,flags):
                    phase='grant' if base else 'revoke';calls.append(phase)
                    if fault==phase:raise RuntimeError('uncertain '+phase)
                def read(*a,**kw):
                    calls.append('read')
                    if fault=='read':raise RuntimeError('uncertain read')
                    return bytes(64)
                pf=types.SimpleNamespace(mem_caps=lambda **kw:{'windows':[(0,0,0)]*8},
                                         mem_window=window,mem_read=read)
                with patch.dict('sys.modules',putfile=pf):
                    with self.assertRaisesRegex(RuntimeError,'uncertain'):
                        cam.file('\\CINEMA\\A001_002\\test.DNG',64,Path(tmp)/'frame.dng')
                self.assertTrue(cam.io.transport_faulted)
                self.assertFalse(cam.freed)
                self.assertEqual(calls,dict(grant=['grant'],read=['grant','read'],
                                            revoke=['grant','read','revoke'])[fault])


if __name__=='__main__':unittest.main(verbosity=2)
