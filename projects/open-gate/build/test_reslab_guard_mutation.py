"""An isolated no-guard ARM build must fail the producer rejection test."""
import hashlib,json,pathlib,shutil,tempfile
import build_v3_reslab as B
import test_virtual_rcd as V
import test_reslab_formula_guards as G
import test_reslab_preview_route as P

def run(report, transition=False):
    good,f=V.built();original=B.compile_unit;keep=B.HERE
    with tempfile.TemporaryDirectory(prefix='reslab-guard-mutation-') as tmp:
        root=pathlib.Path(tmp);source=root/'source';source.mkdir()
        src=(keep/'rl_v3.c').read_text();seam=('    if (m->bin_h==1u && m->bin_v==1u && ph!=pv) return 0;' if transition else
                                                  '    if (!rl_canvas_safe(m)) return 0;')
        assert src.count(seam)==1
        (source/'rl_v3.c').write_text(src.replace(seam,'    /* isolated test: validation removed */'))
        def altered(*args,**kwargs):
            B.HERE=source
            try:return original(*args,**kwargs)
            finally:B.HERE=keep
        B.compile_unit=altered
        try:blob,mf=B.build(root,virtual=True)
        finally:B.compile_unit=original
        card=root/'card';shutil.copytree(good,card)
        (card/'fpSup/50RESLAB.BIN').write_bytes(blob);mf['rescustom']=f['rescustom']
        (card/'build.json').write_text(json.dumps({'sha256':hashlib.sha256(blob).hexdigest(),'facts':mf}))
        V.CARD=(card,mf)
        try:
            if transition:P.PreviewRouteTests('test_m12_r78_geometry_survives_virtual_rcd_and_native_selection').test_m12_r78_geometry_survives_virtual_rcd_and_native_selection()
            else:G.run(root/'must-not-pass.json')
        except AssertionError as e:detected=str(e)
        else:raise AssertionError('The missing producer guard was not detected')
    proof={'mutation':('skip no-bin isotropic preview guard' if transition else 'skip rl_canvas_safe in the real ARM encoder'),'detected':True,
           'failing_case':detected,'artifact_retained':False,'passed':True}
    pathlib.Path(report).write_text(json.dumps(proof,indent=2)+'\n');print(proof)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--report',required=True);p.add_argument('--transition',action='store_true')
    args=p.parse_args();run(args.report,args.transition)
