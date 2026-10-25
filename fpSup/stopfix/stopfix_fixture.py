"""Independent offline fixture for the reviewed Loader v3 stop-queue patch."""
import hashlib
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'fp_usb_shell/v3'))
import build_v3 as B

SITE, STOCK, PATCH = 0xC0377118, 0xE92D4030, 0xEA000160
SHA256 = 'f9f26a092c5676ead5771ba8be4aac9c3734e9ed0cd144002a73b3f6b657c9d9'


def stopfix_sup():
    """Shared patch builder only; assert identity with the original 316-byte BIN."""
    data = B.patch_sup('STFX', [(SITE, struct.pack('<I', PATCH), 2)])
    assert len(data) == 316 and hashlib.sha256(data).hexdigest() == SHA256
    return data
