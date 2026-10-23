"""One authorized reboot; cleanly replace only the verified existing fpshd."""
import fcntl,json,pathlib,socket,subprocess,sys,time
import camera as C
HERE=C.HERE

def main():
 name=sys.argv[1];pid=int(sys.argv[2]);dest=HERE/(name+'.json');assert not dest.exists()
 proof={'reboot_sent':False,'replayed':False,'old_daemon_pid':pid}
 save=lambda:dest.write_text(json.dumps(proof,indent=2)+'\n')
 with open('/tmp/fp-af-fusion.lock') as lease:
  fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
  exe=str(C.live.SHELL/'fpshd')
  assert subprocess.check_output(['ps','-p',str(pid),'-o','command='],text=True).strip()==exe
  proof['idle']=C.idle()
  proof['reboot_sent']=True;save()
  try:proof['reply']=C.live.checked_sh('reboot')
  except RuntimeError as exc:proof['uncertain_reply']=str(exc)
  save()
  with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
   sock.settimeout(5);sock.connect('/tmp/fpshd.sock');sock.sendall(b'QUIT\n');reply=sock.recv(1024).decode().strip();assert reply=='OK bye',reply
   proof['owned_daemon_closed']=reply
  save();time.sleep(25)
  with (HERE/'daemon.log').open('ab') as log:
   proc=subprocess.Popen([exe],cwd=C.live.SHELL,stdout=log,stderr=log,start_new_session=True)
  proof['new_daemon_pid']=proc.pid;(HERE/'daemon-pid.txt').write_text(str(proc.pid)+'\n');save()
  time.sleep(2);assert proc.poll() is None
  proof['postboot_native_rec']=C.recording();assert proof['postboot_native_rec']==0
  proof['postboot_screen']=C.live.screen();proof['postboot_idle']=C.idle();save()
  print(json.dumps(proof,indent=2),flush=True)
if __name__=='__main__':main()
