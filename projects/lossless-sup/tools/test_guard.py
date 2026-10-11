"""In-memory malformed-TIFF and recursively referenced zero-range regressions."""
import struct
import unittest

from run_trial import ClassicTIFF, Rejected, preflight


def put_ifd(data, offset, entries, nxt=0):
    struct.pack_into('<H', data, offset, len(entries))
    for i, item in enumerate(entries):
        struct.pack_into('<HHII', data, offset + 2 + 12 * i, *item)
    struct.pack_into('<I', data, offset + 2 + 12 * len(entries), nxt)


def graph():
    data = bytearray(2048)
    struct.pack_into('<2sHI', data, 0, b'II', 42, 8)
    put_ifd(data, 8, [(34665, 4, 1, 256), (34853, 4, 1, 384),
                       (330, 4, 1, 512)])
    put_ifd(data, 256, [(37500, 7, 200, 1024), (40965, 4, 1, 640)])
    put_ifd(data, 384, [(1, 2, 8, 900)])
    put_ifd(data, 512, [(270, 2, 8, 920)])
    put_ifd(data, 640, [(1, 2, 8, 940)])
    return data


class Allocator:
    @staticmethod
    def largest_zero_run(data, lo, hi, occupied):
        # Stand-in for the existing builder choosing a zero run inside a
        # declared nested MakerNote; the protector must not trust zero bytes.
        return 600, 300


class GuardTests(unittest.TestCase):
    def test_every_standard_nested_ifd_link_is_walked(self):
        tree = ClassicTIFF(graph())
        self.assertEqual({n['path'] for n in tree.nodes},
                         {'IFD0', 'IFD0/Exif[0]', 'IFD0/GPS[0]', 'IFD0/SubIFD[0]',
                          'IFD0/Exif[0]/Interop[0]'})
        self.assertTrue(any(r['start'] == 1024 and r['end'] == 1224 and r['nested']
                            for r in tree.protected))

    def test_big_tiff_and_big_endian_are_rejected(self):
        for prefix in (b'II+\0', b'MM\0*'):
            data = graph()
            data[:4] = prefix
            with self.assertRaises(Rejected):
                ClassicTIFF(data)

    def test_root_next_ifd_is_not_silently_dropped(self):
        data = graph()
        struct.pack_into('<I', data, 8 + 2 + 3 * 12, 384)
        with self.assertRaisesRegex(Rejected, 'top-level'):
            ClassicTIFF(data)

    def test_nested_cycle_is_rejected(self):
        data = graph()
        struct.pack_into('<I', data, 256 + 2 + 12 + 8, 8)
        with self.assertRaisesRegex(Rejected, 'cyclic/shared'):
            ClassicTIFF(data)

    def test_duplicate_tag_is_rejected(self):
        data = graph()
        struct.pack_into('<H', data, 8 + 2 + 12, 34665)
        with self.assertRaisesRegex(Rejected, 'duplicate'):
            ClassicTIFF(data)

    def test_unsupported_type_and_truncated_nested_value_are_rejected(self):
        for kind, count, offset in ((13, 1, 0), (7, 3000, 1024)):
            data = graph()
            struct.pack_into('<HHII', data, 256 + 2, 37500, kind, count, offset)
            with self.assertRaises(Rejected):
                ClassicTIFF(data)

    def test_nested_image_payload_is_not_assumed_to_be_metadata(self):
        data = graph()
        struct.pack_into('<HHII', data, 512 + 2, 273, 4, 1, 1500)
        with self.assertRaisesRegex(Rejected, 'nested image storage'):
            ClassicTIFF(data)

    def test_zero_filled_makernote_is_not_a_free_header_hole(self):
        width, height, start = 1936, 1090, 1024
        strip = width * height * 3 // 2 + 12  # known final-row padding
        data = bytearray((start + strip + 511) & ~511)
        struct.pack_into('<2sHI', data, 0, b'II', 42, 8)
        put_ifd(data, 8, [(256, 4, 1, width), (257, 4, 1, height), (258, 3, 1, 12),
                           (259, 3, 1, 1), (262, 3, 1, 32803), (273, 4, 1, start),
                           (277, 3, 1, 1), (278, 4, 1, height), (279, 4, 1, strip),
                           (34665, 4, 1, 400)])
        put_ifd(data, 400, [(37500, 7, 200, 600)])
        _, plan = preflight(bytes(data), Allocator())
        self.assertEqual(plan['strip_nonpixel_tail_bytes'], 12)
        self.assertEqual(plan['metadata_collisions'],
                         [{'start': 600, 'end': 800,
                           'label': 'IFD0/Exif[0] tag 37500 value', 'nested': True}])


if __name__ == '__main__':
    unittest.main()
