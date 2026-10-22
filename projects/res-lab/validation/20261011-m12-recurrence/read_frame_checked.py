"""Re-read one known trial DNG using the maintained address-tagged RAM reader.

Require a fresh, inspected HDMI STBY capture first. No recording keys or clip
listing. Uses getfile's existing allocator/file read/free and the maintained
read_bulk path rather than anonymous 1 MiB read_direct replies.
"""
import fcntl,hashlib,importlib,json,pathlib,sys,time
import numpy as np
from PIL import Image
HERE=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'20261009-oncamera'))
import live_camera as live
live.LOG=HERE/'commands-checked-read.jsonl'

def main():
    label,number,proof_name=sys.argv[1],int(sys.argv[2]),sys.argv[3]
    dest=HERE/label
    trial=json.loads((dest/'trial.json').read_text())
    frames=json.loads((dest/'raw-frames.json').read_text())
    assert len(trial['new_clips'])==1 and number in [f['number'] for f in frames['frames']]
    proof=HERE/proof_name
    assert proof.is_file() and 0<=time.time()-proof.stat().st_mtime<=30,'need fresh STBY capture'
    a=np.asarray(Image.open(proof).convert('RGB'))
    assert a.shape==(576,1024,3)
    roi=a[:40,440:650].astype(np.int16)
    red=(roi[:,:,0]>110)&(roi[:,:,1]<85)&(roi[:,:,2]<85)
    green=(roi[:,:,1]>110)&(roi[:,:,0]<85)&(roi[:,:,2]<85)
    assert red.sum()<=10 and green.sum()>10,'not positively in STBY'
    clip=trial['new_clips'][0];date=trial['clips_after'][clip]
    local=dest/f'{clip}-{number:06d}-checked-read.DNG'
    report=local.with_suffix('.json');assert not local.exists() and not report.exists()
    with open('/tmp/fp-af-fusion.lock','r') as lease:
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert 'is_recording -> 0' in live.checked_sh('status get is_recording')
        assert live.screen()=='LV_CINE_MEDIUM'
        assert 'slot = sd0' in live.checked_sh('sdcard slot')
        getter=importlib.import_module('getfile')
        getter.read_direct=lambda addr,size:live.putfile.read_bulk(addr,size,'tagged')
        remote=chr(92).join(('', 'CINEMA', clip, f'{clip}_{date}_{number:06d}.DNG'))
        sys.argv=['getfile.py',remote,str(local),'--size',str(frames['bytes'])]
        assert getter.main()==0
        data=local.read_bytes();original=(dest/f'{clip}-{number:06d}.DNG').read_bytes()
        assert len(data)==len(original)==frames['bytes']
        result={'transport':'maintained read_bulk with source-address suffix per chunk',
                'size':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                'equals_original_direct_read':data==original,'standby_proof':str(proof),
                'proof_sha256':hashlib.sha256(proof.read_bytes()).hexdigest()}
        report.write_text(json.dumps(result,indent=2)+chr(10));print(json.dumps(result,indent=2))

if __name__=='__main__':main()
