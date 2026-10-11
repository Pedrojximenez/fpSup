"""Bounded native-key SAVE test; only remove this run's two verified RCDs."""
import fcntl, hashlib, importlib, json, pathlib, re, sys, time

HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'20261010-sidebar-v13'))
import on_camera as C
import inspect_runtime as I
sys.path.insert(0,str(C.ROOT/'projects/open-gate/build/res-custom'))
import rcd

def key(name):
    assert name in ('UP','DOWN','LEFT','RIGHT','OK')
    C.live.checked_sh('key '+name+'ON');time.sleep(.12)
    C.live.checked_sh('key '+name+'OFF');time.sleep(.7)

def text(name):
    reply=C.live.checked_sh('gui gets '+name)
    return reply.split(' -> ',1)[1].strip()

def fetch(name,dest,size):
    sys.argv=['getfile.py','\\fpSup\\RESCUS\\'+name,str(dest),'--size',str(size)]
    assert not importlib.import_module('getfile').main()
    assert dest.stat().st_size==size

dest=HERE/'save-camera.json';assert not dest.exists()
proof={'passed':False,'files':[]}
with open('/tmp/fp-af-fusion.lock','r') as lease:
    fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert C.live.screen()=='SL_LAB'
    assert 'is_recording -> 0' in C.live.checked_sh('status get is_recording')
    assert ' -> 2' in C.live.checked_sh('gui geti SL_LabTab')
    assert ' -> 35010' in C.live.checked_sh('gui geti SL_LabFocus')
    listing=C.live.checked_sh('dir \\fpSup\\RESCUS')
    assert not re.search(r'\s(?:A9|B9)\.RCD\s*$',listing,re.I|re.M)
    proof['before_directory']=listing
    proof['before']=I.snapshot();proof['mode_before']=text('SL_M_Text')
    assert text('SL_E_Name')=='Name AUTO'
    for k in ('DOWN','OK','UP','RIGHT','DOWN','OK'):key(k)
    assert text('SL_E_Name')=='A9.RCD'
    C.shot('v24-name')
    for name in ('A9','B9'):
        if name=='B9':
            for k in ('UP','OK','UP','OK'):key(k)
            assert text('SL_E_Name')=='B9.RCD'
        key('DOWN');key('OK')
        assert text('SL_E_Text')=='Saved '+name+'.RCD'
        listing=C.live.checked_sh('dir \\fpSup\\RESCUS')
        size=int(re.search(r'(\d+)\s+'+name+r'\.RCD\s*$',listing,re.M)[1])
        local=HERE/(name+'.RCD');assert not local.exists();fetch(name+'.RCD',local,size)
        blob=local.read_bytes();decoded=rcd.decode(blob)
        assert decoded['label']==name
        assert decoded['act']==(proof['before']['producer']['out_w'],proof['before']['producer']['out_h'])
        assert decoded['modes'][0][0]==proof['before']['mode_ids'][proof['before']['producer']['mode_sel']]
        proof['files'].append({'name':name+'.RCD','bytes':size,'sha256':hashlib.sha256(blob).hexdigest(),
                               'label':decoded['label'],'act':decoded['act'],'modes':decoded['modes']})
        dest.write_text(json.dumps(proof,indent=2)+'\n')
    C.shot('v24-saved')
    key('OK');assert text('SL_E_Text')=='Name exists'
    fetch('B9.RCD',HERE/'B9-collision.RCD',proof['files'][-1]['bytes'])
    assert (HERE/'B9-collision.RCD').read_bytes()==(HERE/'B9.RCD').read_bytes()
    proof['after']=I.snapshot();proof['mode_after']=text('SL_M_Text')
    assert proof['mode_before']==proof['mode_after']
    for field in ('registry','consumer','rows','mode_ids'):
        assert proof['before'][field]==proof['after'][field],field
    for field,value in proof['before']['producer'].items():
        if field in ('save_name','name_text','name_field','name_editing'):continue
        assert proof['after']['producer'][field]==value,field
    for name in ('A9.RCD','B9.RCD'):C.live.checked_sh('fl del \\fpSup\\RESCUS\\'+name)
    proof['after_directory']=C.live.checked_sh('dir \\fpSup\\RESCUS')
    assert not re.search(r'\s(?:A9|B9)\.RCD\s*$',proof['after_directory'],re.I|re.M)
    proof['passed']=True;dest.write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({'passed':True,'files':proof['files'],'mode':proof['mode_after'],
                     'geometry_and_consumer_unchanged':True,'test_files_removed':True},indent=2))
