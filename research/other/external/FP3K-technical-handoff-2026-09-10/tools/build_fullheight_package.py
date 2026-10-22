"""Package the F1 experimental full-height test; does not install on media."""
import hashlib,json,struct,zipfile
from pathlib import Path
from verify_three_k_fullheight import build,BASE,STATUS,ECHO,ORIGINAL_ECHO,COUNT
ROOT=Path(__file__).resolve().parents[1];DEST=ROOT/'diagnostics/three-k-f1';CARD=DEST/'card'
code,syms,entries,main=build()
tested=json.loads((ROOT/'analysis/firmware/three-k-fullheight-verification.json').read_text())
capture=json.loads((ROOT/'analysis/firmware/fullheight-capture-verification.json').read_text())
assert tested['payload_sha256']==hashlib.sha256(code).hexdigest()
assert len(tested['cases'])==COUNT+10 and all(c['passed'] for c in tested['cases'])
assert capture['frame_cycles']==3000000 and capture['input_raster']==[6064,4042]
layout=[(0xc03e4698,0xe3a08000,0xe3a08060),(0xc03e46a0,0xe1a05008,0xe3a050d0)]
for a,old,new in layout:assert struct.unpack_from('<I',main,a-0xc0000000)[0]==old
lines=['# FP3K F1 - EXPERIMENTAL full-height candidate - Sigma fp5.02 ONLY.',
 '# RAM test, not a firmware update. UHD true24,12-bit CDNG,SSD,crop off.',
 '# Leave idle until FP3K_F1_TEST and busy/access lamp off.', 'ctrl sleep 5000']
allowed=set()
def write(a,v):
 allowed.add((a,v));lines.extend([f'mem set 0x{a:08X} 0x{v:08X}']*3)
def banner(text):
 lines.extend(['display osd 1 0x00000000']*3)
 for _ in range(3):lines.extend([f'display text {text}','display osd 1'])
