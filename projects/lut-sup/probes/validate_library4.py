#!/usr/bin/env python3
"""Local per-cube library delivery, actual ARM bytes and isolated fault copies.

All firmware file calls are simulated; no camera, physical card or publication.
"""
import argparse
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest

import validate_sup4 as V
import library as L
import test_library_native as D
import cube_metadata as CM

P=V.P
U=V.U
ROOT=V.ROOT
LIB=V.LIB

FAULTS=[
    ('ignore_existing_file_guard','if(!library_file_guard(s,io,buf))return SAVE_FAILED;',
     '(void)library_file_guard(s,io,buf);', 'test_missing_or_replaced_bin_is_not_created_or_overwritten'),
    ('ignore_write_readback','ok=pos==n;','ok=1;',
     'test_readback_failure_rolls_back_ram_and_does_not_replay'),
    ('ignore_asset_source_identity','if(rc==OK && !library_same(s->asset->source_sha256,e->sha,32))rc=BAD_ASSET;',
     '/* isolated missing source identity check */','test_wrong_asset_identity_does_not_replace_selected_lut'),
    ('ignore_recording_guard','static int library_busy(void) {','static int library_busy(void) { return 0;',
     'test_recording_blocks_file_loads_and_settings_writes'),
    ('write_first_cube_instead_of_selected','*e=&s->library->entries[index],before;',
     '*e=&s->library->entries[0],before;','test_editing_one_cube_does_not_change_other_or_current_active'),
    ('keep_incomplete_active_selection','if(s->library->h.active==index && (flags&7u)!=7u)s->library->h.active=LIB_NONE;',
     '/* isolated invalid active input */','test_active_input_becoming_incomplete_saves_off_and_reloads_validly'),
]

COMMENT_FAULTS=[
    ('ignore_cube_source_guard','if(cube_read(s,index,1,expected,&old)!=OK)return SAVE_FAILED;',
     '(void)cube_read(s,index,1,expected,&old);','test_cube_missing_replaced_body_or_header_is_not_written'),
    ('ignore_cube_body_checksum',' || h!=e->source_hash','',
     'test_cube_missing_replaced_body_or_header_is_not_written'),
    ('ignore_cube_comment_readback','ok=got==CUBE_HEADER && library_same(buf,expected,CUBE_HEADER);',
     'ok=got==CUBE_HEADER;','test_cube_readback_failure_keeps_ram_and_refuses_replay'),
    ('ignore_saved_cube_comments','if(rc==OK){e->color=current.color;e->gamma=current.gamma;e->flags=current.flags;}',
     'if(rc==OK){ /* isolated stale BIN cache */ }','test_input_writes_cube_comments_and_fresh_import_uses_them'),
]


def mutations(out):
    original=(LIB/'native/library4.c').read_text();results=[]
    with tempfile.TemporaryDirectory(prefix='lut-library-faults-') as td:
        folder=Path(td);source=folder/'lut4.c';source.write_bytes(P.SOURCE.read_bytes())
        for name,before,after,test in FAULTS:
            if original.count(before)!=1:raise RuntimeError('fault target moved: '+name)
            path=folder/'library4.c';path.write_text(original.replace(before,after,1))
            P.build_sup(source)  # Compilation errors do not count as detected behavior.
            D.MUTANT_SOURCE=source;stream=io.StringIO()
            try:
                suite=unittest.defaultTestLoader.loadTestsFromName('LibraryNativeTests.'+test,D)
                result=unittest.TextTestRunner(stream=stream,verbosity=2,failfast=True).run(suite)
            finally:D.MUTANT_SOURCE=None
            (out/(name+'.txt')).write_text(stream.getvalue())
            detected=bool(result.failures) and not result.errors and not result.skipped
            results.append(dict(name=name,compiled=True,detected=detected,test=test,
                                source_sha256=V.sha(path)))
            print('library fault',name,'detected' if detected else 'FAILED',flush=True)
            if not detected:raise RuntimeError('undetected/invalid library fault: '+name)
    return results


