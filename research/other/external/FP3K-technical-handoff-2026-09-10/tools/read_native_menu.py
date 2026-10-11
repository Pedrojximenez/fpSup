"""Decode fixed-address menu-v1 snapshots without dereferencing camera pointers."""
from pathlib import Path
import argparse,json,struct

def analyze(folder):
 result=[]
 for i in range(3):
  parts={}
  for name,size in [('SCREEN',56),('ACTIVE',4),('ENUM',8)]:
   p=folder/f'{name}{i}.BIN'
   if not p.exists():parts[name]=None;continue
   b=p.read_bytes()
   if len(b)!=size:raise ValueError(f'{p}: expected {size} bytes, found {len(b)}')
   parts[name]=struct.unpack('<'+'I'*(size//4),b)
  row={'sample':i,'complete':all(v is not None for v in parts.values())}
  if parts['SCREEN']:
   w=parts['SCREEN'];row.update(screen_vtable=hex(w[0]),settings_receiver=hex(w[9]),enum_provider=hex(w[13]),screen_words=[hex(v) for v in w],expected_screen_vtable=w[0]==0xc0d19654)
  if parts['ACTIVE']:row['active_screen']=hex(parts['ACTIVE'][0]);row['expected_active_screen']=parts['ACTIVE'][0]==0xc3785308
  if parts['ENUM']:row['enum_words']=[hex(v) for v in parts['ENUM']];row['expected_enum_provider']=parts['ENUM']==(0x44,0xc2dead7c)
  result.append(row)
 return {'samples':result,'limitation':'Saved memory snapshots, not proof the resolution choice was visible or a mode change occurred. Settings receiver is an address only; no receiver memory was captured.'}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('folder',type=Path);p.add_argument('--output',type=Path);a=p.parse_args();report=analyze(a.folder);s=json.dumps(report,indent=2)+'\n'
 if a.output:a.output.write_text(s)
 print(s)
