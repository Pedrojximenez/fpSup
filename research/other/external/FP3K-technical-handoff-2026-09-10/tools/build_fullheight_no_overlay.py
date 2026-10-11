"""Make a display-isolation variant of the verified F1 package; never install."""
from pathlib import Path
import hashlib,json,zipfile
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'diagnostics/three-k-f1';DST=ROOT/'diagnostics/three-k-f1-no-overlay'
m=json.loads((SRC/'manifest.json').read_text());data=(SRC/'card/AutoRun.txt').read_bytes();assert hashlib.sha256(data).hexdigest()==m['autorun_sha256']
lines=data.decode('ascii').splitlines();layout_addresses={'0xC03E4698','0xC03E46A0'}
kept=[];removed=[]
for line in lines:
 if line.startswith('display ') or (line.startswith('mem set ') and line.split()[2] in layout_addresses):removed.append(line)
 elif line.startswith('#'):continue
 else:kept.append(line)
assert len(removed)==30 and not any(x.startswith('display ') for x in kept)
assert kept[0]=='ctrl sleep 5000' and kept.count('echo')==1
body=('\r\n'.join(['# FP3K F1 display-isolation variant. NO onscreen status; NOT hardware validated.', '# Same full-height RAM payload. Leave idle THREE MINUTES and wait for access lamp off.', '# UHD true24fps,12-bit CDNG,SSD,crop off. Do not use firmware update.',*kept])+'\r\n').encode('ascii')
(DST/'card/FP3KF1').mkdir(parents=True,exist_ok=True);(DST/'card/AutoRun.txt').write_bytes(body);(DST/'card/FP3KF1/INFO.TXT').write_bytes((SRC/'card/FP3KF1/INFO.TXT').read_bytes())
m.update(status='DISPLAY-ISOLATION CANDIDATE; NOT INSTALLED OR CAMERA-VALIDATED',variant='F1 without custom display commands or text-handler patches',autorun_bytes=len(body),autorun_sha256=hashlib.sha256(body).hexdigest(),text_position=None,source_autorun_sha256=hashlib.sha256(data).hexdigest())
(DST/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
(DST/'README.md').write_text('''# F1 without custom overlay

Prepared to isolate the reported GUI-only flicker. Not installed or camera-tested.
The636-byte full-height payload,18 table changes and diagnostic outputs are exactly
the same as F1. All custom display calls and both temporary text-handler changes
are omitted. This might eliminate overlay interference; it is not a confirmed fix.
Full-height preview/receiver changes remain another possible cause of flicker.

There is NO LOAD or TEST text in this variant. If installed for a future test,
leave the camera idle for THREE MINUTES and wait for the busy/access lamp to go
out. Use only UHD true24fps,12-bit CDNG,SSD,crop off. Start with an idle UI check;
no extra recording is needed merely to report whether menus flicker. FreshFP3KF1
folders on both media are required after preserving earlier results.

All F1 limitations still apply, including unverified every-photosite filtering,
LCD preview mismatch and lack of sustained stability testing. Power-off alone has not been verified to clear RAM changes; see RESET-NOTICE.md.
Disable AutoRun before normal use. Current returned media have F1
AutoRun disabled for a stock full-resolution reference still, not this variant.
''')
with zipfile.ZipFile(DST/'fp3k-f1-no-overlay.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
 for p in [DST/'manifest.json',DST/'README.md',DST/'card/AutoRun.txt',DST/'card/FP3KF1/INFO.TXT']:z.write(p,p.relative_to(DST))
with zipfile.ZipFile(DST/'fp3k-f1-no-overlay.zip') as z:assert z.testzip() is None
print('Prepared uninstalled no-overlay variant:',m['autorun_bytes'],m['autorun_sha256'])
