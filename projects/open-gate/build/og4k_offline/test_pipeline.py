"""Offline native p429 -> actual OG4K ARM core -> descriptor -> allocation.

This joins the independently checked stages with the real descriptor bytes.
Runtime profile selection and physical allocator availability remain mocked or
explicit inputs, as documented by the component verifiers.
"""

import struct
import unittest

import og4k_sizes as sizes
from verify_descriptor_native import NativeDescriptor
from verify_record_allocator import RecordAllocationEmulator


class NativeRecordingPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = sizes.load_firmware()
        cls.allocator = RecordAllocationEmulator(cls.image)
        cls.fixtures = {}
        for candidate in (False, True):
            machine = NativeDescriptor(cls.image)
            descriptor = machine.construct(candidate=candidate)
            recording_copy = machine.recording_copy()
            strip = machine.strip_bytes()
            cls.fixtures[candidate] = machine, descriptor, recording_copy, strip

    def test_actual_core_native_descriptor_and_allocator_agree(self):
        cases = (
            (False, (3856, 2170), (1600, 1600), 12_551_292, 12_638_720),
            (True, (4016, 2676), (1536, 1536), 16_120_232, 16_207_360),
        )
        for candidate, raster, zoom, expected_strip, expected_allocation in cases:
            machine, descriptor, recording_copy, strip = self.fixtures[candidate]
            with self.subTest(candidate=candidate):
                self.assertEqual(len(descriptor), 0xC0)
                self.assertEqual(recording_copy, descriptor[:0x48])
                self.assertEqual(struct.unpack_from("<II", recording_copy), raster)
                self.assertEqual(struct.unpack_from("<II", recording_copy, 0x18), (8, 5))
                self.assertEqual(struct.unpack_from("<I", recording_copy, 0x20), (0,))
                self.assertEqual(struct.unpack_from("<II", descriptor, 0x48), zoom)
                self.assertEqual(strip, expected_strip)
                self.assertIn(0xC0439D18, machine.native_entries)
                self.assertIn(0xC0438018, machine.native_entries)
                self.assertIn(0xC02E5B78, machine.native_entries)
                self.assertIn(0xC03D9630, machine.native_entries)
                self.assertEqual(machine.CODE + machine.symbols["record_canvas"]
                                 in machine.native_entries, candidate)
                result = self.allocator.run(recording_copy)
                self.assertEqual(result["requests"][0]["requested_bytes"], expected_allocation)
                self.assertEqual(result["primary_handle"],
                                 (self.allocator.FAKE_PIXELS, expected_allocation, 10))
                self.assertEqual(result["returned_pointer"], self.allocator.FAKE_PIXELS)
                self.assertEqual(result["requests"][0]["wrapper_callsite"], "0xC037AD28")

    def test_native_og4k_descriptor_preserves_failure_cleanup(self):
        _, _, recording_copy, _ = self.fixtures[True]
        no_slots = self.allocator.run(recording_copy, available_slots=0)
        self.assertEqual(no_slots["requests"], [])
        self.assertEqual(no_slots["returned_pointer"], 0)
        primary_failure = self.allocator.run(recording_copy, allocation_results=(False,))
        self.assertEqual(primary_failure["returned_pointer"], 0)
        self.assertEqual(len(primary_failure["requests"]), 1)
        secondary_failure = self.allocator.run(recording_copy, secondary=True,
                                              allocation_results=(True, False))
        self.assertEqual(secondary_failure["returned_pointer"], 0)
        self.assertEqual(secondary_failure["primary_handle"], (0, 0, 15))
        self.assertEqual(secondary_failure["released_handles"],
                         [(self.allocator.FAKE_PIXELS, 16_207_360, 10)])


if __name__ == "__main__":
    unittest.main()
