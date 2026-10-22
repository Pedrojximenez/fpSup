"""Select a verified FPS row through the native recording menu, idle only."""
import sys,fcntl
import camera as C
row=int(sys.argv[1]);assert row in (8,9,10)
with open('/tmp/fp-af-fusion.lock') as lease:
 fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert C.recording()==0 and C.live.screen()=='LV_CINE_MEDIUM'
 C.key('MENU');assert C.live.screen()=='MainB2'
 C.key('RIGHT');assert C.live.screen()=='B2_5' and C.value('MENU_Level2')==4434
 C.key('RIGHT');current=C.value('B2_n5_ListFocus4');assert current in (8,9,10)
 while current!=row:
  wanted=current+(1 if row>current else -1)
  C.key('DOWN' if row>current else 'UP');current=C.value('B2_n5_ListFocus4');assert current==wanted
 C.key('OK');assert C.value('MV_FrameRate')==row
 C.key('MENU');assert C.live.screen()=='MainB2'
 C.key('MENU');assert C.live.screen()=='LV_CINE_MEDIUM'
 print('Selected',row,flush=True)
