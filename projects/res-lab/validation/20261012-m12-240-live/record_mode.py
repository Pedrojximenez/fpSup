"""One native-LCD guarded M12240 trial. No camera polling while frames run."""
import fcntl,hashlib,importlib,json,pathlib,re,struct,sys,time
import camera as C
from backup import fetch
from importlib.util import spec_from_file_location,module_from_spec
spec=spec_from_file_location('m12_lcd',C.HERE.parent/'20261011-virtual-rate-context-live/native_lcd.py');LCD=module_from_spec(spec);spec.loader.exec_module(LCD)

def clips():
 text=C.live.checked_sh('dir \\CINEMA')
 return {m[4]:''.join(m.groups()[:3]) for m in re.finditer(r'^\s*(\d{4})/(\d{2})/(\d{2}).*\b(A\d{3}_\d{3})\s*$',text,re.M)}
def check(r,rank=23976):
 s=r['state'];cur=s['CUR'];assert s['FLAG']==1 and cur and s['PICKOK']==1
 row=r['rows'][cur-1]
 assert row['label']=='M12240' and row['ON']==1 and [row[k] for k in ('AW','AH','BITMASK')]==[992,662,4],row
 e=r['picked_entry'];assert r['donor']==12
 expected=(0x014A014A,0x0006038E,0x436FC29F,240,23976) if rank==23976 else (0x014A014A,0x0006071C,0x42700000,120,0)
 assert (e['W0'],e['W1'],e['ENGFPS'],e['NOMINAL'],e['VRATE'])==expected
 assert s['VRATE']==rank and s['BITLATCH']==0 and s['RATE_LVOWED']==0
 assert r['frame_rate_getter']=='7' and r['quality_getter']=='0' and r['lossless']==0
 assert r['variant'][1]==C.live.putfile.mem_get(C.L.MAPPING+13*4,tries=1)[0]
 return {'output':[992,662],'raw':[1008,672],'sensor_timing_fps':r['sensor_timing_fps'],'engine_fps':r['engine_fps'],'p13_preserved':True}
def pulse(proof,save,action):
 proof[action+'_down_requested']=True;save()
 try:C.live.checked_sh('key MOVON')
 finally:
  time.sleep(.12);C.live.checked_sh('key MOVOFF');proof[action+'_released']=True;save()
def main():
 name=sys.argv[1];duration=float(sys.argv[2]);rank=int(sys.argv[3]) if len(sys.argv)>3 else 23976;assert rank in (0,23976) and 0<duration<=20
 dest=C.HERE/name;dest.mkdir();proof={'phase':'preflight','target_seconds':duration,'start_sent':False,'stop_sent':False,'camera_polling_during_capture':False}
 save=lambda:(dest/'trial.json').write_text(json.dumps(proof,indent=2)+'\n')
 save()
 with open('/tmp/fp-af-fusion.lock') as l:
  fcntl.flock(l,fcntl.LOCK_EX|fcntl.LOCK_NB)
  proof['idle_before']=C.idle();r=C.snapshot();proof['before']=r;save();proof['mode_checks']=check(r,rank)
  assert r['screen']=='LV_CINE_MEDIUM';proof['slot']=C.live.checked_sh('sdcard slot')
  proof['before_lcd']=LCD.shot(name+'-before',dest)
  proof['clips_before']=clips();proof['audio']=C.live.checked_sh('menu SetAudioRecSupport').strip();save()
  start=time.monotonic();proof['start_sent']=True;proof['phase']='capture';save();pulse(proof,save,'start')
  time.sleep(max(0,duration-(time.monotonic()-start)))
  current=C.recording();proof['recording_at_target']=current;proof['host_elapsed_at_target']=time.monotonic()-start;save()
  if current:
   assert C.recording()==1
   proof['stop_sent']=True;save();pulse(proof,save,'stop')
  else:proof['automatic_stop']=True;save()
  for _ in range(10):
   if C.recording()==0:break
   time.sleep(.5)
  else:raise RuntimeError('REC remains positive; no toggle replay, no file tools')
  for i in range(6):
   try:proof['idle_after']=C.idle();break
   except AssertionError as exc:
    proof['drain_wait']=str(exc);save()
    if i==5:raise
    time.sleep(2)
  proof['after_lcd']=LCD.shot(name+'-after',dest)
  proof['record_log']=C.live.checked_sh('rec log-out');save()
  m=re.search(r'req_cnt=(\d+), fin_cnt=(\d+),',proof['record_log']);assert m,proof['record_log']
  req,fin=map(int,m.groups());proof['requested']=req;proof['finished']=fin
  proof['clips_after']=clips();proof['new_clips']=sorted(proof['clips_after'].keys()-proof['clips_before'].keys())
  proof['after']=C.snapshot();proof['mode_checks_after']=check(proof['after'],rank)
  proof['button_stop_completed']=proof['stop_sent'] and req==fin and req>0
  proof['phase']='trial_completed';save();print(json.dumps({k:proof[k] for k in ('phase','recording_at_target','stop_sent','requested','finished','new_clips','record_log')},indent=2),flush=True)
if __name__=='__main__':main()
