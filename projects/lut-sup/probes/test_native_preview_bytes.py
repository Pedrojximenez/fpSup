import unittest
from unittest.mock import patch
import native_preview_bytes as probe


class Camera:
    def status(self): return 'OK'
    def words(self, address, count):
        self.assert_address = address
        w = [0] * 32
        w[3:5], w[8] = [1620, 911], 4
        w[9:13] = [(a - 0x40000000) // 4 for a in probe.RING]
        return w


class API:
    def __init__(self):
        self.windows, self.events = [(0, 0, 0)] * 8, []
        self.fail_read = self.fail_grant_reply = False
    def mem_caps(self, refresh):
        return {'xfer': 0xFFFFFF, 'windows': list(self.windows)}
    def mem_window(self, slot, base, size, permission):
        self.events.append(('window', slot, base, size, permission))
        self.windows[slot] = (base, size, permission)
        if self.fail_grant_reply and permission:
            raise RuntimeError('uncertain grant reply')
    def mem_read(self, address, size, sync, label):
        self.events.append(('read', address, size, sync))
        if self.fail_read:
            raise RuntimeError('read failed')
        return bytes(size)


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.state = {'app_current': 2, 'is_recording': 0, 'boot_id': 37}
        self.s = patch.object(probe, 'state', return_value=self.state)
        self.c = patch.object(probe, 'controls', return_value={'test': 0})
        self.s.start(); self.c.start()
        self.addCleanup(self.s.stop); self.addCleanup(self.c.stop)
        self.camera, self.api = Camera(), API()

    def test_read_grant_is_exact_read_only_no_cache_flush_and_released(self):
        report = {}
        data = probe.read_once(self.camera, self.api, report)
        self.assertEqual(len(data), probe.SPAN)
        self.assertEqual(self.api.events, [('window', 7, probe.RING[0], probe.SPAN, 1),
                         ('read', probe.RING[0], probe.SPAN, False), ('window', 7, 0, 0, 0)])
        self.assertTrue(report['read_window_revoked'])

    def test_existing_window_is_not_overwritten(self):
        self.api.windows[7] = (0x45000000, 100, 3)
        with self.assertRaisesRegex(RuntimeError, 'already owned'):
            probe.read_once(self.camera, self.api, {})
        self.assertFalse(self.api.events)

    def test_uncertain_grant_and_read_failures_release_only_owned_window(self):
        for flag in ('fail_grant_reply', 'fail_read'):
            api = API(); setattr(api, flag, True)
            with self.assertRaises(RuntimeError): probe.read_once(self.camera, api, {})
            self.assertEqual(api.windows[7], (0, 0, 0))

    def test_external_owner_change_is_never_revoked(self):
        def changed_owner(*args, **kwargs):
            self.api.windows[7] = (0x45000000, 100, 1)
            return bytes(probe.SPAN)
        self.api.mem_read = changed_owner
        with self.assertRaisesRegex(RuntimeError, 'owner changed'):
            probe.read_once(self.camera, self.api, {})
        self.assertEqual(len(self.api.events), 1)

    def test_record_boot_and_bad_ring_are_refused_before_grant(self):
        for values in ({'is_recording': 1}, {'app_current': 5}, {'boot_id': 0}):
            with patch.object(probe, 'state', return_value={**self.state, **values}):
                with self.assertRaises(RuntimeError): probe.read_once(self.camera, self.api, {})
        with patch.object(self.camera, 'words', return_value=[0] * 32):
            with self.assertRaisesRegex(RuntimeError, 'preview ring'):
                probe.read_once(self.camera, self.api, {})
        self.assertFalse(self.api.events)

    def test_removing_state_guard_is_detected_by_refusal_test(self):
        with patch.object(probe, 'guarded_state', return_value=self.state):
            with self.assertRaises(AssertionError):
                self.test_record_boot_and_bad_ring_are_refused_before_grant()


if __name__ == '__main__': unittest.main()
