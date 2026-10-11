"""Fetch evidence from a completed trial; never send recording/capture keys."""
import fcntl,importlib,json,pathlib,re,sys
ROOT=pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'projects/res-lab/validation/20261009-oncamera'))
import live_camera as L
sys.path.insert(0,str(ROOT/'projects/open-gate/build'))
from fpcam import parse_dng
HERE=pathlib.Path(__file__).resolve().parent
label=sys.argv[1];nums=[int(n) for n in sys.argv[2:]]
dest=HERE/(label+'-record.json');r=json.loads(dest.read_text())
def save():dest.write_text(json.dumps(r,indent=2)+'\n')
def fetch(remote,path,size):
 if path.exists():assert path.stat().st_size==size;return
 sys.argv=['getfile.py',remote,str(path),'--size',str(size)]
 assert not importlib.import_module('getfile').main()
 assert path.stat().st_size==size
with open('/tmp/fp-af-fusion.lock','r') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert 'is_recording -> 0' in L.checked_sh('status get is_recording')
 assert r['idle_after'] and len(r['new_clips'])==1
 listing=L.listing();r['previews']=[]
 for i,n in enumerate(nums):
  path=HERE/(label+('-rec-preview.jpg' if len(nums)==1 else f'-rec-preview-{i+1}.jpg'))
  fetch(chr(92)+'DCIM'+chr(92)+'100SIGMA'+chr(92)+f'SS__{n:04d}.JPG',path,listing[n])
  r['previews'].append(str(path));save()
 r['capture_requested']=r.get('capture_count',1);r['capture_delivered']=len(nums)
 r['evidence_recovery']='Fetched existing files after screenshot count mismatch; no new keys.'
 clip=r['new_clips'][0];r['clip']=clip
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
 r['passed_continuous']=r['manual_stop'] and r['idle_after']
 save();print(json.dumps({k:r[k] for k in ['label','previews','frames_finished','passed_continuous','capture_requested','capture_delivered']},indent=2))