for a,old,new in layout:write(a,new)
banner('FP3K_F1_LOAD')
for i in range(4):write(STATUS+4*i,0)
for i,v in enumerate(struct.unpack('<'+'I'*(len(code)//4),code)):write(BASE+4*i,v)
lines.append(f'mem save \\FP3KF1\\LOADED.BIN 0x{BASE:08X},,{len(code)}')
write(ECHO,BASE);lines.append('echo');write(ECHO,ORIGINAL_ECHO)
lines.append(f'mem save \\FP3KF1\\STATUS.BIN 0x{STATUS:08X},,16')
for i,(a,old,new) in enumerate(entries):lines.append(f'mem save \\FP3KF1\\WORD{i}.BIN 0x{a:08X},,4')
banner('FP3K_F1_TEST')
for a,old,new in layout:write(a,old)
for line in lines:
 if line.startswith('mem set '):
  _,_,a,v=line.split();a,v=int(a,16),int(v,16);assert (a,v) in allowed
  assert BASE<=a<BASE+len(code) or STATUS<=a<STATUS+16 or a==ECHO or a in {x[0] for x in layout}
 else:assert line.startswith(('#','display text FP3K_F1_','mem save \\FP3KF1\\')) or line in ('ctrl sleep 5000','display osd 1','display osd 1 0x00000000','echo')
body=('\r\n'.join(lines)+'\r\n').encode('ascii');assert len(body)<32768
(CARD/'FP3KF1').mkdir(parents=True,exist_ok=True)
(CARD/'AutoRun.txt').write_bytes(body)
(CARD/'FP3KF1/INFO.TXT').write_text('FP3K F1 experimental full-height test. Return LOADED.BIN, STATUS.BIN and WORD0.BIN through WORD17.BIN plus the complete short clip.\n')
for label in ('SD','SSD'):(ROOT/'diagnostics/three-k-f1-return'/label/'FP3KF1').mkdir(parents=True,exist_ok=True)
for label in ('clip','reference-still'):(ROOT/'diagnostics/three-k-f1-return'/label).mkdir(exist_ok=True)
manifest=dict(status='EXPERIMENTAL FULL-HEIGHT CANDIDATE; NOT YET CAMERA-VALIDATED',firmware='Sigma fp5.02',payload_base=hex(BASE),payload_bytes=len(code),payload_sha256=hashlib.sha256(code).hexdigest(),autorun_bytes=len(body),autorun_sha256=hashlib.sha256(body).hexdigest(),status_magic='0x3146334b',status_success=16,table_entries=tested['table_entries'],expected_sensor_raster=[6064,4042],expected_raw_raster=[3032,2020],expected_visible_crop=[3000,2000],expected_raw_bytes=9186968,ratio=2048,configuration='UHD true24fps (not23.98),12-bit CinemaDNG,SSD,crop off',text_position={'x':208,'y':96,'camera_position_not_yet_visually_verified':True},limitations=['Candidate only: field of view, Bayer phase, filtering and sustained recording need camera validation.','Sensor mode151 windows are changed globally; use only the specified profile429 configuration.','Preview and auxiliary40-byte table remain stock; LCD may show a narrower16:9 view than the recorded3:2 image.','Mode151 native full-height sensor-register table matches mode3/121, but this does not prove that every photosite contributes through the downstream RAW reducer.','Stock still modes unchanged; normal power-off clears RAM patch. AutoRun reapplies it if left present.','No flash writes. Bootstrap corruption or concurrent hardware faults are not made safe by the payload checksum.'])
(DEST/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
readme='''# FP3K F1: full-height candidate

This is the first full-height camera test, not a proven full-coverage release.
It requests6064×4042 sensor input and3032×2020 RAW with a3000×2000 visible crop,
12-bit CinemaDNG at true24fps. Expected output bandwidth is approximately
222.4MB/s including the previously observed per-frame header/alignment, plus audio.

It changes18 RAM table words. The native full-height mode3 geometry and receiver
windows are applied to mode151 while its stock445/1145/6740 timing is retained.
The main sensor-register settings are already identical between151 and3/121.
RAW reduction changes from1600 to2048; skipping/binning enums remain unchanged.
Every-photosite contribution and Bayer filtering at this ratio are unproven.
The preview remains stock and may crop the recorded3:2 field of view on the LCD.
Use only UHD true24fps,12-bit CDNG,SSD,crop off. Other frame rates, bit depths,
HDMI recording and sustained operation are not validated by this test.

## Installation

With the camera off, replace the SD-root AutoRun.txt with card/AutoRun.txt.
Preserve previous results and use a fresh FP3KF1 folder on BOTH SD and SSD.
Do not combine with other AutoRuns. Do not use the firmware-update menu.

## One short camera test

1. Use a charged battery. Keep the camera in CINE, UHD,true24fps (not23.98),
   12-bit CinemaDNG to SSD, crop mode off. Connect SSD and insert prepared SD.
2. Put the camera on a stable surface facing a detailed, well-lit stationary
   scene. Include recognizable objects near the top, bottom and sides.
3. Power on and leave it idle. Wait for FP3K_F1_TEST and the busy/access lamp
   to stop lighting/flashing. The label is aimed upper middle below top controls.
   TEST means the script returned; the diagnostic files establish application.
   If TEST does not appear within three minutes, power off and return files
   without recording. Restart without the test SD if the camera is unresponsive.
4. Press REC for one2–3second take, then stop. If it stops itself, or the picture
   breaks up, do not retry; report the behavior and return the files.
5. Wait until the busy/access lamp is off. Power off normally. Do not move the
   camera or adjust the lens if making the reference still described below.
6. Connect both devices to the computer for collection. After disabling AutoRun,
   we can collect a full-resolution3:2 reference still of the same scene from
   the same camera position. This will establish actual video field of view;
   matching DNG dimensions alone cannot establish full sensor coverage.
7. Return the media with the camera powered off.
   Return the complete clip and FP3KF1 from each medium. Return folders exist in
   diagnostics/three-k-f1-return/{SD,SSD}/FP3KF1, clip and reference-still.

## Rollback and checks

Normal power-off clears the RAM changes. Rename/remove AutoRun before normal use;
leaving it on the SD reapplies the test at every boot. Original firmware stays
unchanged. This candidate has not been tested on a camera. It may hang or produce
unusable clips, and software guards cannot model hardware or power failures.

Offline checks:28 payload success/failure cases including every changed word,
checksum failure, busy guards and readback rollback. All306 processing rows
checked; only profile429's row changes. Separate execution of native timing,
window and receiver setup matches mode3's input/receiver arguments and retains
stock true24 timing. Hardware I/O is mocked in that latter check. This is not
proof of successful full-height acquisition or image quality.

Diagnostics: LOADED.BIN636B, STATUS.BIN16B, WORD0..17.BIN4B each. Status16 is
applied/read back;2 checksum failure;3 busy;4 stock mismatch;5 rollback attempt.
All diagnostic writes happen before REC; no background worker is installed.
'''
(DEST/'README.md').write_text(readme)
with zipfile.ZipFile(DEST/'fp3k-f1.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
 for p in (DEST/'README.md',DEST/'manifest.json',CARD/'AutoRun.txt',CARD/'FP3KF1/INFO.TXT'):z.write(p,p.relative_to(DEST))
print(json.dumps({k:manifest[k] for k in ['status','payload_bytes','payload_sha256','autorun_bytes','autorun_sha256']},indent=2))
