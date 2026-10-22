"""Repeat the observed postboot native-menu path; no direct setting override."""
import fcntl
import json
import sys
import camera as C

row = int(sys.argv[1])
assert row in (8, 9, 10)
dest = C.HERE/(sys.argv[2]+'.json')
assert not dest.exists()
with open('/tmp/fp-af-fusion.lock') as lease:
    fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert C.recording()==0 and C.live.screen()=='LV_CINE_MEDIUM'
    C.key('MENU'); assert C.live.screen()=='MainB1'
    C.key('LEFT'); assert C.live.screen()=='FT_Y6'
    C.key('RIGHT'); assert C.live.screen()=='FT_LIST'
    assert C.value('FT_Focus')==3451 and C.value('FT_TabActive1')==1
    for _ in range(2): C.key('RIGHT')
    for _ in range(2): C.key('DOWN')
    assert C.value('FT_Focus')==33620
    assert [C.value('FT_More2'),C.value('FT_Lock2'),C.value('FT_Default2')]==[1,0,0]
    C.key('OK'); C.key('RIGHT'); assert C.live.screen()=='SL_LAB'
    assert C.value('SL_LabTab')==0 and C.value('SL_LabFocus')==35010
    assert C.value('SL_F_Bit')==0 and C.value('SL_F_Fps')==0
    for _ in range(5): C.key('DOWN')
    assert C.value('SL_LabFocus')==43136
    for i in range(10):
        C.key('RIGHT'); assert C.value('SL_F_Fps')==i+1
    assert C.value('SL_ModeMax')==1 and C.value('SL_M_Sel')==0
    for _ in range(4): C.key('UP')
    assert C.value('SL_LabFocus')==42912
    C.key('RIGHT'); assert C.value('SL_M_Sel')==1
    for target in ('FT_LIST','FT_Y6','LV_CINE_MEDIUM'):
        C.key('MENU'); assert C.live.screen()==target
    C.key('MENU'); assert C.live.screen()=='MainY5'
    C.key('RIGHT'); assert C.live.screen()=='FT_Y6'
    C.key('UP'); C.key('RIGHT'); assert C.live.screen()=='MainB1'
    C.key('RIGHT'); assert C.live.screen()=='MainB2'
    C.key('DOWN'); C.key('DOWN'); C.key('RIGHT'); assert C.live.screen()=='B2_5'
    for _ in range(3): C.key('DOWN')
    assert C.value('MENU_Level2')==4434
    C.key('RIGHT'); current=C.value('B2_n5_ListFocus4'); assert current in (8,9,10)
    while current!=row:
        wanted=current+(1 if row>current else -1)
        C.key('DOWN' if row>current else 'UP')
        current=C.value('B2_n5_ListFocus4'); assert current==wanted
    C.key('OK'); assert C.value('MV_FrameRate')==row
    for target in ('MainB2','LV_CINE_MEDIUM'):
        C.key('MENU'); assert C.live.screen()==target
    result=C.snapshot()
    dest.write_text(json.dumps(result,indent=2)+'\n')
    print('M12 native FPS row selected:',row,flush=True)
