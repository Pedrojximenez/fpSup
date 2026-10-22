"""One bounded native recording; preserve early stop and preview evidence."""
import fcntl,importlib,json,pathlib,re,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'projects/res-lab/validation/20261009-oncamera'))
import live_camera as L,inspect_runtime as I
from fps_state import snapshot
sys.path.insert(0,str(ROOT/'projects/open-gate/build'))
from fpcam import parse_dng
HERE=pathlib.Path(__file__).resolve().parent
label=sys.argv[1];want=int(sys.argv[2]);options=sys.argv[3:]
sequence='--preview-sequence' in options;duration=6.0 if sequence else 3.5
late='--capture-late' in options
if late:duration=6.0
dest=HERE/(label+'-record.json');assert not dest.exists()
r={'label':label,'expected_rank':want,'observations':[],'manual_stop':False}
def save():dest.write_text(json.dumps(r,indent=2)+'\n')
def rec():
 s=L.checked_sh('status get is_recording');m=re.fullmatch(r'\s*is_recording -> ([01])\s*',s);assert m,s
 return int(m[1])
def clips():
 s=L.checked_sh('dir '+chr(92)+'CINEMA')
 return {m[4]:''.join(m.groups()[:3]) for m in re.finditer(r'^\s*(\d{4})/(\d{2})/(\d{2}).*\b(A\d{3}_\d{3})\s*$',s,re.M)}
def pulse():
 try:L.checked_sh('key MOVON')
 finally:time.sleep(.12);L.checked_sh('key MOVOFF')
def fetch(remote,path,size,partial=False):
 assert not path.exists()
 sys.argv=['getfile.py',remote,str(path),'--size',str(size)]+(['--partial'] if partial else [])
 assert not importlib.import_module('getfile').main()
with open('/tmp/fp-af-fusion.lock','r') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert L.screen()=='LV_CINE_MEDIUM' and rec()==0
 r['before']=snapshot()
 if want:assert r['before']['fps_state']['VRATE']==want and r['before']['picked_entry']['VRATE']==want
 else:assert r['before']['picked_entry']['VRATE']==0
 for option in options:
  if option.startswith('--native-fps='):
   assert int(r['before']['fps_getter'].strip())==int(option.split('=')[1])
 rt=r['before'];assert rt['registry']['provider']==0x42414c52 and rt['registry']['generation']>0
 before=clips();screens=L.listing();r['clips_before']=before;save()
 start=time.monotonic();pulse()
 if '--capture-start' in sys.argv[3:]:
  L.checked_sh('key CAPTUREON');time.sleep(.12);L.checked_sh('key CAPTUREOFF')
  r['capture_sent']=True;save()
 else:time.sleep(.45)
 for i in range(20):
  state=rec();r['observations'].append({'seconds':round(time.monotonic()-start,3),'recording':state});save()
  if not state:break
  elapsed=time.monotonic()-start
  captures=r.get('capture_count',0)
  if (sequence and captures<3 and elapsed>=(.5,2.0,4.0)[captures]) or (not sequence and (elapsed>=3.0 if late else i==0) and not r.get('capture_sent')):
   L.checked_sh('key CAPTUREON');time.sleep(.12);L.checked_sh('key CAPTUREOFF')
   r['capture_sent']=True;r['capture_count']=captures+1;save()
  if time.monotonic()-start>=duration:
   # Only stop an observed active recording, once.
   pulse();r['manual_stop']=True;save();time.sleep(1);break
  time.sleep(.5)
 final=rec();r['idle_after']=not final;save()
 if final:raise RuntimeError('Recording still active; no uncertain toggle replayed')
 time.sleep(2)
 r['native_log']=L.checked_sh('rec log-out');r['clips_after']=clips()
 new=sorted(r['clips_after'].keys()-before.keys());r['new_clips']=new;save()
 if r.get('capture_sent'):
  now=L.listing();nums=sorted(now.keys()-screens.keys())
  r['capture_requested']=r.get('capture_count',1);r['capture_delivered']=len(nums);save()
  if not nums:raise RuntimeError('No screenshot delivered; preserving recording report without replay')
  r['previews']=[]
  for index,n in enumerate(nums):
   path=HERE/(label+('-rec-preview.jpg' if len(nums)==1 else f'-rec-preview-{index+1}.jpg'))
   fetch(chr(92)+'DCIM'+chr(92)+'100SIGMA'+chr(92)+f'SS__{n:04d}.JPG',path,now[n]);r['previews'].append(str(path));save()
 if len(new)==1:
  clip=new[0];r['clip']=clip
  count=re.search(r'req_cnt=(\d+), fin_cnt=(\d+)',r['native_log']);size=re.search(r'file-size=(\d+)',r['native_log'])
  assert count and size
  r['frames_requested']=int(count[1]);r['frames_finished']=int(count[2]);r['file_size']=int(size[1]);samples=[]
  for n in sorted(set([1,max(1,int(count[2])//2),int(count[2])])):
   path=HERE/(label+f'-frame{n:06d}.dng')
   remote=chr(92)+'CINEMA'+chr(92)+clip+chr(92)+clip+'_'+r['clips_after'][clip]+f'_{n:06d}.DNG'
   fetch(remote,path,int(size[1]))
   valid=path.read_bytes()[:4]==b'II*'+bytes(1)
   detail={'frame':n,'file':str(path),'tiff_header':valid}
   if valid:main,ifds=parse_dng(path);detail['tags']=main
   samples.append(detail);r['samples']=samples;save()
 r['after']=snapshot();r['passed_continuous']=r['manual_stop'] and r['idle_after'] and len(new)==1
 save();print(json.dumps({k:r[k] for k in ('label','manual_stop','idle_after','new_clips','frames_finished','passed_continuous','observations') if k in r},indent=2),flush=True)
