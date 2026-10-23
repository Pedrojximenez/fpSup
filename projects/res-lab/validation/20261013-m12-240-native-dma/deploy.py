"""Replace only 32RESCUS.BIN (v19 -> v20), keeping the card's own CFG; full readback, no reboot."""
import fcntl,hashlib,importlib,json,struct,sys
from common import *
sys.path.insert(0,str(ROOT/'projects/open-gate/build/res-custom'))
import ogc_layout as L,rcd
V19=(ROOT/'projects/res-lab/cards/20261012-m12-240/plain/fpSup/32RESCUS.BIN').read_bytes()
V20=(ROOT/'projects/res-lab/cards/20261013-m12-240-native-dma/plain/fpSup/32RESCUS.BIN').read_bytes()
assert hashlib.sha256(V19).hexdigest()=='0cb978b7f1568b3d39de4c6b465a548c442912e0962da1d9d8cb6b1304c87dc8'
assert hashlib.sha256(V20).hexdigest()=='abf70106a7ca703d5491bd4af8e6d28e2521aedf81b669b9226307fc2983f16c'
R='\\fpSup\\32RESCUS.BIN';proof={'phase':'start'}
save=lambda:(HERE/'deployment.json').write_text(json.dumps(proof,indent=1)+'\n')
with open('/tmp/fp-af-fusion.lock') as lease:
 fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
 size=B.entries(live.checked_sh('dir \\fpSup'))['32RESCUS.BIN'];assert size==len(V19)
 old=B.fetch(R,HERE/'before-32RESCUS.BIN',size)
 assert old[:32]==V19[:32] and old[128:]==V19[128:],'card consumer is not v19'
 cfg=old[32:128];assert rcd.fnv(cfg[:L.CFG['SUM']])==struct.unpack_from('<I',cfg,L.CFG['SUM'])[0]
 new=V20[:32]+cfg+V20[128:];(HERE/'prepared-32RESCUS.BIN').write_bytes(new)
 proof.update(before=hashlib.sha256(old).hexdigest(),prepared=hashlib.sha256(new).hexdigest(),cfg_preserved=True,phase='write_requested');save()
 B.idle();sys.argv=['putfile.py',str(HERE/'prepared-32RESCUS.BIN'),R];assert importlib.import_module('putfile').main()==0
 assert B.entries(live.checked_sh('dir \\fpSup'))['32RESCUS.BIN']==len(new)
 got=B.fetch(R,HERE/'installed-32RESCUS.BIN',len(new));assert got==new
 proof['phase']='verified';save();print(json.dumps(proof,indent=1))
