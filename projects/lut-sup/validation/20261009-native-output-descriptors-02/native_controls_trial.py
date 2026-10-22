#!/usr/bin/env python3
"""Bounded native colour-parameter study; no injection, capture or recording.

Uses stock menu setters, captures both ISP shadows and fixed tone descriptors,
then restores each touched mode's own settings and the starting mode. Sequential
register reads are not frame snapshots or proof of pixel effects. Fill Light is
excluded from this CINE study: the stock manual defines it as STILL-only.
"""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import time

from native_mode_trial import Camera, ROOT, ROM_PATH, SHELL, IDENTITY, state

MAP_PATH = ROOT / 'research/imaging-hw/isp-colour-blocks-20260927/isp-map.json'
CONTROL_HANDLERS = {
    'SetColorModeEffect': 0xC03FE170,
    'SetColorModeContrast': 0xC03FE1F0,
    'SetColorModeSaturation': 0xC03FE2F0,
    'SetToneControlMode': 0xC03FE460,
    'SetToneManualHighlight': 0xC03FE4D0,
    'SetToneManualShadow': 0xC03FE540,
}
MODE_CONTROLS = tuple(CONTROL_HANDLERS)[:3]
GLOBAL_CONTROLS = tuple(CONTROL_HANDLERS)[3:]
PLANS = (
    (0, 'Standard', (
        ('contrast_low', {'SetColorModeContrast': -5}),
        ('contrast_high', {'SetColorModeContrast': 5}),
        ('saturation_low', {'SetColorModeSaturation': -5}),
        ('saturation_high', {'SetColorModeSaturation': 5}),
        ('tone_auto_mild', {'SetToneControlMode': 1}),
        ('tone_auto_strong', {'SetToneControlMode': 2}),
        ('highlight_low', {'SetToneControlMode': 3, 'SetToneManualHighlight': -5}),
        ('highlight_high', {'SetToneControlMode': 3, 'SetToneManualHighlight': 5}),
        ('shadow_low', {'SetToneControlMode': 3, 'SetToneManualShadow': -5}),
        ('shadow_high', {'SetToneControlMode': 3, 'SetToneManualShadow': 5}),
    )),
    (6, 'TealOrange', (
        ('effect_low', {'SetColorModeEffect': -5}),
        ('effect_high', {'SetColorModeEffect': 5}),
    )),
    (13, 'PowderBlue', (
        ('effect_low', {'SetColorModeEffect': -5}),
        ('effect_high', {'SetColorModeEffect': 5}),
    )),
)
EXTRA_REGIONS = (
    ('TONE_CONTEXT0_POINTER', 0xC3414510, 1),
    ('TONE_CONTEXT1_POINTER', 0xC3414608, 1),
    ('TONE_CACHED_DESCRIPTOR', 0xC3414D58, 20),
    ('LINEAR_DEVELOP_DESCRIPTOR', 0xC375C05C, 20),
)


def scalar(text):
    text = text.strip()
    if not re.fullmatch(r'-?\d+', text):
        raise RuntimeError('unexpected native scalar reply: ' + text)
    return int(text)


def check_boot(camera, boot):
    camera.status()
    if camera.words(0xC072F6F8, 1)[0] != boot:
        raise RuntimeError('different boot; refusing native control write')
    camera.idle()


def controls(camera):
    return {name: scalar(camera.sh('menu ' + name)) for name in CONTROL_HANDLERS}


def set_control(camera, name, value, boot, settle=0.15):
    if name not in CONTROL_HANDLERS:
        raise ValueError('unreviewed control')
    if (name == 'SetToneControlMode' and value not in range(4)
            or name != 'SetToneControlMode' and value not in range(-5, 6)):
        raise ValueError('outside reviewed native range')
    check_boot(camera, boot)
    camera.sh(f'menu {name} {value}')  # exactly one attempt
    if settle:
        time.sleep(settle)
    actual = scalar(camera.sh('menu ' + name))
    if actual != value:
        raise RuntimeError(f'{name}: requested {value}, got {actual}')


def restore_values(camera, original, boot):
    # Restore highlight/shadow before re-enabling the saved tone mode.
    order = MODE_CONTROLS + ('SetToneManualHighlight', 'SetToneManualShadow',
                             'SetToneControlMode')
    current = controls(camera)
    for name in order:
        if current[name] != original[name]:
            set_control(camera, name, original[name], boot)
    if controls(camera) != original:
        raise RuntimeError('native control restoration mismatch')


def regions():
    data = json.loads(MAP_PATH.read_text())
    wanted = ('MAT_TOP ', 'GAM_TOP ', 'PST_TOP ', 'YMED_TOP C_SAT_C', 'CEQ',
              'DHAZ', 'TNCR')
    result = {}
    for route in data['routes']:
        if not route['name'].startswith(wanted):
            continue
        for mapping in route['mappings']:
            address = int(mapping['shadow_start'], 16)
            count = mapping['words']
            for bank, offset in enumerate((0, 0x30000)):
                key = f'bank{bank}_{route["name"]}_{address:08X}'
                result[key] = (address + offset, count)
    from native_mode_trial import DISPLAY_REGIONS
    for name, address, count in DISPLAY_REGIONS + EXTRA_REGIONS:
        result[name] = (address, count)
    return result


