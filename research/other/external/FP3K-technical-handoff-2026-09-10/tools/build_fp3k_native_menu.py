"""Build experimental native menu resident; no media writes."""
import sys,struct,hashlib,json
from pathlib import Path
from fullheight_candidate import plan
from preview_candidate import plan as preview_plan
from native_resolution_resource import stock,CSV,ROOT
sys.path.insert(0,str(ROOT/'research/fpSup/fp_usb_shell'))
from armasm import assemble,symbols
BASE=0xc072de64;STATE=0xc0732000;UI_RANGE=0xc1a709bc
OUT=ROOT/'prototype/development/native-menu'
HOOKS=[(0xc057a6a0,'resolution_select'),(0xc05931d0,'resolution_display'),(0xc005c020,'set_resolution'),(0xc005be58,'set_format'),(0xc005bef0,'set_quality'),(0xc005c0b8,'set_rate'),(0xc005bb60,'set_crop'),(0xc0062ec8,'set_media')]
HOOKS += [(0xc05824d0,'qs_resolution_select'),(0xc059c640,'hud_display_a'),(0xc059c9f0,'hud_display_b'),(0xc05e84d8,'ui_load'),(0xc05e6400,'ui_record'),(0xc05e5b58,'ui_string')]
THUMB={'ui_load':0xb086b500,'ui_record':0x4ff0e92d,'ui_string':0x3ffff1b1}
HOOKS += [(0xc0437e98,'preview_output')]
HOOKS += [(0xc0306ea0,'preview_layout')]
def branch_word(address,target,label):
 if label not in THUMB:return 0xea000000|(((target-address-8)>>2)&0xffffff)
 d=target-address-4
 assert d%2==0 and -(1<<24)<=d<(1<<24)
 sign=(d>>24)&1;j1=1^((d>>23)&1)^sign;j2=1^((d>>22)&1)^sign
 return (0xf000|(sign<<10)|((d>>12)&0x3ff))|((0x9000|(j1<<13)|(j2<<11)|((d>>1)&0x7ff))<<16)
