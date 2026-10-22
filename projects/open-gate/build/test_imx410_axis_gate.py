#!/usr/bin/env python3
"""The historical AXIS push must fail before camera transport is imported."""
import sys
import types
import unittest
from unittest.mock import patch

import imx410_axis as axis


class AxisGateTests(unittest.TestCase):
    def test_current_plan_blocks_push_without_camera_io(self):
        transport = types.ModuleType("putfile")

        def forbidden(*_args, **_kwargs):
            raise AssertionError("unsafe AXIS push reached camera transport")

        transport.mem_get = forbidden
        transport.mem_set = forbidden
        transport.sh = forbidden
        with patch.dict(sys.modules, {"putfile": transport}):
            with self.assertRaisesRegex(SystemExit, "零相機 I/O"):
                axis.push(None, "A")

    def test_check_stays_offline(self):
        self.assertEqual(axis.main(["--check", "--preset", "A"]), 0)


if __name__ == "__main__":
    unittest.main()
