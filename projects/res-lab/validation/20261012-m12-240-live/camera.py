"""Task-scoped UI and bounded reads against the exact hybrid consumer/prod artifacts."""
import fcntl,hashlib,json,pathlib,re,struct,sys,time
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parents[3]
REFERENCE=HERE/'hybrid-reference'
sys.path.insert(0,str(HERE.parent/'20261009-oncamera'))
import live_camera as live
live.LOG=HERE/'commands.jsonl'
sys.path.insert(0,str(ROOT/'projects/open-gate/build/res-custom'))
import ogc_layout as L
FACT=json.loads((REFERENCE/'build.json').read_text())['facts']
from backup import idle

def value(name):
 reply=live.checked_sh('gui geti '+name);m=re.fullmatch(r'\s*OK:'+re.escape(name)+r' -> (-?\d+)\s*',reply);assert m,reply;return int(m[1])
def text(name):
 return live.checked_sh('gui gets '+name)
def recording():
 reply=live.checked_sh('status get is_recording');m=re.fullmatch(r'\s*is_recording -> ([01])\s*',reply);assert m,reply;return int(m[1])
def key(name):
 assert name in ('UP','DOWN','LEFT','RIGHT','OK','MENU','DISP','AEL','Fn')
 assert recording()==0
 try:live.checked_sh('key '+name+'ON')
 finally:
  time.sleep(.12);live.checked_sh('key '+name+'OFF')
 time.sleep(.8 if name=='MENU' else .65)
def branch(site,thumb=False,call=False):
 w=live.putfile.mem_get(site,tries=1)[0]
 if not thumb:
  assert w&0xff000000==(0xeb000000 if call else 0xea000000),(hex(site),hex(w))
  d=(w&0xffffff)<<2
  if d&0x2000000:d-=0x4000000
  return (site+8+d)&0xffffffff
 a,b=w&65535,w>>16;assert a&0xf800==0xf000 and b&0xd000==0x9000
 s=(a>>10)&1;i1=1^((b>>13)&1)^s;i2=1^((b>>11)&1)^s
 d=(s<<24)|(i1<<23)|(i2<<22)|((a&0x3ff)<<12)|((b&0x7ff)<<1)
 if d&0x1000000:d-=0x2000000
 return (site+4+d)&0xffffffff

def snapshot():
 idle();pf=live.putfile;cf=FACT['rescustom'];raw=(REFERENCE/'fpSup/32RESCUS.BIN').read_bytes()
 ep=branch(0xC043CCF8);assert 0xC072E064<=ep<=0xC072EFB4-24
 v=pf.mem_get(ep,6,tries=1);assert v[2:4]==[0x31435256,2],v
 s=v[5];core=(v[4]&~1)-(cf['virtual_dispatch_off']&~1)
 assert 0x45000000<core<=s<core+cf['block']
 assert pf.mem_get(core,8,tries=1)==list(struct.unpack_from('<8I',raw))
 code=pf.read_bulk(core+128,cf['text'],'tagged');assert code==raw[128:128+cf['text']],'resident core is not v19 candidate'
 vals={k:pf.mem_get(s+L.S[k],tries=1)[0] for k in ('FLAG','CUR','SEL','FMTLATCH','BITLATCH','PICKOK','FPSLATCH','VRATE','VR_UI','VR_WHY','NROWS','ROWS','NENT','ENTS','NVM','VMS','NVAR','VARS','LAST_ENT','VRC','RATE_LVOWED','RATE_LV_RELOADS','M12_LEGACY_HITS','BULK_HITS','HDR_COPY_HITS')}
 assert 0<vals['NROWS']<=6 and vals['NVM']<=16 and vals['NVAR']<=32
 rows=[]
 for i in range(vals['NROWS']):
  at=s+vals['ROWS']+i*L.ROW['SIZE'];assert s<=at<core+cf['block']-L.ROW['SIZE']
  r=pf.mem_get(at,L.ROW['SIZE']//4,tries=1)
  label=b''.join(w.to_bytes(4,'little') for w in r[L.ROW['LABEL']//4:L.ROW['LABEL']//4+2]).split(b'\0')[0].decode()
  rows.append({'index':i,'label':label,**{k:r[L.ROW[k]//4] for k in ('ON','AW','AH','STOCK','MROW','BASE','BITMASK')}})
 result={'consumer_base':hex(core),'consumer_state':hex(s),'consumer_version':19,'loaded_core_sha256':hashlib.sha256(code).hexdigest(),'state':vals,'rows':rows,'screen':live.screen(),'frame_rate_getter':live.checked_sh('menu SetMovFramerate').strip(),'quality_getter':live.checked_sh('menu SetMovCinemaDNGQuality').strip(),'lossless':value('MV_fpLossless')}
 off=vals['LAST_ENT']
 if vals['FLAG'] and vals['CUR'] and off:
  assert vals['ENTS']<=off<vals['ENTS']+vals['NENT']*L.ENT['SIZE'] and (off-vals['ENTS'])%L.ENT['SIZE']==0
  e=pf.mem_get(s+off,L.ENT['SIZE']//4,tries=1);entry={k:e[o//4] for k,o in L.ENT.items() if k not in ('SIZE','KEY')}
  entry['key']=b''.join(w.to_bytes(4,'little') for w in e[L.ENT['KEY']//4:L.ENT['KEY']//4+4]).split(b'\0')[0].decode()
  assert entry['VM']<vals['NVM'] and entry['VAR']<vals['NVAR']
  vm=pf.mem_get(s+vals['VMS']+entry['VM']*L.VM['SIZE'],8,tries=1)
  var=pf.mem_get(s+vals['VARS']+entry['VAR']*L.VAR['SIZE'],4,tries=1)
  result['picked_entry']=entry;result['donor']=vm[L.VM['DONOR']//4];result['variant']=var
  w0,w1=entry['W0'],entry['W1'];cycles=(w0&65535)*((w1&65535)-1)+(w0>>16)
  result['sensor_timing_fps']=72000000/cycles;result['engine_fps']=struct.unpack('<f',struct.pack('<I',entry['ENGFPS']))[0]
 return result

def main():
 with open('/tmp/fp-af-fusion.lock') as lease:
  fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
  action=sys.argv[1]
  if action=='key':
   for k in sys.argv[2:]:key(k);print(k,live.screen(),flush=True)
  elif action=='state':
   print(live.screen(),flush=True)
   for n in sys.argv[2:]:print(n,value(n),flush=True)
  elif action=='snapshot':
   dest=HERE/(sys.argv[2]+'.json');assert not dest.exists();r=snapshot();dest.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2),flush=True)
  else:raise ValueError(action)
if __name__=='__main__':main()
