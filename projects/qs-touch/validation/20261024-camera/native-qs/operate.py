"""Scoped operations for the user's native-QS camera trial.

No backup, recording, loader replacement, media deletion or test-page opening.
Run only the requested action; non-idempotent actions are never retried here.
"""
from pathlib import Path
import argparse
import contextlib
import hashlib
import io
import json
import re
import struct
import sys
import time

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[4]
CARD=ROOT/'projects/qs-touch/cards/native-qs-v0.2.0test-20261024'
OLD=ROOT/'projects/qs-touch/cards/qstouch-v0.1.4test-input-relay-20261024'
sys.path.insert(0,str(OUT.parent))
import trial as T
pf=T.pf
original_sh=pf.sh

def bounded(command,**kw):
    if command.startswith(('echo','key ','poff ','fl ')):kw['retries']=0
    return original_sh(command,**kw)
pf.sh=bounded


def save(name,value):
    (OUT/(name+'.json')).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(value,indent=2,ensure_ascii=False),flush=True)


def read(remote,target,size):
    import getfile
    getfile.sh=bounded
    before=sys.argv
    try:
        sys.argv=['getfile.py',remote,str(target),'--size',str(size)]
        log=io.StringIO()
        try:
            with contextlib.redirect_stdout(log):assert getfile.main()==0
        finally:(OUT/(target.name+'.read.log')).write_text(log.getvalue())
    finally:sys.argv=before
    return target.read_bytes()


def status():
    host=pf.mem_line('STATUS',timeout=3)
    if 'quarantine=0' not in host:raise RuntimeError(host)
    T.idle()
    result={'time':time.time(),'host':host,'boot':T.words(0xC072F6F8)[0],
            'touch':T.words(0xC0CFCCDC)[0],'echo':T.words(0xC0BAC2F8)[0]}
    for c in ('status get app_current','gui geti QSN_Active','gui geti QS_FocusPos',
              'gui geti CM_DCCrop','gui geti MV_RecordingFormat','gui geti MV_Resolution','gui geti MV_FrameRate'):
        result[c]=T.sh(c)
    return result


def old_owner():
    blob=(OLD/'fpSup/QSTOUCH.BIN').read_bytes();info=json.loads((OLD/'build.json').read_text())
    base=T.words(0xC0CFCCDC)[0]-info['functions']['touch_observer']
    assert T.words(base,16)==list(struct.unpack_from('<16I',blob)), 'old QS test not the live owner'
    state=T.words(base+info['state_off'],9);assert state[0]==0x31545351
    svc=state[7];table=T.words(svc,25)
    assert table[0]==6 and all(svc-0x10000<=table[k]<svc for k in (21,22))
    assert T.words(0xC0BAC2F8)[0]==0xC03D99A0
    import callfn
    ok,disabled=callfn.call(table[21],r0=svc,r1=0x5A504154);assert ok
    before=disabled
    if not disabled:
        # Existing user authorization: pause Tap to Zoom for this touch trial,
        # then restore it when testing ends. Use the native loader service.
        T.idle()
        ok,result=callfn.call(table[22],r0=svc,r1=0x5A504154,r2=1)
        assert ok and result==0,'native Tap to Zoom pause did not return success'
        ok,disabled=callfn.call(table[21],r0=svc,r1=0x5A504154);assert ok
    assert disabled==1,'Tap to Zoom pause could not be verified'
    return dict(base=base,svc=svc,tapz_before=before,tapz_disabled=disabled,
                restore_after_trial=True,boot=T.words(0xC072F6F8)[0])


def deploy():
    T.idle()
    verification=json.loads((CARD/'verification.json').read_text())
    assert verification['skipped']==0 and len(verification['checks'])==6
    owner=old_owner();save('owner-before',owner)
    read('\\fpSup\\LOAD.LOG',OUT/'load-before.LOG',4096)
    local=CARD/'fpSup/ZQS.BIN';blob=local.read_bytes()
    meta=json.loads((CARD/'build.json').read_text())
    assert hashlib.sha256(blob).hexdigest()==meta['files']['fpSup/ZQS.BIN']['sha256']
    assert pf.remote_file_size('\\fpSup\\ZQS.BIN') is None,'existing ZQS requires inspection first'
    assert pf.remote_file_size('\\fpSup\\QSTOUCH.BIN')==(OLD/'fpSup/QSTOUCH.BIN').stat().st_size
    T.idle();before=sys.argv
    try:
        sys.argv=['putfile.py',str(local),'\\fpSup\\ZQS.BIN'];log=io.StringIO()
        try:
            with contextlib.redirect_stdout(log):assert pf.main()==0
        finally:(OUT/'write.log').write_text(log.getvalue())
    finally:sys.argv=before
    actual=read('\\fpSup\\ZQS.BIN',OUT/'readback-ZQS.BIN',len(blob))
    assert actual==blob,'full card readback mismatch'
    T.idle();assert T.words(0xC072F6F8)[0]==owner['boot'],'boot changed during transfer'
    assert pf.delete_file('\\fpSup\\QSTOUCH.BIN')
    assert pf.remote_file_size('\\fpSup\\QSTOUCH.BIN') is None
    save('deployment',dict(bytes=len(actual),sha256=hashlib.sha256(actual).hexdigest(),
         old_test_removed=True,loader_replaced=False,autorun_replaced=False,additional_backup=False,
         boot_before_reboot=owner['boot']))


def loaded():
    T.idle();raw=read('\\fpSup\\LOAD.LOG',OUT/'load-after.LOG',4096)
    text=raw.rstrip(b'\0 ').decode()
    m=re.search(r'^0A ([0-9A-F]{8}) 00000003 ZQS\.BIN$',text,re.M)
    assert m,'native QS did not install all three claims: '+text
    assert 'QSTOUCH.BIN' not in text and re.search(r'^13 5A504154 00000000 TAPZ\.BIN$',text,re.M)
    base=int(m[1],16);meta=json.loads((CARD/'build.json').read_text());blob=(CARD/'fpSup/ZQS.BIN').read_bytes()
    assert T.words(base,16)==list(struct.unpack_from('<16I',blob))
    assert T.words(0xC0CFCCDC)[0]==base+meta['functions']['observer']
    state=T.words(base+meta['state_off'],48)
    assert state[0]==0x314E5351 and state[2]==1
    result=dict(base=base,boot=T.words(0xC072F6F8)[0],state=state,log=text)
    save('loaded',result);return result


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['status','deploy','reboot','loaded']);a=ap.parse_args()
    if a.action=='status':save('status',status())
    if a.action=='deploy':deploy()
    if a.action=='reboot':
        d=json.loads((OUT/'deployment.json').read_text());T.idle()
        assert T.words(0xC072F6F8)[0]==d['boot_before_reboot'],'already rebooted; inspect instead'
        save('reboot',T.reboot())
    if a.action=='loaded':loaded()
