"""Restart the verified owned daemon after the user confirms a physical boot."""
import fcntl,json,pathlib,runpy,socket,subprocess,sys,time
import live_camera as live
here=pathlib.Path(__file__).resolve().parent
owned=70672
with open('/tmp/fp-af-fusion.lock','r') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 cmd=subprocess.check_output(['ps','-p',str(owned),'-o','command='],text=True).strip()
 assert cmd==str(live.SHELL/'fpshd'),cmd
 with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
  sock.settimeout(5);sock.connect('/tmp/fpshd.sock');sock.sendall(b'QUIT\n')
  reply=sock.recv(1024).decode().strip();assert reply=='OK bye',reply
  print('Owned daemon shutdown:',reply,flush=True)
 time.sleep(.5)
 proc=subprocess.Popen([str(live.SHELL/'fpshd')],cwd=live.SHELL,
  stdout=(here/'daemon-after-reboot.log').open('ab'),stderr=subprocess.STDOUT,start_new_session=True)
 print('Replacement owned daemon:',proc.pid,flush=True)
 time.sleep(1);assert proc.poll() is None
 sys.argv=['recover_connection.py','--release-only','physical-after-audit']
 try:runpy.run_path(str(here/'recover_connection.py'),run_name='__main__')
 except SystemExit as exc:assert exc.code==0
 time.sleep(.1)
 print('Fresh worker:',live.checked_sh('status get is_recording'),flush=True)
 (here/'daemon-after-audit-recovery.json').write_text(json.dumps({'old_pid':owned,'pid':proc.pid,'physical_boot_confirmed_by_user':True},indent=2)+'\n')
