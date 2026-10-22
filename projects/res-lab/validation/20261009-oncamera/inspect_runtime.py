"""Read-only proof of the two loaded module owners and their bounded states."""
import fcntl,json,os,pathlib,struct,sys
import live_camera as live
pf=live.putfile
HERE=pathlib.Path(__file__).resolve().parent
ROOT=live.ROOT
CARD=pathlib.Path(os.environ.get('RESLAB_LIVE_CARD', str(ROOT/'projects/res-lab/cards/20261009-virtual-rcd-v6/debug')))
FACT=json.loads((CARD/'build.json').read_text())['facts']
def arm_b(site):
 w=pf.mem_get(site)[0]
 assert w&0xff000000==0xea000000,hex(w)
 d=(w&0xffffff)<<2
 if d&0x2000000:d-=0x4000000
 return (site+8+d)&0xffffffff
def thumb_b(site):
 w=pf.mem_get(site)[0];a=w&0xffff;b=w>>16
 assert a&0xf800==0xf000 and b&0xd000==0x9000,hex(w)
 s=(a>>10)&1;i1=1^((b>>13)&1)^s;i2=1^((b>>11)&1)^s
 d=(s<<24)|(i1<<23)|(i2<<22)|((a&0x3ff)<<12)|((b&0x7ff)<<1)
 if d&0x1000000:d-=0x2000000
 return (site+4+d)&0xffffffff
def snapshot():
 ep=arm_b(0xC043CCF8);assert 0xc072e064<=ep<0xc072efb4
 v=pf.mem_get(ep,6);assert v[2:4]==[0x31435256,2],v
 S=v[5];core=(v[4]&~1)-(FACT['rescustom']['virtual_dispatch_off']&~1)
 assert 0x45000000<core<=S<core+FACT['rescustom']['block']
 vp=pf.mem_get(S+0x7dc)[0];assert core<vp<core+FACT['rescustom']['block']
 values=pf.mem_get(vp,11)
 names=['magic','abi','lock','provider','generation','result','detail','count','packs','asset_used','row']
 vh=thumb_b(0xc05e82f0);assert 0xc072e064<=vh<0xc072efb4
 veneer=pf.mem_get(vh,2);assert veneer[0]==0xf000f8df
 base=(veneer[1]&~1)-(FACT['functions']['rl_page_layer']&~1)
 m=base+FACT['state_off'];assert 0x45000000<base<m<base+FACT['block']
 headers={}
 for name,address in [('32RESCUS.BIN',core),('50RESLAB.BIN',base)]:
  words=pf.mem_get(address,8)
  expected=list(struct.unpack('<8I',(CARD/'fpSup'/name).read_bytes()[:32]))
  assert words==expected,(name,words,expected)
  headers[name]={'file_len':words[2],'block_size':words[3],'id':words[5],'version':words[6],'min_services':words[7]}
 fields={k:pf.mem_get(m+o)[0] for k,o in FACT['state_fields'].items() if k not in ['mode_ids','canvas','export_text']}
 ids=b''.join(w.to_bytes(4,'little') for w in pf.mem_get(m+FACT['state_fields']['mode_ids'],18))[:fields['modes_rows']]
 header=pf.mem_get(S,25)
 selected=pf.mem_get(S+0x220)[0]
 rows=pf.mem_get(S+0x34)[0]
 row_info=[]
 for i in range(header[12]):
  r=pf.mem_get(S+rows+112*i,28)
  row_info.append({'index':i,'on':r[3],'width':r[4],'height':r[5],'stock':r[14],'menu_row':r[15],'pack':hex(r[19]),'label':b''.join(w.to_bytes(4,'little') for w in r[12:14]).split(b'\0')[0].decode('ascii'),'ui_result':r[23]})
 result={'endpoint':hex(ep),'consumer_base':hex(core),'consumer_state':hex(S),'registry':dict(zip(names,values)),
 'consumer':{k:header[o//4] for k,o in [('flag',8),('current',16),('res_value',20),('format_latch',24),('nrows',48),('nentries',56),('nmodes',64)]},
 'selected':selected,'rows':row_info,'producer_base':hex(base),'producer_state':hex(m),'producer':fields,'mode_ids':list(ids),'loaded_headers':headers}
 cf=FACT['rescustom'];layout=cf['S']
 navail=pf.mem_get(S+layout['NAVAIL'])[0];assert navail<=16,navail
 available=[]
 for i in range(navail):
  label=pf.mem_get(S+layout['AVAIL']+8*i,2)
  available.append(b''.join(w.to_bytes(4,'little') for w in label).split(b'\0')[0].decode('ascii'))
 cfg=pf.mem_get(S+layout['CFG'])[0];assert core<=cfg and cfg+96<=core+cf['block']
 cw=pf.mem_get(cfg,24);raw=b''.join(w.to_bytes(4,'little') for w in cw)
 checksum=0x811c9dc5
 for byte in raw[:0x4c]:checksum=((checksum^byte)*0x01000193)&0xffffffff
 nen=cw[6];assert nen<=6,nen
 enabled=[raw[28+8*i:36+8*i].split(b'\0')[0].decode('ascii') for i in range(nen)]
 result['file_management']={'available':available,'explicit_enable_count':nen,'enabled_labels':enabled,
   'record_valid':cw[0]==0x31534352 and cw[1]==1 and cw[19]==checksum}
 if 'files_state' in cf:
  ui=pf.mem_get(S+layout['FILE_UI'])[0]
  assert not ui or core+cf['files_state']==ui
  result['file_management']['ui_owner']=hex(ui)
  if ui:result['file_management']['ui_header']=pf.mem_get(ui,7)
 return result
if __name__=='__main__':
 with open('/tmp/fp-af-fusion.lock','r') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  r=snapshot()
  if len(sys.argv)>1:(HERE/sys.argv[1]).write_text(json.dumps(r,indent=2)+'\n')
  print(json.dumps(r,indent=2))
