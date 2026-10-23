"""Prepare a consumer-only update against exact backed-up loader and producer."""
import hashlib,json,pathlib,shutil,struct,sys
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path[:0]=[str(ROOT/'projects/open-gate/build/res-custom')]
import ogc_layout as L,rcd
p=HERE/'backup';m=json.loads((p/'manifest.json').read_text());assert m['phase']=='complete'
oldref=ROOT/'projects/res-lab/validation/20261011-virtual-rate-context-live/reference-capture-header-v17'
newref=ROOT/'projects/res-lab/cards/20261012-m12-240/plain'
old=(p/'fpSup__32RESCUS.BIN').read_bytes();frozen=(oldref/'fpSup/32RESCUS.BIN').read_bytes()
assert old[:32]==frozen[:32] and old[128:]==frozen[128:]
producer=(p/'fpSup__50RESLAB.BIN').read_bytes();assert hashlib.sha256(producer).hexdigest()=='dad8226db751fe10c2cac1f2f21269cc746957c7aacc5b19bec83dd027da155f'
new=(newref/'fpSup/32RESCUS.BIN').read_bytes();assert hashlib.sha256(new).hexdigest()=='0cb978b7f1568b3d39de4c6b465a548c442912e0962da1d9d8cb6b1304c87dc8'
cfg=old[32:128];assert rcd.fnv(cfg[:L.CFG['SUM']])==struct.unpack_from('<I',cfg,L.CFG['SUM'])[0]
prepared=new[:32]+cfg+new[128:]
nh,oh=struct.unpack_from('<8I',new),struct.unpack_from('<8I',old)
assert all(nh[i]==oh[i] for i in (0,1,5,7)) and nh[6]==19 and oh[6]==17
out=HERE/'hybrid-reference';out.mkdir();(out/'fpSup/RESCUS').mkdir(parents=True)
for src,name in [('AutoRun.txt','AutoRun.txt'),('fpSup__LOADER.BIN','fpSup/LOADER.BIN'),('fpSup__00SHELL.BIN','fpSup/00SHELL.BIN'),('fpSup__50RESLAB.BIN','fpSup/50RESLAB.BIN')]:
 (out/name).write_bytes((p/src).read_bytes())
(out/'fpSup/32RESCUS.BIN').write_bytes(prepared)
for src in p.glob('fpSup__RESCUS__*.RCD'):(out/'fpSup/RESCUS'/src.name.split('__')[-1]).write_bytes(src.read_bytes())
shutil.copy2(newref/'fpSup/RESCUS/M12240.RCD',out/'fpSup/RESCUS/M12240.RCD')
meta=json.loads((oldref/'build.json').read_text());meta['file']='50RESLAB.BIN';meta['facts']['rescustom']=json.loads((newref/'build.json').read_text())['facts']['rescustom']
meta['shell']=True;meta['hybrid_source']='Exact card backups; consumer v19 replacing v17, producer v17 and current common loader retained'
meta['physical_optional_modules']='Preserved on camera; not modeled by this focused boot fixture'
(out/'build.json').write_text(json.dumps(meta,indent=2)+'\n')
report={'consumer_before':hashlib.sha256(old).hexdigest(),'consumer_prepared':hashlib.sha256(prepared).hexdigest(),'cfg_preserved':True,'producer_retained_version':17,'loader_retained':hashlib.sha256((out/'fpSup/LOADER.BIN').read_bytes()).hexdigest(),'autorun_retained':hashlib.sha256((out/'AutoRun.txt').read_bytes()).hexdigest(),'no_camera_write':True}
(HERE/'hybrid-preparation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
