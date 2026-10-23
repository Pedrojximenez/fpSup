import socket,subprocess,time,sys
from common import *
exe=str(live.SHELL/'fpshd')
for pid in subprocess.check_output(['pgrep','-f',exe],text=True).split():
  assert subprocess.check_output(['ps','-p',pid,'-o','command='],text=True).strip()==exe
with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
  s.settimeout(5);s.connect('/tmp/fpshd.sock');s.sendall(b'QUIT\n');print(s.recv(1024).decode().strip())
time.sleep(2)
with (HERE/'daemon.log').open('ab') as log:
  p=subprocess.Popen([exe],cwd=live.SHELL,stdout=log,stderr=log,start_new_session=True)
time.sleep(3);assert p.poll() is None;print('daemon',p.pid);print(live.screen(),B.idle())
