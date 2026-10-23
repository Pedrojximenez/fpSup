"""Restore the confirmed-absent LOSS file; never repeat an uncertain delete."""
import sys,fcntl,json,subprocess,hashlib,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'fpSup/fp_usb_shell'));import putfile as pf
out=HERE/'fixed-file-restoration.json';assert not out.exists()
r={'time':time.time(),'commands':[],'delete_replayed':False,'reboot_sent':False}
def save():out.write_text(json.dumps(r,indent=2))
def sh(c):
 v=pf.sh(c,retries=0,timeout_ms=5000);r['commands'].append([c,v]);save();assert v.strip() and not v.startswith('ERR');return v.strip()
def run(script,args,label):
 s=subprocess.run([sys.executable,'-B',str(script),*args],capture_output=True,text=True)
 (HERE/(label+'.log')).write_text(s.stdout+s.stderr);r[label+'_rc']=s.returncode;save();assert s.returncode==0,'uncertain transfer, no reboot'
f=open('/tmp/fp-af-fusion.lock','a');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
try:
 assert sh('status get is_recording')=='is_recording -> 0'
 assert pf.mem_get(0xc358e140)[0]==0 and pf.mem_get(0xc35a952c)[0]&255==0
 listing=sh('dir '+chr(92)+'fpSup');assert not any(l.split()[-1]=='10LOSS.BIN' for l in listing.splitlines() if l.split())
 candidate=HERE/'fixed-profile/10LOSS.BIN';data=candidate.read_bytes();meta=json.loads(candidate.with_name('build.json').read_text())
 assert hashlib.sha256(data).hexdigest()==meta['sha256']
 run(ROOT/'fpSup/fp_usb_shell/putfile.py',[str(candidate),r'\fpSup\10LOSS.BIN'],'fixed-restore-write')
 back=HERE/'fixed-restored-readback.BIN';run(HERE/'read_file_once.py',[r'\fpSup\10LOSS.BIN',str(back),'--size',str(len(data))],'fixed-restore-readback')
 assert back.read_bytes()==data
 rows=[l.split() for l in sh('dir '+chr(92)+'fpSup').splitlines()];assert [int(x[-2]) for x in rows if x and x[-1]=='10LOSS.BIN']==[len(data)]
 r.update(readback_verified=True,sha256=meta['sha256'],file_bytes=len(data),boot=pf.mem_get(0xc072f6f8)[0]);save();print({k:v for k,v in r.items() if k!='commands'})
except BaseException as e:r['error']=repr(e);save();raise
