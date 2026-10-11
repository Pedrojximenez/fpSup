"""Guard tests for the read-only live route diagnostic; no camera I/O."""
import struct
import unittest
from unittest.mock import patch

import native_live_route as probe


BASE = {'app_current': 2, 'is_recording': 0, 'stored_record_mode': 1,
        'applied_record_mode': 1, 'boot_id': 123, 'color_mode': 12, 'relative_gain': 1170}


class MetadataCamera:
    def __init__(self, altered_hook=None):
        self.reads = []
        self.altered_hook = altered_hook
        self.rom = probe.ROM_PATH.read_bytes()

    def status(self):
        return 'verified test transport'

    def idle(self):
        pass

    def words(self, address, count):
        self.reads.append((address, count))
        # Any framebuffer access, unknown range, setter or injected call fails.
        if address >= 0xC0000000 and address < 0xC1000000:
            result = list(struct.unpack_from('<' + 'I' * count, self.rom, address - 0xC0000000))
            if address == self.altered_hook:
                result[0] ^= 1
            return result
        allowed = {(a, n) for _, a, n in probe.REGIONS}
        if (address, count) not in allowed:
            raise AssertionError('access outside reviewed metadata')
        return [0] * count


class RouteGuards(unittest.TestCase):
    def execute(self, camera, states=None, control_values=None):
        state_values = [dict(BASE)] * 8 if states is None else states
        values = [{'effect': 0}] * 8 if control_values is None else control_values
        report = {}
        with patch.object(probe, 'state', side_effect=state_values), \
             patch.object(probe, 'controls', side_effect=values):
            probe.run(camera, report)
        return report

    def test_success_has_only_metadata_reads(self):
        camera = MetadataCamera()
        result = self.execute(camera)
        self.assertEqual(result['status'], 'read-only-live-route-complete')
        self.assertEqual(len(result['samples']), 3)
        self.assertTrue(result['unchanged'])
        self.assertTrue(all(not s['atomic'] for s in result['samples']))
        self.assertFalse(any(0x40000000 <= a < 0x60000000 for a, _ in camera.reads))

    def test_incompatible_state_rejected_before_metadata(self):
        for key, value in [('app_current', 5), ('is_recording', 1), ('boot_id', 0),
                           ('stored_record_mode', 0), ('applied_record_mode', 0)]:
            with self.subTest(key=key):
                camera = MetadataCamera()
                bad = dict(BASE, **{key: value})
                with self.assertRaisesRegex(RuntimeError, 'CINE standby'):
                    self.execute(camera, [bad])
                self.assertEqual(camera.reads, [])

    def test_unknown_hook_prevents_route_reads(self):
        camera = MetadataCamera(altered_hook=0xC0075CF4)
        with self.assertRaisesRegex(RuntimeError, 'unexpected native code or hook'):
            self.execute(camera)
        self.assertFalse(any(a == probe.REGIONS[0][1] for a, _ in camera.reads))

    def test_boot_change_rejected_across_read(self):
        camera = MetadataCamera()
        with self.assertRaisesRegex(RuntimeError, 'state or boot changed'):
            self.execute(camera, [dict(BASE), dict(BASE), dict(BASE, boot_id=124)])
        self.assertEqual(camera.reads.count((probe.REGIONS[0][1], probe.REGIONS[0][2])), 1)

    def test_colour_change_rejected_across_read(self):
        camera = MetadataCamera()
        with self.assertRaisesRegex(RuntimeError, 'controls changed across'):
            self.execute(camera, control_values=[{'effect': 0}, {'effect': 0}, {'effect': 1}])
        self.assertEqual(camera.reads.count((probe.REGIONS[0][1], probe.REGIONS[0][2])), 1)


if __name__ == '__main__':
    unittest.main()
