#!/usr/bin/env python3
"""Offline full-cube, native CEQ, residual and live-runner guard validation."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'fpSup/lut'), str(Path(__file__).parent)]

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('refusing to replace validation evidence')
    names = ['test_lut', 'test_native_ceq', 'test_residual', 'test_preview',
             'test_native_mode_trial', 'test_native_controls_trial', 'test_native_preview_bytes',
             'test_native_live_route']
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    paths = [ROOT / 'fpSup/lut' / (name + '.py') for name in
             ('cube', 'dng', 'fplut', 'native_ceq', 'residual', 'preview', 'test_preview',
              'test_lut', 'test_native_ceq', 'test_residual')]
    paths += [Path(__file__).parent / (name + '.py') for name in
              ('native_mode_trial', 'native_controls_trial', 'native_output_descriptors', 'native_preview_bytes',
               'analyse_native_controls', 'analyse_native_preview', 'native_live_route',
               'analyse_live_route', 'prepare_colour_trial', 'test_native_live_route',
               'test_native_mode_trial', 'test_native_controls_trial')]
    paths.append(Path(__file__).parent / 'test_native_preview_bytes.py')
    paths += [Path(__file__), ROOT / 'out/MAIN_c0000000.bin',
              ROOT / 'projects/lut-sup/validation/20261009-native-controls-trial-01/report.json',
              ROOT / 'projects/lut-sup/validation/20261009-native-live-route-01/report.json',
              ROOT / 'projects/lut-sup/validation/20261009-arri-classic-known-inputs-01/manifest.json']
    report = {'date_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
              'status': 'passed' if result.wasSuccessful() and not result.skipped else 'unverified',
              'tests_run': result.testsRun, 'skipped': result.skipped,
              'failures': [str(t) for t, _ in result.failures],
              'errors': [str(t) for t, _ in result.errors],
              'camera_operations': False, 'isp_pixel_emulation': False,
              'ceq_real_firmware_emulation': {'contexts': [0, 1],
                  'expand_thumb_entry': '0xC01084D9', 'route_thumb_entry': '0xC0108C99',
                  'valid_camera_sample_contexts': 83, 'refused_transient_sample_contexts': 1,
                  'code_execution_allowlist': True, 'rom_and_source_read_only': True,
                  'callee_saved_registers_and_stack_checked': True,
                  'instruction_bound_per_call': 10000, 'scaling_mutation_detected': True},
              'residual_pair_provenance': 'synthetic test fixtures; no measured camera RGB pairs',
              'sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    raise SystemExit(0 if report['status'] == 'passed' else 1)
