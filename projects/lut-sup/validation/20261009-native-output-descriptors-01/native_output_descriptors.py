#!/usr/bin/env python3
"""Read reviewed native output metadata only; no framebuffer read or setter."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
from pathlib import Path
import struct
import sys

from native_mode_trial import Camera, ROOT, ROM_PATH, SHELL, IDENTITY, state
from native_controls_trial import controls

REGIONS = [('SIGSEQ_OUTPUT_' + str(i), 0xC30255B4 + i * 0x80, 32) for i in range(3)] + [
    ('ACTIVE_OUTPUT_0', 0xC30254B4, 32), ('ACTIVE_OUTPUT_1', 0xC3025534, 32),
    ('OUTPUT_PROFILE_SELECTORS', 0xC31DF8D8, 3),
    ('LINEAR_DEVELOP_DESCRIPTOR', 0xC375C05C, 20),
    ('SECOND_DEVELOP_DESCRIPTOR', 0xC375C094, 20),
]


def run(camera, report):
    camera.status()
    camera.idle()
    rom = ROM_PATH.read_bytes()
    for address, count in list(IDENTITY) + [(0xC01D7638, 8), (0xC0429470, 8), (0xC0429560, 8)]:
        actual = camera.words(address, count)
        expected = list(struct.unpack_from('<' + 'I' * count, rom, address - 0xC0000000))
        if actual != expected:
            raise RuntimeError('unexpected native code at ' + hex(address))
    original, original_controls = state(camera), controls(camera)
    if not original['boot_id'] or original['app_current'] != 2:
        raise RuntimeError('requires known CINE standby')
    report.update(original_state=original, original_controls=original_controls, samples=[])
    for _ in range(3):
        if state(camera) != original or controls(camera) != original_controls:
            raise RuntimeError('state changed before metadata read')
        values = {name: {'address': hex(address), 'words': camera.words(address, count)}
                  for name, address, count in REGIONS}
        if state(camera) != original or controls(camera) != original_controls:
            raise RuntimeError('state changed across sequential metadata read')
        report['samples'].append({'regions': values, 'atomic': False})
    report['final_state'], report['final_controls'] = state(camera), controls(camera)
    report['stock_sites'] = {hex(a): camera.words(a, n) for a, n in IDENTITY}
    report['unchanged'] = report['final_state'] == original and report['final_controls'] == original_controls
    if not report['unchanged']:
        raise RuntimeError('final state changed')
    report['status'] = 'read-only-output-metadata-complete'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-live-read-only', action='store_true')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if not args.run_live_read_only:
        parser.error('explicit live read flag required')
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'started', 'date_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'camera_writes': False, 'pixel_data_read': False, 'pixel_format_verified': False,
              'source_rom_sha256': hashlib.sha256(ROM_PATH.read_bytes()).hexdigest()}
    camera = None
    try:
        with open('/tmp/fp-af-fusion.lock', 'a+') as lease:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            sys.path.insert(0, str(SHELL))
            from putfile import mem_line
            camera = Camera(mem_line)
            run(camera, report)
    except Exception as error:
        report.update(status='failed', error=str(error))
    finally:
        if camera:
            report['transcript'] = camera.transcript
        for path in (Path(__file__), Path(__file__).with_name('native_mode_trial.py'),
                     Path(__file__).with_name('native_controls_trial.py')):
            (args.output / path.name).write_bytes(path.read_bytes())
        report['probe_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(report['status'])
    raise SystemExit(0 if report['status'] == 'read-only-output-metadata-complete' else 1)