CONFIG=[(0x5a0,0),(0x62c,0),(0x648,0),(0x69c,12)]
def build():
 b,old=stock();entries=plan()+preview_plan();out=[]
 from audit_fp3k_ui_layout import build as ui_build
 ui=ui_build()
 # Preserve the two verified QS controller limits.
 import build_fp3k_ui_resources as legacy_ui
 ui['plans'] += [p for p in legacy_ui.build()['plans'] if p['kind']=='QS-limit']
 import difflib
 lines=[f'.equ UI_RECORD_COUNT, {len(ui["plans"])}','ui_records:'];edits=bytearray()
 for p in sorted(ui['plans'],key=lambda p:int(p['address'],16)):
  source_bytes=bytes.fromhex(p['old']);h=0x811c9dc5
  for v in source_bytes:h=((h^v)*0x1000193)&0xffffffff
  assert len(source_bytes)<1024
  meta=len(source_bytes)
  if p['kind']=='layout-keys':
   aliases=p['aliases'];assert len(aliases)<=1
   prop=int(next(iter(aliases),'-1'))+1;assert prop<16
   alias=next(iter(aliases.values()),None)
   av={'FP3K_L':0xf0,'FP3K_M':0xf1,'FP3K_QS':0xf2,'FP3K_FONT':0xf4,None:0}[alias]
   meta|=(1<<10)|(p['time']<<13)|(prop<<20)|(av<<24)
  elif p['kind']=='state-end':meta|=(2<<10)|(p['time']<<13)
  elif p['kind']=='summary-label':meta|=3<<10
  elif p['kind']=='literal-delta':
   assert len(edits)<(1<<19)
   meta|=(4<<10)|(len(edits)<<13)
   new=bytes.fromhex(p['new'])
   for tag,i,j,x,y in difflib.SequenceMatcher(None,source_bytes,new,autojunk=False).get_opcodes():
    if tag=='equal':continue
    edits.extend(struct.pack('<HHH',i,j-i,y-x)+new[x:y]);edits.extend(bytes(len(edits)%2))
   edits.extend(b'\xff\xff')
  else:assert p['kind']=='QS-limit'
  lines.append('.word '+','.join(hex(v) for v in [int(p['address'],16),meta,h]))
 lines += ['ui_edits:','.byte '+','.join(str(x) for x in edits),'.align 2']
 lines += ['ui_pack:', '.incbin "prototype/development/native-ui/FP3KUI.NBR"','ui_pack_end:','.align 2']
 (ROOT/'tools/fp3k_native_ui_data.inc').write_text('\n'.join(lines)+'\n')
 assert b[UI_RANGE-0xc0000000:UI_RANGE-0xc0000000+4]==bytes.fromhex("3f800000")
 for address,name in HOOKS:
  word=struct.unpack_from('<I',b,address-0xc0000000)[0]
  expected=THUMB.get(name,0xe3a00003 if name=='preview_layout' else 0xe92d4030 if name=='preview_output' else 0xe92d40f0 if name in ['resolution_select','qs_resolution_select'] else 0xe92d4070)
  assert word==expected,(name,hex(word))
 out+=['.equ HOOK_COUNT, '+str(len(HOOKS)),'hooks:']
 for a,label in HOOKS:
  word=struct.unpack_from('<I',b,a-0xc0000000)[0]
  out.append(f'.word 0x{a:08x}, 0x{word:08x}, 0')
 out += [f'.equ PATCH_COUNT, {len(entries)}', 'patch_table:']+[f'.word 0x{e["address"]:08x}, {e["expected"]}, {e["replacement"]}' for e in entries]
 out+=['config_table:']+[f'.word 0x{0xc31ac59c+o:08x}, {v}' for o,v in CONFIG]
 for label,data in [('csv_stock',old),('csv_new',CSV)]:
  out+=[label+':','.byte '+','.join(str(v) for v in data),'.align 2']
 (ROOT/'tools/fp3k_native_menu_data.inc').write_text('\n'.join(out)+'\n')
 src=ROOT/'tools/fp3k_native_menu.S';code=bytearray(assemble(src));syms=symbols(src)
 for i,(a,label) in enumerate(HOOKS):
  word=struct.unpack_from('<I',b,a-0xc0000000)[0]
  out[2+i]=f'.word 0x{a:08x}, 0x{word:08x}, 0x{branch_word(a,BASE+syms[label],label):08x}'
 (ROOT/'tools/fp3k_native_menu_data.inc').write_text('\n'.join(out)+'\n')
 code=bytearray(assemble(src))
 assert syms['payload_end']==len(code) and BASE+len(code)<STATE
 assert b[BASE-0xc0000000:STATE-0xc0000000+48]==bytes(STATE-BASE+48)
 struct.pack_into('<I',code,syms['checksum_word'],(-sum(struct.unpack('<'+'I'*(len(code)//4),code)))&0xffffffff)
 assert sum(struct.unpack('<'+'I'*(len(code)//4),code))&0xffffffff==0
 OUT.mkdir(parents=True,exist_ok=True);(OUT/'FP3KMENU.BIN').write_bytes(code)
 m=dict(status='EXPERIMENTAL OFFLINE BUILD; not installed or camera validated',base=hex(BASE),state=hex(STATE),bytes=len(code),sha256=hashlib.sha256(code).hexdigest(),hooks=[dict(address=hex(a),entry=l) for a,l in HOOKS],symbols={k:hex(BASE+v) for k,v in syms.items() if not k.startswith('$')},configuration='Existing CinemaDNG,12-bit,true24,crop off,SSD required; selecting another recording setting deselects3K',limitations=['Capture transition and settings guards require camera validation.','Native resource caching/literal text rendering not yet exercised on a camera.','Not a flash update; RAM hooks only.','All-photosite reducer semantics remain unproven.'])
 (OUT/'resident-manifest.json').write_text(json.dumps(m,indent=2)+'\n')
 m['preview_experiment']=dict(table_changes=preview_plan(), state_bytes=64,
     layout_hook=dict(address='0xc0306ea0',scope='Private 3K and native display device kind 1',aspect=[3,2],diagnostic_offsets=[56,60],limitations='Native movie display-fit branch; hardware execution and visible framing not established.'),
     output_hook=dict(address='0xc0437e98',primary_channel=0,dimensions=[1620,1080],
         policy_objects=['0xc375eb68','0xc375ed3c'],
         guards='Private 3K active, exact owner and template pointers, FNV of all 44 stock template bytes. Otherwise stock accessor.',
         behavior='Returns an immutable private output template; only width/height and matching visible dimensions change. Format, allocation limit and video flags preserved.'),
     qs_diagnostic_bits={'0':'first QS limit','1':'second QS limit','2':'first QS footer','3':'second QS footer'},
     qs_seen_offset=48,qs_extended_offset=52,
     limitations=['Only fresh source construction sees table changes; the current standby source can remain cached until a native transition.', 'Buffer-size calculations verified against observed source objects; actual allocations and display framing require camera testing.', 'QS regression is being diagnosed, not claimed fixed.'])
 (OUT/'resident-manifest.json').write_text(json.dumps(m,indent=2)+'\n')
 return bytes(code),syms,entries,b,m
if __name__=='__main__':print(json.dumps(build()[4],indent=2))
