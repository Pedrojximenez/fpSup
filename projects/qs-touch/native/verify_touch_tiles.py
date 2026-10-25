#!/usr/bin/env python3
"""Verify the immediate touch version, including normalized-event C replay."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import build_touch_tiles as T
import test_touch_tiles

B = T.B


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    out = ap.parse_args().out
    B.check(not out.exists(), 'Use a new output directory')
    root = B.ROOT / 'projects/qs-touch'
    sources = [Path(__file__), Path(T.__file__), Path(B.__file__), Path(test_touch_tiles.__file__),
               *[root / f'core/{name}' for name in ('qs_tiles.c', 'qs_tiles.h', 'qs_tiles_touch.c', 'qs_tiles_touch.h')],
               root / 'tests/test_qs_tiles.c', root / 'tests/test_qs_tiles_touch.c']
    hashes = {str(p.relative_to(B.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    page, pool, manifest = T.build()
    out.mkdir(parents=True)
    (out / 'QS_CINE.fpqs-touch.page').write_bytes(page)
    (out / 'QS_CINE.fpqs-touch.strings').write_bytes(pool.data)
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    checks, published, replays = [], {}, {}
    with tempfile.TemporaryDirectory(prefix='fp-qs-touch-native-') as temp:
        for test, cfiles in (('tiles', ['qs_tiles.c']), ('tiles_touch', ['qs_tiles.c', 'qs_tiles_touch.c'])):
            executable = Path(temp) / test
            subprocess.run(['clang', '-std=c11', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined', '-g',
                            *[str(root / 'core' / name) for name in cfiles], str(root / f'tests/test_qs_{test}.c'),
                            '-o', str(executable)], check=True)
            result = subprocess.run([str(executable)], check=True, capture_output=True, text=True)
            replays[test] = result.stdout
            for line in result.stdout.splitlines():
                if line.startswith(('I ', 'T ')):
                    kind, name, value = line.split(' ', 2)
                    B.check(name not in published, 'Duplicate variable publication')
                    published[name] = (kind, value)
            checks.append({'name': f'{test} host sanitizers and behavior', 'passed': True})
        for name in ('qs_tiles', 'qs_tiles_touch'):
            subprocess.run(['clang', '-target', 'arm-none-eabi', '-mcpu=cortex-a7', '-mthumb', '-std=c11', '-Os',
                            '-ffreestanding', '-fno-builtin', '-Wall', '-Wextra', '-Werror', '-c',
                            str(root / f'core/{name}.c'), '-o', str(out / f'{name}.arm.o')], check=True)
        checks.append({'name': 'ARM freestanding compile only', 'passed': True})
    B.check(set(published) == set(manifest['variables']), 'Resource and C variable names disagree')
    for name, definition in manifest['variables'].items():
        B.check(published[name][0] == ('I' if definition['type'] == 'integer' else 'T'), 'Variable type mismatch')
    checks.append({'name': '73-variable C/resource contract', 'passed': True})
    stream = io.StringIO()
    tests = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(test_touch_tiles))
    B.check(test_touch_tiles.TouchResourceTests.page == (out / 'QS_CINE.fpqs-touch.page').read_bytes(), 'Tested page differs')
    checks.append({'name': 'Touch resource, no new animation curves, and native record parser',
                   'passed': tests.wasSuccessful(), 'skipped': len(tests.skipped)})
    B.check(hashes == {str(p.relative_to(B.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}, 'Sources changed')
    report = {'scope': 'Offline normalized touch replay and native resource parse; no camera connection',
              'checks': checks, 'tests_run': tests.testsRun, 'test_output': stream.getvalue(), 'C_replays': replays,
              'source_hashes': hashes,
              'artifacts': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()},
              'limitations': ['Raw XC_TouchPanelData contact flags and single-owner interception are not implemented',
                             'No native page installer, recording service or hardware touch path is executed',
                             'The native parser has explicit OS/construction substitutes; no painting is measured',
                             'Existing stock curves are retained for compatibility; new touch objects use direct bindings only']}
    (out / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(stream.getvalue())
    B.check(tests.wasSuccessful() and not tests.skipped, 'Touch version validation failed')
    print(f'PASS: {tests.testsRun} native resource tests; normalized touch replay; 73-variable contract; ARM compile')


if __name__ == '__main__':
    main()
