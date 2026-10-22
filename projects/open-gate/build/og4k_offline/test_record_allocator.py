"""Project tests for original recording allocation and cleanup control flow."""

import unittest

import og4k_sizes as sizes
from verify_record_allocator import RecordAllocationEmulator, raw12_descriptor


class NativeRecordAllocation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native = RecordAllocationEmulator(sizes.load_firmware())
        cls.og4k = raw12_descriptor(4016, 2676)

    def test_stock_and_og4k_original_requests(self):
        for raster, expected in (((3856, 2170), 12_638_720), ((4016, 2676), 16_207_360)):
            result = self.native.run(raw12_descriptor(*raster))
            self.assertEqual(len(result["requests"]), 1)
            request = result["requests"][0]
            self.assertEqual(request["requested_bytes"], expected)
            self.assertEqual(request["alignment"], 0x400)
            self.assertEqual(request["wrapper_callsite"], "0xC037AD28")
            self.assertEqual(result["primary_handle"], (self.native.FAKE_PIXELS, expected, 10))
            self.assertEqual(result["returned_pointer"], self.native.FAKE_PIXELS)
            self.assertEqual(result["released_handles"], [])

    def test_prefix_is_read_from_frame_not_assumed_header(self):
        result = self.native.run(self.og4k, prefix=0x16000)
        self.assertEqual(result["requests"][0]["requested_bytes"], 16_120_320 + 0x16000)

    def test_primary_allocation_failure_returns_zero(self):
        result = self.native.run(self.og4k, allocation_results=(False,))
        self.assertEqual(result["returned_pointer"], 0)
        self.assertEqual(result["primary_handle"], (0, 0, 10))
        self.assertEqual(len(result["requests"]), 1)
        self.assertEqual(result["released_handles"], [])
        self.assertNotIn("secondary-buffer demand decision", result["mocked_services_called"])

    def test_secondary_failure_releases_primary_and_resets_handle(self):
        result = self.native.run(self.og4k, secondary=True, allocation_results=(True, False))
        self.assertEqual(result["returned_pointer"], 0)
        self.assertEqual([r["requested_bytes"] for r in result["requests"]], [16_207_360, 16_207_360])
        self.assertEqual(result["requests"][1]["wrapper_callsite"], "0xC037ADD4")
        self.assertEqual(result["released_handles"], [(self.native.FAKE_PIXELS, 16_207_360, 10)])
        self.assertEqual(result["primary_handle"], (0, 0, 15))

    def test_secondary_success_keeps_both_handles(self):
        result = self.native.run(self.og4k, secondary=True, allocation_results=(True, True))
        self.assertEqual(result["returned_pointer"], self.native.FAKE_PIXELS)
        self.assertEqual(len(result["requests"]), 2)
        self.assertEqual(result["released_handles"], [])
        self.assertEqual(result["secondary_handle"], (self.native.FAKE_PIXELS + 0x02000000, 16_207_360, 10))

    def test_frame_slot_precondition_avoids_allocation(self):
        result = self.native.run(self.og4k, available_slots=0)
        self.assertEqual(result["returned_pointer"], 0)
        self.assertEqual(result["requests"], [])
        self.assertEqual(result["mocked_services_called"], ["available frame slots"])


if __name__ == "__main__":
    unittest.main()
