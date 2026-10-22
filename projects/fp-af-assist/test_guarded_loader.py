"""Offline guarded-loader bytes and no-task cache-order checks."""
import struct
import unittest

from highrate import build_guarded_loader as build


class GuardedLoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code, cls.source, cls.manifest = build.build(expected_pool=0x44F6FE00, file_crc=0x12345678)

    def test_loader_bounds_and_actual_binary_calls(self):
        self.assertLess(build.LOADER_BASE + len(self.code), build.LOADER_LIMIT)
        calls = []
        for i, (word,) in enumerate(struct.iter_unpack('<I', self.code)):
            if word & 0xFF000000 == 0xEB000000:
                disp = (word & 0xFFFFFF) << 2
                if disp & (1 << 25):
                    disp -= 1 << 26
                calls.append(build.LOADER_BASE + i*4 + 8 + disp)
        self.assertNotIn(0xC0016A58, calls)  # no create task
        self.assertNotIn(0xC0016BC0, calls)  # no start task
        self.assertEqual([v for v in calls if v in (0xC000E91C, 0xC000EABC)],
                         [0xC000E91C, 0xC000EABC])
        self.assertFalse(self.manifest['deployment_ready'])

    def test_read_actual_and_crc_before_cache_and_stage2(self):
        source = self.source
        self.assertIn('mov     r3, sp', source)
        self.assertIn('cmp     r8, #1', source)
        self.assertIn('cmp     r0, r1', source)
        self.assertLess(source.index('loader_crc_byte:'), source.index('    CALL    F_CACHE'))
        self.assertLess(source.index('    CALL    0xC000EABC'), source.index('    blx     r1'))

    def test_source_drift_and_invalid_parameters_stop(self):
        with self.assertRaisesRegex(ValueError, 'source identity'):
            build.guarded_source(self.source)
        for pool, crc in ((0, 1), (0x44F6FE01, 1), (0xC4F6FE00, 1), (0x44F6FE00, -1)):
            with self.assertRaises(ValueError):
                build.build(expected_pool=pool, file_crc=crc)

    def test_review_autorun_has_no_motion_or_arbitrary_worker_and_cache_order(self):
        script = build.autorun_review_script(self.code, entry=self.manifest['entry'])
        self.assertEqual(script.count('memmgr bufmem get 0 1048576'), 1)
        self.assertEqual(script.count('\necho\n'), 3)
        self.assertLess(script.index('0xC000E91C'), script.index('0xC000EABC'))
        self.assertLess(script.index('0xC000EABC'), script.index('0xC0BAC2F8 0xC072DE64'))
        self.assertEqual(script.count('0xC0BAC2F8 0xC03D99A0'), 3)
        self.assertNotIn('shl ', script)
        self.assertNotIn('AF_START', script)
        self.assertNotIn('memmgr bufmem rel', script)


if __name__ == '__main__':
    unittest.main()
