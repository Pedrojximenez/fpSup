"""Offline tests: preprocess source and run only the formatter fixture.

The fixture's renamed daemon entrypoint is never invoked.  This suite does
not start a daemon, initialize libusb, create sockets, or inspect USB devices.
Compile test-frame-log using the documented command before running this file.
"""
from pathlib import Path
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parent


class DiagnosticBuildTests(unittest.TestCase):
    def test_disabled_macro_preserves_preprocessed_source(self):
        def preprocess(name):
            return subprocess.check_output(['cc', '-E', '-P', '-I', str(ROOT / 'include'),
                                            str(ROOT / name)])
        self.assertEqual(preprocess('fpshd.upstream.c'), preprocess('fpshd-diagnostic.c'))

    def test_formatter_exact_bytes_count_bounds_timestamp_and_errno(self):
        result = subprocess.run([str(ROOT / 'test-frame-log')], capture_output=True, check=True)
        self.assertEqual(result.stdout, b'')
        lines = result.stderr.decode('ascii').splitlines()
        self.assertEqual(len(lines), 5)
        parsed = []
        for count, line in enumerate(lines, 1):
            self.assertTrue(line.startswith('FPSH_DIAG_FRAME '))
            fields = dict(re.findall(r'(\w+)=(\S*)', line))
            self.assertEqual(int(fields['count']), count)
            self.assertEqual(int(fields['seq']), 699 + count)
            self.assertEqual(int(fields['frame']), count - 1)
            self.assertEqual(fields['clock'], 'MONOTONIC_RAW')
            self.assertEqual(fields['clock_rc'], '0')
            self.assertGreaterEqual(int(fields['raw_sec']), 0)
            self.assertTrue(0 <= int(fields['raw_nsec']) < 1000000000)
            self.assertEqual(fields['expected'], '64')
            self.assertEqual(len(bytes.fromhex(fields['hex'])), int(fields['captured']))
            parsed.append(fields)
        self.assertEqual(parsed[0]['hex'], bytes(range(12)).hex())
        self.assertEqual(parsed[0]['captured'], '12')
        self.assertEqual(parsed[1]['hex'], '')
        self.assertEqual(parsed[1]['captured'], '0')
        self.assertEqual(parsed[2]['hex'], bytes(range(64)).hex())
        self.assertEqual(parsed[3]['hex'], bytes(range(64)).hex())
        self.assertEqual(parsed[3]['moved'], '100')
        self.assertEqual(parsed[3]['captured'], '64')
        self.assertEqual(parsed[4]['hex'], '')
        self.assertEqual(parsed[4]['moved'], '-1')
        self.assertEqual(parsed[4]['captured'], '0')


if __name__ == '__main__':
    unittest.main()
