import unittest
import focus_bridge as b
import recover_upload as r
from test_focus_bridge import FakeTransport


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.io = FakeTransport()
        self.original = self.io.read(b.P, 192)
        self.events = [{'event': 'lease_prepared', 'original_words': self.original,
                        'version': self.io.shell('version'),
                        'settings': {c: self.io.shell(c) for c in b.SETTINGS}},
                       {'request': 'TMO 1000 SHL mem set 0xC072F800 0x12345678'}]

    def test_only_expected_upload_recovered(self):
        self.io.memory[b.CODE] = 0x12345678
        result = r.recover(self.io, self.events)
        self.assertEqual(result['restored_words'], 1)
        self.assertEqual(self.io.read(b.P, 192), self.original)

    def test_unknown_scratch_refused_without_writes(self):
        self.io.memory[b.CODE + 4] = 0x11112222
        with self.assertRaises(b.BridgeError):
            r.recover(self.io, self.events)
        self.assertFalse(any(row[0] == 'write' for row in self.io.calls))

    def test_executed_or_armed_incident_refused(self):
        for request in ('TMO 1000 SHL echo', 'TMO 1000 SHL mem set 0xC0BAC2F8 0xC072F800',
                        'TMO 1000 SHL mem set 0xC072F700 0x00000000'):
            with self.assertRaises(b.BridgeError):
                r.recovery_plan(self.events + [{'request': request}])

    def test_changed_settings_refused(self):
        self.io.changed_settings = True
        with self.assertRaises(b.BridgeError):
            r.recover(self.io, self.events)


if __name__ == '__main__':
    unittest.main()
