"""Read back final camera files and preserve the observed idle state."""
import fcntl,hashlib,importlib,json,pathlib,struct,sys
import live_camera as live
import inspect_runtime as inspect
sys.path.insert(0,str(live.ROOT/'projects/open-gate/build/res-custom'))
import ogc_layout as L
import rcd
here=pathlib.Path(__file__).resolve().parent
label=sys.argv[1] if len(sys.argv)>1 else 'final'
dest=here/(label+'-readback');dest.mkdir(exist_ok=True)
card=inspect.CARD
sources=[('\\AutoRun.txt',here/'backup-before/AutoRun.txt'),
         ('\\fpSup\\LOADER.BIN',here/'backup-before/LOADER.BIN'),
         ('\\fpSup\\32RESCUS.BIN',card/'fpSup/32RESCUS.BIN'),
         ('\\fpSup\\50RESLAB.BIN',card/'fpSup/50RESLAB.BIN')]
for name in ('S16','OG2K','OG3K','OG4K','OG35K'):
 sources.append(('\\fpSup\\RESCUS\\'+name+'.RCD',here/'rcd-v3'/(name+'.RCD')))
proof={'verified':[]}
def save(): (here/(label+'-audit.json')).write_text(json.dumps(proof,indent=2)+'\n')
def verify_bytes(remote,actual,expected):
 if remote!='\\fpSup\\32RESCUS.BIN':
  assert actual==expected,remote
  return {'comparison':'exact'}
 # ogc_save owns file+32..+128; it saves the current row label after Apply.
 # Verify all program bytes exactly, and validate the settings record rather
 # than treating a legitimate save as corrupted code or overwriting it.
 begin=32;end=begin+L.CFG['BYTES'];cfg=actual[begin:end]
 assert len(actual)==len(expected) and actual[:begin]==expected[:begin] and actual[end:]==expected[end:],remote
 word=lambda key:struct.unpack_from('<I',cfg,L.CFG[key])[0]
 assert word('MAGIC')==L.CFG_MAGIC and word('VERSION')==L.CFG_VERSION
 assert word('SUM')==rcd.fnv(cfg[:L.CFG['SUM']])
 assert cfg[L.CFG['NEN']:L.CFG['SUM']]==expected[begin+L.CFG['NEN']:begin+L.CFG['SUM']]
 assert cfg[L.CFG['SUM']+4:]==expected[begin+L.CFG['SUM']+4:end]
 row=proof['runtime']['rows'][proof['runtime']['registry']['row']]
 assert cfg[L.CFG['SEL']:L.CFG['SEL']+8].split(b'\0')[0].decode()==row['label']=='VRC000'
 assert word('SEL_STOCK')==row['stock']==2 and word('FLAGS')==0
 return {'comparison':'program exact; owned settings validated','source_sha256':hashlib.sha256(expected).hexdigest(),
         'settings':{'label':row['label'],'stock':word('SEL_STOCK'),'flags':word('FLAGS'),'enabled_count':word('NEN'),'checksum_valid':True}}
with open('/tmp/fp-af-fusion.lock','r') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert 'is_recording -> 0' in live.checked_sh('status get is_recording')
 proof['screen']=live.screen()
 # The existing shell exposes menu getter by omitting a value from SetName.
 proof['settings']={key:live.checked_sh('menu Set'+key) for key in ('MovRecSize','MovFramerate','MovCinemaDNGQuality','MovRecFormat','MovBiningSupport','CropMode')}
 proof['runtime']=inspect.snapshot();save()
 for remote,source in sources:
  assert source.is_file(),str(source)
  local=dest/source.name;assert not local.exists(),str(local)
  sys.argv=['getfile.py',remote,str(local),'--size',str(source.stat().st_size)]
  assert not importlib.import_module('getfile').main()
  comparison=verify_bytes(remote,local.read_bytes(),source.read_bytes())
  proof['verified'].append({'remote':remote,'bytes':local.stat().st_size,'sha256':hashlib.sha256(local.read_bytes()).hexdigest(),'readback':str(local),**comparison})
  save();print('Verified',remote,local.stat().st_size,flush=True)
 proof['root_listing']=live.checked_sh('dir \\')
 proof['sup_listing']=live.checked_sh('dir \\fpSup')
 proof['rcd_listing']=live.checked_sh('dir \\fpSup\\RESCUS')
 assert 'is_recording -> 0' in live.checked_sh('status get is_recording')
 proof['idle']=True;proof['passed']=True;save()
