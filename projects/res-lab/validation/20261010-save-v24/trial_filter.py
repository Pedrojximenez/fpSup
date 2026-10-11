"""M12 remains selected and applied while expanding 279.72 to All fps."""
import fcntl,json,pathlib,sys,time
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'20261010-sidebar-v13'))
import on_camera as C
import inspect_runtime as I
def key(k):
    C.live.checked_sh('key '+k+'ON');time.sleep(.12)
    C.live.checked_sh('key '+k+'OFF');time.sleep(.7)
dest=HERE/'filter-camera.json';assert not dest.exists()
with open('/tmp/fp-af-fusion.lock','r') as lease:
    fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert C.live.screen()=='SL_LAB'
    assert ' -> 1' in C.live.checked_sh('gui geti SL_LabTab')
    assert ' -> 35010' in C.live.checked_sh('gui geti SL_LabFocus')
    assert ' -> 11' in C.live.checked_sh('gui geti SL_F_Fps')
    before=I.snapshot();assert before['mode_ids'][before['producer']['mode_sel']]==12
    for k in ['LEFT']+['DOWN']*5+['LEFT']*11:key(k)
    assert ' -> 0' in C.live.checked_sh('gui geti SL_F_Fps')
    after=I.snapshot()
    assert after['mode_ids'][after['producer']['mode_sel']]==12
    assert f" -> {after['producer']['mode_sel']}" in C.live.checked_sh('gui geti SL_M_Sel')
    assert before['registry']==after['registry']
    for field in ('out_w','out_h','crop_w','crop_h','output_policy','lock_num','lock_den','bin_h','bin_v','ro_w','ro_h'):
        assert before['producer'][field]==after['producer'][field],field
    dest.write_text(json.dumps({'passed':True,'before':before,'after':after},indent=2)+'\n')
    for k in ['UP']*5+['RIGHT','RIGHT']:key(k)
    print('PASS: M12 and output preserved; Mode index',before['producer']['mode_sel'],'->',after['producer']['mode_sel'])
