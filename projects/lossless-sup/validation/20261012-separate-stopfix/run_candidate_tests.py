"""Offline only: execute the saved candidate bytes using maintained harnesses.

Select 'ordinary', 'trace' or 'fast'. No rebuild replaces these artifacts.
Media, allocator, task and power-manager boundaries use documented test stubs.
"""
import hashlib
import json
from pathlib import Path
import re
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
LOSS = ROOT / 'fpSup/lossless'
sys.path.insert(0, str(LOSS))
import test_v3_lossless as V
import test_bulk_native as N
import test_stop_release as R
import test_card_emulation as C
from armasm import symbols

submitted_stopfix = (HERE / 'inputs/05STOPFX.BIN').read_bytes()
assert V.stopfix_sup() == submitted_stopfix
V.stopfix_sup = lambda: submitted_stopfix

mode = sys.argv[1]
selection = sys.argv[2] if len(sys.argv) > 2 else None
assert mode in ('ordinary', 'trace', 'fast')
directory = HERE / ('candidate-trace' if mode == 'trace' else 'candidate-card')
facts = json.loads((directory / 'build.json').read_text())['blob']
facts['layout'] = json.loads((directory / 'layout.json').read_text())['fields']
data = (directory / 'fpSup/10LOSS.BIN').read_bytes()
loader = (directory / 'fpSup/LOADER.BIN').read_bytes()
autorun = (directory / 'AutoRun.txt').read_bytes()
# The maintained card fixture takes loader bytes through these two builders;
# supply the saved outputs instead, including boot and warm-repair test cases.
V.B.loader_bin = lambda: (loader, {})
V.B.autorun = lambda *args, **kwargs: autorun


def saved_v3(cls):
    cls.sup, cls.facts = data, facts
    cls.sym = symbols(LOSS / 'native/card.S', facts['defines'])
    cls.img = V.T.IMAGE.read_bytes()


V.LosslessV3Tests.setUpClass = classmethod(saved_v3)
N.BulkNativeTests.setUpClass = classmethod(saved_v3)


def saved_v2():
    directory = HERE / 'candidate-v2-fast'
    text = (directory / 'AutoRun.txt').read_text()
    words = [(int(a, 16), int(v, 16)) for a, v in
             re.findall(r'^mem set (0x[0-9A-Fa-f]+) (0x[0-9A-Fa-f]+)', text, re.M)]
    loader_words = {a: v for a, v in words if C.T.CAVE_LOW <= a < C.T.CAVE_LOW + 0x200}
    C.LAYOUT = json.loads((directory / 'layout.json').read_text())['fields']
    info = json.loads((directory / 'build.json').read_text())['blob']
    C.C_ENTRIES = {name: C.BLOCK + info['c_base'] + (off & ~1)
                   for name, off in info['entries'].items()}
    return (loader_words, (directory / 'fpSup.BIN').read_bytes(),
            (directory / 'lossless.bin').read_bytes())


C.build_card = saved_v2
modules = [V, N] + ([R, C] if mode == 'ordinary' else [])
suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromModule(m) for m in modules)
if mode == 'fast':
    def saved_fast(cls):
        cls.loader, cls.bin, _ = saved_v2()
    C.T.ThreeWayBootTests.setUpClass = classmethod(saved_fast)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(C.T.ThreeWayBootTests)
if selection:
    suite = unittest.defaultTestLoader.loadTestsFromName(selection)
report_name = mode + ('-recheck' if selection else '')
with (HERE / (report_name + '-emulation.log')).open('w') as log:
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
paths = [directory / p for p in ('AutoRun.txt', 'fpSup/LOADER.BIN', 'fpSup/10LOSS.BIN')]
paths += [HERE / 'inputs/05STOPFX.BIN']
if mode == 'fast':
    paths = []
if mode in ('ordinary', 'fast'):
    paths += [HERE / 'candidate-v2-fast' / p for p in ('AutoRun.txt', 'fpSup.BIN', 'lossless.bin')]
report = {'mode': mode, 'tests': result.testsRun, 'failures': len(result.failures),
          'errors': len(result.errors), 'skipped': len(result.skipped),
          'passed': result.wasSuccessful() and not result.skipped,
          'artifacts': {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in paths}, 'camera_tested': False}
report['selection'] = selection
(HERE / (report_name + '-emulation.json')).write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
sys.exit(0 if report['passed'] else 1)
