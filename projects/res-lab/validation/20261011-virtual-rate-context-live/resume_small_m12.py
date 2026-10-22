"""Restore audio and enter the M12 setup after the authorized Lossless boot."""
import fcntl
import runpy
import time
import camera as C

with open('/tmp/fp-af-fusion.lock') as lease:
    fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert C.recording()==0 and C.live.screen()=='LV_CINE_MEDIUM'
    assert C.value('MV_fpLossless')==1
    C.key('MENU');assert C.live.screen()=='MainB2'
    assert C.value('MENU_Level1')==34495
    C.key('UP');assert C.value('MENU_Level1')==28971
    C.key('RIGHT');assert C.value('MV_AudioRecord')==0
    C.key('DOWN');C.key('OK')
    assert C.value('MV_AudioRecord')==1
    assert C.live.checked_sh('menu SetAudioRecSupport').strip()=='1'
    C.live.checked_sh('key CMDDIAL1 -1')
    time.sleep(1)
    assert C.live.screen()=='MainB1'
    C.key('LEFT');assert C.live.screen()=='FT_Y6'
    C.key('RIGHT');assert C.live.screen()=='FT_LIST'
    assert C.value('FT_Focus')==3451
runpy.run_path(str(C.HERE/'prepare_small_m12.py'),run_name='__main__')
with open('/tmp/fp-af-fusion.lock') as lease:
    fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
    for _ in range(5):C.key('DOWN')
    C.key('RIGHT')
    assert C.value('SL_LabFocus')==43537 and C.value('SL_O_A0')==1
runpy.run_path(str(C.HERE/'resize_small_m12.py'),run_name='__main__')
