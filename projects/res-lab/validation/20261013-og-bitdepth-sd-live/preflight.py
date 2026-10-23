import fcntl,hashlib,json
from common import *
with open('/tmp/fp-af-fusion.lock') as lease:
 fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
 p={'idle':B.idle(),'slot':live.checked_sh('sdcard slot').strip(),'screen':live.screen()}
 p['rescus_dir']=live.checked_sh('dir \\fpSup\\RESCUS');p['fpsup_dir']=live.checked_sh('dir \\fpSup')
 ent=B.entries(p['rescus_dir']);d=HERE/'pre';d.mkdir()
 for n in OLD_SHA:
  data=B.fetch('\\fpSup\\RESCUS\\'+n,d/n,ent[n]);p[n]=hashlib.sha256(data).hexdigest()
 for g in ('SetMovCinemaDNGQuality','SetMovFramerate'):p[g]=live.checked_sh('menu '+g).strip()
 (HERE/'preflight.json').write_text(json.dumps(p,indent=1,ensure_ascii=False));print(json.dumps(p,indent=1,ensure_ascii=False))
