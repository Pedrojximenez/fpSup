"""Observed native menu path: change only the selected frame-rate row."""
import fcntl,json,sys
import camera as C

def main():
 row=int(sys.argv[1]);name=sys.argv[2];assert row in (8,9)
 dest=C.HERE/(name+'.json');assert not dest.exists()
 with open('/tmp/fp-af-fusion.lock') as l:
  fcntl.flock(l,fcntl.LOCK_EX|fcntl.LOCK_NB);C.idle();screen=C.live.screen();assert screen in ('LV_CINE_MEDIUM','MainB2')
  if screen=='LV_CINE_MEDIUM':C.key('MENU')
  assert C.live.screen()=='MainB2'
  C.key('RIGHT');assert C.live.screen()=='B2_5'
  current=C.value('MENU_Level2')
  while current!=4434:
   assert current in (4247,4297,4254);C.key('DOWN');current=C.value('MENU_Level2')
  C.key('RIGHT');current=C.value('B2_n5_ListFocus4');assert 0<=current<=12
  while current!=row:
   expect=current+(1 if current<row else -1);C.key('DOWN' if current<row else 'UP');current=C.value('B2_n5_ListFocus4');assert current==expect
  C.key('OK');assert C.value('MV_FrameRate')==row
  C.key('MENU')
  if C.live.screen()!='LV_CINE_MEDIUM':C.key('MENU')
  import time
  time.sleep(2)
  assert C.live.screen()=='LV_CINE_MEDIUM'
  result=C.snapshot();dest.write_text(json.dumps(result,indent=2)+'\n');print(result['picked_entry'],flush=True)
if __name__=='__main__':main()
