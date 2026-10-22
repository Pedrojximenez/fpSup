"""On-camera empty-filter preservation and binned-output edit completion."""
import fcntl,json,re,time
import on_camera as C
import inspect_runtime as I
dest=C.HERE/'v14-filter-bin-trial.json'
assert not dest.exists()
proof={'states':{}}
def value(n):
    r=C.live.checked_sh('gui geti '+n);m=re.fullmatch(r'\s*OK:'+n+r' -> (-?\d+)\s*',r);assert m,r
    return int(m[1])
def key(n):
    C.live.checked_sh('key '+n+'ON');time.sleep(.12)
    C.live.checked_sh('key '+n+'OFF');time.sleep(.45)
def keys(*names):
    for name in names:key(name)
def state(name):
    r=I.snapshot();proof['states'][name]=r;dest.write_text(json.dumps(proof,indent=2)+'\n')
    print(name,r['registry'],flush=True);return r
with open('/tmp/fp-af-fusion.lock','r') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert C.live.screen()=='SL_LAB' and value('SL_LabTab')==2
    assert 'is_recording -> 0' in C.live.checked_sh('status get is_recording')
    before=state('before')
    keys('UP','UP','LEFT','LEFT','DOWN','DOWN','DOWN','DOWN')
    assert value('SL_F_Fps')==10 and value('SL_F_Width')==0
    keys(*(['RIGHT']*5))
    empty=state('empty_filter')
    assert empty['producer']['modes_rows']==0
    assert empty['registry']['generation']==before['registry']['generation']
    assert empty['rows']==before['rows']
    assert 'Unsupported output' in C.live.checked_sh('gui gets SL_E_Text')
    keys(*(['LEFT']*5))
    valid=state('restored_filter');assert valid['producer']['modes_rows']==2
    keys('UP','UP','UP','UP','RIGHT','DOWN','DOWN','DOWN','DOWN','DOWN','OK','UP')
    editing=state('bin_editing')
    assert editing['producer']['bin_h']==3 and editing['producer']['editing']==1
    assert editing['registry']['generation']==valid['registry']['generation']
    key('OK');done=state('bin_committed')
    assert done['registry']['generation']==valid['registry']['generation']+1
    keys('OK','UP','OK');restored=state('bin_restored')
    assert restored['producer']['bin_h']==1
    proof['passed']=True;dest.write_text(json.dumps(proof,indent=2)+'\n')
