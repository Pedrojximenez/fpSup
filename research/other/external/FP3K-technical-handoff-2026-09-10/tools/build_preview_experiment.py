"""Bind the preview3 resident and bounded trace into an isolated experiment."""
import hashlib
import json
import runpy
import shutil
from pathlib import Path
import build_preview_probe as probe

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT/'prototype/fp3k-0.3.5-preview3'
OUT = ROOT/'diagnostics/fullheight-preview-experiment-v3'

def configure():
    m=json.loads((PACKAGE/'manifest.json').read_text())
    probe.BASELINE=PACKAGE
    probe.RESIDENT_SHA=m['files']['FP3KMENU.BIN']['sha256']
    probe.AUTORUN_SHA=m['files']['AutoRun.txt']['sha256']
    probe.BASE=(0xc072de64+m['files']['FP3KMENU.BIN']['bytes']+15)&~15
    probe.OUT=OUT
    probe.STATE_BYTES=64
    return m

def build():
    m=configure()
    # This verifier builds the configured probe, bounds its writes and checks
    # idle-only saving, including late-stop and failure cases.
    runpy.run_path(str(ROOT/'tools/verify_preview_probe.py'),run_name='__main__')
    manifest=json.loads((OUT/'manifest.json').read_text())
    manifest['status']='Offline-tested preview geometry experiment; not installed'
    manifest['preview_experiment']=m['resident']['preview_experiment']
    manifest['baseline_version']=m['version']
    manifest['ranges']['0x7a0']='C0732000 +64 private state, including QS and display-fit diagnostics'
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for label in ('SD','SSD'):
        (ROOT/'diagnostics/fullheight-preview-experiment3-return'/label/'FP3KPV').mkdir(parents=True,exist_ok=True)
    for source in (ROOT/'tools').iterdir():
        if source.is_file() and source.suffix in ('.py','.S','.inc'):
            shutil.copy2(source,OUT/'sources'/source.name)
    for path in ('native-menu/resident-verification.json','native-ui/layout-ui-verification.json','native-menu/preview-output-verification.json','native-menu/preview-layout-verification.json'):
        source=ROOT/'prototype/development'/path
        assert source.exists(),source
        report=json.loads(source.read_text())
        digest=report.get('payload_sha256',report.get('sha256'))
        assert digest==probe.RESIDENT_SHA,(source,digest)
        shutil.copy2(source,OUT/source.name)
    shutil.copy2(PACKAGE/'package-verification.json',OUT/'package-verification.json')
    print(json.dumps({k:manifest[k] for k in ('status','probe_base','probe_bytes','autorun_sha256','baseline_resident_sha256')},indent=2))

if __name__=='__main__':build()
