#!/usr/bin/env python3
"""Offline tests for lcd.py: the 10-09 ring capture, plus a fake camera for
the window handling.  python3 -B -m unittest test_lcd"""
import json
from pathlib import Path
import unittest

import lcd

CAP = lcd.ROOT / 'projects/lut-sup/validation/20261009-native-preview-bytes-01'
RING = CAP / 'native-ring.bin'
WORDS = json.loads((CAP / 'report.json').read_text())['descriptor']['words']


class Decode(unittest.TestCase):
    def test_descriptor_of_the_capture(self):
        d = lcd.parse_descriptor(WORDS)
        self.assertEqual((d['w'], d['h']), (1620, 911))
        self.assertEqual(d['slots'], [0x49801000, 0x49BFD000, 0x49FF9000, 0x4A3F5000])

    def test_descriptor_rejects(self):
        for bad in ([1] + WORDS[1:],                       # word 0 not zero
                    WORDS[:3] + [0] + WORDS[4:],           # no width
                    WORDS[:8] + [9] + WORDS[9:],           # slot count
                    WORDS[:10] + [WORDS[9] + 1] + WORDS[11:]):   # slots overlap a frame
            self.assertIsNone(lcd.parse_descriptor(bad))

    def test_own_stride_wins(self):
        buf = RING.read_bytes()
        self.assertTrue(lcd.stride_check(buf, 1620, 911)['ok'])

    def test_wrong_width_is_caught(self):
        # mutation: decode at a width that is not the ring's -> must not pass
        buf = RING.read_bytes()
        self.assertFalse(lcd.stride_check(buf, 1632, 911)['ok'])
        self.assertFalse(lcd.stride_check(buf, 1920, 911)['ok'])

    def test_decode_shape_and_neutral_chroma(self):
        y, rgb = lcd.decode(RING.read_bytes(), 1620, 911)
        self.assertEqual(rgb.shape, (911, 1620, 3))
        self.assertGreater(y.std(), 10)              # a scene, not a flat buffer


class FakeApi:
    def __init__(self, owned=False):
        self.windows = [(0, 0, 0)] * 8
        if owned:
            self.windows[lcd.WIN_SLOT] = (1, 2, 1)
        self.reads = []

    def mem_caps(self, refresh=False):
        return {'xfer': 16 << 20, 'windows': list(self.windows)}

    def mem_window(self, slot, base, length, perm):
        self.windows[slot] = (base, length, perm)

    def mem_read(self, addr, n, sync=True, label=''):
        assert self.windows[lcd.WIN_SLOT] == (addr, n, 1), 'read outside the granted window'
        self.reads.append((addr, n))
        return RING.read_bytes()[:n]


class FakeCam:
    def __init__(self, recording=0):
        self.recording, self.transcript = recording, []

    def status(self):
        return 'OK'

    def integer(self, cmd):
        return self.recording

    def words(self, addr, n):
        return WORDS if addr == lcd.OUT_DESC[0] else [0] * n


class Grab(unittest.TestCase):
    def test_reads_and_revokes(self):
        api = FakeApi()
        frames, *_ = lcd.grab(FakeCam(), api)
        self.assertEqual(len(frames), 1)
        self.assertEqual(api.reads, [(0x49801000, 1620 * 911 * 2)])
        self.assertEqual(api.windows[lcd.WIN_SLOT], (0, 0, 0))

    def test_refuses_owned_window(self):
        api = FakeApi(owned=True)
        with self.assertRaises(RuntimeError):
            lcd.grab(FakeCam(), api)
        self.assertEqual(api.windows[lcd.WIN_SLOT], (1, 2, 1))     # someone else's, untouched

    def test_refuses_while_recording(self):
        api = FakeApi()
        with self.assertRaises(RuntimeError):
            lcd.grab(FakeCam(recording=1), api)
        self.assertEqual(api.reads, [])


if __name__ == '__main__':
    unittest.main()
