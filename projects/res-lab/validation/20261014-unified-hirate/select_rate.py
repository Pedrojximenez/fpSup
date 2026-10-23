"""Native menu: change only the frame-rate row (9 = 239.76p for M12 240-capable recipes)."""
import fcntl,json,sys,time
import snap;C=snap.C
row=int(sys.argv[1]);dest=snap.HERE/(sys.argv[2]+'.json');assert row in (8,9) and not dest.exists()
with open('/tmp/fp-af-fusion.lock') as l:
 fcntl.flock(l,fcntl.LOCK_EX|fcntl.LOCK_NB);C.idle();screen=C.live.screen();assert screen in ('LV_CINE_MEDIUM','MainB2')
 if screen=='LV_CINE_MEDIUM':C.key('MENU')
 assert C.live.screen()=='MainB2'
 C.key('RIGHT');assert C.live.screen()=='B2_5'
 cur=C.value('MENU_Level2')
 while cur!=4434:
  assert cur in (4247,4297,4254),cur;C.key('DOWN');cur=C.value('MENU_Level2')
 C.key('RIGHT');cur=C.value('B2_n5_ListFocus4');assert 0<=cur<=12
 while cur!=row:
  exp=cur+(1 if cur<row else -1);C.key('DOWN' if cur<row else 'UP');cur=C.value('B2_n5_ListFocus4');assert cur==exp
 C.key('OK');assert C.value('MV_FrameRate')==row
 C.key('MENU')
 if C.live.screen()!='LV_CINE_MEDIUM':C.key('MENU')
 time.sleep(2);assert C.live.screen()=='LV_CINE_MEDIUM'
 r=snap.snapshot();dest.write_text(json.dumps(r,indent=1)+'\n')
 print(r['picked_entry'],r['sensor_timing_fps'],r['engine_fps'],{k:r['state'][k] for k in ('VRATE','HDR_COPY_HITS','BULK_HITS')},flush=True)
