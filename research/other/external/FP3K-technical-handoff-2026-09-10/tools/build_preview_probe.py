"""Prepare a bounded RAM trace alongside the unchanged, tested v0.3.2 resident.

This is a diagnostic, not a preview patch. No sensor/preview configuration writes.
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = 0xc0731930
COUNT, STRIDE, INTERVAL = 56, 0x900, 750
TOTAL = 64 + COUNT * STRIDE
OUT = ROOT / 'diagnostics/fullheight-preview-probe-v1'
BASELINE = ROOT / 'prototype/fp3k-0.3.2-native-ui'
RESIDENT_SHA = 'c47af36a53728418d416f1efb9ad71bd88e5065e140f02400a9816264ba69529'
AUTORUN_SHA = 'd317396b6505eeb90ed01519d8fc392b1da96fc6b05d869ff6ab594ad73a39fa'
STATE_BYTES = 48
sys.path.insert(0, str(ROOT / 'research/fpSup/fp_usb_shell'))
from armasm import assemble, symbols

def build():
    baseline = BASELINE
    resident = (baseline / 'FP3KMENU.BIN').read_bytes()
    assert hashlib.sha256(resident).hexdigest() == RESIDENT_SHA
    autorun = (baseline / 'AutoRun.txt').read_bytes()
    assert hashlib.sha256(autorun).hexdigest() == AUTORUN_SHA
    assert 0xc072de64 + len(resident) <= BASE
    OUT.mkdir(parents=True, exist_ok=True)
    source_dir = OUT / 'sources'
    source_dir.mkdir(exist_ok=True)
    snapshot = (ROOT / 'tools/raw_snapshot.S').read_text()
    snapshot = snapshot.replace('0x340-byte output', '0x900-byte output').replace('cmp r1, #0x340', 'cmp r1, #0x900')
    extra = '''
    /* Fixed RAM only. These copies are sequential, not atomic snapshots. */
    address r0, 0xC375D840
    add r1, r4, #0x340
    mov r2, #0x100
    bl copy_words
    address r0, 0xC31DF564
    add r1, r4, #0x440
    mov r2, #0x360
    bl copy_words
    address r0, 0xC0732000
    add r1, r4, #0x7A0
    mov r2, #48
    bl copy_words
    address r0, 0xC31D2800
    add r1, r4, #0x800
    mov r2, #0x100
    bl copy_words
'''
    extra = extra.replace('mov r2, #48', f'mov r2, #{STATE_BYTES}')
    snapshot = snapshot.replace('    mov r0, r10\n', extra + '    mov r0, r10\n')
    (source_dir / 'preview_snapshot.S').write_text(snapshot)
    capture = (ROOT / 'tools/raw_capture.S').read_text()
    capture = capture.replace('.equ LOAD_BASE, 0xC072DE64', f'.equ LOAD_BASE, 0x{BASE:08X}')
    capture = capture.replace('.equ NRECORDS, 120', f'.equ NRECORDS, {COUNT}')
    capture = capture.replace('.equ RECORD_SIZE, 0x340', f'.equ RECORD_SIZE, 0x{STRIDE:X}')
    capture = capture.replace('0x33525046       /* FPR3 */', '0x31565046       /* FPV1 */')
    capture = capture.replace('mov r0, #3\n    str r0, [r5, #4]', 'mov r0, #1\n    str r0, [r5, #4]')
    # Only the sampling interval changes. Keep the finalization polling at250ms.
    capture = capture.replace('mov r0, #250\n    str r0, [r5, #0x18]', f'movw r0, #{INTERVAL}\n    str r0, [r5, #0x18]')
    capture = capture.replace('    mov r0, #250\n    call 0xC0421770\n    cmp r7, #NRECORDS', f'    movw r0, #{INTERVAL}\n    call 0xC0421770\n    cmp r7, #NRECORDS')
    capture = capture.replace('FPD003', 'FP3KPV').replace('99904', str(TOTAL))
    capture = capture.replace('/* Stop sampling after ~30s.', '/* Stop sampling after ~42s.')
    capture = capture.replace('.include "tools/raw_snapshot.S"', f'.include "{source_dir.relative_to(ROOT)}/preview_snapshot.S"')
    source = source_dir / 'preview_capture.S'
    source.write_text(capture)
    code = bytearray(assemble(source))
    syms = symbols(source)
    struct.pack_into('<I', code, syms['checksum_word'], (-sum(struct.unpack('<'+'I'*(len(code)//4), code))) & 0xffffffff)
    assert BASE + len(code) <= 0xc0732000
    assert TOTAL <= 0x20000
    assert sum(struct.unpack('<'+'I'*(len(code)//4), code)) & 0xffffffff == 0
    main = (ROOT / 'analysis/firmware/MAIN_c0000000.bin').read_bytes()
    assert hashlib.sha256(main).hexdigest() == 'aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
    assert main[BASE-0xc0000000:BASE-0xc0000000+len(code)] == bytes(len(code))
    (OUT / 'probe.bin').write_bytes(code)
    lines = autorun.decode('ascii').splitlines()
    lines += ['# Preview trace only: no sensor or preview configuration changes.',
              'mem set 0xC3757A7C 0x00000000', 'memmgr bufmem get 0 131072']
    lines += [f'mem set 0x{BASE+i*4:08X} 0x{word:08X}' for i, word in enumerate(struct.unpack('<'+'I'*(len(code)//4), code))]
    lines += ['mem save \\FP3KPV\\POOL.BIN 0xC3757A7C,,12',
              f'mem save \\FP3KPV\\LOADED.BIN 0x{BASE:08X},,{len(code)}',
              f'mem set 0xC0BAC2F8 0x{BASE:08X}', 'echo', 'mem set 0xC0BAC2F8 0xC03D99A0']
    body = ('\r\n'.join(lines)+'\r\n').encode('ascii')
    assert len(body) < 32768
    assert not any(line.startswith(('display ', 'ctrl sleep ')) for line in lines)
    card = OUT / 'card'
    card.mkdir(exist_ok=True)
    (card / 'AutoRun.txt').write_bytes(body)
    (card / 'FP3KMENU.BIN').write_bytes(resident)
    for folder in [card/'FP3KM2', card/'FP3KPV', ROOT/'diagnostics/fullheight-preview-trace-return/SD/FP3KPV', ROOT/'diagnostics/fullheight-preview-trace-return/SSD/FP3KPV']:
        folder.mkdir(parents=True, exist_ok=True)
    manifest = dict(status='Diagnostic prepared offline; not installed', firmware='Sigma fp 5.02',
                    baseline_resident_sha256=hashlib.sha256(resident).hexdigest(), probe_base=hex(BASE),
                    probe_bytes=len(code), probe_sha256=hashlib.sha256(code).hexdigest(),
                    autorun_bytes=len(body), autorun_sha256=hashlib.sha256(body).hexdigest(),
                    sample_count=COUNT, sample_stride=STRIDE, interval_ms=INTERVAL, capture_bytes=TOTAL,
                    explicit_startup_sleep_ms=0, sampling_seconds=COUNT*INTERVAL/1000,
                    ranges={'0x340':'C375D840 +0x100 manager', '0x440':'C31DF564 +0x360 native processing config',
                            '0x7a0':'C0732000 +48 private state', '0x800':'C31D2800 +0x100 display state'},
                    limitations=['Trace copies are sequential; frame/config changes can race reads.',
                                 'Snapshot reads RAM only. It does not program preview geometry.',
                                 '128KiB diagnostic allocation retained until restart.',
                                 'Camera scheduling and file writes require hardware validation.',
                                 'No new take after sampling window; one delayed save after native idle checks.'])
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    return bytes(code), syms, manifest

if __name__ == '__main__':
    print(json.dumps(build()[2], indent=2))
