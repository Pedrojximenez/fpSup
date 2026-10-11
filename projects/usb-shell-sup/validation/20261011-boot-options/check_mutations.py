"""Controlled mutations of temporary artifacts only; no camera or source edits."""
import pathlib
import sys
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'fpSup/fp_usb_shell'))
from v3 import build_v3 as B
from v3 import test_boot_options as T
from v3 import test_allsups as A
from unicorn import UcError

# Delete just the store bootstrap's stack alignment. The real ARM still
# completes, but the ABI assertion detects unaligned firmware cache calls.
ar, blob, _ = B.boot_card(instant=True, fast=True)
cam = T.Camera(ar, blob, active=True)
cam.boot()
cam.power_off_all()
cam.registered.clear()
cam.heap_next = T.T.HEAP
cam.put(T.T.DRAW, T.T.DRAW_PAUSED)
assert cam.w(T.BOOT_AT + 8) == 0xE3CDD007
cam.put(T.BOOT_AT + 8, T.T.NOP)
cam.call(T.BOOT_AT)
assert cam.misaligned == ['DCACHE', 'ICACHE'], cam.misaligned
print('caught: missing Fast bootstrap alignment fails cache-call ABI assertion')

# Give the v3 entry a wrong outer-file offset. The manager must never accept
# this as a valid saved self-image. Reproduce the actual build with the bad
# stub offset and require the saved-envelope behaviour check to reject it.
original = B.loader_bin
def bad_offset(*args, **kw):
    if kw.get('file_offset') is not None:
        kw['file_offset'] = 0
    return original(*args, **kw)
with mock.patch.object(B, 'loader_bin', side_effect=bad_offset):
    _ar, bad, _info = B.boot_card(instant=True, allsups=True)
try:
    cam = A.boot(vbin=bad)
except (UcError, AssertionError) as e:
    print('caught: wrong outer-file offset rejected by actual manager execution:', type(e).__name__)
else:
    cam.notify('FT_Choice1', 1)
    saved = cam.written.get(A.SELF_PATH)
    assert saved is None or saved[:-128] != bad[:-128]
    print('caught: wrong outer-file offset fails complete-envelope save assertion')

print('2 controlled mutations caught; sources and frozen releases unchanged')
