"""Build a state-only AutoRun, using existing firmware shell commands.
No injected code, memory writes, sensor commands, or firmware updates.
"""
from pathlib import Path
import hashlib,json,re,argparse
ROOT=Path(__file__).resolve().parents[1]
ap=argparse.ArgumentParser();ap.add_argument('--run', choices=['001','002'], default='001');args=ap.parse_args()
DEST=ROOT/f'diagnostics/fp-state-v{args.run}';CARD=DEST/'card';RUN_DIR='FPD'+args.run
RANGES={'S':(0xC343B588,0x100,'IMX410 sensor object; current mode at +4'), 'C':(0xC31F869C,0x80,'CameraMgrSetting +0x40; recording configuration'), 'G':(0xC37CE210,0x80,'Recording scratch geometry; may be zero/stale outside FHD')}
COUNT=24;INTERVAL=2000;INITIAL=5000
# Precreate FPD001 on the card. Avoid mkdir and its handling of existing paths.
lines=['# FP state diagnostic v001: SIGMA fp firmware 5.02 ONLY', '# Save small RAM regions to SD using stock shell; no patches.', '# Copy the FPD001 directory alongside this file. Fresh run only.', f'ctrl sleep {INITIAL}', 'mem save \\FPD001\\GEOM.BIN 0xC0B59DC0,,7000']
files=[dict(name='GEOM.BIN',address=0xC0B59DC0,size=7000)]
for i in range(COUNT):
 for kind,(a,n,desc) in RANGES.items():
  name=f'{kind}{i:03d}.BIN';lines.append(f'mem save \\FPD001\\{name} 0x{a:08X},,{n}');files.append(dict(name=name,address=a,size=n,sample=i,description=desc))
 if i<COUNT-1:lines.append(f'ctrl sleep {INTERVAL}')
# A runtime-initialized vector prefix is a completion marker, NOT an assertion all prior writes succeeded.
lines.append('mem save \\FPD001\\DONE.BIN 0xC0000000,,64');files.append(dict(name='DONE.BIN',address=0xC0000000,size=64))
lines=[line.replace('FPD001',RUN_DIR).replace('v001','v'+args.run) for line in lines]
text='\r\n'.join(lines)+'\r\n'
(CARD/RUN_DIR).mkdir(parents=True,exist_ok=True);(CARD/'AutoRun.txt').write_bytes(text.encode('ascii'))
manifest=dict(version='v'+args.run,output_directory=RUN_DIR,firmware='5.02',initial_delay_ms=INITIAL,minimum_interval_ms=INTERVAL,sample_count=COUNT,expected_files=files,autorun_sha256=hashlib.sha256(text.encode()).hexdigest(),total_capture_bytes=sum(x['size'] for x in files))
(DEST/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
# Audit every executable line: nothing except bounded waits and exact allowlisted reads.
allowed={(f['address'],f['size'],f['name']) for f in files}
for line in lines:
 if line.startswith('#'):continue
 if line in (f'ctrl sleep {INITIAL}',f'ctrl sleep {INTERVAL}'):continue
 m=re.fullmatch(r'mem save \\FPD001\\([A-Z0-9]+\.BIN) (0x[0-9A-F]+),,(\d+)',line.replace(RUN_DIR,'FPD001'))
 if not m or (int(m[2],16),int(m[3]),m[1]) not in allowed:raise ValueError('Unapproved diagnostic command: '+line)
print(f'Built and allowlist-audited {len(files)} files / {manifest["total_capture_bytes"]} bytes; no hardware run yet')
