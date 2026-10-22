"""Recover only the confirmed SIGMA USB claimant and owned test daemon."""
import json,os,pathlib,plistlib,re,socket,subprocess,time,sys
import live_camera as live
HERE=pathlib.Path(__file__).resolve().parent
raw=subprocess.check_output(['ioreg','-a','-l','-p','IOService'])
tag=sys.argv[2] if len(sys.argv)>2 else 'transfer-loss'
(HERE/('usb-service-'+tag+'.plist')).write_bytes(raw)
owners=[]
def scan(n,camera=False):
 if isinstance(n,dict):
  camera=camera or (n.get('USB Product Name')=='SIGMA fp' and n.get('IOObjectClass')=='IOUSBHostDevice')
  if camera and n.get('bInterfaceNumber')==0 and n.get('UsbExclusiveOwner'):owners.append(n['UsbExclusiveOwner'])
  for c in n.get('IORegistryEntryChildren',[]):scan(c,camera)
 elif isinstance(n,list):
  for c in n:scan(c,camera)
scan(plistlib.loads(raw))
print('SIGMA interface owners:',owners,flush=True)
for owner in owners:
 m=re.fullmatch(r'pid (\d+), ptpcamerad',owner)
 if not m:raise RuntimeError('Unexpected interface owner; no process stopped: '+owner)
 pid=int(m.group(1));cmd=subprocess.check_output(['ps','-p',str(pid),'-o','comm='],text=True).strip()
 assert cmd=='/usr/libexec/ptpcamerad',cmd
 os.kill(pid,15);time.sleep(1)
 if subprocess.run(['ps','-p',str(pid),'-o','comm='],capture_output=True,text=True).stdout.strip()==cmd:os.kill(pid,9)
 print('Released exact SIGMA claimant',pid,flush=True)
if len(sys.argv)>1 and sys.argv[1]=='--release-only':raise SystemExit(0)
owned=66928
cmd=subprocess.check_output(['ps','-p',str(owned),'-o','command='],text=True).strip()
assert cmd==str(live.SHELL/'fpshd'),cmd
with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
 s.settimeout(5);s.connect('/tmp/fpshd.sock');s.sendall(b'QUIT\n');print(s.recv(1024).decode(),flush=True)
time.sleep(.5)
p=subprocess.Popen([str(live.SHELL/'fpshd')],cwd=live.SHELL,stdout=(HERE/'daemon-after-reboot.log').open('ab'),stderr=subprocess.STDOUT,start_new_session=True)
print('Owned replacement daemon',p.pid,flush=True)
(HERE/'daemon-after-transfer-loss.json').write_text(json.dumps({'pid':p.pid,'usb_owners':owners},indent=2)+'\n')
time.sleep(2)
assert p.poll() is None
