"""Offline source equivalence and mocked-drain tests; never starts a daemon."""
from pathlib import Path
import re
import struct
import subprocess
import unittest
import zlib

ROOT = Path(__file__).resolve().parent


class DiagnosticV2Tests(unittest.TestCase):
    def test_disabled_macro_preserves_preprocessed_upstream(self):
        def preprocess(name):
            return subprocess.check_output(['cc', '-E', '-P', '-I', str(ROOT / 'include'),
                                            str(ROOT / name)])
        self.assertEqual(preprocess('fpshd.upstream.c'), preprocess('fpshd-diagnostic-v2.c'))

    def test_matching_synthetic_fpsh_is_observed_in_existing_drain_loop(self):
        result = subprocess.run([str(ROOT / 'test-drain-log')], capture_output=True, check=True)
        self.assertEqual(result.stdout, b'')
        lines = result.stderr.decode('ascii').splitlines()
        self.assertEqual(len(lines), 4)
        records = [dict(re.findall(r'(\w+)=(\S*)', line)) for line in lines]
        self.assertTrue(lines[0].startswith('FPSH_DIAG_FRAME '))
        self.assertEqual(records[0]['hex'], '0c00000003000320c1000000')
        first, last, cap = records[1:]
        for index, entry in enumerate((first, last, cap), 1):
            self.assertTrue(lines[index].startswith('FPSH_DIAG_DRAIN '))
            self.assertEqual(entry['source'], 'drain')
            self.assertEqual(entry['count'], str(index))
            self.assertEqual(entry['expected'], '16384')
            self.assertEqual(entry['clock'], 'MONOTONIC_RAW')
            self.assertEqual(entry['clock_rc'], '0')
            self.assertTrue(0 <= int(entry['raw_nsec']) < 1000000000)
        self.assertEqual(first['seq'], '193')
        self.assertEqual(first['drain_iteration'], '0')
        self.assertEqual(first['rc'], '0')
        self.assertEqual(first['moved'], '64')
        self.assertEqual(first['captured'], '64')
        raw = bytearray.fromhex(first['hex'])
        self.assertEqual(len(raw), 64)
        self.assertEqual(raw[:6], b'FPSH\x01\x03')
        self.assertEqual(struct.unpack_from('<I', raw, 8)[0], 193)
        expected_crc = struct.unpack_from('<I', raw, 16)[0]
        struct.pack_into('<I', raw, 16, 0)
        self.assertEqual(zlib.crc32(raw), expected_crc)
        self.assertEqual(last['seq'], '193')
        self.assertEqual(last['drain_iteration'], '1')
        self.assertEqual(last['rc'], '-7')
        self.assertEqual(last['moved'], '0')
        self.assertEqual(last['hex'], '')
        self.assertEqual(cap['seq'], '194')
        self.assertEqual(cap['drain_iteration'], '7')
        self.assertEqual(cap['moved'], '128')
        self.assertEqual(cap['captured'], '64')
        self.assertEqual(cap['hex'], bytes(range(64)).hex())


if __name__ == '__main__':
    unittest.main()
