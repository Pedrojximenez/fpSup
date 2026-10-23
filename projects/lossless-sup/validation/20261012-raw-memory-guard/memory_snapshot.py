import sys,fcntl,json
from pathlib import Path
r=Path('/Users/dido/Developer.localized/SIGMAfp_re'); d=r/'projects/lossless-sup/validation/20261012-raw-memory-guard'
sys.path.insert(0,str(r/'fpSup/fp_usb_shell'));import putfile as p
out=d/sys.argv[1]; assert not out.exists();a={}
with open('/tmp/fp-af-fusion.lock','a') as f:
 fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
 def sh(s):
  v=p.sh(s,retries=0,timeout_ms=5000);a[s]=v;out.write_text(json.dumps(a,indent=2)+'\n');assert v.strip() and not v.startswith('ERR'),v;return v.strip()
 assert sh('status get is_recording')=='is_recording -> 0'
 assert p.mem_get(0xc358e140)==[0] and p.mem_get(0xc35a952c)[0]&255==0
 sh('memmgr bufuse');sh('memmgr heapmem')
 assert sh('status get is_recording')=='is_recording -> 0'
 print(json.dumps(a,indent=2))
