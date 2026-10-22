import time
import unittest

import fp_af_assist as app


class PreviewTests(unittest.TestCase):
    def test_hardware_motion_remains_disabled(self):
        self.assertFalse(app.HARDWARE_MOTION_VERIFIED)

    def test_preview_runs_controller(self):
        service = app.PreviewService()
        self.assertTrue(service.start()['ok'])
        self.assertFalse(service.start()['ok'])
        service.worker.join(3)
        state = service.status()
        self.assertFalse(state['busy'])
        self.assertTrue(state['demo'])
        self.assertTrue(state['outcome']['synthetic'])
        self.assertEqual(state['outcome']['status'], 'completed')
        self.assertLessEqual(abs(state['outcome']['final_position'] - 10035), 5)

    def test_stop_cancels(self):
        service = app.PreviewService()
        service.start()
        service.stop()
        service.worker.join(3)
        state = service.status()
        self.assertFalse(state['busy'])
        self.assertIn(state['outcome']['status'], ('cancelled', 'fault'))

    def test_demo_native_button_does_not_invent_af_success(self):
        service = app.PreviewService()
        service.start('native')
        service.worker.join(1)
        self.assertEqual(service.status()['outcome']['status'], 'not_run')

    def test_explicit_cli_mode_required(self):
        with self.assertRaises(SystemExit):
            app.main([])


if __name__ == '__main__':
    unittest.main()
