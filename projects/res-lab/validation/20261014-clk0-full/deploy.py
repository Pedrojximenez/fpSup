"""Replace 32RESCUS.BIN v20 -> v21 (OGC_CLK0_FULL experiment), keeping the card's CFG; full readback."""
import fcntl,hashlib,importlib,json,struct,sys
from common import *
V20=(ROOT/'projects/res-lab/cards/20261013-m12-240-native-dma/plain/fpSup/32RESCUS.BIN').read_bytes()
V21=(ROOT/'projects/res-lab/cards/20261014-clk0-full/plain/fpSup/32RESCUS.BIN').read_bytes()
assert hashlib.sha256(V21).hexdigest()=='69e024b4a01e4ac0aef0d327b50f3f2a37b54adb585c5537ea5ceb595fc290ed'
R='\\fpSup\\32RESCUS.BIN';proof={}
save=lambda:(HERE/'deployment.json').write_text(json.dumps(proof,indent=1)+'\n')
with open('/tmp/fp-af-fusion.lock') as lease:
 fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
 size=B.entries(live.checked_sh('dir \\fpSup'))['32RESCUS.BIN']
 old=B.fetch(R,HERE/'before-32RESCUS.BIN',size)
 assert old[:32]==V20[:32] and old[128:]==V20[128:],'card consumer is not v20'
 assert len(V21)==len(V20)
 new=V21[:32]+old[32:128]+V21[128:];(HERE/'prepared-32RESCUS.BIN').write_bytes(new)
 proof.update(before=hashlib.sha256(old).hexdigest(),prepared=hashlib.sha256(new).hexdigest(),phase='write_requested');save()
 B.idle();sys.argv=['putfile.py',str(HERE/'prepared-32RESCUS.BIN'),R];assert importlib.import_module('putfile').main()==0
 got=B.fetch(R,HERE/'installed-32RESCUS.BIN',len(new));assert got==new
 proof['phase']='verified';save();print(json.dumps(proof,indent=1))
