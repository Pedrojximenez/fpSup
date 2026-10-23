import sys,fcntl,json,time,argparse
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'fpSup/fp_usb_shell'));import putfile as pf
ap=argparse.ArgumentParser();ap.add_argument('label');ap.add_argument('--verification',type=Path,required=True);ap.add_argument('--candidate',type=Path,required=True);a=ap.parse_args();
import hashlib
verification=json.loads(a.verification.read_text());assert verification['readback_verified']
assert verification['sha256']==hashlib.sha256(a.candidate.read_bytes()).hexdigest();assert a.label.replace('-','').isalnum()
out=HERE/(a.label+'-reboot.json');assert not out.exists()
f=open('/tmp/fp-af-fusion.lock','a');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert pf.sh('status get is_recording',retries=0,timeout_ms=5000).strip()=='is_recording -> 0'
assert pf.mem_get(0xc358e140)[0]==0 and pf.mem_get(0xc35a952c)[0]&255==0
r={'boot_before':pf.mem_get(0xc072f6f8)[0],'sent_at':time.time()};out.write_text(json.dumps(r,indent=2))
r['reply']=pf.sh('reboot',retries=0,timeout_ms=5000);out.write_text(json.dumps(r,indent=2));print(r,flush=True)
time.sleep(12)
