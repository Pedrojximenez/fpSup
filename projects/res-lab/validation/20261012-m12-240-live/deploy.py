"""Authorized consumer/RCD-only card update; complete exact readback, no reboot."""
import fcntl,hashlib,importlib,json,pathlib,re,sys
import backup as B
HERE=B.HERE;REFERENCE=HERE/'hybrid-reference';live=B.live

def main():
 log=(HERE/'hybrid-offline-corrected.log').read_text();assert log.rstrip().endswith('OK')
 dest=HERE/'deployment';dest.mkdir()
 manifest=json.loads((HERE/'backup/manifest.json').read_text());assert manifest['phase']=='complete'
 expected={r:(HERE/'backup'/d['file']).read_bytes() for r,d in manifest['files'].items()}
 candidate=(REFERENCE/'fpSup/32RESCUS.BIN').read_bytes()
 assert hashlib.sha256(candidate).hexdigest()=='7a1ca8757169585952031032e31a1cd4ada7d2e96255f72ff6c718021c0bbb71'
 rcd=(REFERENCE/'fpSup/RESCUS/M12240.RCD').read_bytes()
 assert hashlib.sha256(rcd).hexdigest()=='971fe0f3c78966f2f8ca8c4246260612ff2852a9481eedfcf6d48b35a674490e'
 proof={'phase':'preflight','writes':['\\fpSup\\32RESCUS.BIN','\\fpSup\\RESCUS\\M12240.RCD'],'cfg_preserved':True,'autorun_loader_producer_retained':True,'rebooted':False}
 save=lambda:(dest/'deployment.json').write_text(json.dumps(proof,indent=2)+'\n')
 with open('/tmp/fp-af-fusion.lock') as lease:
  fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB);proof['idle']=B.idle()
  assert 'slot = sd0' in live.checked_sh('sdcard slot')
  listing=live.checked_sh('dir \\fpSup\\RESCUS');assert 'M12240.RCD' not in listing
  for remote in ('\\AutoRun.txt','\\fpSup\\LOADER.BIN','\\fpSup\\32RESCUS.BIN','\\fpSup\\50RESLAB.BIN'):
   data=B.fetch(remote,dest/('pre-'+remote.lstrip('\\').replace('\\','__')),len(expected[remote]))
   assert data==expected[remote],'card changed after backup: '+remote
  sys.path.insert(0,str(HERE.parent/'20261011-virtual-rate-context-live'))
  import camera as C
  from importlib.util import spec_from_file_location,module_from_spec
  spec=spec_from_file_location('m12_native_lcd',HERE.parent/'20261011-virtual-rate-context-live/native_lcd.py')
  lcd=module_from_spec(spec);spec.loader.exec_module(lcd)
  proof['standby_before']=lcd.shot('m12240-before-write',dest)
  proof['phase']='backup_and_standby_verified';save()
  for local,remote,data in ((REFERENCE/'fpSup/32RESCUS.BIN','\\fpSup\\32RESCUS.BIN',candidate),(REFERENCE/'fpSup/RESCUS/M12240.RCD','\\fpSup\\RESCUS\\M12240.RCD',rcd)):
   B.idle();proof['phase']='write_requested';proof['current_write']=remote;save()
   sys.argv=['putfile.py',str(local),remote];assert importlib.import_module('putfile').main()==0
   folder,name=remote.rsplit('\\',1);listing=live.checked_sh('dir '+folder)
   assert B.entries(listing)[name]==len(data)
   got=B.fetch(remote,dest/('installed-'+name),len(data));assert got==data
   proof.setdefault('verified',{})[remote]={'bytes':len(got),'sha256':hashlib.sha256(got).hexdigest(),'full_readback':True};save()
  proof['unchanged']={}
  for remote,data in expected.items():
   if remote in ('\\fpSup\\32RESCUS.BIN','\\fpSup\\LOAD.LOG'):continue
   name=remote.lstrip('\\').replace('\\','__')
   got=B.fetch(remote,dest/('after-'+name),len(data));assert got==data,remote
   proof['unchanged'][remote]=hashlib.sha256(got).hexdigest();save()
  proof['phase']='verified_card_update';save();print(json.dumps(proof,indent=2),flush=True)
if __name__=='__main__':main()
