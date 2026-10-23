#!/usr/bin/env python3
"""Focused, offline validation; parser execution requires working Unicorn JIT."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import build_tiles as B
import test_tiles


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    B.check(not args.out.exists(), 'Use a new validation output directory')
    base = B.ROOT / 'projects/qs-touch'
    sources = [Path(__file__), Path(B.__file__), Path(test_tiles.__file__),
               base / 'core/qs_tiles.c', base / 'core/qs_tiles.h', base / 'tests/test_qs_tiles.c']
    source_hashes = {str(path.relative_to(B.ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in sources}
    page, pool, manifest = B.build()
    args.out.mkdir(parents=True)
    (args.out / 'QS_CINE.fpqs.page').write_bytes(page)
    (args.out / 'QS_CINE.fpqs.strings').write_bytes(pool.data)
    (args.out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    evidence = {'scope': 'Offline resource and C intent controller; no camera or installation', 'checks': []}
    with tempfile.TemporaryDirectory(prefix='fp-qs-tiles-') as temp:
        host = Path(temp) / 'test'
        cflags = ['-std=c11', '-Wall', '-Wextra', '-Werror']
        subprocess.run(['clang', *cflags, '-fsanitize=address,undefined', '-g',
                        str(base / 'core/qs_tiles.c'), str(base / 'tests/test_qs_tiles.c'), '-o', str(host)], check=True)
        result = subprocess.run([str(host)], check=True, capture_output=True, text=True)
        values = {}
        for line in result.stdout.splitlines():
            if line.startswith(('I ', 'T ')):
                kind, name, value = line.split(' ', 2)
                B.check(name not in values, 'Duplicate published variable')
                values[name] = (kind, value)
        B.check(set(values) == set(manifest['variables']), 'C/resource variable namespace mismatch')
        for name, declaration in manifest['variables'].items():
            B.check(values[name][0] == ('I' if declaration['type'] == 'integer' else 'T'), 'Variable type mismatch')
        B.check(values['FPQS_Legacy5'] == ('I', '1') and values['FPQS_FormatOn5'] == ('I', '0'),
                'Unreplaced tile did not remain native')
        B.check(values['FPQS_DCOn2'] == ('I', '1') and values['FPQS_Legacy2'] == ('I', '0'),
                'Custom DC did not replace the native face')
        evidence['checks'].append({'name': 'C sanitizers, routing, feedback and 64-variable contract', 'passed': True})
        subprocess.run(['clang', '-target', 'arm-none-eabi', '-mcpu=cortex-a7', '-mthumb', *cflags,
                        '-Os', '-ffreestanding', '-fno-builtin', '-c', str(base / 'core/qs_tiles.c'),
                        '-o', str(args.out / 'qs_tiles.arm.o')], check=True)
        evidence['checks'].append({'name': 'ARM freestanding compile only', 'passed': True})
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(test_tiles))
    evidence['tests_run'] = result.testsRun
    evidence['test_output'] = stream.getvalue()
    evidence['checks'].append({'name': 'Private resource invariants, mutations and original NBU parser',
                               'passed': result.wasSuccessful(), 'skipped': len(result.skipped)})
    # The bytes parsed by the tests must be the exact delivered resource.
    B.check(test_tiles.TilesTests.page == (args.out / 'QS_CINE.fpqs.page').read_bytes(), 'Tested page differs')
    B.check(bytes(test_tiles.TilesTests.pool.data) == (args.out / 'QS_CINE.fpqs.strings').read_bytes(), 'Tested pool differs')
    evidence['artifacts'] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in args.out.iterdir() if path.is_file()}
    B.check(source_hashes == {str(path.relative_to(B.ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in sources}, 'Source changed during validation')
    evidence['source_hashes'] = source_hashes
    evidence['limitations'] = ['Native OS, painting, variable callbacks, touch input and recording service are not executed',
                               'No page installer or camera-ready card is produced',
                               'ARM compile is not execution of the C controller on the camera']
    (args.out / 'verification.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    print(stream.getvalue())
    B.check(result.wasSuccessful() and not result.skipped, 'Native tile verification failed')
    print(f'PASS: {result.testsRun} resource tests; C sanitizers and ARM compile; exact artifact hashes recorded')


if __name__ == '__main__':
    main()
