import unittest
from unittest.mock import patch

from native_mode_trial import Camera, decode_reply, parse_words, restore_mode, snapshot


class ProbeTests(unittest.TestCase):
    def test_parser_never_accepts_echo_stale_address_or_partial_dump(self):
        good = 'get : A:0x30211024, D:0x12345678\nget : A:0x30211028, D:0xFFFFFFFF\n'
        self.assertEqual(parse_words(good, 0x30211024, 2), [0x12345678, 0xFFFFFFFF])
        for bad in ('mem get 0x30211024,,8', good.split('\n')[0],
                    good.replace('30211028', '30241028'), good + good):
            with self.assertRaises(RuntimeError):
                parse_words(bad, 0x30211024, 2)

    def test_transport_errors_and_malformed_hex_are_rejected(self):
        for reply in ('ERR timeout', 'OKX xyz', 'OKX '):
            with self.assertRaises(RuntimeError):
                parse_words(decode_reply(reply), 0x30211024, 1)

    def test_trial_failure_still_restores_original_absolute_mode(self):
        class FakeCamera:
            def __init__(self): self.mode = 6; self.set_calls = []
            def status(self): return 'healthy'
            def set_mode(self, mode): self.set_calls.append(mode); self.mode = mode
            def integer(self, command): return self.mode
        camera = FakeCamera(); report = {}
        with self.assertRaisesRegex(RuntimeError, 'incomplete snapshot'):
            with restore_mode(camera, 12, report):
                raise RuntimeError('incomplete snapshot')
        self.assertEqual(camera.set_calls, [12])
        self.assertTrue(report['mode_restored'])

    def test_quarantined_transport_does_not_run_restore_setter(self):
        class FakeCamera:
            def status(self): raise RuntimeError('quarantined')
            def set_mode(self, mode): raise AssertionError('must not call setter')
        report = {}
        with self.assertRaisesRegex(RuntimeError, 'quarantined'):
            with restore_mode(FakeCamera(), 12, report): pass
        self.assertFalse(report['mode_restored'])

    def test_recording_guard_prevents_mutation(self):
        sent = []
        def transport(command, timeout):
            sent.append(command)
            return 'OK is_recording -> 1\\n'
        with self.assertRaisesRegex(RuntimeError, 'recording'):
            Camera(transport).set_mode(6)
        self.assertEqual(sent, ['TMO 1500 SHL status get is_recording'])

    def test_large_read_uses_complete_bounded_chunks(self):
        sent = []
        def transport(command, timeout):
            sent.append(command)
            import re
            address, size = re.search(r'mem get 0x(\w+),,0x(\w+)', command).groups()
            address, size = int(address, 16), int(size, 16)
            self.assertLessEqual(size, 32)
            dump = ''.join(f'get : A:0x{a:08X}, D:0x{a:08X}\n'
                           for a in range(address, address + size, 4))
            return 'OKX ' + dump.encode().hex()
        self.assertEqual(Camera(transport).words(0x30211024, 17),
                         list(range(0x30211024, 0x30211024 + 68, 4)))
        self.assertEqual(len(sent), 3)

    def test_partial_chunk_stops_without_retry_or_following_reads(self):
        sent = []
        def transport(command, timeout):
            sent.append(command)
            return 'OK get : A:0x30211024, D:0x00000000'
        with self.assertRaisesRegex(RuntimeError, 'incomplete'):
            Camera(transport).words(0x30211024, 17)
        self.assertEqual(len(sent), 1)

    def test_reboot_prevents_trial_and_restore_setters(self):
        sent = []
        def transport(command, timeout):
            sent.append(command)
            if command == 'STATUS':
                return 'OK name=fpshd camera=open quarantine=0 fault=none'
            return 'OK get : A:0xC072F6F8, D:0x00000002'
        camera = Camera(transport); camera.expected_boot = 1
        with self.assertRaisesRegex(RuntimeError, 'different boot'):
            camera.set_mode(6)
        report = {}
        with self.assertRaisesRegex(RuntimeError, 'different boot'):
            with restore_mode(camera, 12, report, expected_boot=1): pass
        self.assertFalse(report['mode_restored'])
        self.assertFalse(any('menu ' in command for command in sent))


if __name__ == '__main__':
    unittest.main()
