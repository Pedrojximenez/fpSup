#!/usr/bin/env python3
"""Prepare known cube-domain RGB and full-cube targets; no camera execution.

These numeric samples are not Bayer, YUYV, an optical chart or calibrated fp
input. Native trials must first establish the input conversion and owned job.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'fpSup/lut'))
from cube import Cube


def rgb_grid(axis):
    b, g, r = np.meshgrid(axis, axis, axis, indexing='ij')
    return np.stack((r, g, b), axis=-1).reshape(-1, 3)


def prepare(cube_path, output, input_space, output_space):
    cube = Cube.read(cube_path)
    if cube.table1d is not None or cube.table3d is None:
        raise ValueError('this trial pack requires a pure 3D cube with an explicit input domain')
    if not input_space.strip() or not output_space.strip():
        raise ValueError('explicit input/output colour spaces required')
    low, high = map(np.asarray, cube.range3d)
    ramp = np.linspace(0, 1, 513)
    groups = [('fit_lattice_17', rgb_grid(np.linspace(0, 1, 17)), 'fit'),
              ('holdout_cell_centres_16', rgb_grid((np.arange(16) + .5) / 16), 'holdout'),
              ('neutral_ramp_513', np.repeat(ramp[:, None], 3, axis=1), 'diagnostic')]
    for name, colour in [('R', [1, 0, 0]), ('G', [0, 1, 0]), ('B', [0, 0, 1]),
                         ('C', [0, 1, 1]), ('M', [1, 0, 1]), ('Y', [1, 1, 0])]:
        groups.append((name + '_ramp_513', ramp[:, None] * colour, 'diagnostic'))
    groups.append(('holdout_random_2048', np.random.default_rng(20261009).random((2048, 3)), 'holdout'))
    fit = groups[0][1]
    fit_rows = {row.tobytes() for row in fit}
    for name, points, role in groups:
        if role == 'holdout' and any(row.tobytes() in fit_rows for row in points):
            raise ValueError('holdout intersects fitting lattice')
    inputs = np.concatenate([low + p * (high - low) for _, p, _ in groups])
    targets = cube.apply(inputs)
    if not np.isfinite(inputs).all() or not np.isfinite(targets).all():
        raise ValueError('nonfinite trial values')
    output.mkdir(parents=True, exist_ok=False)
    manifest = {'schema': 'fpSup-known-colour-trial-1',
                'date_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                'camera_operations': False, 'executed_on_camera': False,
                'input_space': input_space, 'output_space': output_space,
                'input_is_calibrated_fp_data': False, 'native_input_conversion_verified': False,
                'input_format': 'float64 cube-domain RGB; not a camera buffer',
                'reference': 'full original cube, tetrahedral interpolation, strength 1, no output clamp',
                'source_sha256': cube.sha256, 'sample_count': len(inputs), 'groups': [],
                'hardware_output_provided': False, 'fidelity_measured': False,
                'holdout_disjoint_from_fit_lattice': True,
                'before_native_execution': ['verified colour-input conversion',
                    'owned input/output buffers and native job completion',
                    'exact format/stride/bit depth and original state restoration'],
                'comparison': ['same input sample ID through stock path',
                    'same input sample ID through native fitted matrix/tone',
                    'same input sample ID through native fit plus CPU residual',
                    'compare against target on separate holdout samples'], 'assets': {}}
    start = 0
    for name, points, role in groups:
        manifest['groups'].append({'name': name, 'start': start, 'count': len(points), 'role': role})
        start += len(points)
    for name, array in [('input_rgb_f64.npy', inputs), ('target_rgb_f64.npy', targets)]:
        with (output / name).open('xb') as f:
            np.save(f, array, allow_pickle=False)
        restored = np.load(output / name, allow_pickle=False)
        if not np.array_equal(restored, array):
            raise ValueError('trial asset round trip mismatch')
    (output / 'source.cube').write_bytes(cube.source)
    for name in ('input_rgb_f64.npy', 'target_rgb_f64.npy', 'source.cube'):
        data = (output / name).read_bytes()
        manifest['assets'][name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    manifest['generator_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (output / 'prepare_colour_trial.py').write_bytes(Path(__file__).read_bytes())
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cube', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--input-space', required=True)
    parser.add_argument('--output-space', required=True)
    args = parser.parse_args()
    manifest = prepare(args.cube, args.output, args.input_space, args.output_space)
    print(json.dumps({k: manifest[k] for k in ('sample_count', 'holdout_disjoint_from_fit_lattice',
          'executed_on_camera', 'fidelity_measured')}, indent=2))
