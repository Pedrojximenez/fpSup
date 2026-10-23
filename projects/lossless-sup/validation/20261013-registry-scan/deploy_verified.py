"""One-file deployment, with outcome verification after a lost acknowledgement.

The only continuation is a NEW write after a proven completed delete stopped
putfile before its write helper. An uncertain file write is never repeated.
"""
import argparse,fcntl,hashlib,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'fpSup/fp_usb_shell'));import putfile as pf
ap=argparse.ArgumentParser();ap.add_argument('--candidate',type=Path,required=True);ap.add_argument('--label',required=True);a=ap.parse_args()
assert a.label.replace('-','').isalnum();candidate=a.candidate.resolve();data=candidate.read_bytes()
meta=json.loads(candidate.with_name('build.json').read_text());assert hashlib.sha256(data).hexdigest()==meta['sha256']
r=subprocess.run([sys.executable,str(HERE/'deploy_candidate.py'),'--candidate',str(candidate),'--label',a.label])
d=HERE/a.label;report_path=d/'verified.json';assert not report_path.exists()
if r.returncode==0:
 report=json.loads((d/'deployment.json').read_text());assert report['readback_verified'];report_path.write_text(json.dumps(report,indent=2));print('Verified deployment:',report_path);raise SystemExit(0)
report={'initial_returncode':r.returncode,'commands':[],'uncertain_write_replayed':False,'reboot_sent':False}
def save():report_path.write_text(json.dumps(report,indent=2))
def sh(c):
 v=pf.sh(c,retries=0,timeout_ms=5000);report['commands'].append([c,v]);save()
 assert v.strip() and not v.startswith('ERR'),v
 return v.strip()
def sizes():
 rows=[l.split() for l in sh('dir '+chr(92)+'fpSup').splitlines()]
 return {x[-1]:int(x[-2]) for x in rows if len(x)>=4 and x[-2].isdigit()}
def run(script,args,name):
 t=subprocess.run([sys.executable,'-B',str(script),*args],capture_output=True,text=True)
 (d/(name+'.log')).write_text(t.stdout+t.stderr);report[name+'_rc']=t.returncode;save();return t.returncode
f=open('/tmp/fp-af-fusion.lock','a');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
try:
 assert sh('status get is_recording')=='is_recording -> 0'
 assert pf.mem_get(0xc358e140)[0]==0 and pf.mem_get(0xc35a952c)[0]&255==0
 assert pf.mem_get(0xc0bac2f8)[0]==0xc03d99a0
 listing=sizes();write_log=(d/'write.log').read_text()
 if '10LOSS.BIN' not in listing:
  assert 'replace_if_shorter' in write_log and 'fl del' in write_log and 'unexpected reply' in write_log
  report['continued_after_confirmed_delete']=True;save()
  rc=run(ROOT/'fpSup/fp_usb_shell/putfile.py',[str(candidate),r'\fpSup\10LOSS.BIN'],'new-write-after-delete')
  if rc:
   # Fresh command proves the helper returned; exact native flags prove it closed.
   assert sh('status get is_recording')=='is_recording -> 0'
   assert pf.mem_get(0xc0bac2f8)[0]==0xc03d99a0
   report['native_write_result']=pf.mem_get(pf.P,6)
   assert report['native_write_result'][2:5]==[2,1,1]
  listing=sizes()
 assert listing['10LOSS.BIN']==len(data)
 back=d/'verified-readback.BIN';assert run(HERE/'read_file_once.py',[r'\fpSup\10LOSS.BIN',str(back),'--size',str(len(data))],'verified-readback')==0
 assert back.read_bytes()==data
 assert sh('status get is_recording')=='is_recording -> 0'
 report.update(readback_verified=True,sha256=meta['sha256'],file_bytes=len(data),boot=pf.mem_get(0xc072f6f8)[0],completed_at=time.time());save()
 print('Verified recovered deployment:',report_path)
except BaseException as e:report['error']=repr(e);save();raise
