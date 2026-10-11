"""A single fresh CinemaDNG clip with observed start/stop and retained header."""
import fcntl,importlib,json,pathlib,re,sys,time
from fractions import Fraction
import live_camera as live
import inspect_runtime as inspect
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(live.ROOT/'projects/open-gate/build'))
from fpcam import parse_dng
label=sys.argv[1]
expected_fps=Fraction(int(sys.argv[2]),1001) if len(sys.argv)>2 else None
proof={'label':label,'started':False,'stopped':False}
def save(): (HERE/('record-'+label+'.json')).write_text(json.dumps(proof,indent=2)+'\n')
def recording():
 r=live.checked_sh('status get is_recording');m=re.fullmatch(r'\s*is_recording -> ([01])\s*',r);assert m,r
 return int(m[1])
def clips():
 r=live.checked_sh('dir \\CINEMA');return {m[4]:''.join(m.groups()[:3]) for m in re.finditer(r'^\s*(\d{4})/(\d{2})/(\d{2}).*\b(A\d{3}_\d{3})\s*$',r,re.M)}
def pulse():
 try:live.checked_sh('key MOVON')
 finally:
  time.sleep(.12);live.checked_sh('key MOVOFF')
with open('/tmp/fp-af-fusion.lock','r') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert live.screen()=='LV_CINE_MEDIUM'
 assert re.fullmatch(r'\s*app_current -> 2\s*',live.checked_sh('status get app_current'))
 assert recording()==0
 runtime=inspect.snapshot();proof['runtime_before']=runtime;save()
 assert runtime['registry']['provider']==0x42414c52 and runtime['registry']['generation']>0
 assert runtime['consumer']['flag']==1 and runtime['consumer']['current']==runtime['registry']['row']+1
 if expected_fps is not None:
  from fps_state import snapshot
  fps=snapshot();proof['fps_before']=fps
  assert fps['fps_state']['VRATE']==int(expected_fps*100),fps['fps_state']
 row=runtime['rows'][runtime['registry']['row']]
 before=clips();proof['clips_before']=before;save()
 pulse()
 time.sleep(1)
 for _ in range(5):
  if recording()==1:break
  time.sleep(.5)
 else:raise RuntimeError('Recording did not start; no stop toggle sent')
 proof['started']=True;save();time.sleep(2)
 pulse();time.sleep(1)
 for _ in range(6):
  if recording()==0:break
  time.sleep(1)
 else:raise RuntimeError('Recording did not stop; no toggle replayed')
 proof['stopped']=True;save();time.sleep(2)
 after=clips();new=sorted(after.keys()-before.keys());proof['clips_after']=after;save()
 assert len(new)==1,new
 clip=new[0];remote=f'\\CINEMA\\{clip}\\{clip}_{after[clip]}_000001.DNG';dest=HERE/(clip+'-first-frame-header.dng')
 sys.argv=['getfile.py',remote,str(dest),'--size','131072','--partial']
 assert not importlib.import_module('getfile').main()
 main,ifds=parse_dng(dest)
 proof.update(clip=clip,remote=remote,header=str(dest),main_ifd=main,ifds=ifds,expected_size=[row['width'],row['height']])
 proof['record_raster']=[main['ImageWidth'],main['ImageLength']]
 proof['size_matches']=list(main.get('DefaultCropSize',()))==proof['expected_size'];save()
 assert proof['size_matches'],proof
 if expected_fps is not None:
  proof['expected_fps']=str(expected_fps)
  proof['fps_matches']=Fraction(main['FrameRate'])==expected_fps;save()
  assert proof['fps_matches'],proof
 print(json.dumps({k:proof[k] for k in ('clip','started','stopped','expected_size','main_ifd','size_matches')},indent=2),flush=True)
