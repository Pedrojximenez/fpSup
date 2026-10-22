"""Index stock NBU big-endian records; diagnostic reader, never modifies firmware."""
from pathlib import Path
import struct, hashlib, json, argparse
ROOT=Path(__file__).resolve().parents[1]
BASE=0xc0000000;NBU=0x18c0460;POOL=NBU+20;START=0x18eb48c;END=0x2d8cef8

def load():
 b=(ROOT/'analysis/firmware/MAIN_c0000000.bin').read_bytes()
 assert hashlib.sha256(b).hexdigest()=='aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
 assert b[NBU:NBU+4]==b'NBU\0'
 # Header's length includes the 8 bytes preceding the string-pool contents.
 assert NBU+12+struct.unpack_from('>I',b,NBU+16)[0]==START
 strings={};p=POOL
 while p<START:
  end=b.index(0,p,START)
  if end>p:
   try:strings[p-POOL]=b[p:end].decode('utf-8')
   except UnicodeDecodeError:pass
  p=(end+4)&~3
 records=[];p=START
 while p<END:
  tag,size=struct.unpack_from('>II',b,p)
  assert size>=8 and p+size<=END,(hex(p),size)
  records.append((p,size,tag));p+=size
 assert p==END
 return b,strings,records

def describe(b,strings,p,n,t):
 refs=[]
 # Unaligned fields occur in serialized expressions; references are candidates.
 for k in range(8,n-3):
  value=struct.unpack_from('>I',b,p+k)[0]
  if value in strings and len(strings[value])>2:refs.append({'offset':k,'string':strings[value]})
 return dict(address=hex(BASE+p),size=n,tag=hex(t),string_candidates=refs)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('address',type=lambda x:int(x,0));ap.add_argument('--radius',type=lambda x:int(x,0),default=0x200);a=ap.parse_args()
 b,s,records=load()
 for p,n,t in records:
  if p+n>=a.address-BASE-a.radius and p<=a.address-BASE+a.radius:print(json.dumps(describe(b,s,p,n,t),ensure_ascii=False))
