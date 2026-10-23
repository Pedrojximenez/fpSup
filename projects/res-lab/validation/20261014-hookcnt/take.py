"""One guarded SD take on the v22 diagnostic consumer: hook counters before/after, native rec log.
No USB traffic while frames run. Usage: take.py NAME SECONDS"""
import fcntl,json,struct,sys,time
sys.path.insert(0,str(__import__('pathlib').Path(__file__).resolve().parents[1]/'20261012-m12-240-live'))
from common import *
import camera as C
C.live=live
REF=ROOT/'projects/res-lab/cards/20261014-hookcnt/plain'
C.REFERENCE=REF;C.FACT=json.load(open(REF/'build.json'))['facts']
sys.path.insert(0,str(ROOT/'projects/open-gate/build/res-custom'));import ogc_layout as L
NAMES=[n for n,_,_ in L.HOOKS];BACK=0x100
name=sys.argv[1];dur=float(sys.argv[2]);dest=HERE/name;dest.mkdir()
p={'target_s':dur};save=lambda:(dest/'trial.json').write_text(json.dumps(p,indent=1)+'\n')
def counts(s):return dict(zip(NAMES,live.putfile.mem_get(s-BACK,len(NAMES),tries=1)))
def pulse():
 try:live.checked_sh('key MOVON')
 finally:time.sleep(.12);live.checked_sh('key MOVOFF')
with open('/tmp/fp-af-fusion.lock') as l:
 fcntl.flock(l,fcntl.LOCK_EX|fcntl.LOCK_NB)
 r=C.snapshot();s=int(r['consumer_state'],16);e=r.get('picked_entry',{})
 assert r['screen']=='LV_CINE_MEDIUM',r['screen']
 p.update(entry=e,sensor=r.get('sensor_timing_fps'),engine=r.get('engine_fps'),slot=live.checked_sh('sdcard slot').strip())
 c0=counts(s);time.sleep(2.0);c1=counts(s)        # 2 s of standby: the idle rate
 p['standby_2s']={k:c1[k]-c0[k] for k in NAMES if c1[k]-c0[k]};save()
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
 c2=counts(s);p['take']={k:c2[k]-c1[k] for k in NAMES if c2[k]-c1[k]}
 p['rec_log']=live.checked_sh('rec log-out');(dest/'rec-log.txt').write_text(p['rec_log']);save()
 hdr=[x for x in p['rec_log'].splitlines() if x.startswith('req_cnt')]
 print(json.dumps({k:p[k] for k in ('entry','slot','standby_2s','take')},indent=1));print(hdr)
