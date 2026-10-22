"""Restore M12 through the verified normal sidebar UI from its tab header."""
import fcntl
import camera as C
with open('/tmp/fp-af-fusion.lock') as lease:
 fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert C.recording()==0 and C.live.screen()=='SL_LAB'
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
 for target in ('FT_LIST','FT_Y6','LV_CINE_MEDIUM'):
  C.key('MENU');assert C.live.screen()==target
 print('M12 selected; verify full runtime before recording',flush=True)