def comment_mutations(out):
    original=(LIB/'native/cube4.c').read_text();results=[]
    with tempfile.TemporaryDirectory(prefix='cube-comment-faults-') as td:
        folder=Path(td);source=folder/'lut4.c';source.write_bytes(P.SOURCE.read_bytes())
        (folder/'library4.c').write_bytes((LIB/'native/library4.c').read_bytes())
        for name,before,after,test in COMMENT_FAULTS:
            if original.count(before)!=1:raise RuntimeError('comment fault target moved: '+name)
            path=folder/'cube4.c';path.write_text(original.replace(before,after,1))
            P.build_sup(source)
            D.MUTANT_SOURCE=source;stream=io.StringIO()
            try:
                suite=unittest.defaultTestLoader.loadTestsFromName('LibraryNativeTests.'+test,D)
                result=unittest.TextTestRunner(stream=stream,verbosity=2,failfast=True).run(suite)
            finally:D.MUTANT_SOURCE=None
            (out/(name+'.txt')).write_text(stream.getvalue())
            detected=bool(result.failures) and not result.errors and not result.skipped
            results.append(dict(name=name,compiled=True,detected=detected,test=test,source_sha256=V.sha(path)))
            print('comment fault',name,'detected' if detected else 'FAILED',flush=True)
            if not detected:raise RuntimeError('undetected/invalid comment fault: '+name)
    return results


def demo(folder):
    folder.mkdir()
    paths=[]
    for name,color,gamma,scale in [('Demo_709.cube','rec709','gamma24',1),
                                  ('Demo_P3.cube','p3-d65','gamma26',.7),
                                  ('Unmarked_709.cube',None,None,.8)]:
        path=folder/name
        tags=f'# FPSUP_INPUT_COLOR_SPACE {color}\n# FPSUP_INPUT_GAMMA {gamma}\n' if color else ''
        path.write_bytes((tags+f'TITLE "Diagnostic only: {name}"\n').encode()+
                         V.make_cube(2,fn=lambda r,g,b:(scale*r,scale*g,scale*b)))
        paths.append(path)
    doc=L.import_cubes(L.blank(),paths)
    doc=L.configure(doc,'Demo_709.cube',enabled=True,active=True)
    doc=L.configure(doc,'Demo_P3.cube',enabled=True)
    L.save(folder/'library.json',doc)
    return doc


