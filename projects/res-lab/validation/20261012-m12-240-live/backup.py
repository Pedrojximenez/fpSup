"""Back up exact existing card files with maintained getfile in guarded standby."""
import fcntl,hashlib,importlib,json,pathlib,re,sys
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(HERE.parent/'20261009-oncamera'))
import live_camera as live
live.LOG=HERE/'commands.jsonl'

def idle():
 pf=live.putfile
 assert 'is_recording -> 0' in live.checked_sh('status get is_recording')
 selector=pf.mem_get(0xC347D1D4,tries=1)[0]
 at=0xC3476609 if selector==0x21 else 0xC347E08F
 fields={'movie_recording':(pf.mem_get(at&~3,tries=1)[0]>>((at&3)*8))&255,
         'xmp_file_pointer':pf.mem_get(0xC358E140,tries=1)[0],
         'movie_writing':pf.mem_get(0xC35A952C,tries=1)[0]&255}
 assert not any(fields.values()),fields
 assert pf.mem_get(0xC347D1D4,tries=1)==[selector]
 assert 'is_recording -> 0' in live.checked_sh('status get is_recording')
 return fields

def fetch(remote,dest,size):
 idle();assert not dest.exists() and 0<size<2000000
 getter=importlib.import_module('getfile')
 getter.read_direct=lambda addr,n:live.putfile.read_bulk(addr,n,'tagged')
 sys.argv=['getfile.py',remote,str(dest),'--size',str(size)]
 assert getter.main()==0
 data=dest.read_bytes();assert len(data)==size
 return data

def entries(listing):
 return {m[2]:int(m[1]) for m in re.finditer(r'^.*?\s(\d+)\s+([^\r\n]+)\s*$',listing,re.M)
         if not m[2].strip().startswith('._')}

def main():
 dest=HERE/'backup';dest.mkdir()
 proof={'phase':'backup','written_to_camera':False,'files':{}}
 save=lambda:(dest/'manifest.json').write_text(json.dumps(proof,indent=2)+'\n')
 with open('/tmp/fp-af-fusion.lock') as lease:
  fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
  proof['idle']=idle()
  assert 'slot = sd0' in live.checked_sh('sdcard slot')
  proof['screen']=live.screen();assert proof['screen']=='LV_CINE_MEDIUM'
  todo={'\\AutoRun.txt':4666}
  for folder in ('\\fpSup','\\fpSup\\RESCUS'):
   listing=live.checked_sh('dir '+folder);proof[folder]=listing
   for name,size in entries(listing).items():
    if name.upper().endswith(('.BIN','.RCD')) or name=='LOAD.LOG':todo[folder+'\\'+name]=size
  save()
  for remote,size in todo.items():
   name=remote.lstrip('\\').replace('\\','__')
   data=fetch(remote,dest/name,size)
   proof['files'][remote]={'file':name,'bytes':size,'sha256':hashlib.sha256(data).hexdigest()}
   save();print('BACKED UP',remote,size,flush=True)
  proof['phase']='complete';save()

if __name__=='__main__':main()
