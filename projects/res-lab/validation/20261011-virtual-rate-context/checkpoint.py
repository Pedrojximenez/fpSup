"""Copy this task's reviewable changes into its already-authorized private snapshot.

Never modifies the nested fpSup Git checkout. Large transient/capture files are
hashed into an evidence manifest; complete local originals remain untouched.
"""
from pathlib import Path
import hashlib,json,shutil,sys
ROOT=Path(__file__).resolve().parents[4]
DEST=Path('/private/tmp/reslab-m12-baseline-20261011-1329')
assert (DEST/'.git').is_dir() and (DEST/'SNAPSHOT.json').is_file()
source=[ROOT/'projects/open-gate/build'/p for p in (
 'res-custom/ogc.c','res-custom/ogc_layout.py','res-custom/ogc_shims.S',
 'res-custom/build_v3_rescustom.py','res-custom/rcd.py','test_reslab_record_rate.py','test_reslab_header_copy.py')]
folders=[ROOT/'projects/res-lab/cards'/p for p in ('20261011-virtual-rate-system','20261011-virtual-rate-context','20261011-virtual-header-copy','20261011-virtual-header-inner')]
folders += [ROOT/'projects/res-lab/validation'/p for p in (
 '20261011-m12-rate-reload-live','20261011-virtual-rate-system',
 '20261011-virtual-rate-live','20261011-virtual-rate-context','20261011-virtual-rate-context-live')]
assert sys.argv[1:] in ([], ['--evidence-only'])
evidence_only = bool(sys.argv[1:])
if evidence_only:
 folders=[ROOT/'projects/res-lab/validation/20261011-virtual-rate-context-live']
files=set() if evidence_only else set(source)
files.add(Path(__file__).resolve())
for directory in folders:
 files.update(p for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='evidence-manifest.json')
manifest=[]
for p in sorted(files):
 rel=p.relative_to(ROOT);size=p.stat().st_size
 include=p.suffix.lower() not in ('.mkv','.rgb','.plist','.bundle') and p.name not in ('commands.jsonl','evidence-manifest.json') and size<=4*1024*1024
 h=hashlib.sha256()
 with p.open('rb') as f:
  while chunk:=f.read(1024*1024):h.update(chunk)
 manifest.append({'path':str(rel),'bytes':size,'sha256':h.hexdigest(),'included':include})
 if include:
  q=DEST/rel;q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
report=ROOT/'projects/res-lab/validation/20261011-virtual-rate-context/evidence-manifest.json'
report.write_text(json.dumps({'policy':'Authored changes, candidate cards, DNG samples and small evidence included. Full HDMI, bulk command transcripts and host USB enumerations retained locally with hashes.',
 'scope':'Incremental live-test evidence only; earlier code/card snapshots remain in prior commits. Shared source changes are not copied.' if evidence_only else 'Full task snapshot',
 'files':manifest},indent=2)+'\n')
shutil.copy2(report,DEST/report.relative_to(ROOT))
print(json.dumps({'included':sum(x['included'] for x in manifest),'local_only':sum(not x['included'] for x in manifest),'included_bytes':sum(x['bytes'] for x in manifest if x['included'])}))
