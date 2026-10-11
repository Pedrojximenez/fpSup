"""One native Apply pulse, with producer/consumer agreement checked in RAM."""
import fcntl,json,pathlib,sys,time
import live_camera as live
import inspect_runtime as inspect
here=pathlib.Path(__file__).resolve().parent
dest=here/('apply-'+sys.argv[1]+'.json')
assert not dest.exists(),str(dest)
with open('/tmp/fp-af-fusion.lock','r') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert live.screen()=='SL_LAB'
 assert 'is_recording -> 0' in live.checked_sh('status get is_recording')
 before=inspect.snapshot()
 proof={'before':before};dest.write_text(json.dumps(proof,indent=2)+'\n')
 assert 'SL_LabTab -> 2' in live.checked_sh('gui geti SL_LabTab')
 assert 'SL_LabFocus -> 43357' in live.checked_sh('gui geti SL_LabFocus')
 live.checked_sh('key OKON');time.sleep(.12);live.checked_sh('key OKOFF');time.sleep(1)
 after=inspect.snapshot();proof['after']=after
 dest.write_text(json.dumps(proof,indent=2)+'\n')
 reg=after['registry'];row=after['rows'][reg['row']]
 geometry=lambda r:[r['producer'][k] for k in ('out_w','out_h','crop_w','crop_h','ratio')]
 assert geometry(before)==geometry(after),(geometry(before),geometry(after))
 assert [row['width'],row['height']]==geometry(after)[:2]
 assert reg['generation']==before['registry']['generation']+1
 assert reg['result']==0 and row['on']==1 and row['menu_row']>0
 assert after['consumer']['flag']==1 and after['consumer']['current']==reg['row']+1
 if reg['generation']>1 and before['rows'][reg['row']]['width']==row['width'] and before['rows'][reg['row']]['height']==row['height']:
  assert reg['packs']==before['registry']['packs'] and reg['asset_used']==before['registry']['asset_used']
 proof['passed']=True;dest.write_text(json.dumps(proof,indent=2)+'\n')
 print(json.dumps({'passed':True,'geometry':geometry(after),'registry':reg,'consumer':after['consumer']},indent=2),flush=True)
