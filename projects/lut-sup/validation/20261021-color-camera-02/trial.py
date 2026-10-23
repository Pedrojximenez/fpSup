"""Bounded camera evidence helper for the authorized 2026-10-21 LUT trial.
Each invocation issues one UI action at most. No record or settings-save command.
Uses maintained transfer/screenshot tools; no replacement loader or camera code.
"""
import argparse, json, pathlib, re, shutil, subprocess, sys, time
ROOT=pathlib.Path(__file__).resolve().parents[4]
OUT=pathlib.Path(__file__).resolve().parent
SHELL=ROOT/'fpSup/fp_usb_shell'
sys.path.insert(0,str(SHELL))
import putfile as pf
ap=argparse.ArgumentParser()
ap.add_argument('action',choices=['snapshot','key','shot','loadlog','state'])
ap.add_argument('value',nargs='?',default='')
a=ap.parse_args()
if pathlib.Path('/tmp/fp-af-fusion.lock').exists(): raise SystemExit('AF owner lock present')
rec=pf.sh('status get is_recording',retries=0).strip()
if rec!='is_recording -> 0': raise SystemExit('not confirmed standby: '+rec)
record={'time':time.time(),'action':a.action,'value':a.value,'recording':rec}
def sh(c):
 r=pf.sh(c,retries=0)
 if r.lstrip().startswith('ERR'): raise RuntimeError(c+': '+r)
 return r.strip()
def snapshot():
 out={c:sh(c) for c in ['status get app_current','gui geti FT_Title','gui geti FT_Focus','gui geti FT_Key','gui gets FT_PageText']}
 for k in range(6):
  out[str(k)]={n:sh(f'gui '+('gets' if n in ['N','A','Ia','Ib','Ic'] else 'geti')+f' FT_{n}{k}') for n in ['N','A','Ia','Ib','Ic','Visible','Max','Lock']}
 return out
if a.action=='key':
 if a.value not in ['MENU','UP','DOWN','LEFT','RIGHT','OK','DISP']: raise SystemExit('key refused')
 record['reply']=sh('key '+a.value+'ON');time.sleep(.8)
 record['snapshot']=snapshot()
elif a.action=='snapshot': record['snapshot']=snapshot()
elif a.action=='shot':
 import ui_drive
 image=ui_drive.shot(a.value or 'lut')
 target=OUT/'screenshots'/image.name;target.parent.mkdir(exist_ok=True)
 shutil.copy2(image,target);record['file']=str(target);print(target,flush=True)
elif a.action=='loadlog':
 target=OUT/('load-'+(a.value or 'first')+'.LOG')
 r=subprocess.run([sys.executable,'-B',str(SHELL/'getfile.py'),'\\fpSup\\LOAD.LOG',str(target),'--size','4096'],capture_output=True,text=True)
 (OUT/('load-'+(a.value or 'first')+'.txt')).write_text(r.stdout+r.stderr)
 if r.returncode: raise SystemExit(r.stdout+r.stderr)
 text=target.read_bytes().rstrip(b'\0 ').decode(errors='replace');record['log']=text
 m=re.search(r'^0A ([0-9A-Fa-f]{8}) 00000000 LUT\.BIN$',text,re.M)
 if not m: raise SystemExit('LUT not loaded: '+text)
 base=int(m[1],16);state=base+7424
 api=pf.mem_get(state,8)
 if api[:3]!=[0x3454554c,1,state]: raise SystemExit('unexpected LUT API '+repr(api))
 (OUT/'running.json').write_text(json.dumps({'base':base,'state':state,'api':api},indent=2))
elif a.action=='state':
 running=json.loads((OUT/'running.json').read_text());state=running['state']
 api=pf.mem_get(state,3)
 if api!=[0x3454554c,1,state]:raise SystemExit('running state changed')
 names=['asset','last','color','gamma','strength','samples','outside1','outside3']
 vals=pf.mem_get(state+48,8)
 if len(vals)!=8 or any(v is None for v in vals):raise SystemExit('incomplete state')
 vals=[v-2**32 if i<2 and v>=2**31 else v for i,v in enumerate(vals)]
 record['state']=dict(zip(names,vals));record['backend_not_connected_by_contract']=True
with (OUT/'trial.jsonl').open('a') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')
print(json.dumps(record,ensure_ascii=False,indent=2),flush=True)
