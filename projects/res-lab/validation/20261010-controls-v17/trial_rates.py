"""Bounded, native-key check of the installed MB/s row; never changes REC FPS."""
import fcntl
import json
import pathlib
import re
import sys
import time

HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'20261010-sidebar-v13'))
import on_camera as C
import inspect_runtime as I

def integer(name):
    text=C.live.checked_sh('gui geti '+name)
    match=re.fullmatch(r'\s*OK:'+name+r' -> (\d+)\s*',text)
    assert match,text
    return int(match[1])

def key(name):
    assert name in ('LEFT','RIGHT')
    C.live.checked_sh('key '+name+'ON');time.sleep(.12)
    C.live.checked_sh('key '+name+'OFF');time.sleep(.5)

dest=HERE/'rates-v23.json'
assert not dest.exists()
proof={'steps':[],'passed':False}
with open('/tmp/fp-af-fusion.lock','r') as lease:
    fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert C.live.screen()=='SL_LAB'
    assert 'is_recording -> 0' in C.live.checked_sh('status get is_recording')
    assert integer('SL_LabTab')==1 and integer('SL_LabFocus')==43583 and integer('SL_O_RFps')==0
    proof['before']=I.snapshot()
    proof['native_fps_before']=C.live.checked_sh('menu SetMovFramerate')
    # Two words inside the just-verified producer's owned state allocation.
    base=int(proof['before']['producer_state'],16)
    matrix=C.live.putfile.mem_get(base+I.FACT['state_fields']['canvas'],2)
    proof['record_matrix']=matrix
    assert proof['before']['mode_ids'][proof['before']['producer']['mode_sel']]==123
    for i,fps in enumerate((2398,2400,2500,2997,4800,5000,5994,10000,11988,23976,27972)):
        if i:key('RIGHT')
        assert integer('SL_O_RFps')==i
        text=C.live.checked_sh('gui gets SL_O_Rate')
        expected=(matrix[0]*matrix[1]*12*fps+400000000)//800000000
        label=f'{fps/100:.2f}'.rstrip('0').rstrip('.')
        assert f'{label}p {expected} MB/s' in text,text
        proof['steps'].append({'fps100':fps,'expected_MBps':expected,'reply':text})
        dest.write_text(json.dumps(proof,indent=2)+'\n')
    C.shot('v23-rate-279')
    for _ in range(7):key('LEFT')
    assert integer('SL_O_RFps')==3
    proof['after']=I.snapshot()
    proof['native_fps_after']=C.live.checked_sh('menu SetMovFramerate')
    assert proof['native_fps_after']==proof['native_fps_before']
    assert proof['after']['registry']==proof['before']['registry']
    assert proof['after']['producer']==proof['before']['producer']
    proof['passed']=True
    dest.write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({'passed':True,'rates':len(proof['steps']),'record_matrix':matrix,'native_fps':proof['native_fps_after'].strip()},indent=2))
