#!/usr/bin/env python3
"""Bounded read-only CINE display route and producer/consumer index audit.

No framebuffer payload, native function call, setter, memory write or injection.
Sequential metadata cannot grant a frame lease or establish pixel colourimetry.
"""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
from pathlib import Path
import struct
import sys

from native_mode_trial import Camera, ROOT, ROM_PATH, SHELL, IDENTITY, state, DISPLAY_REGIONS
from native_controls_trial import controls

ROM_SHA256 = '92a8ee993f6c3d66c251e88d45a2ccd5135c6cf7342717784321c2ed506e2fb4'
CODE = (0xC00DEA80, 0xC00E4858, 0xC00E4648, 0xC00E4830,
        0xC00DD6C8, 0xC00E60C0, 0xC00E3948,
        0xC0182228, 0xC01822B8, 0xC01D7638, 0xC0429560)
REGIONS = (
    ('DISPLAY_ROUTE_IDS', 0xC31D2858, 1),
    ('DISPLAY_RANGE_SELECTORS', 0xC2EFC388, 2),
    ('DISPLAY_OUTPUT_KIND', 0x30190004, 1),
    ('DISPLAY_COMPOSITE_KIND', 0x301902C0, 1),
    ('DISPLAY_SCANOUT_INDICES', 0x30192020, 2),
    ('OUTPUT_PROFILE_SELECTORS', 0xC31DF8D8, 3),
    ('OUTPUT_TARGET_SELECTORS', 0xC31DF8E4, 3),
    ('SIGSEQ_OUTPUT_0', 0xC30255B4, 32),
    ('ACTIVE_OUTPUT_0', 0xC30254B4, 32),
    ('ACTIVE_OUTPUT_1', 0xC3025534, 32),
    ('NEXT_OUTPUT_SELECTION', 0xC3025524, 4),
    ('NEXT_OUTPUT_SELECTION_1', 0xC30255A4, 4),
    ('SECOND_DEVELOP_DESCRIPTOR', 0xC375C094, 12),
    ('WRITER_INDEX_2', 0x301832E8, 1),
    ('WRITER_INDEX_3', 0x301833E8, 1),
    ('WRITER_INDEX_4', 0x301834E8, 1),
    ('WRITER_INDEX_5', 0x301835E8, 1),
    ('WRITER_INDEX_6', 0x301836E8, 1),
    ('WRITER_INDEX_8', 0x301837E8, 1),
    ('LCD_MATRIX_CACHE_A', 0xC2EFEC6C, 7),
    ('LCD_MATRIX_CACHE_A_6', 0xC31D7154, 1),
    ('LCD_MATRIX_CACHE_A_8', 0xC31D7158, 1),
    ('LCD_MATRIX_CACHE_B', 0xC2EFEDE8, 7),
    ('LCD_MATRIX_CACHE_B_6', 0xC31D716C, 1),
    ('LCD_MATRIX_CACHE_B_8', 0xC31D7168, 1),
    ('LCD_MATRIX_PENDING', 0xC31D7170, 1),
) + DISPLAY_REGIONS


def require_state(current, original=None):
    if (current['app_current'] != 2 or current['is_recording'] != 0
            or current['stored_record_mode'] != 1 or current['applied_record_mode'] != 1
            or not current['boot_id']):
        raise RuntimeError('requires known-boot CINE standby')
    if original is not None and current != original:
        raise RuntimeError('camera state or boot changed during route audit')


def run(camera, report):
    camera.status()
    camera.idle()
    original, original_controls = state(camera), controls(camera)
    report.update(original_state=original, original_controls=original_controls, samples=[])
    require_state(original)
    rom = ROM_PATH.read_bytes()
    if hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise RuntimeError('unexpected local firmware image')
    for address, count in list(IDENTITY) + [(a, 8) for a in CODE]:
        expected = list(struct.unpack_from('<' + 'I' * count, rom, address - 0xC0000000))
        if camera.words(address, count) != expected:
            raise RuntimeError('unexpected native code or hook at ' + hex(address))
    for _ in range(3):
        require_state(state(camera), original)
        if controls(camera) != original_controls:
            raise RuntimeError('colour controls changed before route read')
        regions = {name: {'address': hex(address), 'words': camera.words(address, count)}
                   for name, address, count in REGIONS}
        require_state(state(camera), original)
        if controls(camera) != original_controls:
            raise RuntimeError('colour controls changed across route read')
        report['samples'].append({'regions': regions, 'atomic': False})
    camera.status()
    report['final_state'], report['final_controls'] = state(camera), controls(camera)
    require_state(report['final_state'], original)
    if report['final_controls'] != original_controls:
        raise RuntimeError('final colour controls changed')
    report.update(status='read-only-live-route-complete', unchanged=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-live-read-only', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.run_live_read_only:
        parser.error('explicit live read-only flag required')
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'started', 'date_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'camera_writes': False, 'pixel_data_read': False, 'frame_lease_owned': False,
              'cube_deployed': False, 'pixel_formula_verified': False,
              'source_rom_sha256': ROM_SHA256}
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
        paths = [Path(__file__), Path(__file__).with_name('native_mode_trial.py'),
                 Path(__file__).with_name('native_controls_trial.py')]
        report['source_sha256'] = {}
        for path in paths:
            data = path.read_bytes()
            (args.output / path.name).write_bytes(data)
            report['source_sha256'][path.name] = hashlib.sha256(data).hexdigest()
        (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(report['status'])
    return 0 if report['status'] == 'read-only-live-route-complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
