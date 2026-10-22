#!/usr/bin/env python3
"""Bounded original-instruction tests; no native renderer, OS, allocator or device."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest

import page_probe as p

IMAGE = None


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.p = p.PageProbe(IMAGE)

    def tearDown(self):
        self.p.close()

    def test_vtable_slot_is_lazy_selector(self):
        self.assertEqual(struct.unpack_from("<I", IMAGE, 0x2E0036C)[0], p.SELECT | 1)

    def test_mainb2_serialized_declaration(self):
        q = self.p
        self.assertEqual(q.parse(q.single_mainb2_declaration()), 0)
        self.assertEqual(len(q.staged_screens), 1)
        screen = q.staged_screens[0]
        self.assertEqual(q.words(screen + 8)[0], p.POOL + 0x1A3B8)
        self.assertEqual(q.words(screen + 0x24)[0], q.READER)
        table = q.words(q.READER + 0xAC)[0]
        self.assertEqual(q.words(table, 3), (0xBDD26684, p.POOL + 0x1A3B8, p.MAINB2 - p.NBU))
        self.assertEqual(q.words(q.READER + 4)[0], 48)

    def test_first_parse_registers_and_cache_publication(self):
        q = self.p
        q.parse_script = [(0, 1, q.ROOT_OBJECT), (1, 1, q.ROOT_OBJECT)]
        self.assertEqual(q.select(), 0)
        self.assertEqual(q.parse_events[0], {"reader": q.READER, "position": p.MAINB2 - p.NBU,
                         "context": q.TABLE + 12, "source": p.NBU})
        self.assertEqual(len(q.parse_events), 2)
        self.assertEqual(q.words(q.SCREEN + 12)[0], q.ROOT_OBJECT)

    def test_cached_page_bypasses_preflight_and_parser(self):
        q = self.p
        q.write_words(q.SCREEN + 12, q.ROOT_OBJECT)
        q.preflight_result = 0
        q.parse_script = []
        self.assertEqual(q.select(), 0)
        self.assertEqual(q.words(q.ROOT_OBJECT + 12)[0], 2)
        self.assertFalse(q.parse_events)
        self.assertFalse(q.stub_events)

    def test_preflight_zero_returns_two(self):
        q = self.p
        q.preflight_result = 0
        q.parse_script = []
        self.assertEqual(q.select(), 2)
        self.assertFalse(q.parse_events)

    def test_opaque_preflight_registers_are_not_conventional_this(self):
        q = self.p
        q.preflight_result = 0
        q.parse_script = []
        self.assertEqual(q.select(), 2)
        call = q.stub_events[0]
        self.assertEqual(call["address"], hex(q.PREFLIGHT))
        self.assertEqual(call["args"][:3], [q.VTABLE, q.PREFLIGHT | 1, q.APP])

    def test_missing_reader_returns_two(self):
        q = self.p
        q.write_words(q.SCREEN + 0x24, 0)
        q.parse_script = []
        self.assertEqual(q.select(), 2)

    def test_missing_name_returns_zero_without_root(self):
        q = self.p
        q.write(q.NAME, b"NotMainB2\0")
        q.write_words(q.SCREEN + 8, q.NAME)
        q.parse_script = []
        self.assertEqual(q.select(), 0)
        self.assertEqual(q.words(q.SCREEN + 12)[0], 0)
        self.assertFalse(q.parse_events)

    def test_nonzero_record_return_is_not_treated_as_error(self):
        q = self.p
        q.parse_script = [(0xBAD, 1, q.ROOT_OBJECT)]
        self.assertEqual(q.select(), 0)
        self.assertEqual(q.words(q.SCREEN + 12)[0], q.ROOT_OBJECT)

    def test_stopped_without_objects_returns_two(self):
        q = self.p
        q.parse_script = [(1, 0, q.ROOT_OBJECT)]
        self.assertEqual(q.select(), 2)
        self.assertEqual(q.words(q.SCREEN + 12)[0], 0)

    def test_stopped_without_root_returns_two(self):
        q = self.p
        q.parse_script = [(1, 1, 0)]
        self.assertEqual(q.select(), 2)

    def test_failed_parse_does_not_clear_old_scratch_fields(self):
        q = self.p
        q.parse_script = [(1, 0, 0)]
        q.write_words(q.READER + 0x7C, q._allocate(8))
        self.assertEqual(q.select(), 2)
        self.assertEqual(q.words(q.READER + 0x7C)[0], 0)
        self.assertNotEqual(q.words(q.READER + 0x54)[0], 0)

    def test_unknown_record_continues_and_skips_body(self):
        q = self.p
        self.assertEqual(q.parse(struct.pack(">4I", 0xABCDEF00, 16, 0, 0)), 0)
        self.assertEqual(q.words(q.READER + 4)[0], 16)

    def test_terminal_record_returns_one_after_eight_bytes(self):
        q = self.p
        self.assertEqual(q.parse(struct.pack(">2I", 0xFFFFFFFF, 8)), 1)
        self.assertEqual(q.words(q.READER + 4)[0], 8)

    def test_record_underlength_is_not_rejected(self):
        q = self.p
        self.assertEqual(q.parse(struct.pack(">2I", 0xABCDEF00, 0)), 0)
        self.assertEqual(q.words(q.READER + 4)[0], 8)

    def test_real_mainb2_header_consumption(self):
        q = self.p
        q.write_words(q.READER + 12, q.TABLE + 12)
        self.assertEqual(q.parse(position=p.MAINB2 - p.NBU), 0)
        self.assertEqual(q.words(q.READER + 4)[0], p.MAINB2 - p.NBU + 3028)
        self.assertEqual(q.words(q.READER + 0x48)[0], 193)
        self.assertEqual(q.words(q.READER + 0x50)[0], 0)


def main():
    global IMAGE
    parser = argparse.ArgumentParser()
    parser.add_argument("--seg0", required=True)
    parser.add_argument("--report")
    args = parser.parse_args()
    IMAGE = p.registry.load_firmware(args.seg0)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BoundaryTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    evidence = {"offline_only": True, "camera_ready": False,
                "tests": result.testsRun, "failures": len(result.failures),
                "errors": len(result.errors), "skipped": len(result.skipped),
                "firmware_sha256": hashlib.sha256(IMAGE).hexdigest(),
                "sources": {f: hashlib.sha256(Path(__file__).with_name(f).read_bytes()).hexdigest()
                            for f in ("page_probe.py", "test_page_probe.py")},
                "limits": "Synthetic RAM, component sizes, arena, opaque app preflight, register-screen, root release and root-owner services; scripted parser only in selector tests. Native renderer/allocator/Lua/OS/device not run."}
    if args.report:
        with Path(args.report).open("x") as stream:
            stream.write(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":
    sys.exit(main())
