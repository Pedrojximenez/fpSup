"""Run separated suites offline; saved artifact bytes only, no camera I/O.

Modes: lossless, stopfix, integration. Only the explicit integration mode
imports both modules. Product code is unchanged from the prior validated split.
"""
import hashlib
import json
from pathlib import Path
import re
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
FPSUP = ROOT / 'fpSup'
PREVIOUS = HERE.parent / '20261012-separate-stopfix'
mode = sys.argv[1]
assert mode in ('lossless', 'stopfix', 'integration')
artifacts = {}


def record(path):
    data = path.read_bytes()
    artifacts[str(path.relative_to(ROOT))] = hashlib.sha256(data).hexdigest()
    return data


if mode in ('lossless', 'integration'):
    sys.path.insert(0, str(FPSUP / 'lossless'))
    import test_v3_lossless as V
    import test_card_emulation as C
    from armasm import symbols
    module = HERE / 'module'
    facts = json.loads((module / 'build.json').read_text())['blob']
    facts['layout'] = json.loads((module / 'layout.json').read_text())['fields']
    data = record(module / '10LOSS.BIN')
    loader = record(PREVIOUS / 'candidate-card/fpSup/LOADER.BIN')
    autorun = record(PREVIOUS / 'candidate-card/AutoRun.txt')
    V.B.loader_bin = lambda: (loader, {})
    V.B.autorun = lambda *args, **kwargs: autorun

    def saved_v3(cls):
        cls.sup, cls.facts = data, facts
        cls.sym = symbols(FPSUP / 'lossless/native/card.S', facts['defines'])
        cls.img = V.T.IMAGE.read_bytes()

    V.LosslessV3Tests.setUpClass = classmethod(saved_v3)

    def saved_v2():
        directory = PREVIOUS / 'candidate-v2-fast'
        text = record(directory / 'AutoRun.txt').decode()
        words = [(int(a, 16), int(v, 16)) for a, v in
                 re.findall(r'^mem set (0x[0-9A-Fa-f]+) (0x[0-9A-Fa-f]+)', text, re.M)]
        loader_words = {a: v for a, v in words if C.T.CAVE_LOW <= a < C.T.CAVE_LOW + 0x200}
        C.LAYOUT = json.loads((directory / 'layout.json').read_text())['fields']
        info = json.loads((directory / 'build.json').read_text())['blob']
        C.C_ENTRIES = {name: C.BLOCK + info['c_base'] + (off & ~1)
                       for name, off in info['entries'].items()}
        return loader_words, record(directory / 'fpSup.BIN'), record(directory / 'lossless.bin')

    C.build_card = saved_v2

if mode == 'lossless':
    import test_bulk_native as N
    N.BulkNativeTests.setUpClass = classmethod(saved_v3)
    original_patch = V.B.patch_sup

    def reject_stopfix(sup_id, *args, **kwargs):
        assert sup_id != 'STFX', 'LOSS suite attempted to build the independent stopfix'
        return original_patch(sup_id, *args, **kwargs)

    V.B.patch_sup = reject_stopfix
    modules = [V, N, C]
elif mode == 'stopfix':
    sys.path.insert(0, str(FPSUP / 'stopfix'))
    import test_stop_release as S
    modules = [S]
else:
    sys.path.insert(0, str(FPSUP / 'integration_tests'))
    import test_lossless_stopfix as I
    modules = [I]

suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(m) for m in modules)
with (HERE / (mode + '-tests.log')).open('w') as stream:
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
stopfix_imported = any('stopfix' in name.lower() or name == 'test_stop_release' for name in sys.modules)
if mode == 'lossless':
    assert not stopfix_imported, 'LOSS imported a stopfix module'
if mode == 'stopfix':
    assert 'test_v3_lossless' not in sys.modules and 'build_v3_lossless' not in sys.modules
report = {'suite': mode, 'tests': result.testsRun, 'failures': len(result.failures),
          'errors': len(result.errors), 'skipped': len(result.skipped),
          'passed': result.wasSuccessful() and not result.skipped,
          'stopfix_imported': stopfix_imported, 'artifacts': artifacts, 'camera_tested': False}
(HERE / (mode + '-tests.json')).write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
sys.exit(0 if report['passed'] else 1)
