"""Resident v20 identity + active recipe snapshot (reuses the maintained snapshot with v20 reference)."""
import fcntl,json,pathlib,sys
from common import *
import camera as C
C.live=live
REF=ROOT/'projects/res-lab/cards/20261013-m12-240-native-dma/plain'
C.REFERENCE=REF;C.FACT=json.loads((REF/'build.json').read_text())['facts']
src=C.snapshot.__code__
def snapshot():
 r=C.snapshot();r['consumer_version']=20;return r
if __name__=='__main__':
 name=sys.argv[1];dest=HERE/(name+'.json');assert not dest.exists()
 with open('/tmp/fp-af-fusion.lock') as lease:
  fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
  r=snapshot();r['C038C77C']=hex(live.putfile.mem_get(0xC038C77C,tries=1)[0])
  dest.write_text(json.dumps(r,indent=1)+'\n')
  print(json.dumps({k:r.get(k) for k in ('loaded_core_sha256','screen','frame_rate_getter','quality_getter','lossless','C038C77C','donor','sensor_timing_fps','engine_fps')},indent=1))
  print({k:r['state'][k] for k in ('FLAG','CUR','VRATE','FPSLATCH','HDR_COPY_HITS','BULK_HITS')})
  print([ (x['label'],x['ON']) for x in r['rows']])
