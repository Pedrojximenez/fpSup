"""Reduce OUTPUT width with verified normal editor events only."""
import fcntl
import camera as C

with open('/tmp/fp-af-fusion.lock') as lease:
    fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert C.recording()==0 and C.live.screen()=='SL_LAB'
    assert C.value('SL_LabFocus')==43537 and C.value('SL_O_A0')==1
    assert (C.value('SL_O_W'),C.value('SL_O_H'))==(992,662)
    for i in range(22):
        C.key('DOWN')
        assert C.value('SL_O_W')==992-16*(i+1)
    assert (C.value('SL_O_W'),C.value('SL_O_H'))==(640,426)
    C.key('OK');assert C.value('SL_O_A0')==0
    for target in ('FT_LIST','FT_Y6','LV_CINE_MEDIUM'):
        C.key('MENU');assert C.live.screen()==target
    print('M12 OUTPUT selected: 640x426',flush=True)
