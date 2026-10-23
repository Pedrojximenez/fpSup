"""Replace 32RESCUS.BIN v22b -> v22c (hook counters + last virtual-profile record capture), keeping the card's CFG; full readback."""
import fcntl,hashlib,importlib,json,sys
from common import *
V21=(ROOT/'projects/res-lab/cards/20261014-hookcnt/plain/fpSup/32RESCUS.BIN').read_bytes()
V22=(ROOT/'projects/res-lab/cards/20261014-cap/plain/fpSup/32RESCUS.BIN').read_bytes()
assert hashlib.sha256(V22).hexdigest()=='524f8853db7342badc9026cf7a0b0cbf7a3012310bd0e7850ec3296670b028c1'
R='\\fpSup\\32RESCUS.BIN';proof={}
save=lambda:(HERE/'deployment.json').write_text(json.dumps(proof,indent=1)+'\n')
with open('/tmp/fp-af-fusion.lock') as lease:
 fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
 size=B.entries(live.checked_sh('dir \\fpSup'))['32RESCUS.BIN']
 old=B.fetch(R,HERE/'before-32RESCUS.BIN',size)
 assert old[:32]==V21[:32] and old[128:]==V21[128:],'card consumer is not v22b'
 new=V22[:32]+old[32:128]+V22[128:];(HERE/'prepared-32RESCUS.BIN').write_bytes(new)
 proof.update(before=hashlib.sha256(old).hexdigest(),prepared=hashlib.sha256(new).hexdigest(),phase='write_requested');save()
 B.idle();sys.argv=['putfile.py',str(HERE/'prepared-32RESCUS.BIN'),R];assert importlib.import_module('putfile').main()==0
 assert B.entries(live.checked_sh('dir \\fpSup'))['32RESCUS.BIN']==len(new)
 got=B.fetch(R,HERE/'installed-32RESCUS.BIN',len(new));assert got==new
 proof['phase']='verified';save();print(json.dumps(proof,indent=1))
