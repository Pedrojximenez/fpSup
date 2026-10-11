"""Select a supported mode using only observed, complete native UI key pulses."""
import fcntl,json,pathlib,re,sys,time
import live_camera as live
import inspect_runtime as inspect
HERE=pathlib.Path(__file__).resolve().parent
with open('/tmp/fp-af-fusion.lock','r') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert live.screen()=='SL_LAB'
 def value(name):
  reply=live.checked_sh('gui geti '+name)
  m=re.fullmatch(r'\s*OK:'+name+r' -> (-?\d+)\s*',reply);assert m,reply
  return int(m[1])
 assert value('SL_LabTab')==1
 proof=inspect.snapshot();ids=proof['mode_ids'];target=ids.index(int(sys.argv[1]));cur=value('SL_M_Sel')
 for _ in range(len(ids)):
  if cur==target:break
  name='RIGHT' if cur<target else 'LEFT';want=cur+(1 if cur<target else -1)
  live.checked_sh('key '+name+'ON');time.sleep(.12);live.checked_sh('key '+name+'OFF');time.sleep(.55)
  cur=value('SL_M_Sel');assert cur==want,(cur,want)
  if cur%8==0:print('Mode index:',cur,'M'+str(ids[cur]),flush=True)
 assert cur==target
 proof=inspect.snapshot();assert proof['producer']['mode_sel']==target and proof['mode_ids'][target]==int(sys.argv[1])
 label=sys.argv[2] if len(sys.argv)>2 else sys.argv[1]
 dest=HERE/('runtime-mode-'+label+'.json')
 assert not dest.exists(),str(dest)
 dest.write_text(json.dumps(proof,indent=2)+'\n')
 print('Selected M'+sys.argv[1],proof['producer']['out_w'],proof['producer']['out_h'],flush=True)
