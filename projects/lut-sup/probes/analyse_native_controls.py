#!/usr/bin/env python3
"""Recompute native control evidence; never treat shadow words as pixels."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from native_controls_trial import stable_differences

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'fpSup/lut'))
from native_ceq import CEQResource


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def analyse(path):
    path = path.resolve()
    data = json.loads(path.read_text())
    if data['status'] != 'native-controls-study-complete' or not data['restored']:
        raise ValueError('incomplete native trial')
    if digest(path.parent / 'native_controls_trial.py') != data['probe_sha256']:
        raise ValueError('executed probe provenance mismatch')
    if digest(ROOT / 'out/MAIN_c0000000.bin') != data['source_rom_sha256']:
        raise ValueError('firmware provenance mismatch')
    if digest(ROOT / 'research/imaging-hw/isp-colour-blocks-20260927/isp-map.json') != data['source_map_sha256']:
        raise ValueError('register map provenance mismatch')
    rows, refused, resources, linear = [], [], {}, []
    valid_count = 0
    for group in data['groups']:
        for condition in group['conditions']:
            changes = stable_differences(condition['baseline_before'], condition['changed'],
                                         condition['baseline_after'])
            if changes != condition['stable_changes']:
                raise ValueError('recorded stable differences disagree with raw observations')
            pointer = condition['changed'][0]['regions']['TONE_CONTEXT0_POINTER']['words'][0]
            row = {'mode': group['mode'], 'mode_name': group['name'],
                   'condition': condition['label'], 'requested': condition['changes'],
                   'stable_changed_regions': {k: len(v) for k, v in changes.items()},
                   'tone_context0_pointer': hex(pointer), 'ceq_samples': []}
            for index, sample in enumerate(condition['changed']):
                words = sample['regions']['LINEAR_DEVELOP_DESCRIPTOR']['words']
                linear.append({'mode': group['mode'], 'condition': condition['label'],
                               'sample': index, 'width': words[4], 'height': words[5],
                               'base': hex(words[7])})
                for context in (0, 1):
                    try:
                        resource = CEQResource.from_snapshot(sample['regions'], context)
                    except ValueError as error:
                        refused.append({'mode': group['mode'], 'condition': condition['label'],
                                        'sample': index, 'context': context, 'reason': str(error)})
                        continue
                    binary = resource.to_bytes()
                    sha = hashlib.sha256(binary).hexdigest()
                    resources[sha] = {**resource.summary(), 'source_hex': binary.hex()}
                    row['ceq_samples'].append({'sample': index, 'context': context, 'sha256': sha})
                    valid_count += 1
            rows.append(row)
    return {'trial': str(path.relative_to(ROOT)), 'trial_sha256': digest(path),
            'source_rom_sha256': data['source_rom_sha256'],
            'analysis_sha256': digest(Path(__file__)),
            'ceq_decoder_sha256': digest(ROOT / 'fpSup/lut/native_ceq.py'),
            'evidence_kind': 'native_configuration_measurement',
            'pixel_effect_verified': False, 'cube_deployed': False,
            'atomic_frame_snapshot': False, 'restored': data['restored'],
            'final_state': data['final_state'], 'final_controls': data['final_controls'],
            'conditions': rows, 'valid_ceq_sample_contexts': valid_count,
            'refused_ceq_samples': refused, 'unique_ceq_resources': resources,
            'linear_descriptor_samples': linear,
            'linear_full_colour_source_available': any(v['base'] != '0x0' and v['width'] and v['height']
                                                      for v in linear),
            'conclusions': [
                'TealOrange/PowderBlue effect couples matrices, CEQ anchors and native tone pointers.',
                'Manual highlight/shadow produces stable CEQ YGAM configuration differences.',
                'Contrast/saturation/auto tone produced no stable differences in sampled regions; capability is unresolved.',
                'CEQ source layout is six planes of 24 u16 entries, split 16+8; plane B scales by four.',
                'One unrepresentable transient CEQ word is refused; it is not converted to deployable bytes.',
                'CEQ channel semantics, interpolation, pipeline ordering, clamp and pixel fidelity remain unmeasured.',
                'Native tone RAM is owned by firmware; it is not a free LUT staging buffer.',
            ]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trial', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    summary = analyse(args.trial)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(f"{len(summary['conditions'])} conditions, {summary['valid_ceq_sample_contexts']} valid CEQ observations, "
          f"{len(summary['refused_ceq_samples'])} refused; pixel verification pending")
