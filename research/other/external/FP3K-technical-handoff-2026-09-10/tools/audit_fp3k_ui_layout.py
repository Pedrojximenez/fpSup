"""Trace resolution animation groups and produce a bounded UI repair plan.

No media or firmware writes. All coordinates use the stock firmware image.
The plan covers HUD Resolution and QS 20_MV_Resolution / 21_MV_Resolution groups, including every
companion clip. It deliberately excludes playback and unrelated menu screens.
"""
import json,struct,hashlib
from pathlib import Path
from inspect_uic_resources import load
from experimental_ui_record_compaction import animation,encode_animation
ROOT=Path(__file__).resolve().parents[1]
U=lambda d,o:int.from_bytes(d[o:o+4],'big')
def build():
 b,s,rs=load();clips={};groups=[];objects={};screen=0
 for p,n,t in rs:
  if t==0x10002:screen=p
  d=b[p:p+n]
  if t==0x10003:objects[(screen,U(d,20))]=(U(d,24),s.get(U(d,28)))
  if t==0x1000a:clips[(screen,U(d,20),U(d,24))]=(p,d)
  if t==0x1000b:groups.append((screen,p,d))
 changes={};group_rows=[]
 def add(p,old,new,**extra):
  row=dict(address=hex(p+0xc0000000),size=len(old),old=old.hex(),new=bytes(new).hex(),**extra)
  if p in changes:assert changes[p]==row
  changes[p]=row
 for screen,p,d in groups:
  name=s.get(U(d,20));ns,nt,nc=[U(d,o) for o in (8,12,16)]
  if name not in ('Resolution','20_MV_Resolution','21_MV_Resolution') or ns!=1 or nt!=0:continue
  assert 28+21+8*nc+8==len(d)
  refs=[(screen,U(d,49+8*i),U(d,53+8*i)) for i in range(nc)]
  assert all(k in clips for k in refs)
  props=[(k,*clips[k],animation(clips[k][1])) for k in refs]
  aliases={};valid=False
  for k,cp,cd,pp in props:
   assert pp is not None
   for j,(typ,c,prop,dim,keys) in enumerate(pp):
    names=tuple(s.get(U(key,6)) for key in keys)
    if typ==2 and s.get(prop)=='image':
     alias={('L_resolution_1','L_resolution_2','L_resolution_dci4K'):'FP3K_L',('M_resolution_1','M_resolution_2','M_resolution_dci4K'):'FP3K_M',('qs_resolution_1_S','qs_resolution_2_S'):'FP3K_QS',('font_menu_MB_resolution_1','font_menu_MB_resolution_2'):'FP3K_FONT'}.get(names)
     if alias:aliases[(cp,j)]=alias;valid=True
  if not valid:continue
  newtime=99 if name=='Resolution' else 66
  assert U(d,32)==0 and U(d,36)==newtime-33
  gd=bytearray(d);struct.pack_into('>I',gd,36,newtime)
  add(p,d,gd,kind='state-end',time=newtime)
  members=[]
  for k,cp,cd,pp in props:
   for j,prop in enumerate(pp):
    keys=prop[4];assert len(keys)<255;assert U(keys[0],2)==0 and max(U(key,2) for key in keys)<newtime
    key=bytearray(keys[0]);struct.pack_into('>I',key,2,newtime)
    if (cp,j) in aliases:
     alias=aliases[(cp,j)];v={'FP3K_L':0xfffffff0,'FP3K_M':0xfffffff1,'FP3K_QS':0xfffffff2,'FP3K_FONT':0xfffffff4}[alias];struct.pack_into('>I',key,6,v)
    keys.append(bytes(key))
   new=encode_animation(cd,pp)
   assert len(new)<=512
   add(cp,cd,new,kind='layout-keys',time=newtime,aliases={str(j):a for (a_cp,j),a in aliases.items() if a_cp==cp})
   members.append(hex(cp+0xc0000000))
  group_rows.append(dict(address=hex(p+0xc0000000),name=name,old_end=newtime-33,new_end=newtime,clips=members))
 # Footer uses shared option slots, independent of the large QS tile.
 # Add the third image/visibility key only at the resolution mode's time700.
 for screen in [0x2278c02,0x24d1dc8]:
  candidates=[]
  for (cs,owner,cid),(cp,cd) in clips.items():
   if cs!=screen:continue
   pp=animation(cd)
   if pp is None:continue
   names=[s.get(U(k,6)) for prop in pp if prop[0]==2 for k in prop[4]]
   if 'set_mode_3' in names and 'set_fps_2' in names:candidates.append((cp,cd,pp))
  assert len(candidates)==1
  cp,cd,pp=candidates[0]
  for prop in pp:
   if s.get(prop[2]) not in ('image','collapse'):continue
   keys=prop[4];assert not any(U(k,2)==700 for k in keys)
   prior=max((k for k in keys if U(k,2)<700),key=lambda k:U(k,2))
   key=bytearray(prior);struct.pack_into('>I',key,2,700)
   struct.pack_into('>I',key,6,0xfffffff3 if s.get(prop[2])=='image' else 0)
   keys.append(bytes(key));keys.sort(key=lambda k:U(k,2))
  add(cp,cd,encode_animation(cd,pp),kind='literal-delta')
 # Scope cursor redirection to the resolution controller's two event actions.
 for start in [0x237244f,0x25e400a]:
  bound=[]
  for cp,n,t in rs:
   if start<=cp<start+0x200 and t==0x10009:
    cd=b[cp:cp+n]
    if n==51 and s.get(U(cd,36))=='Cursor2' and s.get(U(cd,41))=='Cursor2' and s.get(U(cd,46))=='MV_Resolution':
     nd=bytearray(cd);ref=next(k for k,v in s.items() if v=='Cursor3')
     struct.pack_into('>I',nd,36,ref);struct.pack_into('>I',nd,41,ref)
     add(cp,cd,nd,kind='literal-delta');bound.append(cp)
  assert len(bound)==2,(hex(start),bound)
 # Settings summary has independent text; CSV modification never touched it.
 p=0x1a7246b;old=b[p:p+53];assert U(old,0)==0x10005 and s[U(old,32)]=='3'
 summary_screen=max(cp for cp,n,t in rs if t==0x10002 and cp<p)
 oid=U(old,20);lineage=[]
 while (summary_screen,oid) in objects:
  oid,name=objects[(summary_screen,oid)];lineage.append(name)
 assert lineage[:4]==['IconText03','IconText','MenuItem_Select','B2_5_4'],lineage
 # Its first two summary texts identify resolution, not the neighboring quality row.
 sibling_texts=[]
 for cp,n,t in rs:
  if p-0x300<cp<p and t==0x10005 and s.get(U(b[cp:cp+n],8))=='drawText':
   sibling_texts.append(s.get(U(b[cp:cp+n],32)))
 assert sibling_texts[-2:]==['1516','1517'],sibling_texts
 new=bytearray(old);struct.pack_into('>I',new,32,0xfffffff6)
 add(p,old,new,kind='summary-label',alias='3K')
 out=dict(status='Offline repair plan; not installed; final rendering unverified',firmware_sha256=hashlib.sha256(b).hexdigest(),groups=group_rows,plans=list(sorted(changes.values(),key=lambda p:int(p['address'],16))),limitations=['UI parse timing and already-cached screen instances remain unresolved.','Private resource initialization and final raster rendering need camera validation.'])
 dest=ROOT/'prototype/development/native-ui/layout-repair-plan.json';dest.write_text(json.dumps(out,indent=2)+'\n')
 print(f'{len(group_rows)} groups; {len(changes)} bounded record changes; max {max(len(bytes.fromhex(x["new"])) for x in changes.values())} bytes')
 return out
if __name__=='__main__':build()
