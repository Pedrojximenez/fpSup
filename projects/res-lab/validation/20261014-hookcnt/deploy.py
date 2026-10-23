"""Replace 32RESCUS.BIN v21 -> v22 (OGC_HOOKCNT diagnostic: per-hook call counters), keeping the card's CFG; full readback."""
import fcntl,hashlib,importlib,json,sys
from common import *
V21=(ROOT/'projects/res-lab/cards/20261014-clk0-full/plain/fpSup/32RESCUS.BIN').read_bytes()
V22=(ROOT/'projects/res-lab/cards/20261014-hookcnt/plain/fpSup/32RESCUS.BIN').read_bytes()
assert hashlib.sha256(V22).hexdigest()=='36ccf01cccd6d1d7c482ddfa0e640e34230bddb345a0226f0026c690709b1042'
R='\\fpSup\\32RESCUS.BIN';proof={}
save=lambda:(HERE/'deployment.json').write_text(json.dumps(proof,indent=1)+'\n')
with open('/tmp/fp-af-fusion.lock') as lease:
 fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
 size=B.entries(live.checked_sh('dir \\fpSup'))['32RESCUS.BIN']
 old=B.fetch(R,HERE/'before-32RESCUS.BIN',size)
 assert old[:32]==V21[:32] and old[128:]==V21[128:],'card consumer is not v21'
 new=V22[:32]+old[32:128]+V22[128:];(HERE/'prepared-32RESCUS.BIN').write_bytes(new)
 proof.update(before=hashlib.sha256(old).hexdigest(),prepared=hashlib.sha256(new).hexdigest(),phase='write_requested');save()
 B.idle();sys.argv=['putfile.py',str(HERE/'prepared-32RESCUS.BIN'),R];assert importlib.import_module('putfile').main()==0
 assert B.entries(live.checked_sh('dir \\fpSup'))['32RESCUS.BIN']==len(new)
 got=B.fetch(R,HERE/'installed-32RESCUS.BIN',len(new));assert got==new
 proof['phase']='verified';save();print(json.dumps(proof,indent=1))