def exact_card(card,doc):
    files=U.runtime_files(card);cam=D.Camera(files,files['\\AutoRun.txt'])
    assert set(cam.loaded())=={'LUT.BIN','SUPMGR.BIN','SHELL.BIN'}
    assert set(cam.current_rows(False))=={'Color','SupManager'}
    assert cam.callsvc('page_count')==2 and cam.status()['asset']==0
    assert U.U.ui_lines(cam)==[(0,0,'LOADER.BIN'),(0x100,2,'LOADER.BIN')]
    cam.open_color();home=cam.current_rows()
    assert set(home)=={'Active LUT','LUT manager','LUT monitoring'}
    cam.choose('LUT monitoring',1)
    assert cam.status()['last']==-13 and cam.find_row('LUT monitoring')[1]['A']=='Off'
    cam.jump('Active LUT');picker=cam.current_rows()
    assert set(picker)=={'Off','Demo_709.cube','Demo_P3.cube'}
    cam.jump('Demo_P3.cube');assert (cam.status()['color'],cam.status()['gamma'])==(4,2)
    cam.edit('Demo_709.cube');cam.choose('LUT strength range',0);cam.choose('LUT strength value',1)
    assert cam.status()['strength']==100  # editing another LUT leaves active P3 unchanged
    saved=L.recover(doc,cam.written[D.BIN]);assert L.resolved(saved['luts'][0])['strength_percent']==25
    source_path=cam.source_path(1);before=files[source_path]
    cam.edit('Demo_P3.cube');cam.choose('LUT color family',0);cam.choose('LUT color space',1)
    cam.choose('LUT gamma family',1);cam.choose('LUT gamma value',0)
    portable=cam.written[source_path]
    assert portable[CM.SIZE:]==before[CM.SIZE:] and CM.identity(portable)==doc['luts'][1]['id']
    source_settings=L.author_settings(V.Cube.parse(portable))
    assert (source_settings['input_space'],source_settings['input_gamma'])==('adobe-rgb','linear')
    again=D.Camera(cam.saved_files(),files['\\AutoRun.txt']);again.open_color()
    assert again.find_row('Active LUT')[1]['A']=='Demo_P3.cube'
    assert (again.status()['color'],again.status()['gamma'])==(1,3)
    again.jump('Active LUT');again.jump('Demo_709.cube');assert again.status()['strength']==25
    sites=(0xC056461C,0xC05E5B58,0xC05E61C8,0xC05E61E0)
    stock=[struct.unpack_from('<I',cam.img,a-0xc0000000)[0] for a in sites]
    cam.power_off_all();assert [cam.w(a) for a in sites]==stock
    previous=ROOT/'projects/lut-sup/cards/20261021-color-single-entry-01'
    shared=['AutoRun.txt','fpSup/LOADER.BIN','fpSup/SUPMGR.BIN','fpSup/UI/FPSUP.BIN','fpSup/UI/SUPMGR.BIN']
    unchanged={p:(card/p).read_bytes()==(previous/p).read_bytes() for p in shared}
    assert all(unchanged.values())
    return dict(loaded=cam.loaded(),home_rows=2,color_rows=3,enabled_picker=list(picker),
                private_pages=[name for name,_ in U.C.PAGES],
                monitoring_enable=-13,monitoring_after_attempt='Off',
                per_cube_saved_and_reloaded=True,disabled_cube_excluded=True,
                cube_comment_writeback_and_body_preservation=True,
                recording_and_source_guards_verified_by_native_tests=True,
                unchanged_shared_files=unchanged,power_off_shared_hooks_restored=True,
                file_calls_simulated=True,native_gui_display_simulated=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('output',type=Path)
    ap.add_argument('--card-dir',required=True,type=Path)
    a=ap.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    doc=demo(a.output/'demo-sources')
    info=P.build(a.card_dir,card=True,debug=True,collection=doc)
    stream=io.StringIO()
    suite=unittest.defaultTestLoader.loadTestsFromNames([
        'test_library','test_library_native','test_sup_native','test_sup_ui',
        'test_fp4','test_cinemadng','test_monitor','test_lut','test_preview','test_residual',
        'test_ui_v4.HomePageTests.test_stock_lookups_keep_the_firmware_rule',
        'test_ui_v4.HomePageTests.test_private_strings_resolve_to_themselves',
        'test_ui_v4.HomePageTests.test_our_pointers_are_borrowed'])
    result=unittest.TextTestRunner(stream=stream,verbosity=2,failfast=True).run(suite)
    (a.output/'tests.txt').write_text(stream.getvalue())
    if not result.wasSuccessful() or result.skipped:raise RuntimeError('tests failed/skipped; see tests.txt')
    print('tests',result.testsRun,'passed; no skips',flush=True)
    faults=V.mutations(a.output)+[V.private_ui_mutation(a.output)]+mutations(a.output)+comment_mutations(a.output)
    exact=exact_card(a.card_dir,doc)
    # The numerical fixture has its own source cube, using the same current
    # processing code in single-asset mode. It is not the exported demo library.
    reference,facts=P.build_sup();(a.output/'numerical-reference.BIN').write_bytes(reference)
    numerical=V.numerical(a.output,reference)
    numerical['separate_reference_payload_sha256']=P.sha(reference)
    numerical['exported_demo_library_is_not_numerical_fixture']=True
    changed=[path for path,expected in info['source_hashes'].items() if V.sha(ROOT/path)!=expected]
    if changed:raise RuntimeError('build sources changed during validation: '+repr(changed))
    report=dict(schema='fpSup-lut-library-validation-1',tests=result.testsRun,skipped=0,
        mutations=faults,numerical=numerical,exact_card=exact,library=L.summary(doc),
        card_dir=str(a.card_dir.resolve()),resident_bytes=info['block_bytes'],
        file_hashes={str(p.relative_to(a.card_dir)):V.sha(p) for p in a.card_dir.rglob('*') if p.is_file()},
        build_source_hashes=info['source_hashes'],
        validation_source_hashes={str(p.relative_to(ROOT)):V.sha(p) for p in
            [Path(__file__).resolve(),Path(V.__file__),LIB/'test_library.py',LIB/'test_library_native.py',LIB/'fplut.py']},
        camera_operations=False,physical_card_written=False,on_camera_verified=False,
        live_view_backend_connected=False,realtime_performance_verified=False,
        resolve_cinemadng_pixel_match_verified=False)
    V.save(a.output/'report.json',report)
    print(json.dumps(dict(tests=result.testsRun,mutations_detected=len(faults),
                         numerical_max_channel=numerical['max_channel'],card=report['card_dir']),indent=2))


if __name__=='__main__':main()
