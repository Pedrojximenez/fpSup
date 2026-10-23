"""Read only bounded, completed profile records inside the loaded LOSS block."""
import sys,fcntl,json,time,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'fpSup/fp_usb_shell'),str(ROOT/'fpSup/lossless')]
import putfile as pf,card_status as cs
label=sys.argv[1];out=HERE/(label+'-phases.json');assert not out.exists()
layout=Path(os.environ.get('FPL_LIVE_LAYOUT',str(HERE/'baseline-profile/layout.json')))
fields=json.loads(layout.read_text())['fields'];blob=json.loads(layout.with_name('build.json').read_text())['blob']
f=open('/tmp/fp-af-fusion.lock','a');fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
assert pf.sh('status get is_recording',retries=0,timeout_ms=5000).strip()=='is_recording -> 0'
record,state,base=cs.find_record(pf.mem_get);assert state<0x80000000,'cached-alias state (2026-10-13+): mem_read DMA cannot reach it; use mem_get';assert pf.mem_get(state+fields['hold_live'])[0]==0
trial=json.loads((HERE/(label+'.json')).read_text())
assert trial['after']['state']==hex(state) and trial['after']['base']==hex(base)
assert pf.mem_get(state+fields['rec_events'])[0]==trial['after']['values']['rec_events'], 'another take replaced the phase records'
caps=pf.mem_caps();assert caps and caps['windows'][7]==(0,0,0)
r={'time':time.time(),'boot':pf.mem_get(0xc072f6f8)[0],'state':state,'base':base,'lanes':{}}
import struct
for lane in ('hold','hold_b'):
 n=pf.mem_get(state+fields[lane+'.profile_n'])[0];assert 0<=n<=512
 assert n==trial['after']['values'][lane+'.profile_n'], 'phase count changed after trial'
 at=state+fields[lane+'.profile'];assert base<=at<=at+n*16<=base+blob['block_bytes']
 if n:
  pf.mem_window(7,at,n*16,1)
  try:raw=pf.mem_read(at,n*16,label=lane+' phases')
  finally:pf.mem_window(7,0,0,0)
  assert n==pf.mem_get(state+fields[lane+'.profile_n'])[0]
  r['lanes'][lane]=list(struct.iter_unpack('<4I',raw))
 else:r['lanes'][lane]=[]
out.write_text(json.dumps(r,indent=2));print(out.name,{k:len(v) for k,v in r['lanes'].items()})
