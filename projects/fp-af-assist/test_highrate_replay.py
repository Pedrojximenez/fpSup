import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest

from highrate import replay_batch
from test_ep83_receiver import NONCE, valid_batch


class HighrateReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'sample.afb'
        self.path.write_bytes(valid_batch(capacity=256))

    def test_maximum_batch_preserves_diagnostic_only_flags(self):
        result = replay_batch.replay(self.path, expected_nonce=NONCE)
        self.assertEqual(result['input_bytes'], 32896)
        self.assertEqual(result['capture']['count'], 256)
        self.assertFalse(result['capture']['usable_for_af_control'])
        self.assertFalse(result['usb_completion_verified'])
        self.assertFalse(result['camera_io_performed'])

    def test_bad_nonce_corruption_extra_and_truncation_are_rejected(self):
        good = valid_batch()
        bad = bytearray(good)
        bad[-1] ^= 1
        for data, nonce in ((good, NONCE + 1), (bad, NONCE),
                            (good + b'x', NONCE), (good[:-1], NONCE),
                            (b'', NONCE), (b'x' * 32897, NONCE)):
            with self.subTest(size=len(data), nonce=nonce):
                self.path.write_bytes(data)
                with self.assertRaises(ValueError):
                    replay_batch.replay(self.path, expected_nonce=nonce)

    def test_cli_writes_new_json_but_never_overwrites(self):
        output = Path(self.tmp.name) / 'report.json'
        args = [str(self.path), '--expected-nonce', hex(NONCE), '--output', str(output)]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(replay_batch.main(args), 0)
        before = output.read_bytes()
        self.assertEqual(json.loads(before)['capture']['count'], 256)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            replay_batch.main(args)
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(output.read_bytes(), before)

    def test_invalid_input_never_creates_output(self):
        self.path.write_bytes(b'bad')
        output = Path(self.tmp.name) / 'report.json'
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            replay_batch.main([str(self.path), '--expected-nonce', hex(NONCE),
                               '--output', str(output)])
        self.assertFalse(output.exists())

    def test_fifo_is_rejected_without_waiting_for_writer(self):
        fifo = Path(self.tmp.name) / 'pipe'
        os.mkfifo(fifo)
        with self.assertRaisesRegex(ValueError, 'regular file'):
            replay_batch.replay(fifo, expected_nonce=NONCE)


if __name__ == '__main__':
    unittest.main()
