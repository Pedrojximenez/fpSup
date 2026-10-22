#!/usr/bin/env python3
"""Offline re-audit of existing fp captures; no camera transport is imported."""
import argparse,hashlib,json
from pathlib import Path
BASE=Path('/Users/dido/Developer.localized/SIGMAfp_re')
HIST=Path('/Users/dido/Documents/Codex/2026-08-16/4')
OUT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,default=OUT/'capture-evidence-audit.json',help='JSON path or existing directory (default: beside this script)')
args=parser.parse_args()
output=args.output/'capture-evidence-audit.json' if args.output.is_dir() else args.output

def info(p):
 b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
report={'scope':[str(BASE),str(HIST)],'pq':{},'gamma_dump_payload_search':{},'iso_sessions':{},'supporting_sources':[]}
for mode in ('OFF','T&O'):
 d=HIST/'outputs'/mode;b=(d/'PQP844.bin').read_bytes()
 report['pq'][mode]={'files':[info(d/n) for n in ('PQP844.bin','TONE_CH0.bin','TONE_CH1.bin')],
  'nonzero_bytes':sum(v!=0 for v in b),'tone0_hex':b[0x140:0x154].hex(),
  'tone1_hex':b[0x55c:0x570].hex(),'tone0_slice_matches':b[0x140:0x154]==(d/'TONE_CH0.bin').read_bytes(),
  'tone1_slice_matches':b[0x55c:0x570]==(d/'TONE_CH1.bin').read_bytes()}
a=(HIST/'outputs/OFF/PQP844.bin').read_bytes();b=(HIST/'outputs/T&O/PQP844.bin').read_bytes()
report['pq']['different_byte_count']=sum(x!=y for x,y in zip(a,b))
for root in (BASE,HIST):
 report['gamma_dump_payload_search'][str(root)]={stem:[str(p) for p in root.rglob(stem+'*')] for stem in ('GAM158','PST15E','CEQ1D0','YUV1E0')}
AF=BASE/'research/autofocus/captures/af-fusion'
for name in ('2026-09-16-iso100-v5','2026-09-16-iso12800-c'):
 p=AF/name/'samples.jsonl';rows=[json.loads(s) for s in p.read_text().splitlines() if s.strip()]
 report['iso_sessions'][name]={'source':info(p),'binary_source':info(AF/name/'samples.bin'),'records':len(rows),
  'coherent_records':sum(r['integrity']['snapshot_coherent'] for r in rows),
  'sequence_min':min(r['sequence'] for r in rows),'sequence_max':max(r['sequence'] for r in rows),
  'unique_imx410_gains':[json.loads(s) for s in sorted({json.dumps(r['exposure']['imx410_gain'],sort_keys=True) for r in rows})],
  'movie_recording_values':sorted({r['exposure']['movie_recording'] for r in rows})}
for rel in ('research/autofocus/captures/af-fusion/2026-09-16-iso100-v5/README.md',
 'research/other/notes/CAMERA_STATE_SOURCES.md',
 'research/other/external/FP3K-technical-handoff-2026-09-10/analysis/reduction-method/native-trace.json',
 'research/other/external/FP3K-technical-handoff-2026-09-10/analysis/reduction-method/FINDINGS.md',
 'projects/open-gate/notes/REDUCTION_KERNEL_MEASURED.md',
 'projects/open-gate/notes/reduction-kernel/README.md',
 'projects/open-gate/notes/LIVE_VIEW_DISPLAY_CHAIN.md',
 'research/imaging-hw/notes/CRCT_PATH_SELECTOR_SOLVED.md',
 'projects/open-gate/captures/opengate_ev_bug_20260914/compare_083_084/result.json'):
 report['supporting_sources'].append(info(BASE/rel))
output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'pq_diff':report['pq']['different_byte_count'],'pq_nonzero':report['pq']['OFF']['nonzero_bytes'],'iso_sessions':report['iso_sessions']},indent=2))
