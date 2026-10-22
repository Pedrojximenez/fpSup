import unittest
from unittest.mock import patch

import native_controls_trial as study


class FakeCamera:
    def __init__(self):
        self.mode = 12
        self.boot = 99
        self.recording = False
        self.healthy = True
        self.saved = {0: dict(zip(study.MODE_CONTROLS, (1, 2, 3))),
                      6: dict(zip(study.MODE_CONTROLS, (-1, -2, -3)))}
        self.global_values = dict.fromkeys(study.GLOBAL_CONTROLS, 0)
        self.writes = []
        self.fail_once = None

    def status(self):
        if not self.healthy:
            raise RuntimeError('quarantined')

    def idle(self):
        if self.recording:
            raise RuntimeError('recording')

    def words(self, address, count):
        assert address == 0xC072F6F8 and count == 1
        return [self.boot]

    def set_mode(self, mode):
        self.mode = mode

    def sh(self, command):
        parts = command.split()
        assert parts[0] == 'menu'
        name = parts[1]
        if name == 'SetColorMode':
            return str(self.mode)
        owner = self.global_values if name in study.GLOBAL_CONTROLS else self.saved[self.mode]
        if len(parts) == 3:
            value = int(parts[2])
            self.writes.append((self.mode, name, value))
            owner[name] = value
            if self.fail_once == (name, value):
                self.fail_once = None
                raise RuntimeError('uncertain reply after setter')
            return 'OK'
        return str(owner[name])


class StudyTests(unittest.TestCase):
    def test_signed_values_are_preserved_and_noise_rejected(self):
        self.assertEqual(study.scalar('-5\n'), -5)
        for text in ('OK -5', '5 0', '', 'nan', 'set -5 -> -5'):
            with self.assertRaises(RuntimeError):
                study.scalar(text)

    def test_unreviewed_command_and_range_do_not_contact_camera(self):
        camera = FakeCamera()
        for name, value in (('SetFillLightEffect', 1), ('SetColorModeEffect', 6),
                            ('SetToneControlMode', 4)):
            with self.assertRaises(ValueError):
                study.set_control(camera, name, value, 99, 0)
        self.assertEqual(camera.writes, [])

    def test_boot_recording_and_quarantine_block_setters(self):
        for field, value in (('boot', 100), ('recording', True), ('healthy', False)):
            camera = FakeCamera(); camera.mode = 0
            setattr(camera, field, value)
            with self.assertRaises(RuntimeError):
                study.set_control(camera, 'SetColorModeContrast', -5, 99, 0)
            self.assertEqual(camera.writes, [])

    @patch.object(study.time, 'sleep')
    def test_capture_failure_restores_the_modes_own_values(self, sleep):
        camera = FakeCamera(); before = camera.saved[0].copy()
        report = {'groups': []}
        with patch.object(study, 'capture', side_effect=RuntimeError('incomplete capture')):
            with self.assertRaisesRegex(RuntimeError, 'incomplete capture'):
                study.group(camera, 0, 'Standard', (), 99, report, 3, {})
        self.assertEqual(camera.saved[0], before)
        self.assertEqual(camera.saved[6], dict(zip(study.MODE_CONTROLS, (-1, -2, -3))))
        self.assertTrue(report['groups'][0]['controls_restored'])

    @patch.object(study.time, 'sleep')
    def test_uncertain_setter_is_not_replayed_and_values_restore(self, sleep):
        camera = FakeCamera(); before = camera.saved[0].copy()
        camera.fail_once = ('SetColorModeContrast', -5)
        report = {'groups': []}
        baseline = [{'regions': {}}]
        with patch.object(study, 'capture', return_value=baseline):
            with self.assertRaisesRegex(RuntimeError, 'uncertain reply'):
                study.group(camera, 0, 'Standard',
                            (('low', {'SetColorModeContrast': -5}),),
                            99, report, 3, {})
        self.assertEqual(camera.writes.count((0, 'SetColorModeContrast', -5)), 1)
        self.assertEqual(camera.saved[0], before)
        self.assertTrue(report['groups'][0]['controls_restored'])

    @patch.object(study.time, 'sleep')
    def test_external_mode_change_cannot_restore_wrong_mode_settings(self, sleep):
        camera = FakeCamera(); report = {'groups': []}
        def changed(*args):
            camera.mode = 6
            raise RuntimeError('external mode change')
        with patch.object(study, 'capture', side_effect=changed):
            with self.assertRaisesRegex(RuntimeError, 'another mode'):
                study.group(camera, 0, 'Standard', (), 99, report, 3, {})
        self.assertFalse(report['groups'][0]['controls_restored'])
        self.assertEqual(camera.saved[6], dict(zip(study.MODE_CONTROLS, (-1, -2, -3))))
        self.assertIn('external mode change', report['groups'][0]['error'])

    def test_stability_filter_excludes_transients_and_baseline_drift(self):
        def sample(values):
            return {'regions': {'R': {'address': '0x30211024', 'words': values}}}
        before = [sample([0, 0, 0]), sample([0, 0, 0])]
        after = [sample([0, 0, 2]), sample([0, 0, 2])]
        changed = [sample([1, 1, 1]), sample([1, 2, 1])]
        result = study.stable_differences(before, changed, after)
        self.assertEqual(result['R'], [{'address': '0x30211024', 'before': '0x0', 'after': '0x1'}])

    def test_region_map_has_both_banks_and_complete_ceq_family(self):
        regions = study.regions()
        self.assertTrue(any('bank0_CEQ24_TGT' in k for k in regions))
        self.assertTrue(any('bank1_CEQ_ORG' in k for k in regions))
        self.assertTrue(any('CKNEE' in k for k in regions))
        self.assertIn('TONE_CACHED_DESCRIPTOR', regions)
        for address, count in regions.values():
            self.assertEqual(address % 4, 0)
            self.assertGreater(count, 0)


if __name__ == '__main__':
    unittest.main()
