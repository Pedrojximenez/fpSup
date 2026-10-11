"""Read-only validation of the installed shell; no memory writes or recording."""
from pathlib import Path
import socket,re,json,struct,hashlib,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research/fpSup/fp_usb_shell'))
from armasm import assemble
from patches import PATCHES,SCREEN

def call(line):
 with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
  s.settimeout(5);s.connect('/tmp/fpware-fpshd.sock');s.sendall((line+'\n').encode());b=b''
  while not b.endswith(b'\n'):
   chunk=s.recv(65536)
   if not chunk:break
   b+=chunk
 r=b.decode().strip()
 if r.startswith('OKX '):return bytes.fromhex(r[4:]).decode('ascii')
 if r.startswith('OK '):return r[3:].replace('\\n','\n').replace('\\\\','\\')
 raise RuntimeError(r)

def read(addr,size):
 assert size%4==0 and 0<size<=128
 for attempt in range(3):
  try:
   out=call(f'SHL mem get 0x{addr:08X},,0x{size:X}')
   words={int(a,16):int(v,16) for a,v in re.findall(r'A:0x([0-9a-fA-F]+), D:0x([0-9a-fA-F]+)',out)}
   return b''.join(struct.pack('<I',words[a]) for a in range(addr,addr+size,4))
  except (RuntimeError,KeyError,TimeoutError):
   if attempt==2:raise

def main():
    code=assemble(ROOT/'research/fpSup/fp_usb_shell/camera/worker.S')
    live=b''.join(read(0xc072f050+i,min(128,len(code)-i)) for i in range(0,len(code),128))
    patches=[]
    for a,v,*_ in PATCHES+SCREEN:
     got=struct.unpack('<I',read(a,4))[0]
     patches.append({'address':hex(a),'expected':hex(v),'actual':hex(got),'match':got==v})
    state=struct.unpack('<20I',read(0xc072f000,80))
    hook=struct.unpack('<I',read(0xc00d0794,4))[0]
    pool=struct.unpack('<3I',read(0xc3757a7c,12))
    r={'code_exact_match':live==code,'loaded_sha256':hashlib.sha256(live).hexdigest(),'code_differences':[hex(0xc072f050+i) for i,(a,b) in enumerate(zip(live,code)) if a!=b],'patches':patches,'worker_state':[hex(v) for v in state],'bootstrap_hook_restored':hook==0xfa046fd7,'allocation':{'base':hex(pool[0]),'bytes':pool[1],'type':pool[2]}}
    dest=ROOT/'analysis/usb-shell-live-check.json';dest.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2))

if __name__ == '__main__':
    main()
