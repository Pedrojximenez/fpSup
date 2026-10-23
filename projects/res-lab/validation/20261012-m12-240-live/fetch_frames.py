"""Fetch exact known first/middle/last DNG names only after guarded standby."""
import fcntl,hashlib,json,pathlib,re,sys
import camera as C
from backup import fetch
sys.path.insert(0,str(C.ROOT/'projects/open-gate/build'))
from fpcam import parse_dng

def main():
 name=sys.argv[1];dest=C.HERE/name;trial=json.loads((dest/'trial.json').read_text())
 assert trial['phase']=='trial_completed' and len(trial['new_clips'])==1
 clip=trial['new_clips'][0];date=trial['clips_after'][clip]
 size=int(re.search(r'file-size=(\d+),',trial['record_log'])[1]);count=trial['finished']
 assert 0<count==trial['requested']<10000 and size==1095168
 report={'clip':clip,'count':count,'sample_only':True,'frames':[]};save=lambda:(dest/'raw-frames.json').write_text(json.dumps(report,indent=2)+'\n')
 with open('/tmp/fp-af-fusion.lock') as l:
  fcntl.flock(l,fcntl.LOCK_EX|fcntl.LOCK_NB);report['idle_before']=C.idle();save()
  for n in sorted({1,(count+1)//2,count}):
   remote=f'\\CINEMA\\{clip}\\{clip}_{date}_{n:06d}.DNG';local=dest/f'{clip}-{n:06d}.DNG'
   data=fetch(remote,local,size);main,ifds=parse_dng(local)
   report['frames'].append({'number':n,'sha256':hashlib.sha256(data).hexdigest(),'main_ifd':main,'ifds':ifds});save()
 print([(r['number'],r['main_ifd'].get('FrameRate')) for r in report['frames']],flush=True)
if __name__=='__main__':main()
