"""Bounded, sequential evidence for the authorized QS Touch hardware trial."""
import argparse, json, pathlib, re, struct, subprocess, sys, time
ROOT=pathlib.Path(__file__).resolve().parents[4]
OUT=pathlib.Path(__file__).resolve().parent
SHELL=ROOT/'fpSup/fp_usb_shell'
sys.path.insert(0,str(SHELL))
import putfile as pf

def sh(command):
    answer=pf.sh(command,retries=0,timeout_ms=1500 if command.startswith('key ') else 0)
    if answer.lstrip().startswith('ERR'):
        raise RuntimeError(command+': '+answer)
    return answer.strip()

def idle():
    if pathlib.Path('/tmp/fp-af-fusion.lock').exists():raise RuntimeError('AF owner lock')
    if sh('status get is_recording')!='is_recording -> 0':raise RuntimeError('not standby')

def words(addr,count=1):
    got=pf.mem_get(addr,count)
    if len(got)!=count or any(x is None for x in got):raise RuntimeError('incomplete read')
    return got

def screen():
    app=words(0xC37B7048)[0];scr=words(app+0x84c)[0]
    name=words(scr+8)[0] if scr else 0
    return b''.join(w.to_bytes(4,'little') for w in words(name,8)).split(b'\0')[0].decode('ascii') if name else '?'

def snapshot():
    boot=words(0xC072F6F8)[0]
    present=pf.remote_file_size('\\fpSup\\QSTOUCH.BIN') is not None
    cmds=['status get app_current','gui geti MENU_Level1','gui geti MENU_Level2','gui geti FT_Focus']
    if present:cmds += ['gui geti QST_Active','gui geti QST_Touch','gui gets QST_Status','gui gets QST_Footer']
    cmds += [f'gui gets FT_N{k}' for k in range(6)]
    if present:cmds += [f'gui gets QST_V{k}' for k in range(8)]
    result={c:sh(c) for c in cmds};result['screen']=screen()
    result['touch_slot']=hex(words(0xC0CFCCDC)[0]);result['boot']=boot
    running=OUT/'running.json'
    if present and running.exists():
        info=json.loads(running.read_text());base=info['base'];blob=pathlib.Path(info.get('artifact',OUT/'exact-card/fpSup/QSTOUCH.BIN')).read_bytes()
        off=int.from_bytes(blob[52:56],'little')
        # A manual reboot can retain an old block with a valid magic. Prove
        # this exact header and its live observer before interpreting BSS.
        live=int(result['touch_slot'],16)
        owns=base<=live<base+len(blob) and words(base,16)==list(struct.unpack_from('<16I',blob))
        if owns and words(base+off)[0]==0x31545351:
            result['sup_state']=dict(zip(['magic','result','installed','packets','consumed','cancelled','applied','svc','ui'],words(base+off,9)))
        else:result['sup_state_unavailable']='running metadata belongs to an earlier boot or artifact'
    if words(0xC072F6F8)[0]!=boot:
        result.pop('sup_state',None);result['snapshot_invalid']='camera rebooted during these sequential reads'
    return result

def loadlog(tag):
    out=OUT/f'load-{tag}.LOG'
    r=subprocess.run([sys.executable,'-B',str(SHELL/'getfile.py'),'\\fpSup\\LOAD.LOG',str(out),'--size','4096'],capture_output=True,text=True)
    (OUT/f'load-{tag}.txt').write_text(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError('loadlog read failed')
    text=out.read_bytes().rstrip(b'\0 ').decode('ascii')
    m=re.search(r'^0A ([0-9A-F]{8}) 00000001 QSTOUCH\.BIN$',text,re.M)
    if not m:raise RuntimeError('QS Touch did not load: '+text)
    active=OUT/'active-artifact.json'
    artifact=json.loads(active.read_text())['path'] if active.exists() else str(OUT/'exact-card/fpSup/QSTOUCH.BIN')
    (OUT/'running.json').write_text(json.dumps({'base':int(m[1],16),'artifact':artifact},indent=2))
    return text

def shot(tag):
    def listing():
        return {int(m[2]):int(m[1]) for m in re.finditer(r'(\d+)\s+SS__(\d{4})\.JPG',sh('dir \\DCIM\\100SIGMA'))}
    before=listing();sh('key CAPTUREON');time.sleep(.1);sh('key CAPTUREOFF')
    for _ in range(8):
        time.sleep(1);now=listing();new=set(now)-set(before)
        if new:break
    else:raise RuntimeError('no capture appeared; do not repeat key')
    n=max(new);time.sleep(.5);size=listing()[n]
    out=OUT/f'{tag}-SS{n:04d}.jpg'
    r=subprocess.run([sys.executable,'-B',str(SHELL/'getfile.py'),f'\\DCIM\\100SIGMA\\SS__{n:04d}.JPG',str(out),'--size',str(size)],capture_output=True,text=True)
    (OUT/f'{tag}-capture.txt').write_text(r.stdout+r.stderr)
    if r.returncode:raise RuntimeError('capture read failed')
    return str(out)

def reboot():
    old=words(0xC072F6F8)[0]
    answer=pf.sh('poff 2',retries=0);time.sleep(4)
    # The old USB device has intentionally gone away. Close its one daemon,
    # then open the new device once. No code/DMA is freed by this host action.
    quit_reply=pf.mem_line('QUIT',timeout=3);time.sleep(1)
    proc=subprocess.Popen([str(SHELL/'fpshd')],cwd=SHELL,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    time.sleep(2)
    status=pf.mem_line('STATUS',timeout=3)
    if 'quarantine=0' not in status:raise RuntimeError(status)
    for attempt in range(20):
        answer_idle=pf.sh('status get is_recording',retries=0)
        if answer_idle.strip()=='is_recording -> 0':break
        if 'quarantine=1' in answer_idle:raise RuntimeError(answer_idle)
        time.sleep(1)
    else:raise RuntimeError('USB did not return; no reboot replayed')
    new=words(0xC072F6F8)[0]
    if new==old:raise RuntimeError('new boot not established')
    return {'old_boot':old,'new_boot':new,'reply':answer,'quit':quit_reply,'daemon_pid':proc.pid,'status':status,'retained_dram':bool(words(0x2D000280)[0]&1)}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['snapshot','key','shot','loadlog','reboot']);ap.add_argument('value',nargs='?',default='trial');a=ap.parse_args()
    idle();record={'time':time.time(),'action':a.action,'value':a.value}
    try:
        if a.action=='key':
            if a.value not in ['MENU','UP','DOWN','LEFT','RIGHT','OK','DISP']:raise RuntimeError('key refused')
            record['reply']=sh('key '+a.value+'ON');time.sleep(.8)
        elif a.action=='shot':record['file']=shot(a.value)
        elif a.action=='loadlog':record['log']=loadlog(a.value)
        elif a.action=='reboot':record['reboot']=reboot()
        record['snapshot']=snapshot()
    except Exception as error:
        record['error']=str(error);raise
    finally:
        with (OUT/'trial.jsonl').open('a') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')
        print(json.dumps(record,ensure_ascii=False,indent=2),flush=True)
