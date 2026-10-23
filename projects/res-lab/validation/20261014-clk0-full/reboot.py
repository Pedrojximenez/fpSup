"""One reboot; cleanly replace only the verified existing fpshd."""
import fcntl,json,socket,subprocess,sys,time
from common import *
pid=int(sys.argv[1]);proof={'old_daemon_pid':pid}
save=lambda:(HERE/'reboot.json').write_text(json.dumps(proof,indent=1)+'\n')
with open('/tmp/fp-af-fusion.lock') as lease:
 fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
 exe=str(live.SHELL/'fpshd')
 assert subprocess.check_output(['ps','-p',str(pid),'-o','command='],text=True).strip()==exe
 proof['idle']=B.idle();proof['reboot_sent']=True;save()
 try:proof['reply']=live.checked_sh('reboot')
 except RuntimeError as exc:proof['uncertain_reply']=str(exc)
 with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
  s.settimeout(5);s.connect('/tmp/fpshd.sock');s.sendall(b'QUIT\n');proof['quit']=s.recv(1024).decode().strip()
 save();time.sleep(25)
 with (HERE/'daemon.log').open('ab') as log:
  p=subprocess.Popen([exe],cwd=live.SHELL,stdout=log,stderr=log,start_new_session=True)
 proof['new_daemon_pid']=p.pid;save();time.sleep(3);assert p.poll() is None
 proof['postboot_screen']=live.screen();proof['postboot_idle']=B.idle();save()
 print(json.dumps(proof,indent=1))
