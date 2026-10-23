"""Replace interim v20a with final v20 (240: native DMA header + native 64MiB). CFG kept; full readback."""
import fcntl,hashlib,importlib,json,sys
from common import *
A=(HERE/'interim-v20a-installed.BIN').read_bytes()
V20=(ROOT/'projects/res-lab/cards/20261013-m12-240-native-dma/plain/fpSup/32RESCUS.BIN').read_bytes()
assert hashlib.sha256(V20).hexdigest()=='03ad3119a7680bccdf8be6b27a834abe3324fbd8decb8f2be6ff294aef6b8a28'
R='\\fpSup\\32RESCUS.BIN';proof={'phase':'start'}
save=lambda:(HERE/'deployment.json').write_text(json.dumps(proof,indent=1)+'\n')
with open('/tmp/fp-af-fusion.lock') as lease:
 fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
 old=B.fetch(R,HERE/'before2-32RESCUS.BIN',len(A));assert old==A
 new=V20[:32]+A[32:128]+V20[128:];(HERE/'prepared2-32RESCUS.BIN').write_bytes(new)
 proof.update(before=hashlib.sha256(old).hexdigest(),prepared=hashlib.sha256(new).hexdigest(),cfg_preserved=True,phase='write_requested');save()
 B.idle();sys.argv=['putfile.py',str(HERE/'prepared2-32RESCUS.BIN'),R];assert importlib.import_module('putfile').main()==0
 got=B.fetch(R,HERE/'installed-32RESCUS.BIN',len(new));assert got==new
 proof['phase']='verified';save();print(json.dumps(proof,indent=1))
