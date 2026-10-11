"""Package the verified cropped3K hardware test; never installs it."""
import hashlib,json,struct,zipfile
from pathlib import Path
from verify_three_k_geometry import build,BASE,STATUS,ECHO,ORIGINAL_ECHO
ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'diagnostics/three-k-g1'
CARD=DEST/'card'
code,syms,entries,main=build()
tested=json.loads((ROOT/'analysis/firmware/three-k-geometry-verification.json').read_text())
assert tested['payload_sha256']==hashlib.sha256(code).hexdigest()
assert len(tested['cases'])==16 and all(c['passed'] for c in tested['cases'])
lines=['# FP3K G1 - Sigma fp5.02 ONLY. Cropped geometry test, NOT full-height.',
       '# RAM only. Do not run firmware update. Configure UHD true24,12-bit CDNG,SSD.',
       '# Leave idle until FP3K_G1_TEST. Then record one short take.',
       'ctrl sleep 5000']
allowed=set()
# Verified in fp5.02 display-text handler: x=r5, y=r8, width=384.
# Center the short labels approximately on the640-wide OSD, below top controls.
layout=[(0xc03e4698,0xe3a08000,0xe3a08060),(0xc03e46a0,0xe1a05008,0xe3a050d0)]
for a,old,new in layout:assert struct.unpack_from('<I',main,a-0xc0000000)[0]==old
def write(a,v):
    allowed.add((a,v))
    lines.extend([f'mem set 0x{a:08X} 0x{v:08X}']*3)
def banner(text):
    assert len(text)<=19
    lines.extend(['display osd 1 0x00000000']*3)
    for _ in range(3):lines.extend([f'display text {text}','display osd 1'])
