"""Bounded read-only RAW pipeline snapshot through the verified USB shell."""
from pathlib import Path
import struct,json
from check_usb_shell import read,ROOT

def block(addr,n):
 return b''.join(read(addr+i,min(128,n-i)) for i in range(0,n,128))
def valid(addr,n):
 return addr%4==0 and (0x40000000<=addr<=0x50000000-n or 0xc0000000<=addr<=0xc4000000-n)
def words(b):return list(struct.unpack('<'+str(len(b)//4)+'I',b))
sensor=words(block(0xc343b588,0x100))
manager=words(block(0xc375d840,0x20))
settings=words(block(0xc31f865c,0x80))
r={'sensor_mode':sensor[1],'sensor_words':sensor,'manager_words':manager,'settings_words':settings,'limitations':'Sequential USB reads are not atomic; computer-connected standby is not SSD recording.'}
src=manager[2]
if valid(src,0x168):
 h=words(block(src,0x60));r['source_header']=h
 if h[1]==src+0x5c:
  p=words(block(h[1],0x10c));r['profile_id']=h[0];r['parameters']=p
  stock=json.loads((ROOT/'analysis/firmware/raw-profiles.json').read_text())
  matches=[row for row in stock['rows'] if h[0] in row['profile_ids']]
  if matches:r['stock_differences']=[{'offset':hex(i*4),'stock':a,'live':b} for i,(a,b) in enumerate(zip(matches[0]['words']+[6064,4042],p)) if a!=b]
route=manager[4]
if valid(route,16):r['selected_route_words']=words(block(route,16))
r['manager_after']=words(block(0xc375d840,0x20))
r['sensor_mode_after']=words(read(0xc343b58c,4))[0]
(ROOT/'analysis/usb-raw-standby.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({k:v for k,v in r.items() if k not in ('sensor_words','manager_words','settings_words','source_header','parameters','manager_after')},indent=2))
