"""One guarded take (v21 reference); no USB traffic while frames run; native rec log after."""
import fcntl,json,sys,time
sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parent.parent/'20261014-unified-hirate'))
import snap;C=snap.C
REF=snap.ROOT/'projects/res-lab/cards/20261014-clk0-full/plain'
C.REFERENCE=REF;C.FACT=json.load(open(REF/'build.json'))['facts']
HERE=__import__('pathlib').Path(__file__).resolve().parent
name=sys.argv[1];dur=float(sys.argv[2]);dest=HERE/name;dest.mkdir()
p={'target_s':dur};save=lambda:(dest/'trial.json').write_text(json.dumps(p,indent=1)+'\n')
def pulse():
 try:C.live.checked_sh('key MOVON')
 finally:time.sleep(.12);C.live.checked_sh('key MOVOFF')
with open('/tmp/fp-af-fusion.lock') as l:
 fcntl.flock(l,fcntl.LOCK_EX|fcntl.LOCK_NB)
 p['idle_before']=C.idle();r=C.snapshot();e=r['picked_entry']
 assert r['screen']=='LV_CINE_MEDIUM' and e['ENGFPS']==0x436FC29F,e
 p['entry']=e;p['sensor']=r['sensor_timing_fps'];p['engine']=r['engine_fps']
 p['hits_before']={k:r['state'][k] for k in ('HDR_COPY_HITS','BULK_HITS')}
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
 p['rec_log']=C.live.checked_sh('rec log-out');(dest/'rec-log.txt').write_text(p['rec_log'])
 r=C.snapshot();p['hits_after']={k:r['state'][k] for k in ('HDR_COPY_HITS','BULK_HITS')};save()
 print(json.dumps({k:p[k] for k in ('entry','slot','rec_at_target','elapsed','hits_before','hits_after')}))
 print('\n'.join(p['rec_log'].splitlines()[:13]))
