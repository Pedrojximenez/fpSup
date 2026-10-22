#!/usr/bin/env python3
"""Bounded SIGMA fp 5.02 native color-mode experiment, restoring original mode.

Uses native shell getters/SetColorMode only: no injected code, direct RAM write,
capture key, recording, persistent-save command or card deployment. Register
reads are sequential, not an atomic frame snapshot. Physical ISP context is
not inferred from the bank number. Default invocation is offline.
"""
import argparse
from contextlib import contextmanager
import datetime as dt
import fcntl
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
ROM_PATH = ROOT / 'out/MAIN_c0000000.bin'
SHELL = ROOT / 'fpSup/fp_usb_shell'
MODES = ((12, 'OFF'), (0, 'Standard'), (6, 'TealOrange'),
         (9, 'FOVBlue'), (13, 'PowderBlue'))
BANK_OFFSETS = (0, 0x30000)  # C07D4360: checked against ROM and camera.
REGIONS = (
    ('IGAMMA', 0x30210C70, 16), ('RGBLMAT', 0x30210CB0, 26),
    ('PSTIGAM', 0x30210D18, 14), ('GAMDEC', 0x30210D50, 35),
    ('GAM_BAS', 0x30210DDC, 34), ('YCMAT', 0x30210E64, 20),
    ('GAM_TABLE_SBUS', 0x30210EB4, 11), ('RGBMAT_PL', 0x30210EE0, 9),
    ('Y_GAMMA', 0x30210F08, 20), ('APSUP', 0x30210FBC, 20),
    ('SHOOT_G', 0x30211014, 4),
    ('CUVAREA', 0x30211024, 17), ('CUVCONT', 0x30211068, 8),
    ('CSUP', 0x30211088, 12), ('ECSUP', 0x302110B8, 2),
    ('C_SAT_C', 0x3021127C, 24), ('DHAZ', 0x302112E4, 21),
    ('TNCR', 0x30211338, 21), ('CEQ_YGAM', 0x30212140, 18),
    ('CEQ_CLIP', 0x30212228, 63), ('CEQ_Y_GAMMA', 0x30212324, 18),
)
DISPLAY_REGIONS = (
    ('DISPLAY_CSC_1', 0x30190800, 16), ('DISPLAY_CSC_0', 0x30190860, 16),
    ('DISPLAY_GAMMA_A', 0x30190940, 12), ('DISPLAY_CSC_2', 0x30190C70, 16),
    ('DISPLAY_GAMMA_B', 0x30190CB0, 12),
)
IDENTITY = ((0xC010BAF0, 8), (0xC005C958, 8), (0xC03FE100, 8),
            (0xC0075CF4, 1), (0xC0313244, 1),
            (0xC07D4360, 2), (0xC0BAC2F8, 1))


def decode_reply(answer):
    if answer.startswith('OKX '):
        try:
            return bytes.fromhex(answer[4:].strip()).decode('latin1')
        except ValueError as error:
            raise RuntimeError('malformed hexadecimal reply') from error
    if answer.startswith('OK '):
        return answer[3:].replace('\\n', '\n')
    raise RuntimeError('shell failed or reply uncertain: ' + answer)


def parse_words(reply, address, count):
    pairs = re.findall(r'A:0x([0-9A-Fa-f]+),\s*D:0x([0-9A-Fa-f]+)', reply)
    got = {int(a, 16): int(v, 16) for a, v in pairs}
    want = list(range(address, address + 4 * count, 4))
    if len(pairs) != count or set(got) != set(want):
        raise RuntimeError(f'incomplete or mismatched memory reply at {address:08X}')
    return [got[a] for a in want]


