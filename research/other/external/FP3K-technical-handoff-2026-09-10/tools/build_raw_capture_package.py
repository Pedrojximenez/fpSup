"""Package the emulator-verified FPD003 idle preflight. Never deploys it."""
import hashlib
import json
import struct
import zipfile
from pathlib import Path
from verify_raw_capture import build

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'diagnostics/fp-state-v003'
CARD=DEST/'card'
code,_=build()
verification=json.loads((ROOT/'analysis/firmware/raw-capture-emulation.json').read_text())
assert hashlib.sha256(code).hexdigest()==verification['code_sha256']
assert len(verification['cases'])==8 and all(c['passed'] for c in verification['cases'])
main=(ROOT/'analysis/firmware/MAIN_c0000000.bin').read_bytes()
assert hashlib.sha256(main).hexdigest()=='aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
assert main[0x72de64:0x72de64+len(code)]==bytes(len(code))
assert struct.unpack_from('<I',main,0xbac2f8)[0]==0xc03d99a0
lines=['# FPD003: Sigma fp 5.02 ONLY. First run must remain idle.',
       '# Temporary RAM diagnostic. No sensor mode change or firmware update.',
       'ctrl sleep 5000']
allowed_writes=set()
def write(address,value,repeats=3):
    allowed_writes.add((address,value))
    lines.extend([f'mem set 0x{address:08X} 0x{value:08X}']*repeats)
def banner(message):
    assert len(message)<=19
    for _ in range(3):lines.extend([f'display text {message}','display osd 1'])
banner('FPD003_LOADING')
# A dropped allocator command must leave a null base, not a previous allocation.
write(0xc3757a7c,0)
lines.append('memmgr bufmem get 0 131072')
for i,word in enumerate(struct.unpack(f'<{len(code)//4}I',code)):
    write(0xc072de64+i*4,word)
lines.extend(['mem save \\FPD003\\POOL.BIN 0xC3757A7C,,12',
              f'mem save \\FPD003\\LOADED.BIN 0xC072DE64,,{len(code)}'])
banner('FPD003_SAMPLING')
write(0xc0bac2f8,0xc072de64)
lines.append('echo')
write(0xc0bac2f8,0xc03d99a0)
banner('FPD003_CHECK_FILES')
body=('\r\n'.join(lines)+'\r\n').encode('ascii')
assert len(body)<32768
for line in lines:
    if line.startswith('mem set '):
        _,_,address,value=line.split()
        assert (int(address,16),int(value,16)) in allowed_writes
    elif line.startswith('#') or line.startswith('display text FPD003_'):pass
    else:
        assert line in ('ctrl sleep 5000','memmgr bufmem get 0 131072','display osd 1','echo',
                        'mem save \\FPD003\\POOL.BIN 0xC3757A7C,,12',
                        f'mem save \\FPD003\\LOADED.BIN 0xC072DE64,,{len(code)}'),line
(CARD/'FPD003').mkdir(parents=True,exist_ok=True)
(CARD/'AutoRun.txt').write_bytes(body)
(CARD/'FPD003/INFO.TXT').write_text('FPD003 idle preflight. Return this directory from both SD and SSD. Expected: POOL.BIN, LOADED.BIN, STATE.BIN. No recording on the first run.\n')
manifest={'status':'READY FOR FIRST IDLE PREFLIGHT; NOT CAMERA-VALIDATED',
          'firmware':'Sigma fp 5.02','payload_base':'0xC072DE64','payload_bytes':len(code),
          'payload_sha256':hashlib.sha256(code).hexdigest(),'autorun_sha256':hashlib.sha256(body).hexdigest(),
          'autorun_bytes':len(body),'allocation_bytes':131072,'capture_file_bytes':99904,
          'sample_count':120,'nominal_interval_ms':250,'sampling_seconds_nominal':30,
          'additional_idle_wait_limit_seconds':60,'minimum_idle_observation_seconds':3,
          'expected_files':{'POOL.BIN':12,'LOADED.BIN':len(code),'STATE.BIN':99904},
          'mutations':['zero allocation-result base before allocating USER RAM','1020 bytes of previously zero RAM cave',
                       'temporarily replace echo handler; restore on entry and after return','allocate 128 KiB until restart',
                       'write diagnostic output files and display diagnostic text'],
          'limits':['Emulation does not validate camera scheduling or native file handler behavior.',
                    'Body checksum cannot guarantee that a corrupted entry/bootstrap executes safely.',
                    'No concurrent take may be started during final save; first run stays idle throughout.']}
(DEST/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
readme='''# FPD003 — first idle preflight

This diagnostic identifies the live RAW-processing profile and geometry. It does not enable open gate. **First run: do not record or take photographs.**

Unlike v001/v002, this uses temporary ARM code in RAM. It does not flash firmware, alter sensor modes, hook the gyro callback, or install a USB worker. The echo shell handler is temporarily borrowed and restored. Offline checks passed, but this build has not yet run on a camera; a loading fault can still hang the camera. Restarting without this AutoRun removes the diagnostic.

1. With the camera off, put `card/AutoRun.txt` at the SD card root, replacing the previous diagnostic AutoRun. Copy `card/FPD003` to the SD root **and** the SSD root. Keep the existing clips; no formatting is needed. Do not combine this AutoRun with another payload.
2. Connect the SSD and use the existing UHD / true 24 fps / 12-bit CinemaDNG configuration. Power on and leave the camera idle. Do not press record or the shutter.
3. Loading may take about a minute. The display should progress through `FPD003_LOADING`, `FPD003_SAMPLING`, then `FPD003_CHECK_FILES`. Sampling takes about 30 seconds. The last message means the routine returned, not that the file write necessarily succeeded.
4. After the last message and once media activity has stopped, power off normally. If it has not finished after three minutes, stop the test and power off; do not repeat it yet. If the camera hangs, restart with the diagnostic SD removed.
5. Copy the `FPD003` folders from both media into `FPware/diagnostics/v003-idle/SD/FPD003` and `FPware/diagnostics/v003-idle/SSD/FPD003`. Return whatever files exist, including partial results. Remove or rename the SD's AutoRun before normal camera use.

Expected files, possibly on the active SSD: `POOL.BIN` (12 bytes), `LOADED.BIN` (1020 bytes), `STATE.BIN` (99,904 bytes). The first two are saved before sampling. The capture is saved once afterward, only when both movie flags and native lifecycle signals are clear and sensor mode 8 has remained observed for three seconds. If that condition never arrives, it returns without saving STATE.BIN after a bounded wait.

We will inspect this preflight before any recording test. Do not improvise a second take or run firmware update from this package.

## Local verification

`analysis/venv/bin/python tools/verify_raw_profiles_emulated.py` checks the stock profile loader, snapshot bounds, pointer-change detection, capture timeout and delayed-save behavior. Unicorn requires approved execution outside the macOS sandbox here. File and sleep calls are simulated; the real camera remains untested.

`python3 tools/read_raw_capture.py PATH_TO_FPD003 --output analysis/v003-idle.json` validates the result and compares LOADED.BIN byte-for-byte with the tested payload.
'''
(DEST/'README.md').write_text(readme)
with zipfile.ZipFile(DEST/'fp-state-v003-idle.zip','w',compression=zipfile.ZIP_DEFLATED) as z:
    for p in (DEST/'README.md',DEST/'manifest.json',CARD/'AutoRun.txt',CARD/'FPD003/INFO.TXT'):
        z.write(p,p.relative_to(DEST))
print(json.dumps(manifest,indent=2))
