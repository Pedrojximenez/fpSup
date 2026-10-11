"""Reject the observed REC0-but-draining case before screenshot/file tools."""
import pathlib
import sys
import unittest
from unittest.mock import patch
import native_lcd as L


class NativeIdle(unittest.TestCase):
    def test_rec_zero_does_not_authorize_files_while_writer_or_xmp_is_busy(self):
        for active,xmp,recording in ((1,0,0),(0,0x45000100,0),(0,0,1)):
            words={0xC347D1D4:0x21,0xC3476608:0xAABB00CC|(recording<<8),
                   0xC358E140:xmp,0xC35A952C:active}
            with self.subTest(active=active,xmp=xmp,recording=recording), \
                 patch.object(L.C,'recording',return_value=0), \
                 patch.object(L.C.live.putfile,'mem_get',side_effect=lambda at,**kw:[words[at]]), \
                 patch.object(L.C.live,'shot') as shot:
                with self.assertRaises(AssertionError):
                    L.shot('must-not-capture',pathlib.Path('/tmp'))
                shot.assert_not_called()

    def test_both_native_selectors_use_the_recording_byte(self):
        for selector,at,word in ((0x21,0xC3476608,0xAABB00CC),(0,0xC347E08C,0x00BBCCDD)):
            words={0xC347D1D4:selector,at:word,0xC358E140:0,0xC35A952C:0x12340000}
            with self.subTest(selector=selector),patch.object(L.C,'recording',return_value=0), \
                 patch.object(L.C.live.putfile,'mem_get',side_effect=lambda at,**kw:[words[at]]):
                self.assertEqual(L.idle()['movie_recording'],0)


if __name__=='__main__':
    unittest.main(verbosity=2)
