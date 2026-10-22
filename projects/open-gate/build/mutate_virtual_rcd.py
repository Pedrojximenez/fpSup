#!/usr/bin/env python3
"""Build isolated consumer mutations and require functional assertions.
The producer, shared loader and AutoRun are the exact saved baseline bytes.
"""
import argparse,hashlib,io,json,pathlib,shutil,tempfile,unittest
import test_virtual_rcd as V
import build_v3_rescustom as B

MUTATIONS=(
    ('recording-guard','ogc.c','if (B8(sel)) return R_MOVREC;','if (B8(sel)) return 0;',
     'test_recording_guards_preserve_active_recipe'),
    ('rcd-checksum','ogc_virtual.c','if (rc) return vrc_finish(v,VRC_BAD_RCD,rc);',
     '(void)rc; /* mutation: accept a damaged recipe */',
     'test_bad_checksum_rejected_without_changing_active_tables'),
)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--card',type=pathlib.Path,required=True)
    ap.add_argument('--out',type=pathlib.Path,required=True)
    a=ap.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    facts=json.loads((a.card/'build.json').read_text())['facts'];results=[]
    original=B.HERE
    for name,filename,before,after,test in MUTATIONS:
        with tempfile.TemporaryDirectory(prefix='vrc-mutation-') as d:
            root=pathlib.Path(d);source=root/'source';source.mkdir()
            for f in ('ogc.c','ogc_virtual.c','ogc_shims.S','virtual_rcd.h'):
                shutil.copy2(original/f,source/f)
            for f in original.glob('*.py'):(source/f.name).symlink_to(f)
            p=source/filename;text=p.read_text()
            assert text.count(before)==1,(name,'mutation seam')
            p.write_text(text.replace(before,after))
            build=root/'build';build.mkdir()
            try:
                B.HERE=source
                core,cf,_=B.build_core(build,virtual=True)
            finally:B.HERE=original
            card=root/'card';shutil.copytree(a.card,card)
            (card/'fpSup/32RESCUS.BIN').write_bytes(core)
            f=dict(facts,rescustom=cf);V.CARD=(card,f)
            log=io.StringIO()
            result=unittest.TextTestRunner(stream=log,verbosity=2).run(
                unittest.TestSuite([V.VirtualTests(test)]))
            (a.out/f'{name}.log').write_text(log.getvalue())
            assert result.testsRun==1 and result.failures and not result.errors and not result.skipped,log.getvalue()
            results.append(dict(name=name,test=test,detected='assertion',failures=len(result.failures),
                                errors=0,sha256=hashlib.sha256(core).hexdigest()))
            print(f'PASS mutation {name}: functional assertion, no emulator error',flush=True)
    (a.out/'mutations.json').write_text(json.dumps(results,indent=2)+'\n')

if __name__=='__main__':main()
