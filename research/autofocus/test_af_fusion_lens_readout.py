"""Mocked tests for the audited read-only lens command helper.

Every daemon request is intercepted.  No camera or USB connection is made.
"""

from contextlib import nullcontext
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import af_fusion_lens_readout as readout


class AuditedLensReadTests(unittest.TestCase):
    def setUp(self):
        self.shell = SimpleNamespace(SOCK="/unused/mock-only.sock")
        self.transcript = []
        request_patch = patch.object(readout.collector, "_daemon_request")
        self.request = request_patch.start()
        self.addCleanup(request_patch.stop)

    def test_only_four_audited_read_commands_use_decimal_arguments(self):
        self.assertEqual(readout.READ_COMMANDS, {"getfpos", "getfedge", "cnvfpos", "cnvfdist"})
        for name, value, command in (
            ("getfpos", None, "lens getfpos"),
            ("getfedge", 0, "lens getfedge 0"),
            ("getfedge", 1, "lens getfedge 1"),
            ("cnvfpos", 0x10, "lens cnvfpos 16"),
            ("cnvfdist", -0x10, "lens cnvfdist -16"),
        ):
            with self.subTest(name=name, value=value):
                self.request.reset_mock()
                reply = ("OK lens " + name + " 123\\n\\n").encode("ascii")
                self.request.return_value = reply
                self.assertEqual(readout.read_lens(self.shell, name, value, self.transcript), 123)
                self.request.assert_called_once_with(self.shell, "TMO 1000 SHL " + command)
                self.assertEqual(self.transcript[-1], {"command": command, "reply": reply.decode("ascii")})

    def test_parses_signed_and_unsigned_decimal_reply_with_lens_prefix(self):
        for name, arg, raw, expected in (
            ("getfpos", None, b"OK lens getfpos -2147483648\n", -2147483648),
            ("cnvfdist", 1000, b"OK lens cnvfdist 4294967295\\n\\n", 4294967295),
            ("getfpos", None, b"OK lens getfpos 0\n\n", 0),
        ):
            with self.subTest(reply=raw):
                self.request.return_value = raw
                self.assertEqual(readout.read_lens(self.shell, name, arg, self.transcript), expected)

    def test_setters_control_commands_and_injection_names_never_reach_daemon(self):
        for name in (
            "setfpos", "drive", "stop", "wait", "capture", "getfpos; lens setfpos 10",
            "getfpos\nlens setfpos 10", "menu", "version", "", None,
        ):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    readout.read_lens(self.shell, name, None, self.transcript)
        self.request.assert_not_called()
        self.assertEqual(self.transcript, [])

    def test_argument_shapes_selectors_and_conversion_inputs_are_checked_before_io(self):
        for name, value in (
            ("getfpos", 0),
            ("getfedge", None), ("getfedge", -1), ("getfedge", 2),
            ("getfedge", True), ("getfedge", False),
            ("cnvfpos", None), ("cnvfdist", None),
            ("cnvfpos", "16"), ("cnvfpos", "0x10"),
            ("cnvfdist", 1.0), ("cnvfdist", True),
            ("cnvfdist", "1; lens setfpos 10"),
        ):
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                readout.read_lens(self.shell, name, value, self.transcript)
        self.request.assert_not_called()
        self.assertEqual(self.transcript, [])

    def test_signed_32_bit_input_boundaries_are_enforced(self):
        for value in (-0x80000001, 0x80000000):
            with self.subTest(invalid=value), self.assertRaises(ValueError):
                readout.read_lens(self.shell, "cnvfpos", value, self.transcript)
        self.request.assert_not_called()
        for value in (-0x80000000, 0x7FFFFFFF):
            with self.subTest(valid=value):
                self.request.return_value = b"OK lens cnvfpos 1\n"
                self.assertEqual(readout.read_lens(self.shell, "cnvfpos", value, self.transcript), 1)
                self.request.assert_called_with(self.shell, "TMO 1000 SHL lens cnvfpos " + str(value))

    def test_errors_malformed_prefixes_and_extra_reply_tokens_are_refused_and_recorded(self):
        for reply in (
            b"ERR unavailable\n", b"", b"OK 123\n", b"OK getfpos 123\n",
            b"OK lens getfedge 123\n", b"OK lens getfpos 0x10\n",
            b"OK lens getfpos 1.5\n", b"OK lens getfpos 123 extra\n",
            b"OK lens getfpos 123\nlens setfpos 100\n",
            b"OK lens getfpos 4294967295\n", b"OK lens getfpos -2147483649\n",
        ):
            with self.subTest(reply=reply):
                self.request.return_value = reply
                with self.assertRaises(RuntimeError):
                    readout.read_lens(self.shell, "getfpos", None, self.transcript)
                self.assertEqual(self.transcript[-1]["reply"], reply.decode("ascii"))

    def test_non_ascii_reply_is_refused_with_raw_transcript_retained(self):
        self.request.return_value = b"OK lens getfpos \xff\n"
        with self.assertRaises((RuntimeError, UnicodeError)):
            readout.read_lens(self.shell, "getfpos", None, self.transcript)
        self.assertEqual(len(self.transcript), 1)
        self.assertIn("\ufffd", self.transcript[0]["reply"])

    def test_outside_nominal_edges_aborts_before_offset_conversions_and_saves_evidence(self):
        self.request.side_effect = [
            b"OK mock daemon\n",
            b"OK w71c1 5.02.0.V91\n",
            b"OK lens getfpos 10707\n",
            b"OK lens getfedge 2147483647\n",
            b"OK lens getfedge 300\n",
            b"OK lens cnvfpos 6276\n",
            b"OK lens cnvfpos 10706\n",
        ]
        with tempfile.TemporaryDirectory(prefix="af-lens-read-test-") as directory:
            output = Path(directory) / "readout.json"
            with patch.object(readout.collector, "_exclusive_host_lock", return_value=nullcontext()), patch(
                "sys.argv", ["af_fusion_lens_readout.py", "--socket", self.shell.SOCK, "--output", str(output)]
            ):
                with self.assertRaisesRegex(RuntimeError, "outside converted nominal edge range"):
                    readout.main()
            evidence = json.loads(output.read_bytes())
            self.assertEqual(evidence["status"], "readout-incomplete")
            self.assertIs(evidence["lens_movement_requested"], False)
            self.assertEqual(len(evidence["transcript"]), 5)
            self.assertIn("10707", evidence["transcript"][0]["reply"])
            self.assertIn("outside converted nominal edge range", evidence["error"])
        commands = [call.args[1] for call in self.request.call_args_list]
        self.assertEqual(len(commands), 7)
        self.assertFalse(any("cnvfdist" in command for command in commands))
        self.assertFalse(any("10607" in command or "10807" in command for command in commands))


if __name__ == "__main__":
    unittest.main()
