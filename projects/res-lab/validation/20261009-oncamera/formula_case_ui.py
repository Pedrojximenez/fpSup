"""Bounded native UI recipes for the two reproduced M98 formula failures."""
import fcntl,json,pathlib,re,sys,time
import live_camera as L
import inspect_runtime as I
here=pathlib.Path(__file__).resolve().parent
def value(name):
    reply=L.checked_sh('gui geti '+name)
    m=re.fullmatch(r'\s*OK:'+name+r' -> (-?\d+)\s*',reply);assert m,reply
    return int(m[1])
def key(name,wait=.35):
    assert name in ('UP','DOWN','LEFT','RIGHT','OK','MENU')
    L.checked_sh('key '+name+'ON');time.sleep(.12)
    L.checked_sh('key '+name+'OFF');time.sleep(wait)
def editor_to(name,target,step):
    for n in range(150):
        now=value(name)
        if now==target:return
        assert abs(now-target)%step==0,(name,now,target)
        direction='UP' if now<target else 'DOWN'
        # Under 20 steps remaining, reset hold acceleration before each key.
        if abs(now-target)<20*step:time.sleep(.4)
        key(direction,.04)
        got=value(name)
        assert got!=now and (got-now)*(target-now)>0,(name,now,target,got)
    raise AssertionError(('edit limit',name,value(name),target))
with open('/tmp/fp-af-fusion.lock','r') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert L.screen()=='SL_LAB'
    assert 'is_recording -> 0' in L.checked_sh('status get is_recording')
    name=sys.argv[1];dest=here/('ui-formula-'+name+'.json');assert not dest.exists()
    if name=='v6-m98-bin3-ratio276':
        assert value('SL_LabTab')==1
        before=I.snapshot();assert before['mode_ids'][before['producer']['mode_sel']]==98
        for k in ('UP','RIGHT','DOWN','OK','RIGHT','RIGHT'):key(k)
        state=I.snapshot();assert state['producer']['editing']==1 and state['producer']['edit_field']==2
        key('UP');assert value('SL_O_BH')==3
        key('OK');key('DOWN')
        assert value('MV_SLScale')==0
        for n in range(7):
            key('RIGHT');assert value('MV_SLScale')==n+1
        assert (value('SL_O_W'),value('SL_O_H'))==(992,360)
        for k in ('DOWN','DOWN','DOWN'):key(k)
    elif name=='v6-m98-free-half':
        # Starting on the Apply row of the previous test.
        assert value('SL_LabTab')==2 and value('SL_LabFocus')==43357
        before=I.snapshot()
        for k in ('UP','UP','UP'):key(k)
        assert value('MV_SLScale')==7
        for n in range(9):
            key('RIGHT');assert value('MV_SLScale')==n+8
        key('UP');key('OK')
        state=I.snapshot();assert state['producer']['editing']==1
        for _ in range(4):
            if I.snapshot()['producer']['edit_field']==2:break
            key('RIGHT')
        assert I.snapshot()['producer']['edit_field']==2
        key('UP');assert value('SL_O_BH')==1
        key('RIGHT');key('RIGHT')
        assert I.snapshot()['producer']['edit_field']==0
        editor_to('SL_O_W',1504,16)
        key('RIGHT');assert I.snapshot()['producer']['edit_field']==1
        editor_to('SL_O_H',1006,2)
        key('OK')
        for k in ('DOWN','DOWN','DOWN','DOWN'):key(k)
    else:raise ValueError(name)
    after=I.snapshot()
    assert value('SL_LabTab')==2 and value('SL_LabFocus')==43357
    p=after['producer'];assert p['editing']==0 and p['canvas_valid']==1
    if name.endswith('free-half'):assert (p['out_w'],p['out_h'],p['bin_h'],p['bin_v'],p['ratio'])==(1504,1006,1,1,16)
    else:assert (p['out_w'],p['out_h'],p['bin_h'],p['bin_v'],p['ratio'])==(992,360,3,1,7)
    canvas=L.putfile.mem_get(int(after['producer_state'],16)+I.FACT['state_fields']['canvas'],29)
    proof={'before':before,'after':after,'canvas':canvas,'rate':L.checked_sh('gui gets SL_O_Rate'),'passed':True}
    dest.write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2),flush=True)
