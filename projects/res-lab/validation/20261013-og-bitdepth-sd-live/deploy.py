"""Authorized: replace OG35K.RCD/OG4K.RCD with v18 section-13 versions; full readback, no reboot."""
import fcntl,hashlib,importlib,json
from common import *
proof={'phase':'start','writes':{}}
save=lambda:(HERE/'deployment.json').write_text(json.dumps(proof,indent=1))
with open('/tmp/fp-af-fusion.lock') as lease:
 fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
 for n in OLD_SHA:
  data=(NEW/n).read_bytes();assert hashlib.sha256(data).hexdigest()==NEW_SHA[n]
 pre=B.entries(live.checked_sh('dir \\fpSup\\RESCUS'))
 for n in OLD_SHA:
  B.idle();remote='\\fpSup\\RESCUS\\'+n;data=(NEW/n).read_bytes()
  proof['phase']='write_requested';proof['current']=remote;save()
  sys.argv=['putfile.py',str(NEW/n),remote];assert importlib.import_module('putfile').main()==0
  ent=B.entries(live.checked_sh('dir \\fpSup\\RESCUS'));assert ent[n]==len(data),(n,ent.get(n))
  got=B.fetch(remote,HERE/('installed-'+n),len(data));assert got==data
  proof['writes'][remote]={'bytes':len(got),'sha256':hashlib.sha256(got).hexdigest(),'old_bytes':pre[n]};save()
 post=B.entries(live.checked_sh('dir \\fpSup\\RESCUS'))
 proof['other_entries_unchanged']={k:v for k,v in post.items() if k not in OLD_SHA}=={k:v for k,v in pre.items() if k not in OLD_SHA}
 proof['phase']='verified';save();print(json.dumps(proof,indent=1))
