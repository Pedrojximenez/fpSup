#!/usr/bin/env python3
"""One diagnostic native-ring read through existing MEM1, never a frame lease.

No ARM injection, allocation, cache flush, image writes, setters or file I/O on
camera. A temporary read-only transport window is verified and revoked. The
producer remains running: bytes may tear and cannot calibrate pixel fidelity.
"""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
from pathlib import Path
import sys

from native_mode_trial import Camera, ROOT, SHELL, state
from native_controls_trial import controls

RING = (0x49801000, 0x49BFD000, 0x49FF9000, 0x4A3F5000)
SPAN = 0x3FC000
SLOT = 7


def guarded_state(camera, expected=None):
    camera.status()
    value = state(camera)
    if (not value['boot_id'] or value['app_current'] != 2 or value['is_recording']
            or expected is not None and value != expected):
        raise RuntimeError('CINE standby/boot/state guard rejected')
    return value


def ring_descriptor(camera):
    words = camera.words(0xC30255B4, 32)
    handles = words[9:13]
    if words[0] != 0 or words[8] != 4 or tuple(0x40000000 + 4 * h for h in handles) != RING:
        raise RuntimeError('unexpected native preview ring')
    if not (0 < words[3] <= 1920 and 0 < words[4] <= 1088):
        raise RuntimeError('unexpected native preview geometry')
    return {'address': '0xC30255B4', 'words': words, 'width': words[3], 'height': words[4]}


def read_once(camera, api, report):
    original = guarded_state(camera)
    original_controls = controls(camera)
    descriptor = ring_descriptor(camera)
    caps = api.mem_caps(refresh=True)
    if not caps or caps['xfer'] < SPAN or len(caps['windows']) != 8:
        raise RuntimeError('MEM1 required; no legacy fallback permitted')
    if tuple(caps['windows'][SLOT]) != (0, 0, 0):
        raise RuntimeError('transport window already owned; refusing to borrow')
    report.update(original_state=original, original_controls=original_controls,
                  descriptor=descriptor, mem_caps_before=caps)
    granted = (RING[0], SPAN, 1)
    touched = False
    data = None
    try:
        guarded_state(camera, original)
        # Mark touched before the request: a missing reply is an uncertain grant.
        touched = True
        api.mem_window(SLOT, *granted)
        actual = api.mem_caps(refresh=True)
        if tuple(actual['windows'][SLOT]) != granted:
            raise RuntimeError('read-only window grant mismatch')
        guarded_state(camera, original)
        if controls(camera) != original_controls:
            raise RuntimeError('colour controls changed before pixel read')
        data = api.mem_read(RING[0], SPAN, sync=False, label='preview diagnostic')
        if len(data) != SPAN:
            raise RuntimeError('incomplete native ring read')
        report['raw_sha256'] = hashlib.sha256(data).hexdigest()
        report['raw_bytes'] = len(data)
    finally:
        if touched:
            # Only revoke our exact tuple, never somebody else's window.
            camera.status()
            current = api.mem_caps(refresh=True)
            if current is None:
                raise RuntimeError('transport window state uncertain')
            window = tuple(current['windows'][SLOT])
            if window == granted:
                api.mem_window(SLOT, 0, 0, 0)
            elif window != (0, 0, 0):
                raise RuntimeError('transport window owner changed; refusing revoke')
            after = api.mem_caps(refresh=True)
            report['mem_caps_after'] = after
            report['read_window_revoked'] = tuple(after['windows'][SLOT]) == (0, 0, 0)
            if not report['read_window_revoked']:
                raise RuntimeError('transport window revocation not verified')
    report['final_state'] = guarded_state(camera, original)
    report['final_controls'] = controls(camera)
    if report['final_controls'] != original_controls:
        raise RuntimeError('colour controls changed during native ring read')
    report['state_unchanged'] = True
    report['status'] = 'diagnostic-native-ring-read-complete'
    return data


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-live-read-only', action='store_true')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if not args.run_live_read_only:
        parser.error('explicit live read flag required')
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'started', 'date_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'source_address': hex(RING[0]), 'atomic_frame': False, 'producer_frozen': False,
              'frame_lease_owned': False, 'pixel_format_verified': False,
              'camera_image_writes': False, 'camera_card_writes': False,
              'injected_code': False, 'camera_cache_flush': False,
              'transport_read_window_temporarily_modified': True}
    camera, raw = None, None
    try:
        with open('/tmp/fp-af-fusion.lock', 'a+') as lease:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            sys.path.insert(0, str(SHELL))
            import putfile
            camera = Camera(putfile.mem_line)
            raw = read_once(camera, putfile, report)
    except Exception as error:
        report.update(status='failed', error=str(error))
    finally:
        if camera:
            report['transcript'] = camera.transcript
        if raw is not None:
            (args.output / 'native-ring.bin').write_bytes(raw)
        for path in (Path(__file__), Path(__file__).with_name('native_mode_trial.py'),
                     Path(__file__).with_name('native_controls_trial.py')):
            (args.output / path.name).write_bytes(path.read_bytes())
        report['probe_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        report['putfile_sha256'] = hashlib.sha256((SHELL / 'putfile.py').read_bytes()).hexdigest()
        (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(report['status'])
    raise SystemExit(0 if report['status'] == 'diagnostic-native-ring-read-complete' else 1)
