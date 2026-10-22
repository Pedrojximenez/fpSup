"""Native-key M12 sidebar trial; assert consumer changes only at edit completion."""
import fcntl
import json
import pathlib
import re
import sys
import time
import on_camera as C
import inspect_runtime as I

dest = C.HERE/(sys.argv[1]+'.json')
assert not dest.exists()
proof = {'steps': []}


def save(): dest.write_text(json.dumps(proof, indent=2)+'\n')
def value(name):
    reply = C.live.checked_sh('gui geti '+name)
    m = re.fullmatch(r'\s*OK:'+name+r' -> (-?\d+)\s*',reply)
    assert m, reply
    return int(m[1])
def key(name):
    assert name in ('UP','DOWN','LEFT','RIGHT','OK','MENU')
    C.live.checked_sh('key '+name+'ON'); time.sleep(.12)
    C.live.checked_sh('key '+name+'OFF'); time.sleep(.5)
def state(label):
    r = I.snapshot(); proof['steps'].append({'label':label, **r}); save()
    print(label, 'generation', r['registry']['generation'], 'output', r['producer']['out_w'], r['producer']['out_h'], flush=True)
    return r


with open('/tmp/fp-af-fusion.lock','r') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert C.live.screen() == 'SL_LAB'
    assert 'is_recording -> 0' in C.live.checked_sh('status get is_recording')
    assert value('SL_LabTab') == 1 and value('SL_LabFocus') == 35010
    initial = state('initial')
    assert initial['mode_ids'][initial['producer']['mode_sel']] == 12
    g = initial['registry']['generation']
    for k in ('DOWN','DOWN','RIGHT'): key(k)
    assert value('SL_O_Lock') == 1
    assert state('shape_lock')['registry']['generation'] == g
    for k in ('DOWN','OK','DOWN','DOWN','DOWN','DOWN'): key(k)
    edit = state('crop_editing')
    assert edit['registry']['generation'] == g and edit['producer']['crop_w'] > 0
    key('OK'); cropped = state('crop_committed')
    assert cropped['registry']['generation'] == g+1
    assert abs((2016-cropped['producer']['crop_w'])/(672-cropped['producer']['crop_h'])-3) < .04
    for k in ('DOWN','OK','DOWN','DOWN'): key(k)
    output = state('output_editing')
    assert output['producer']['editing'] == 1 and output['registry']['generation'] == g+1
    key('MENU'); done = state('output_committed_by_menu')
    assert C.live.screen() == 'SL_LAB'
    assert done['producer']['editing'] == 0 and done['registry']['generation'] == g+2
    # Anamorphic lens is independent of the crop and mode-restoration setting.
    for k in ('DOWN','DOWN','DOWN','RIGHT'): key(k)
    lens = state('lens_on')
    assert lens['producer']['lens_on'] == 1
    assert (lens['producer']['crop_w'],lens['producer']['crop_h']) == (done['producer']['crop_w'],done['producer']['crop_h'])
    assert abs(lens['producer']['out_w']/lens['producer']['out_h']-1.5*1.33) < .03
    for k in ('DOWN','OK','UP','UP'): key(k)
    factor = state('factor_editing')
    assert factor['producer']['lens_factor'] == 135
    assert factor['registry']['generation'] == lens['registry']['generation']
    key('OK'); factor = state('factor_committed')
    assert factor['registry']['generation'] == lens['registry']['generation']+1
    C.shot(sys.argv[1]+'-lens')
    proof['passed'] = True; save()
