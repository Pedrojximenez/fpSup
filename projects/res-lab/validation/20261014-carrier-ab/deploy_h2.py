"""Add \\fpSup\\RESCUS\\H2S240.RCD (new file; 9/29 native-29.97 carrier) and verify full read-back."""
import fcntl,hashlib,importlib,json,sys
from common import *
NEW=HERE/'H2S240.RCD';data=NEW.read_bytes()
assert hashlib.sha256(data).hexdigest()=='835d214cf4c0b17d26f075e6ce3f749fe346ac88fb7c9ab4b9fe3642f15cbc99'
R='\\fpSup\\RESCUS\\H2S240.RCD';proof={'phase':'start','sha256':hashlib.sha256(data).hexdigest()}
save=lambda:(HERE/'deployment.json').write_text(json.dumps(proof,indent=1)+'\n')
with open('/tmp/fp-af-fusion.lock') as lease:
 fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert 'H2S240.RCD' not in B.entries(live.checked_sh('dir \\fpSup\\RESCUS'))
 proof['phase']='write_requested';save()
 B.idle();sys.argv=['putfile.py',str(NEW),R];assert importlib.import_module('putfile').main()==0
 assert B.entries(live.checked_sh('dir \\fpSup\\RESCUS'))['H2S240.RCD']==len(data)
 got=B.fetch(R,HERE/'installed-H2S240.RCD',len(data));assert got==data
 proof['phase']='verified';save();print(json.dumps(proof,indent=1))
