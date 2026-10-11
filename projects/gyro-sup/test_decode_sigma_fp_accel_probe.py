#!/usr/bin/env python3

import subprocess
import struct
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class AccelProbeDecoderTest(unittest.TestCase):
    def test_decodes_ordered_signed_axes(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            (directory / "ACC001.BIN").write_bytes(struct.pack("<hhh", -4, 5, -6) + bytes(26))
            (directory / "ACC000.BIN").write_bytes(struct.pack("<hhh", 1, -2, 3) + bytes(26))
            output = directory / "decoded.csv"
            result = subprocess.run(
                [sys.executable, str(ROOT / "decode_sigma_fp_accel_probe.py"),
                 str(directory), "--csv", str(output)],
                check=True, capture_output=True, text=True,
            )
            self.assertIn("snapshots: 2", result.stdout)
            self.assertEqual(
                output.read_text(encoding="ascii").splitlines(),
                [
                    "sample,nominal_ms,ax_raw,ay_raw,az_raw",
                    "0,0.0,1,-2,3",
                    "1,100.0,-4,5,-6",
                ],
            )


if __name__ == "__main__":
    unittest.main()

