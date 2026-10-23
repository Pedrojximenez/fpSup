"""Temporary colour control inside exact-verified owned LV records; no card write."""
import argparse,fcntl,hashlib,json,struct,sys
from pathlib import Path
import experiment as E
sys.path.insert(0,str(E.ROOT/'projects/open-gate/build/res-custom'))
import vr_ui as V
p=argparse.ArgumentParser();p.add_argument('--variant',choices=('combined-fix8','combined-fix9','combined-fix11','combined-fix12'),required=True);p.add_argument('--restore-black',action='store_true');p.add_argument('--out',type=Path,required=True);a=p.parse_args();assert not a.out.exists()
nr_want,black_count,mask_want,colour_offset,table_limit={
 'combined-fix8':(15,12,0x4000203D,45,0x14000),
 'combined-fix9':(15,12,0x4000203F,49,0x14000),
 'combined-fix11':(27,24,0x4000203F,49,0x16000),
 'combined-fix12':(51,48,0x4000203F,49,0x20000),
}[a.variant]
old_colour,new_colour=(0xE03858FF,0xFF) if a.restore_black else (0xFF,0xE03858FF)
with open('/tmp/fp-af-fusion.lock','r') as f:
 fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);E.daemon();E.B.idle();state,identity=E.core_state(a.variant)
 tab=E.pf.mem_get(state+0x774,tries=1)[0];head=E.pf.mem_get(tab,2,tries=1);assert head[0]==16 and head[1]<=table_limit
 image=(E.ROOT/'out/MAIN_c0000000.bin').read_bytes();want=bytearray(V.lv_record_blob(image));assert len(want)==head[1]
 ids=E.pf.mem_get(state+0xa80,29,tries=1);assert len(ids)==29 and None not in ids
 cur=8;changes=[]
 for i in range(16):
  site,old,hash0,n,nr,nm=struct.unpack_from('<6I',want,cur);data=cur+24;mk=data+((n+3)&~3)
  for k in range(nm):
   off,label=struct.unpack_from('<2I',want,mk+8*k);struct.pack_into('>I',want,data+off,ids[label])
  if nr==nr_want:
   pos=data
   for k in range(nr_want):
    tag,size=struct.unpack_from('>2I',want,pos);assert tag==0x10005
    mask=struct.unpack_from('>I',want,pos+8+20)[0]
    assert mask==mask_want
    colour_at=pos+8+colour_offset
    if k<black_count:
     assert struct.unpack_from('>I',want,colour_at)[0]==0xFF
     struct.pack_into('>I',want,colour_at,old_colour);changes.append(colour_at)
    else:assert struct.unpack_from('>I',want,colour_at)[0]==0xFFFFFFFF
    pos+=size
   assert pos==data+n
  cur=mk+8*nm
 assert cur==len(want) and len(changes)==4*black_count
 assert E.pf.read_bulk(tab,len(want),'owned LV records')==bytes(want),'refuse unknown record contents'
 new=bytearray(want)
 for off in changes:struct.pack_into('>I',new,off,new_colour)
 addresses=sorted({(tab+i)&~3 for i,(x,y) in enumerate(zip(want,new)) if x!=y})
 for address in addresses:
  value=E.pf.mem_get(address,tries=1)[0];raw=bytearray(struct.pack('<I',value));off=address-tab
  for j in range(4):
   if 0<=off+j<len(new):assert raw[j]==want[off+j];raw[j]=new[off+j]
  value=struct.unpack('<I',raw)[0];E.pf.mem_set(address,value);assert E.pf.mem_get(address,tries=1)==[value]
 assert E.pf.read_bulk(tab,len(new),'verified colour control')==bytes(new)
 result={'variant':a.variant,'identity':identity,'card_modified':False,'old_colour':hex(old_colour),'new_colour':hex(new_colour),'glyph_copies_changed':len(changes),'whole_table_verified':True,'sha256':hashlib.sha256(new).hexdigest(),'idle':E.B.idle()}
 a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
