"""Update only the reviewed consumer and producer; keep the consumer's config."""
import fcntl, hashlib, importlib, json, pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'projects/res-lab/validation/20261009-oncamera'))
import live_camera as live
HERE=pathlib.Path(__file__).resolve().parent
CARD=ROOT/'projects/res-lab/cards/20261009-virtual-rcd-v9/debug'
sources=[('32RESCUS.BIN',HERE/'v9-32RESCUS-install.BIN')]
proof={'verified':[]}
with open('/tmp/fp-af-fusion.lock','r') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert 'is_recording -> 0' in live.checked_sh('status get is_recording')
    for name,source in sources:
        target='\\fpSup\\'+name
        dest=HERE/('v9-installed-'+name)
        assert not dest.exists()
        live.checked_sh('fl del '+target)
        sys.argv=['putfile.py',str(source),target]
        assert not importlib.import_module('putfile').main()
        sys.argv=['getfile.py',target,str(dest),'--size',str(source.stat().st_size)]
        assert not importlib.import_module('getfile').main()
        assert dest.read_bytes()==source.read_bytes()
        proof['verified'].append({'file':name,'bytes':dest.stat().st_size,
                                  'sha256':hashlib.sha256(dest.read_bytes()).hexdigest()})
        (HERE/'v9-deployment.json').write_text(json.dumps(proof,indent=2)+'\n')
        print('Verified',name,dest.stat().st_size,flush=True)
    proof['passed']=True
    (HERE/'v9-deployment.json').write_text(json.dumps(proof,indent=2)+'\n')
