"""Capture actual LV after a confirmed QS cycle; never approve pre-refresh LCD.
Caller authorizes screenshot writes. No settings changes or recording keys.
"""
import argparse,fcntl,json,shutil,time
from pathlib import Path
import experiment as E
from current_screen import Screen
p=argparse.ArgumentParser();p.add_argument('--variant',required=True);p.add_argument('--tag',required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--from-qs',action='store_true');p.add_argument('--shots',type=int,choices=(1,2),default=2);a=p.parse_args()
assert a.variant in ('stock','combined-fix4','combined-fix5','combined-fix6','combined-fix7','combined-fix8','combined-fix9','combined-fix10','combined-fix11','combined-fix12')
assert a.tag.replace('-','').replace('_','').isalnum()
out=a.out.resolve();assert not out.exists();out.mkdir(parents=True)
E.live.LOG=out/'commands.jsonl'
with open('/tmp/fp-af-fusion.lock','r') as lease:
 fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
 daemon=E.daemon();E.B.idle()
 if a.variant=='stock':
  assert E.pf.remote_file_size('\\fpSup\\32RESCUS.BIN') is None
  image=(E.ROOT/'out/MAIN_c0000000.bin').read_bytes()
  for address,size in ((0xC043CCF8,4),(0xC1E8E924,56)):
   assert E.pf.read_bulk(address,size,'stock control')==image[address-0xC0000000:address-0xC0000000+size]
  identity={'RESCUS_card_file_absent':True,'picker_and_medium_draw_original':True}
 else:state,identity=E.core_state(a.variant)
 screen=Screen();initial=screen.read();target='LV_CINE_MEDIUM';assert initial in ('QS_CINE',target),initial
 if a.from_qs:assert initial=='QS_CINE',initial
 record={'daemon':daemon,'identity':identity,'initial_screen':initial,'sequence':[],'screenshots':[],'settings_changed':False}
 sequence=[('QSON',target),('QSOFF',target)] if initial=='QS_CINE' else [('QSON','QS_CINE'),('QSOFF','QS_CINE'),('QSON',target),('QSOFF',target)]
 for key,want in sequence:
  E.B.idle();E.live.checked_sh('key '+key,timeout_ms=30000);observed=screen.read()
  record['sequence'].append({'key':key,'screen':observed});assert observed==want,(key,observed)
  (out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
 for suffix in ['A','B'][:a.shots]:
  E.B.idle();assert screen.read()==target;time.sleep(1)
  tag=a.tag+'-'+suffix;E.live.shot(tag)
  paths=list((E.ROOT/'projects/res-lab/validation/20261009-oncamera/screenshots').glob('*-'+tag+'.jpg'));assert len(paths)==1
  destination=out/paths[0].name;shutil.copy2(paths[0],destination);record['screenshots'].append(str(destination))
  (out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
 record['final_screen']=screen.read();assert record['final_screen']==target
 record['final_idle']=E.B.idle();record['echo_restored']=E.pf.mem_get(E.pf.ECHO_SLOT,tries=1)==[E.pf.ECHO_ORIG];assert record['echo_restored']
 (out/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2),flush=True)
