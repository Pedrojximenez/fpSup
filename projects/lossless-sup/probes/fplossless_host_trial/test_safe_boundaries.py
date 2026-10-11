"""Output/source safety checks that never load or execute the JPEG encoder."""
from pathlib import Path
import tempfile
import unittest

import mkcompressed_safe
from tiff_guard import Rejected


class SafeBuilderBoundaryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='fpl-safe-test-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.source = self.root / 'source.DNG'
        self.original = b'II+\0' + bytes(12)  # deliberately unsupported BigTIFF
        self.source.write_bytes(self.original)

    def test_source_cannot_be_output(self):
        with self.assertRaisesRegex(Rejected, 'overwrite'):
            mkcompressed_safe.build(self.source, self.source)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_existing_output_is_not_overwritten(self):
        output = self.root / 'already.DNG'
        sentinel = b'pre-existing output must survive'
        output.write_bytes(sentinel)
        with self.assertRaisesRegex(Rejected, 'overwrite'):
            mkcompressed_safe.build(self.source, output)
        self.assertEqual(output.read_bytes(), sentinel)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_bad_tiff_is_rejected_before_encoder_or_output(self):
        output = self.root / 'new.DNG'
        with self.assertRaisesRegex(Rejected, 'classic little-endian'):
            mkcompressed_safe.build(self.source, output)
        self.assertFalse(output.exists())
        self.assertEqual(self.source.read_bytes(), self.original)


if __name__ == '__main__':
    unittest.main()
