"""User-authorized reboot while movie_recording is stuck at 1 (writer/XMP idle)."""
import json,socket,subprocess,time,fcntl
from common import *
pf=live.putfile;proof={}
with open('/tmp/fp-af-fusion.lock') as lease:
 fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
 exe=str(live.SHELL/'fpshd')
 proof['xmp']=pf.mem_get(0xC358E140,tries=1)[0];proof['writing']=pf.mem_get(0xC35A952C,tries=1)[0]&255
 assert proof['xmp']==0 and proof['writing']==0,proof
 try:proof['reply']=live.checked_sh('reboot')
 except RuntimeError as e:proof['uncertain']=str(e)
 with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
  s.settimeout(5);s.connect('/tmp/fpshd.sock');s.sendall(b'QUIT\n');proof['quit']=s.recv(1024).decode().strip()
 time.sleep(25)
 with (HERE/'daemon.log').open('ab') as log:
  p=subprocess.Popen([exe],cwd=live.SHELL,stdout=log,stderr=log,start_new_session=True)
 time.sleep(3);assert p.poll() is None;proof['daemon']=p.pid
 proof['screen']=live.screen();proof['idle']=B.idle()
 (HERE/'reboot-stuck.json').write_text(json.dumps(proof,indent=1));print(json.dumps(proof,indent=1))