def capture(camera, boot, samples, region_map):
    batch = []
    for _ in range(samples):
        before = state(camera)
        control_before = controls(camera)
        if before['boot_id'] != boot or before['is_recording']:
            raise RuntimeError('capture precondition changed')
        values = {name: {'address': hex(address), 'words': camera.words(address, count)}
                  for name, (address, count) in region_map.items()}
        if state(camera) != before or controls(camera) != control_before:
            raise RuntimeError('state changed across sequential register capture')
        batch.append({'state': before, 'controls': control_before, 'regions': values,
                      'atomic': False, 'pixel_effect_verified': False})
    return batch


def stable_differences(before, changed, after):
    result = {}
    for name, region in changed[0]['regions'].items():
        differences = []
        for i in range(len(region['words'])):
            refs = [s['regions'][name]['words'][i] for s in before + after]
            tests = [s['regions'][name]['words'][i] for s in changed]
            if len(set(refs)) == len(set(tests)) == 1 and refs[0] != tests[0]:
                differences.append({'address': hex(int(region['address'], 16) + i * 4),
                                    'before': hex(refs[0]), 'after': hex(tests[0])})
        if differences:
            result[name] = differences
    return result


def group(camera, mode, name, plan, boot, report, sample_count, region_map):
    check_boot(camera, boot)
    camera.set_mode(mode)
    saved = controls(camera)
    row = {'mode': mode, 'name': name, 'original_controls': saved, 'conditions': [],
           'controls_restored': False}
    report['groups'].append(row)
    try:
        # A normalized baseline makes each condition comparable without
        # overwriting the user's saved per-mode values on exit.
        baseline = {key: 0 for key in saved}
        restore_values(camera, baseline, boot)
        time.sleep(1)
        reference = capture(camera, boot, sample_count, region_map)
        for label, changes in plan:
            condition = {'label': label, 'changes': changes}
            row['conditions'].append(condition)
            try:
                for key, value in changes.items():
                    set_control(camera, key, value, boot)
                time.sleep(1)
                condition['changed'] = capture(camera, boot, sample_count, region_map)
            finally:
                check_boot(camera, boot)
                restore_values(camera, baseline, boot)
            time.sleep(1)
            condition['baseline_before'] = reference
            condition['baseline_after'] = capture(camera, boot, sample_count, region_map)
            condition['stable_changes'] = stable_differences(
                reference, condition['changed'], condition['baseline_after'])
            reference = condition['baseline_after']
            print(f'{name}/{label}: {len(condition["stable_changes"])} stable regions', flush=True)
    except Exception as error:
        row['error'] = str(error)
        raise
    finally:
        try:
            check_boot(camera, boot)
            if scalar(camera.sh('menu SetColorMode')) != mode:
                raise RuntimeError('mode changed; refusing to restore another mode values')
            restore_values(camera, saved, boot)
            row['controls_restored'] = True
        except Exception as error:
            row['restore_error'] = str(error)
            raise


def run(camera, report, sample_count=3):
    rom = ROM_PATH.read_bytes()
    camera.status()
    camera.idle()
    checks = list(IDENTITY) + [(a, 8) for a in CONTROL_HANDLERS.values()]
    for address, count in checks:
        expected = list(struct.unpack_from('<' + 'I' * count, rom, address - 0xC0000000))
        if camera.words(address, count) != expected:
            raise RuntimeError(f'unknown firmware or hook at {address:08X}; no setter executed')
    original = state(camera)
    original_controls = controls(camera)
    boot = original['boot_id']
    if original['app_current'] != 2 or not boot:
        raise RuntimeError('requires known CINE standby')
    for key, value in original_controls.items():
        if value not in (range(4) if key == 'SetToneControlMode' else range(-5, 6)):
            raise RuntimeError('unrecognized original control value')
    camera.expected_boot = boot
    report.update(original_state=original, original_controls=original_controls,
                  groups=[], region_map={n: [hex(a), c] for n, (a, c) in regions().items()})
    try:
        for mode, name, plan in PLANS:
            group(camera, mode, name, plan, boot, report, sample_count, regions())
    finally:
        check_boot(camera, boot)
        camera.set_mode(original['color_mode'])
        if controls(camera) != original_controls:
            restore_values(camera, original_controls, boot)
        report['final_state'] = state(camera)
        report['final_controls'] = controls(camera)
        if report['final_state'] != original or report['final_controls'] != original_controls:
            raise RuntimeError('final restoration mismatch')
        report['original_state_restored'] = True
        report['restored'] = all(g['controls_restored'] for g in report['groups'])
    report['status'] = 'native-controls-study-complete'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-live-native-controls', action='store_true')
    parser.add_argument('--samples', type=int, choices=(2, 3), default=3)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if not args.run_live_native_controls:
        parser.error('explicit live flag required; no camera access occurred')
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'started', 'date_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'injected_code': False, 'direct_memory_writes': False,
              'recording_started': False, 'card_write': False, 'restored': False,
              'source_rom_sha256': hashlib.sha256(ROM_PATH.read_bytes()).hexdigest(),
              'source_map_sha256': hashlib.sha256(MAP_PATH.read_bytes()).hexdigest()}
    camera = None
    try:
        with open('/tmp/fp-af-fusion.lock', 'a+') as lease:
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            sys.path.insert(0, str(SHELL))
            from putfile import mem_line
            camera = Camera(mem_line)
            run(camera, report, args.samples)
    except Exception as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        print(str(error), file=sys.stderr)
    finally:
        if camera:
            report['transcript'] = camera.transcript
        for path in (Path(__file__), Path(__file__).with_name('native_mode_trial.py')):
            (output / path.name).write_bytes(path.read_bytes())
        report['probe_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return 0 if report['status'] == 'native-controls-study-complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