class Camera:
    def __init__(self, transport):
        self.transport = transport
        self.transcript = []
        self.expected_boot = None

    def request(self, command):
        answer = self.transport(command, timeout=5)
        self.transcript.append({'time_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                                'command': command, 'reply': answer})
        return answer

    def sh(self, command):
        return decode_reply(self.request('TMO 1500 SHL ' + command)).strip()

    def words(self, address, count):
        # Native textual replies have a bounded capture buffer. Each 8-word
        # chunk must be complete by itself; never merge partial retry replies.
        result = []
        for offset in range(0, count, 8):
            chunk_address = address + offset * 4
            chunk_count = min(8, count - offset)
            result.extend(parse_words(self.sh(
                f'mem get 0x{chunk_address:08X},,0x{chunk_count * 4:X}'),
                chunk_address, chunk_count))
        return result

    def integer(self, command):
        text = self.sh(command)
        values = re.findall(r'(?:^|->\s*)(\d+)\s*$', text)
        if len(values) != 1:
            raise RuntimeError('unrecognized integer reply: ' + text)
        return int(values[0])

    def idle(self):
        if self.integer('status get is_recording') != 0:
            raise RuntimeError('camera is recording; refusing color-mode trial')

    def status(self):
        answer = self.request('STATUS')
        if (not answer.startswith('OK name=fpshd ') or 'camera=open' not in answer
                or 'quarantine=0' not in answer or 'fault=none' not in answer):
            raise RuntimeError('daemon/transport preflight rejected: ' + answer)
        return answer

    def set_mode(self, mode):
        if self.expected_boot is not None and self.words(0xC072F6F8, 1)[0] != self.expected_boot:
            raise RuntimeError('camera rebooted; refusing setter in a different boot')
        self.idle()
        self.sh(f'menu SetColorMode {mode}')  # one attempt, no replay of an uncertain setter
        time.sleep(1.0)
        if self.integer('menu SetColorMode') != mode:
            raise RuntimeError('color mode readback mismatch')


@contextmanager
def restore_mode(camera, original, report, expected_boot=None):
    # An absolute native setter is restored even if the trial setter's reply
    # was lost. A quarantined transport must be resolved first, not bypassed.
    try:
        yield
    finally:
        report['restore_attempted'] = True
        try:
            camera.status()
            if expected_boot is not None and camera.words(0xC072F6F8, 1)[0] != expected_boot:
                raise RuntimeError('camera rebooted; refusing restore in a different boot')
            camera.set_mode(original)
            report['restored_color_mode'] = camera.integer('menu SetColorMode')
            report['mode_restored'] = report['restored_color_mode'] == original
        except Exception as error:
            report['mode_restored'] = False
            report['restore_error'] = str(error)
            raise


def state(camera):
    return {'color_mode': camera.integer('menu SetColorMode'),
            'app_current': camera.integer('status get app_current'),
            'is_recording': camera.integer('status get is_recording'),
            'stored_record_mode': camera.words(0xC31C01B0, 1)[0],
            'applied_record_mode': camera.words(0xC31F86E0, 1)[0],
            'relative_gain': camera.words(0xC343B5A0, 1)[0],
            'boot_id': camera.words(0xC072F6F8, 1)[0]}


def snapshot(camera, expected_mode):
    before = state(camera)
    if before['color_mode'] != expected_mode or before['is_recording']:
        raise RuntimeError('snapshot precondition changed')
    regions = {}
    for bank, offset in enumerate(BANK_OFFSETS):
        for name, address, count in REGIONS:
            key = f'bank{bank}_{name}'
            regions[key] = {'address': hex(address + offset),
                            'words': camera.words(address + offset, count)}
    for name, address, count in DISPLAY_REGIONS:
        regions[name] = {'address': hex(address), 'words': camera.words(address, count)}
    after = state(camera)
    if before != after:
        raise RuntimeError('snapshot state changed across sequential reads')
    return {'state_before': before, 'state_after': after, 'regions': regions,
            'atomic': False, 'pixel_effect_verified': False}


def differences(reference, sample):
    result = {}
    for name, region in sample['regions'].items():
        old = reference['regions'][name]['words']
        changed = [{'address': hex(int(region['address'], 16) + i * 4),
                    'before': hex(a), 'after': hex(b)}
                   for i, (a, b) in enumerate(zip(old, region['words'])) if a != b]
        if changed:
            result[name] = changed
    return result


def run(camera, report, modes=MODES, samples_per_mode=1):
    rom = ROM_PATH.read_bytes()
    report['source_rom_sha256'] = hashlib.sha256(rom).hexdigest()
    report['daemon'] = camera.status()
    camera.idle()
    report['identity'] = []
    for address, count in IDENTITY:
        got = camera.words(address, count)
        expected = list(struct.unpack_from('<' + 'I' * count, rom, address - 0xC0000000))
        report['identity'].append({'address': hex(address), 'words': got, 'matches_rom': got == expected})
        if got != expected:
            raise RuntimeError(f'unknown color/shell hook or firmware at {address:08X}; no setter executed')
    original = state(camera)
    report['original_state'] = original
    if original['color_mode'] not in range(16) or not original['boot_id']:
        raise RuntimeError('unknown/private original color state; no setter executed')
    camera.expected_boot = original['boot_id']
    report['samples'] = []
    with restore_mode(camera, original['color_mode'], report, original['boot_id']):
        for mode, name in modes:
            camera.set_mode(mode)
            sample = snapshot(camera, mode)
            sample['name'] = name
            report['samples'].append(sample)
            sample['repeat_snapshots'] = []
            for _ in range(samples_per_mode - 1):
                repeated_mode = snapshot(camera, mode)
                repeated_mode['diff_from_first'] = differences(sample, repeated_mode)
                sample['repeat_snapshots'].append(repeated_mode)
            changes = differences(report['samples'][0], sample)
            sample['diff_from_off'] = changes
            print(f'{name}: {len(changes)} changed blocks, '
                  f'{sum(len(v) for v in changes.values())} words', flush=True)
        camera.set_mode(12)
        repeated = snapshot(camera, 12)
        report['off_repeat'] = repeated
        report['off_repeat_diff'] = differences(report['samples'][0], repeated)
    report['final_state'] = state(camera)
    if report['final_state'] != original:
        raise RuntimeError('camera state differs after restoration')
    report['status'] = 'native-color-mode-trial-complete'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-live-native-modes', action='store_true')
    parser.add_argument('--all-native-modes', action='store_true',
                        help='OFF reference followed by every native enum 0..15')
    parser.add_argument('--samples-per-mode', type=int, choices=(1, 2, 3), default=1)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if not args.run_live_native_modes:
        parser.error('explicit --run-live-native-modes required; no camera access occurred')
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    report = {'status': 'started', 'camera_setting_changes': [],
              'direct_camera_memory_writes': False, 'injected_code': False,
              'recording_started': False, 'card_deployment': False}
    camera = None
    try:
        # Cooperates with current AF tools and prevents this trial being run twice.
        with open('/tmp/fp-af-fusion.lock', 'a+') as lease:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            sys.path.insert(0, str(SHELL))
            from putfile import mem_line
            camera = Camera(mem_line)
            modes = MODES
            if args.all_native_modes:
                names = dict(MODES)
                modes = ((12, 'OFF'),) + tuple(
                    (mode, names.get(mode, f'native_enum_{mode}'))
                    for mode in range(16) if mode != 12)
            run(camera, report, modes, args.samples_per_mode)
    except Exception as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        print(str(error), file=sys.stderr)
    finally:
        if camera is not None:
            report['transcript'] = camera.transcript
            report['camera_setting_changes'] = [entry['command'] for entry in camera.transcript
                if re.fullmatch(r'TMO 1500 SHL menu SetColorMode \d+', entry['command'])]
        report['probe_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        (out / 'native_mode_trial.py').write_bytes(Path(__file__).read_bytes())
        (out / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    return 0 if report['status'] == 'native-color-mode-trial-complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
