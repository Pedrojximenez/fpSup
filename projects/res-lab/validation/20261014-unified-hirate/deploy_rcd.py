"""Replace \\fpSup\\RESCUS\\HS280.RCD with the same recipe plus 240/280 record-tap pairs. Original backed up."""
import fcntl,hashlib,importlib,json,sys
from common import *
NEW=HERE/'HS280-hirate.RCD';data=NEW.read_bytes()
R='\\fpSup\\RESCUS\\HS280.RCD';proof={'phase':'start','new_sha256':hashlib.sha256(data).hexdigest()}
save=lambda:(HERE/'deployment-rcd.json').write_text(json.dumps(proof,indent=1)+'\n')
with open('/tmp/fp-af-fusion.lock') as lease:
 fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
 size=B.entries(live.checked_sh('dir \\fpSup\\RESCUS'))['HS280.RCD']
 old=B.fetch(R,HERE/'before-HS280.RCD',size);proof['old_sha256']=hashlib.sha256(old).hexdigest()
 assert proof['old_sha256']=='42024e624ad68c4b6336e9f729aca88acfa85eabb39befdfa70e11eafa89e685'
 proof['phase']='write_requested';save()
 B.idle();sys.argv=['putfile.py',str(NEW),R];assert importlib.import_module('putfile').main()==0
 assert B.entries(live.checked_sh('dir \\fpSup\\RESCUS'))['HS280.RCD']==len(data)
 got=B.fetch(R,HERE/'installed-HS280.RCD',len(data));assert got==data
 proof['phase']='verified';save();print(json.dumps(proof,indent=1))
