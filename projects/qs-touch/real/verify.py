#!/usr/bin/env python3
"""Build and check native QS SUP bytes offline. No USB operations."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import build as B


def run(script,out,names=()):
    result=subprocess.run([sys.executable,'-B',str(HERE/script),*names],
        env=dict(os.environ,QSN_ARTIFACTS=str(out.resolve())),capture_output=True,text=True,timeout=180)
    return result,result.stdout+result.stderr


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();out=a.out.resolve();info=B.build(out,card=True);checks=[]
    for script in ('test_sup.py','test_settings.py','test_page.py'):
        result,log=run(script,out);(out/(script+'.log')).write_text(log)
        if result.returncode or 'skipped=' in log:raise RuntimeError(log)
        checks.append(dict(name=script,passed=True,output=log))
        print('PASS '+script,flush=True)
    source=(HERE/'native.c').read_text()
    mutations=[
        ('missing_touch_journal',
         '    if(svc->claim(svc,TOUCH_SLOT,4,&(const uint32_t){TOUCH_STOCK},SL_EXCL)!=SL_OK)return SL_RELEASE;',
         '', 'NativeSupTests.test_idle_and_interaction_power_off_restore_all_three_words'),
        ('unknown_touch_owner',
         '    if(fpui_rd(TOUCH_SLOT)!=TOUCH_STOCK)return SL_RELEASE;',
         '', 'NativeSupTests.test_unknown_touch_owner_is_left_alone'),
        ('wrong_original_record_position',
         'poke(reader+4,pos+p[k].old_len);return result;',
         'poke(reader+4,pos+p[k].len);return result;',
         'NativeSupTests.test_sparse_arm_stream_preserves_original_coordinates')]
    for name,old,new,test in mutations:
        assert source.count(old)==1,name
        with tempfile.TemporaryDirectory(prefix='qsn-mutation-') as temp:
            temp=Path(temp);mutant=temp/'native.c';mutant.write_text(source.replace(old,new))
            blob,_=B.sup_file(mutant);card=temp/'card';shutil.copytree(out,card)
            (card/'fpSup/ZQS.BIN').write_bytes(blob)
            result,log=run('test_sup.py',card,[test])
            (out/(name+'.log')).write_text(log)
            if not result.returncode or 'FAIL:' not in log:raise RuntimeError('Mutation not caught: '+name+'\n'+log)
            checks.append(dict(name=name,detected=True,test=test,output=log))
        print('PASS detected '+name,flush=True)
    report=dict(checks=checks,skipped=0,physical_touch_verified=False,camera_verified=False,
        limitations=['Native NBU construction, GUI scheduling, heap/OS/file services use explicit substitutes',
                     'No display painting, camera cache lifetime, physical touch, hardware timing or recording test',
                     'First native candidate has limited labels/features; see README.md'],
        harness_sources={str(p.relative_to(B.ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [HERE/'verify.py',HERE/'test_sup.py',HERE/'test_settings.py',HERE/'test_page.py',HERE/'README.md']})
    (out/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    shutil.copyfile(HERE/'README.md',out/'README.md')
    (out/'SHA256SUMS').write_text('\n'.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(out))
        for p in sorted(out.rglob('*')) if p.is_file())+'\n')
    print(out,flush=True)


if __name__=='__main__':main()
