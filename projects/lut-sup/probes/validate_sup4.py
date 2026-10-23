#!/usr/bin/env python3
"""Freeze a local LUT4 development card, exact-byte tests and ARM comparisons.

No camera/device I/O or website publication. Mutants live only in temporary
copies, never in the shared production source. Missing/skipped tests fail.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT=Path(__file__).resolve().parents[3]
LIB=ROOT/'fpSup/lut'
sys.path.insert(0,str(LIB))
import build_sup as P
import test_sup_native as N
import test_sup_ui as U
from cinemadng import COLOR_SPACES,COMMON_GAMMAS
from color import source_to_xyz
from cube import Cube
from monitor import Monitor
from test_lut import make_cube


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value): path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


MUTANTS=[
    ('allow_preview_without_backend','on?NO_BACKEND:OK','OK',
     'test_loads_cached_with_resident_rows_and_dma_only_file_scratch'),
    ('skip_asset_checksum','hash((const u8 *)a,next)!=a->checksum','0',
     'test_missing_short_corrupt_trailing_and_corrupt_header_remain_unapplied'),
    ('execute_pending_model','if(!supported(s->color,s->gamma)) return s->last_error=MODEL_PENDING;',
     'if(0) return s->last_error=MODEL_PENDING;',
     'test_bad_input_never_changes_destination_and_pending_models_refuse'),
    ('accept_out_of_contract_xyz','xyz[i*3+c]>64*Q','xyz[i*3+c]>127*Q',
     'test_bad_input_never_changes_destination_and_pending_models_refuse'),
    ('reverse_red_blue_table_order','((idx[2]*n+idx[1])*n+idx[0])*3','((idx[0]*n+idx[1])*n+idx[2])*3',
     'test_all_35_models_against_float_reference_and_strengths'),
    ('skip_dependent_ui_refresh','choices(s);\n    if(s->file_status','/* isolated stale choices */\n    if(s->file_status',
     'test_group_popup_refreshes_the_dependent_value_immediately'),
]


def mutations(out):
    original=P.SOURCE.read_text()
    results=[]
    with tempfile.TemporaryDirectory(prefix='lut4-mutants-') as td:
        folder=Path(td)
        (folder/'lut4.h').write_bytes((LIB/'native/lut4.h').read_bytes())
        for name,before,after,test in MUTANTS:
            if original.count(before)!=1: raise RuntimeError('mutation target moved: '+name)
            path=folder/(name+'.c')
            path.write_text(original.replace(before,after,1))
            P.build_sup(path)                   # a compiler error is NOT detection
            N.MUTANT_SOURCE=path
            stream=io.StringIO()
            module,cls=(U,'LutUiTests') if name=='skip_dependent_ui_refresh' else (N,'NativeLutTests')
            suite=unittest.defaultTestLoader.loadTestsFromName(cls+'.'+test,module)
            result=unittest.TextTestRunner(stream=stream,verbosity=2,failfast=True).run(suite)
            (out/(name+'.txt')).write_text(stream.getvalue())
            detected=bool(result.failures) and not result.errors and not result.skipped
            record=dict(name=name,compiled=True,detected=detected,test=test,source_sha256=sha(path))
            results.append(record)
            print('mutation',name,'detected' if detected else 'FAILED',flush=True)
            if not detected: raise RuntimeError('undetected/invalid mutation: '+name)
    N.MUTANT_SOURCE=None
    return results


def private_ui_mutation(out):
    """Prove the LUT/private-page integration test rejects unborrowed strings."""
    library=P.B.FPSUP_UI
    original=(library/'fpsup_ui.c').read_text()
    before='if (svc->borrow(svc, b, b + t->file_len) != SL_OK) return 9;'
    if original.count(before)!=1: raise RuntimeError('private UI borrow mutation target moved')
    test='LutUiTests.test_private_home_and_manager_strings_resolve_and_stay_borrowed_with_lut'
    with tempfile.TemporaryDirectory(prefix='color-private-ui-mutant-') as td:
        directory=Path(td)
        path=directory/'fpsup_ui.c'
        path.write_text(original.replace(before,'(void)svc; /* isolated missing borrow */',1))
        stream=io.StringIO()
        try:
            P.B.FPSUP_UI=directory
            P.B.loader_bin(ui=True);P.B.supmgr_sup()
            suite=unittest.defaultTestLoader.loadTestsFromName(test,U)
            result=unittest.TextTestRunner(stream=stream,verbosity=2,failfast=True).run(suite)
        finally:
            P.B.FPSUP_UI=library
        (out/'skip_private_string_borrow.txt').write_text(stream.getvalue())
        detected=bool(result.failures) and not result.errors and not result.skipped
        record=dict(name='skip_private_string_borrow',compiled=True,detected=detected,test=test,
                    source_sha256=sha(path),original_source_sha256=sha(library/'fpsup_ui.c'))
    if not detected: raise RuntimeError('private string borrow mutation was not detected')
    print('mutation skip_private_string_borrow detected',flush=True)
    return record


def numerical(out,sup):
    cube=Cube.parse(make_cube(17,fn=lambda r,g,b:(r*g+.03*b,.2*r+.6*g+.2*b,b*b-.04*r),
                             headers='TITLE "LUT4 cross-channel numerical fixture"\n'))
    (out/'cross-channel.cube').write_bytes(cube.source)
    prepared=P.asset(cube)
    (out/'cross-channel.LUT').write_bytes(prepared)
    cam=N.Camera(sup,prepared)
    rng=np.random.default_rng(0x4c555434)
    rgb=np.concatenate([rng.uniform(-.02,2,(128,3)),
                        np.repeat((.18*2**np.linspace(-10,6,33))[:,None],3,axis=1)])
    xyz=source_to_xyz(rgb,'linear-709')
    expected=[]; native=[]; models=[]; errors=[]
    for ci,color in enumerate(COLOR_SPACES):
        if color=='blackmagic-design': continue
        for gi,gamma in enumerate(COMMON_GAMMAS):
            if gamma=='rec709': continue
            assert cam.invoke(3,ci,gi)==0
            rc,actual=cam.render(xyz)
            if rc: raise RuntimeError('ARM reference rejected bounded samples')
            reference,_=Monitor(cube,color,input_gamma=gamma).evaluate_xyz(xyz)
            difference=np.abs(actual-reference)
            record=dict(color=color,gamma=gamma,samples=len(xyz),rgb_mae=float(difference.mean()),
                        max_channel=float(difference.max()))
            if record['max_channel']>.0005: raise RuntimeError('native/reference error exceeds 0.0005 code')
            models.append(dict(color=color,gamma=gamma)); errors.append(record)
            expected.append(reference); native.append(actual)
    np.save(out/'xyz_d65_f64.npy',xyz,allow_pickle=False)
    np.save(out/'reference_709_f64.npy',np.array(expected),allow_pickle=False)
    np.save(out/'native_709_f64.npy',np.array(native),allow_pickle=False)
    save(out/'models.json',models)
    return dict(models=len(models),samples_per_model=len(xyz),comparisons=len(models)*len(xyz),
                rgb_mae=float(np.abs(np.array(native)-expected).mean()),
                max_channel=float(max(e['max_channel'] for e in errors)),per_model=errors,
                metric='normalized Rec.709 Gamma2.4 channel code error; not DeltaE',
                includes_xyz_matrix_curve_node_and_interpolation_quantization=True,
                resolve_pixel_match_verified=False,camera_pixels=False)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('output',type=Path,help='new validation directory')
    ap.add_argument('--card-dir',required=True,type=Path,help='new local development card directory')
    a=ap.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    info=P.build(a.card_dir,card=True,debug=True)
    stream=io.StringIO()
    suite=unittest.defaultTestLoader.loadTestsFromNames(
        ['test_sup_native','test_sup_ui','test_fp4','test_cinemadng','test_monitor','test_lut',
         'test_preview','test_residual',
         'test_ui_v4.HomePageTests.test_stock_lookups_keep_the_firmware_rule',
         'test_ui_v4.HomePageTests.test_private_strings_resolve_to_themselves',
         'test_ui_v4.HomePageTests.test_our_pointers_are_borrowed'])
    result=unittest.TextTestRunner(stream=stream,verbosity=2,failfast=True).run(suite)
    (a.output/'tests.txt').write_text(stream.getvalue())
    if not result.wasSuccessful() or result.skipped:
        raise RuntimeError('tests failed/skipped; see tests.txt')
    print('tests',result.testsRun,'passed; no skips',flush=True)
    mutation_results=mutations(a.output)
    mutation_results.append(private_ui_mutation(a.output))
    sup=(a.card_dir/'fpSup/LUT.BIN').read_bytes()
    numerical_results=numerical(a.output,sup)
    # Exercise the exact exported card again, not a fresh look-alike build.
    files=U.runtime_files(a.card_dir)
    cam=U.Camera(files,files['\\AutoRun.txt'])
    assert set(cam.loaded())=={'LUT.BIN','SUPMGR.BIN','SHELL.BIN'}
    assert cam.status()['asset']==0 and cam.status()['backend']==0
    assert cam.callsvc('page_count')==2
    assert U.U.ui_lines(cam)==[(0,0,'LOADER.BIN'),(0x100,2,'LOADER.BIN')]
    home_rows=cam.current_rows(False)
    assert set(home_rows)=={'Color','SupManager'}
    cam.open_color()
    assert cam.shown[-1][1]=='FT_COLOR'
    all_rows={title:cam.find_row(title)[1] for title in
              ('LUT color family','LUT color space','LUT file / status',
               'LUT gamma family','LUT gamma value','LUT monitoring','LUT strength range',
               'LUT strength value')}
    cam.choose('LUT monitoring',1)
    assert cam.status()['last']==-13
    assert cam.find_row('LUT monitoring')[1]['A']=='Off'
    ui_result=dict(install_log=U.U.ui_lines(cam),registered_rows=cam.callsvc('page_count'),
                   home_rows=home_rows,private_setting_rows=len(all_rows),private_page='FT_COLOR',
                   initial_row_values=all_rows,monitor_enable_result=cam.status()['last'],
                   monitor_after_enable_attempt=cam.find_row('LUT monitoring')[1]['A'],
                   page_renderer='real ARM core / fpsup-ui private FT4S data with simulated native GUI app',
                   on_camera_verified=False)
    cam.power_off_all()
    sources=[LIB/'native/lut4.c',LIB/'native/lut4.h',LIB/'native/color_ui.c',LIB/'color_ui.py',LIB/'build_sup.py',LIB/'test_sup_native.py',
             LIB/'test_sup_ui.py',P.B.FPSUP/'uishare/tab/test_fp4.py',
             LIB/'color.py',LIB/'cinemadng.py',LIB/'monitor.py',Path(__file__).resolve()]
    changed=[dict(path=path,built_sha256=expected,current_sha256=sha(ROOT/path))
             for path,expected in info['source_hashes'].items() if sha(ROOT/path)!=expected]
    if changed:
        save(a.output/'incomplete.json',dict(status='not accepted',tests=result.testsRun,skipped=0,
             mutations_detected=len(mutation_results),changed_sources=changed,
             reason='build sources changed during validation; rerun with consistent sources'))
        raise RuntimeError('build sources changed during validation; see incomplete.json')
    report=dict(schema='fpSup-lut4-validation-2',tests=result.testsRun,skipped=0,
                mutations=mutation_results,numerical=numerical_results,
                card_dir=str(a.card_dir.resolve()),exact_card_loaded=cam.loaded(),
                exact_card_ui=ui_result,
                native_status=cam.status(),resident_bytes=info['block_bytes'],
                file_hashes={str(p.relative_to(a.card_dir)):sha(p) for p in a.card_dir.rglob('*') if p.is_file()},
                source_hashes={str(p.relative_to(ROOT)):sha(p) for p in sources},
                build_source_hashes=info['source_hashes'],
                camera_operations=False,physical_card_written=False,on_camera_verified=False,
                live_view_backend_connected=False,ui_renderer_present=True,lut_ui_on_camera_verified=False,
                realtime_performance_verified=False,resolve_cinemadng_pixel_match_verified=False)
    save(a.output/'report.json',report)
    print(json.dumps(dict(tests=report['tests'],mutations_detected=len(mutation_results),
                         numerical_max_channel=numerical_results['max_channel'],
                         card=report['card_dir'],live_view_backend_connected=False),indent=2))


if __name__=='__main__': main()
