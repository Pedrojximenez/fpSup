"""Select M12 through the existing normal sidebar; no direct live fields."""
import fcntl
import camera as C

with open('/tmp/fp-af-fusion.lock') as lease:
    fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert C.recording()==0 and C.live.screen()=='FT_LIST'
    assert C.value('FT_Focus')==3451 and C.value('FT_TabActive1')==1
    for _ in range(2):C.key('RIGHT')
    for _ in range(2):C.key('DOWN')
    assert C.value('FT_Focus')==33620
    assert [C.value('FT_More2'),C.value('FT_Lock2'),C.value('FT_Default2')]==[1,0,0]
    C.key('OK');C.key('RIGHT')
    assert C.live.screen()=='SL_LAB'
    assert C.value('SL_LabTab')==0 and C.value('SL_LabFocus')==35010
    assert C.value('SL_F_Bit')==0 and C.value('SL_F_Fps')==0
    for _ in range(5):C.key('DOWN')
    assert C.value('SL_LabFocus')==43136
    for i in range(10):
        C.key('RIGHT');assert C.value('SL_F_Fps')==i+1
    assert C.value('SL_ModeMax')==1 and C.value('SL_M_Sel')==0
    for _ in range(4):C.key('UP')
    assert C.value('SL_LabFocus')==42912
    C.key('RIGHT');assert C.value('SL_M_Sel')==1
    C.key('UP');assert C.value('SL_LabFocus')==35010
    C.key('RIGHT');assert C.value('SL_LabTab')==1
    print('M12 selected, OUTPUT tab ready',flush=True)
