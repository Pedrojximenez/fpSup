"""Keys / screen / strict screenshots. usage: ui.py KEY[:n] ... shot:tag where"""
import fcntl,importlib,re,sys,time
from common import *
pf=live.putfile
def shots():
 out=live.checked_sh('dir \\DCIM\\100SIGMA',timeout_ms=30000)
 got={int(m[2]):int(m[1]) for m in re.finditer(r'(\d+)\s+SS__(\d{4})\.JPG',out)}
 assert got,'empty listing: '+out[-200:];return got
def shot(tag):
 before=shots();live.checked_sh('key CAPTUREON');time.sleep(.3);live.checked_sh('key CAPTUREOFF')
 for _ in range(10):
  time.sleep(2);now=shots();new=set(now)-set(before)
  if new:break
 else:raise SystemExit('no new screenshot')
 n=max(new);time.sleep(.6);size=shots()[n];d=HERE/'shots';d.mkdir(exist_ok=True)
 local=d/f'{time.strftime("%H%M%S")}-{tag}-SS{n:04d}.jpg'
 getter=importlib.import_module('getfile');getter.read_direct=lambda a,k:pf.read_bulk(a,k,'tagged')
 sys.argv=['getfile.py',f'\\DCIM\\100SIGMA\\SS__{n:04d}.JPG',str(local),'--size',str(size)]
 assert getter.main()==0 and local.stat().st_size==size;print('SHOT',local,flush=True)
def key(k):
 assert 'is_recording -> 0' in live.checked_sh('status get is_recording')
 live.checked_sh('key '+k+'ON');time.sleep(.12);live.checked_sh('key '+k+'OFF');time.sleep(.9)
with open('/tmp/fp-af-fusion.lock') as lease:
 fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
 for a in sys.argv[1:]:
  if a.startswith('shot:'):shot(a[5:])
  elif a=='where':live.screen()
  elif a.startswith('wait'):time.sleep(float(a[4:]))
  else:
   k,_,n=a.partition(':')
   assert k in ('UP','DOWN','LEFT','RIGHT','OK','MENU','S1')
   for _ in range(int(n or 1)):key(k)
   print(a,flush=True)
