"""Describe F1: native full-height windows with existing true24 timing and 3K RAW."""
from pathlib import Path
import struct,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis/firmware'
def plan():
 b=(OUT/'MAIN_c0000000.bin').read_bytes()
 assert hashlib.sha256(b).hexdigest()=='aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
 entries=[]
 def add(a,new,reason):
  old=struct.unpack_from('<I',b,a-0xc0000000)[0]
  if old!=new:entries.append(dict(address=a,expected=old,replacement=new,reason=reason))
 for a,v in [(0xc0be3f54,3032),(0xc0be441c,2020),(0xc0be2c34,3000),(0xc0be30fc,2000),(0xc0be35c4,3032),(0xc0be3a8c,2020),(0xc0be1914,2048),(0xc0be1ddc,2048)]:add(a,v,'profile429 RAW geometry and reduction')
 # Geometry and receiver records use verified row strides. Keep mode151 ID
 # and nominal24fps; transplant only differences from stock full-height mode3.
 for base,stride,exclude,label in [(0xc0b59dc0,100,{0,0x40},'sensor geometry'),(0xc0b5c638,56,{0},'receiver')]:
  assert struct.unpack_from('<I',b,base+64*stride-0xc0000000)[0]==151
  assert struct.unpack_from('<I',b,base+3*stride-0xc0000000)[0]==3
  for off in range(4,stride,4):
   if off not in exclude:add(base+64*stride+off,struct.unpack_from('<I',b,base+3*stride+off-0xc0000000)[0],label+' from stock mode3')
 # Keep HMAX445, tail1145, VMAX6740 exactly. Enlarge input window only.
 base=0xc0b59500
 for off in (12,16):add(base+64*32+off,struct.unpack_from('<I',b,base+3*32+off-0xc0000000)[0],'full-height input window from stock mode3')
 assert len({e['address'] for e in entries})==len(entries)
 return entries
if __name__=='__main__':
 entries=plan();src=(ROOT/'tools/three_k_geometry.S').read_text().replace('0x3147334B','0x3146334B').replace('/* K3G1 */','/* K3F1 */').replace('mov r5, #6',f'mov r5, #{len(entries)}')
 start=src.index('patch_table:\n');end=src.index('checksum_word:',start)
 src=src[:start]+'patch_table:\n'+''.join(f"    .word 0x{e['address']:08X}, {e['expected']}, {e['replacement']}\n" for e in entries)+src[end:]
 (ROOT/'tools/three_k_fullheight.S').write_text(src)
 (OUT/'fullheight-f1-plan.json').write_text(json.dumps(entries,indent=2)+'\n')
 print(json.dumps(entries,indent=2))
