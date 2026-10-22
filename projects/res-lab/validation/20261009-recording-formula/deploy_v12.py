"""Reviewed BIN-only producer update, preserving a complete old file."""
import fcntl,hashlib,importlib,json,pathlib,sys
ROOT=pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'projects/res-lab/validation/20261009-oncamera'))
import live_camera as live
HERE=pathlib.Path(__file__).resolve().parent
OLD=ROOT/'projects/res-lab/cards/20261009-virtual-rcd-v11-final/debug'
CARD=ROOT/'projects/res-lab/cards/20261010-virtual-rcd-v12/debug'
name='50RESLAB.BIN';target=chr(92)+'fpSup'+chr(92)+name
source=CARD/'fpSup'/name;backup=HERE/('v12-before-'+name);dest=HERE/('v12-installed-'+name)
proof={'target':target,'card':str(CARD),'phase':'preflight'}
def save(): (HERE/'v12-deployment.json').write_text(json.dumps(proof,indent=2)+'\n')
def fetch(local,size):
 sys.argv=['getfile.py',target,str(local),'--size',str(size)]
 assert not importlib.import_module('getfile').main()
 assert local.stat().st_size==size
with open('/tmp/fp-af-fusion.lock','r') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert not backup.exists() and not dest.exists()
 assert 'is_recording -> 0' in live.checked_sh('status get is_recording')
 assert 'slot = sd0' in live.checked_sh('sdcard slot')
 assert (OLD/'AutoRun.txt').read_bytes()==(CARD/'AutoRun.txt').read_bytes()
 assert (OLD/'fpSup/32RESCUS.BIN').read_bytes()==(CARD/'fpSup/32RESCUS.BIN').read_bytes()
 fetch(backup,(OLD/'fpSup'/name).stat().st_size)
 assert backup.read_bytes()==(OLD/'fpSup'/name).read_bytes()
 proof['backup_sha256']=hashlib.sha256(backup.read_bytes()).hexdigest();save()
 live.checked_sh('fl del '+target);proof['phase']='old_deleted';save()
 sys.argv=['putfile.py',str(source),target]
 assert not importlib.import_module('putfile').main()
 proof['phase']='written';save()
 fetch(dest,source.stat().st_size)
 assert dest.read_bytes()==source.read_bytes()
 proof.update(phase='verified',bytes=dest.stat().st_size,sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),passed=True)
 save();print(json.dumps(proof,indent=2),flush=True)
