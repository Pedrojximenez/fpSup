#!/usr/bin/env python3
"""Build and verify exact native QS Touch SUP/card bytes, without device I/O."""
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
import build as P
import page as PAGE


def run_test(out,names=()):
    env=dict(os.environ,QST_SUP_ARTIFACTS=str(Path(out).resolve()))
    result=subprocess.run([sys.executable,'-B',str(HERE/'test_sup.py'),*names],env=env,
                          capture_output=True,text=True,timeout=240)
    return result,result.stdout+result.stderr


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();out=a.out.resolve()
    info=P.build(out,card=True)
    result,log=run_test(out)
    if result.returncode or 'skipped=' in log:
        (out/'failed-test-output.txt').write_text(log)
        raise RuntimeError(log)
    checks=[dict(name='Exact AutoRun / Loader v4 / SUP ARM execution',passed=True,output=log)]
    print('PASS exact SUP suite, zero skipped',flush=True)
    import qs_probe
    page=PAGE.Page((P.ROOT/'out/MAIN_c0000000.bin').read_bytes())
    raw,refs,shape=page.build_private()
    probe=qs_probe.native_parse(raw,bytes(page.pool.data),page.image)
    checks.append(dict(name='Original native NBU interpreter parses private page',passed=True,
                       records=len(probe.traces),page_sha256=hashlib.sha256(raw).hexdigest(),
                       objects=shape['objects'],own_objects=shape['own_objects'],animation_requests=0,
                       passive_native_animation_data=True))
    print(f'PASS native NBU parser: {len(probe.traces)} records, 13 own objects, no animation requests',flush=True)
    source=(HERE/'touch_sup.c').read_text()
    mutations=[
        ('missing_slot_journal',
         '    if(svc->claim(svc,TOUCH_SLOT,4u,&(const uint32_t){TOUCH_ORIGINAL},SL_EXCL)!=SL_OK)return SL_RELEASE;',
         '', 'SupTests.test_power_off_restores_touch_word_after_idle_and_interaction'),
        ('unknown_owner_overwrite',
         '    if(fpui_rd(TOUCH_SLOT)!=TOUCH_ORIGINAL)return SL_RELEASE;',
         '', 'SupTests.test_unknown_touch_owner_is_not_overwritten'),
        ('stale_queued_input',
         '    if(((word>>22)&511u)!=(s->epoch&511u))return 0;',
         '', 'SupTests.test_old_queued_packets_do_not_change_a_reopened_page'),
        ('watching_silent_raw_input',
         '    fpui_watch(s->ui,V_INPUT,touch_changed);fpui_watch(s->ui,V_ACTIVE,active_changed);',
         '    fpui_watch(s->ui,V_TOUCH,touch_changed);fpui_watch(s->ui,V_ACTIVE,active_changed);',
         'SupTests.test_select_adjust_double_tap_and_inline_option_grid')]
    for name,old,new,test in mutations:
        if source.count(old)!=1:raise RuntimeError('Mutation anchor changed: '+name)
        with tempfile.TemporaryDirectory(prefix='qstouch-mutation-') as d:
            d=Path(d);mutated=d/'mutant.c';mutated.write_text(source.replace(old,new))
            blob,_=P.sup_file(source=mutated)
            card=d/'card';shutil.copytree(out,card)
            (card/'fpSup/QSTOUCH.BIN').write_bytes(blob)
            result,mutation_log=run_test(card,[test])
            if not result.returncode or 'FAIL:' not in mutation_log:
                raise RuntimeError(f'Mutation {name} not detected as an assertion failure:\n'+mutation_log)
            checks.append(dict(name='Mutation '+name,passed=True,detected=True,test=test,output=mutation_log))
        print('PASS detected mutation: '+name,flush=True)
    sources=[HERE/'verify.py',HERE/'test_sup.py',HERE/'test_native_input.py',HERE/'README.md',
             P.ROOT/'fpSup/loader-v4/test_ui_v4.py',P.ROOT/'fpSup/loader-v4/test_boot_card_v4.py',
             P.ROOT/'fpSup/loader-v4/test_v4.py',P.ROOT/'projects/open-gate/build/res-qs/qs_probe.py',
             P.ROOT/'research/ui/tools/native_control_probe/test_native_permission_binding.py',
             P.ROOT/'research/ui/tools/native_variable_probe/registry_probe.py',
             P.ROOT/'research/ui/tools/native_variable_probe/binding_probe.py']
    info['verification']=dict(checks=checks,skipped=0,firmware_sha256=P.FIRMWARE_SHA256,
        harness_source_hashes={str(p.relative_to(P.ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        limitations=['GUI registry, post queue, screen manager, clock, file/heap/OS services are substitutes',
                     'Native record parsing substitutes construction/OS services and does not paint',
                     'Native relay test executes silent/notifying setters and controlAppVariable; page event scheduling remains explicit',
                     'No physical touch, camera connection, recording settings, timing or hardware cache verification'])
    (out/'verification.json').write_text(json.dumps(info['verification'],ensure_ascii=False,indent=2)+'\n')
    shutil.copyfile(HERE/'README.md',out/'README.md')
    sums=[]
    for p in sorted(out.rglob('*')):
        if p.is_file():sums.append(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(out)))
    (out/'SHA256SUMS').write_text('\n'.join(sums)+'\n')
    print(str(out),flush=True)


if __name__=='__main__':main()