for a,old,new in layout:write(a,new)
banner('FP3K_G1_LOAD')
for i in range(4):write(STATUS+4*i,0)
for i,v in enumerate(struct.unpack('<'+'I'*(len(code)//4),code)):write(BASE+4*i,v)
lines.append(f'mem save \\FP3KG1\\LOADED.BIN 0x{BASE:08X},,{len(code)}')
write(ECHO,BASE)
lines.append('echo')
write(ECHO,ORIGINAL_ECHO)
lines.append(f'mem save \\FP3KG1\\STATUS.BIN 0x{STATUS:08X},,16')
for i,(a,old,new) in enumerate(entries):lines.append(f'mem save \\FP3KG1\\WORD{i}.BIN 0x{a:08X},,4')
banner('FP3K_G1_TEST')
for a,old,new in layout:write(a,old)
body=('\r\n'.join(lines)+'\r\n').encode('ascii')
assert len(body)<32768
# Direct shell writes cover bootstrap/status/echo and temporary text coordinates.
# The six table writes happen only inside the guarded payload.
for line in lines:
    if line.startswith('mem set '):
        _,_,a,v=line.split();assert (int(a,16),int(v,16)) in allowed
        address=int(a,16)
        assert BASE<=address<BASE+len(code) or STATUS<=address<STATUS+16 or address==ECHO or address in {a for a,_,_ in layout}
    else:assert line.startswith(('#','display text FP3K_G1_','mem save \\FP3KG1\\')) or line in ('ctrl sleep 5000','display osd 1','display osd 1 0x00000000','echo')
(CARD/'FP3KG1').mkdir(parents=True,exist_ok=True)
(CARD/'AutoRun.txt').write_bytes(body)
(CARD/'FP3KG1/INFO.TXT').write_text('FP3K G1 cropped geometry test only. Expected LOADED.BIN, STATUS.BIN, WORD0.BIN through WORD5.BIN. Return from both media with one DNG.\n')
for medium in ('SD','SSD'):(ROOT/f'diagnostics/three-k-g1-return/{medium}/FP3KG1').mkdir(parents=True,exist_ok=True)
(ROOT/'diagnostics/three-k-g1-return/clip').mkdir(parents=True,exist_ok=True)
manifest=dict(status='EXPERIMENTAL CAMERA TEST; NOT FULL-HEIGHT; NOT HARDWARE-VALIDATED',
    firmware='Sigma fp5.02',payload_base=hex(BASE),payload_bytes=len(code),payload_sha256=hashlib.sha256(code).hexdigest(),
    autorun_bytes=len(body),autorun_sha256=hashlib.sha256(body).hexdigest(),
    profile=429,configuration='UHD true24fps,12-bit CinemaDNG,SSD; no crop mode',
    expected_raw_raster=[3032,2020],expected_visible_crop=[3000,2000],expected_raw_bytes=9186968,
    sensor_mode_unchanged=151,scaling_ratio_unchanged=1600,
    text_position={'x':208,'y':96,'width':384,'camera_position_not_yet_visually_verified':True},
    text_handler_changes=[{'address':hex(a),'original':hex(old),'temporary':hex(new)} for a,old,new in layout],
    status_success=16,table_entries=tested['table_entries'],
    limitations=tested['limitations'],rollback='Normal power-off; remove or rename AutoRun before restarting to prevent reapplication.')
(DEST/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
readme='''# FP3K G1 — cropped3K recording test

**This is not the finished full-height patch.** It tests a3000×2000 visible
CinemaDNG image while retaining the stock sensor readout and scaling. Expect
a tighter field of view. Its purpose is to validate the live buffer and DNG
path before changing sensor height. It is untested on hardware.

The revised labels are positioned toward the upper middle, below the top
controls (OSD x208,y96). Exact placement still needs visual confirmation.
Two display-handler instructions are temporarily changed for drawing and
restored after the final label. The492-byte recording-test payload is unchanged.
The camera's busy/access lamp indicates media activity: wait until it is no
longer lit or flashing before powering off or removing media.

It modifies six RAM table words for the true24fps12-bit UHD profile only.
It does not flash firmware. Restarting restores stock RAM, but AutoRun will
reapply the test unless removed or renamed. Do not use firmware update.

1. With the camera off, copy `card/AutoRun.txt` to the SD root, replacing the
   previous AutoRun. Copy the empty `card/FP3KG1` folder to both SD and SSD
   roots. Use empty result folders for this boot; preserve existing clips.
2. Configure UHD, true24fps (not23.98),12-bit CinemaDNG, crop mode off, recording
   to SSD. Keep the current firmware5.02. Do not combine this with gyro or USB
   shell AutoRun. Connect the SSD and power on.
3. Leave the camera idle during `FP3K_G1_LOAD`. Wait for `FP3K_G1_TEST` and
   media activity to finish. Loading may take about a minute. If the message
   has not appeared after three minutes, do not record; power off normally
   and return whatever diagnostic files exist. If it hangs, restart without
   the test SD. The TEST message means the script returned, not proof of success.
4. Once TEST appears, press **REC**, not the still shutter. Make one2–3second
   take of a detailed stationary scene, then stop. If it stops itself, leave
   it stopped; do not repeat. The menu may still say UHD. Stop if the picture
   corrupts or the camera becomes unresponsive.
5. Wait for media activity to stop and power off normally. Mount both media
   on the computer. We need each `FP3KG1` folder and one DNG from this take
   (preferably the whole short clip). Note whether framing changed and whether
   recording stopped itself. Return directories already exist:
   `diagnostics/three-k-g1-return/SD/FP3KG1`,
   `diagnostics/three-k-g1-return/SSD/FP3KG1`, and
   `diagnostics/three-k-g1-return/clip`.
6. Rename or remove this AutoRun before normal use. Keep original firmware and
   existing recordings. Do not format either medium for this test.

The payload restores the borrowed echo handler on entry, checks its checksum,
checks idle/recording/finalization signals, verifies all six expected stock
words before any table mutation, rechecks idle, then writes and reads back all
six values. A readback mismatch attempts to restore all six original values.
A corrupted bootstrap, interrupted load or hardware fault is not made safe by
these checks; this is an experimental RAM patch, not a released firmware.

Expected diagnostic files: LOADED.BIN492 bytes; STATUS.BIN16 bytes; WORD0.BIN
through WORD5.BIN4 bytes each. Status16 means applied/read back;2 checksum
failure;3 busy;4 unexpected stock value;5 readback failure with rollback attempt.
All file writes occur before the requested take; no background worker remains.
Use `tools/read_three_k_geometry.py` to inspect the returned diagnostic folder.
'''
(DEST/'README.md').write_text(readme)
with zipfile.ZipFile(DEST/'fp3k-g1.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
    for p in (DEST/'README.md',DEST/'manifest.json',CARD/'AutoRun.txt',CARD/'FP3KG1/INFO.TXT'):z.write(p,p.relative_to(DEST))
print(json.dumps(manifest,indent=2))
