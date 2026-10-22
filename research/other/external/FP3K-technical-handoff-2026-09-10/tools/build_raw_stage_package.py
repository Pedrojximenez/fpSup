"""Build an idle-only launch diagnostic using the existing verified RAM payload."""
from pathlib import Path
import hashlib,json,zipfile
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'diagnostics/fp-state-v003/card/AutoRun.txt'
original=source.read_bytes()
assert hashlib.sha256(original).hexdigest()=='855121cd12ba7794fd0ea1962a6daf759afbca34d81632227a1f35abd8316fa9'
lines=original.decode('ascii').splitlines()
first=lines.index('display text FPD003_SAMPLING')
lines.insert(first,'mem save \\FPD003\\PRE.BIN 0xC0BAC2F8,,4')
i=lines.index('echo')
lines.insert(i,'mem save \\FPD003\\ARMED.BIN 0xC0BAC2F8,,4')
i=lines.index('echo')
lines.insert(i+1,'mem save \\FPD003\\RETURN.BIN 0xC0BAC2F8,,4')
body=('\r\n'.join(lines)+'\r\n').encode('ascii')
assert len(body)<32768
assert [l for l in lines if not any('\\'+n+'.BIN' in l for n in ('PRE','ARMED','RETURN'))]==original.decode('ascii').splitlines()
dest=ROOT/'diagnostics/fp-state-v003-stage'
(dest/'card/FPD003').mkdir(parents=True,exist_ok=True)
(dest/'card/AutoRun.txt').write_bytes(body)
(dest/'card/FPD003/INFO.TXT').write_text('FPD003 launch-stage test. Stay idle. Return entire folder from both media.\n')
for media in ('SD','SSD'):(ROOT/'diagnostics/v003-stage'/media/'FPD003').mkdir(parents=True,exist_ok=True)
readme='''# FPD003 launch-stage test — stay idle

This uses the previously tested 1020-byte RAM payload. Three added stock memory-readback commands record the echo handler before arming (PRE.BIN), after arming (ARMED.BIN), and immediately after echo returns (RETURN.BIN). These diagnose script progress; they do not individually prove sampling succeeded. No resolution or firmware change is included.

1. With the camera off, replace the SD-root AutoRun.txt with card/AutoRun.txt from this package.
2. On both SD and SSD, rename the existing FPD003 folder to a unique backup name, then create a fresh FPD003 folder using the included card/FPD003 folder. Do not merge it with old output. Existing returned files are also preserved in the workspace. Stock saves add numbered filenames when a name already exists; suffixes cannot safely pair files across incomplete runs.
3. Keep the SSD connected. Power on and leave the camera idle: do not press REC, shutter, or half-press. The script still displays FPD003_LOADING, FPD003_SAMPLING, and FPD003_CHECK_FILES.
4. Wait for CHECK_FILES and media activity to stop. If it has not appeared after three minutes, stop the test using normal power-off. Return files even if the display never advances; do not repeat the run. Report if normal power-off does not work.
5. Copy the complete FPD003 folders into these already-created workspace destinations:
   - diagnostics/v003-stage/SD/FPD003
   - diagnostics/v003-stage/SSD/FPD003
6. Remove or rename AutoRun.txt before normal camera use.

Expected output may land on the SSD. Return both locations, including incomplete output. Added readbacks execute only during this idle-only test; this script is not the recording-test script. Temporary RAM code remains experimental. The original idle payload passed on this camera, but this revised script has not yet been camera-tested.
'''
(dest/'README.md').write_text(readme)
(dest/'manifest.json').write_text(json.dumps({'autorun_sha256':hashlib.sha256(body).hexdigest(),'autorun_bytes':len(body),'payload_changed':False,'added_files':['PRE.BIN','ARMED.BIN','RETURN.BIN'],'status':'READY FOR IDLE-ONLY CAMERA TEST; revised script not camera-tested'},indent=2)+'\n')
with zipfile.ZipFile(dest/'fp-state-v003-stage.zip','w',zipfile.ZIP_DEFLATED) as z:
 for rel in ('README.md','manifest.json','card/AutoRun.txt','card/FPD003/INFO.TXT'):z.write(dest/rel,rel)
print(dest/'fp-state-v003-stage.zip')
