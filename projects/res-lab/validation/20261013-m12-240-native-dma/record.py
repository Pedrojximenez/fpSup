"""One guarded take; no USB traffic while frames run."""
import fcntl,json,re,sys,time
import snap;C=snap.C
name=sys.argv[1];dur=float(sys.argv[2]);dest=snap.HERE/name;dest.mkdir()
p={'target_s':dur};save=lambda:(dest/'trial.json').write_text(json.dumps(p,indent=1)+'\n')
def pulse():
 try:C.live.checked_sh('key MOVON')
 finally:time.sleep(.12);C.live.checked_sh('key MOVOFF')
with open('/tmp/fp-af-fusion.lock') as l:
 fcntl.flock(l,fcntl.LOCK_EX|fcntl.LOCK_NB)
 p['idle_before']=C.idle();r=snap.snapshot();e=r['picked_entry']
 assert r['screen']=='LV_CINE_MEDIUM' and e['ENGFPS']==0x436FC29F and e['VRATE']==23976
 p['entry']=e;p['hits_before']={k:r['state'][k] for k in ('HDR_COPY_HITS','BULK_HITS')}
 p['slot']=C.live.checked_sh('sdcard slot').strip();save()
 t=time.monotonic();pulse();time.sleep(max(0,dur-(time.monotonic()-t)))
 p['rec_at_target']=C.recording();p['elapsed']=time.monotonic()-t
 if p['rec_at_target']:pulse();p['stop_sent']=True
 save()
 for _ in range(20):
  if C.recording()==0:break
  time.sleep(.5)
 for i in range(10):
  try:p['idle_after']=C.idle();break
  except AssertionError:time.sleep(2)
 p['rec_log']=C.live.checked_sh('rec log-out')
 r=snap.snapshot();p['hits_after']={k:r['state'][k] for k in ('HDR_COPY_HITS','BULK_HITS')};save()
 print(json.dumps({k:p[k] for k in ('rec_at_target','elapsed','hits_before','hits_after')},indent=1));print(p['rec_log'][-600:])
