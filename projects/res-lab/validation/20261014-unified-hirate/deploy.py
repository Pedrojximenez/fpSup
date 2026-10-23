"""Replace only \\fpSup\\50RESLAB.BIN (producer v18 -> v19, high-rate record-tap canvas). Full readback, no reboot."""
import fcntl,hashlib,importlib,json,sys
from common import *
NEW=ROOT/'projects/res-lab/cards/20261014-unified-hirate/plain/fpSup/50RES-Lab v0.1.0test.BIN'
OLD_SHA='19491eb0b4a8798ddf145cf73c2704558f1caee82d07dfd8f74da384a4138d00'
R='\\fpSup\\50RESLAB.BIN';data=NEW.read_bytes();proof={'phase':'start','new_sha256':hashlib.sha256(data).hexdigest()}
save=lambda:(HERE/'deployment.json').write_text(json.dumps(proof,indent=1)+'\n')
with open('/tmp/fp-af-fusion.lock') as lease:
 fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
 size=B.entries(live.checked_sh('dir \\fpSup'))['50RESLAB.BIN']
 old=B.fetch(R,HERE/'before-50RESLAB.BIN',size);proof['old_sha256']=hashlib.sha256(old).hexdigest()
 assert proof['old_sha256']==OLD_SHA,'unexpected producer on card'
 proof['phase']='write_requested';save()
 B.idle();sys.argv=['putfile.py',str(NEW),R];assert importlib.import_module('putfile').main()==0
 assert B.entries(live.checked_sh('dir \\fpSup'))['50RESLAB.BIN']==len(data)
 got=B.fetch(R,HERE/'installed-50RESLAB.BIN',len(data));assert got==data
 proof['phase']='verified';save();print(json.dumps(proof,indent=1))
