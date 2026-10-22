"""Install only the two reviewed Sup payloads and verify full readback."""
import fcntl,hashlib,importlib,json,pathlib,sys
import live_camera as live
HERE=pathlib.Path(__file__).resolve().parent
CARD=live.ROOT/'projects/res-lab/cards/20261009-virtual-rcd-v5/debug'
READ=HERE/'v5-readback';READ.mkdir(exist_ok=True)
with open('/tmp/fp-af-fusion.lock','r') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert 'is_recording -> 0' in live.checked_sh('status get is_recording')
 verified=[]
 for name in ('50RESLAB.BIN',):
  source=CARD/'fpSup'/name;target='\\fpSup\\'+name;dest=READ/name
  live.checked_sh('fl del '+target)
  sys.argv=['putfile.py',str(source),target]
  assert not importlib.import_module('putfile').main()
  sys.argv=['getfile.py',target,str(dest),'--size',str(source.stat().st_size)]
  assert not importlib.import_module('getfile').main()
  assert source.read_bytes()==dest.read_bytes()
  verified.append({'remote':target,'bytes':dest.stat().st_size,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()})
  print('Verified',target,dest.stat().st_size,flush=True)
 (HERE/'v5-installed-verification.json').write_text(json.dumps(verified,indent=2)+'\n')
