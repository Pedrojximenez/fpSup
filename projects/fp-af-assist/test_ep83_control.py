"""Offline native-task control guard tests; no boot hook or device access."""
import ctypes as c
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class Snapshot(c.Structure):
    _fields_ = [(n, c.c_uint32) for n in (
        'mode', 'pending', 'out_armed', 'out_active', 'out_bytes',
        'partial_mode', 'partial_offset', 'bulk_gate', 'usb_state',
        'shadow_enabled', 'hardware_enabled', 'out_mps',
        'out_mode', 'out_direction', 'out_endpoint', 'in_mode', 'in_direction', 'in_endpoint',
        'out_buffer', 'out_trb_pointer', 'out_trb_bus', 'trb_word0', 'trb_word1', 'trb_word2', 'trb_word3')]


def valid(mps=1024):
    return Snapshot(mode=5, pending=1, out_bytes=64, usb_state=2,
                    shadow_enabled=0xA7, hardware_enabled=0xA7, out_mps=mps,
                    out_mode=1, out_endpoint=1, in_mode=1, in_direction=1, in_endpoint=2,
                    out_buffer=0x442F71C0, out_trb_pointer=0x431E32D0, out_trb_bus=0x031E32D0,
                    trb_word0=0x042F71C0, trb_word2=mps-64, trb_word3=0x812)


class ControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='ep83-control-test-')
        cls.addClassCleanup(cls.temp.cleanup)
        lib = Path(cls.temp.name) / 'control.dylib'
        src = Path(__file__).parent / 'highrate/af_ep83_control.c'
        flags = ['-dynamiclib'] if sys.platform == 'darwin' else ['-shared', '-fPIC']
        subprocess.run(['clang', *flags, '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        str(src), '-o', str(lib)], check=True, capture_output=True, text=True)
        cls.lib = c.CDLL(str(lib))
        cls.lib.af_ep83_control_snapshot_ok.argtypes = [c.POINTER(Snapshot)]
        cls.lib.af_ep83_control_snapshot_ok.restype = c.c_int32

    def accepts(self, s):
        return self.lib.af_ep83_control_snapshot_ok(c.byref(s))

    def test_only_exact_completed_64byte_packet_at_all_bulk_speeds(self):
        for mps in (64, 512, 1024):
            self.assertEqual(self.accepts(valid(mps)), 1)

    def test_every_fixed_field_mismatch_rejected(self):
        for name, _ in Snapshot._fields_:
            if name == 'usb_state':
                continue
            s = valid()
            setattr(s, name, getattr(s, name) ^ (4 if name.endswith('enabled') else 1))
            self.assertEqual(self.accepts(s), 0, name)

    def test_no_partial_full_packet_or_queued_transfer(self):
        for count in (0, 12, 63, 65, 512, 1024):
            s = valid()
            s.out_bytes = count
            self.assertEqual(self.accepts(s), 0)
        for name in ('out_armed', 'out_active', 'partial_mode', 'partial_offset', 'bulk_gate'):
            s = valid()
            setattr(s, name, 1)
            self.assertEqual(self.accepts(s), 0)

    def test_wrong_direction_hwo_end_state_and_suspend(self):
        for name, value in (('out_direction', 1), ('out_active', 2), ('trb_word3', 0x813),
                            ('trb_word3', 0x818), ('usb_state', 4)):
            s = valid()
            setattr(s, name, value)
            self.assertEqual(self.accepts(s), 0)

    def test_null_and_nonarm_entry_fail_closed(self):
        self.assertEqual(self.lib.af_ep83_control_snapshot_ok(None), 0)
        self.assertEqual(self.lib.af_ep83_control_entry(5, 0x44F6FE00, None), -308)

    def test_arm_compile_and_fixed_entries_in_rom(self):
        from highrate import build_publication, build_sender
        import struct
        src = Path(__file__).parent / 'highrate/af_ep83_control.c'
        subprocess.run(['clang', *build_sender.FLAGS, '-fsyntax-only', str(src)],
                       check=True, capture_output=True, text=True)
        rom = (build_publication.root() / 'out/seg0_c0000000.bin').read_bytes()
        self.assertEqual(struct.unpack_from('<I', rom, 0x33B3C)[0], 0xEB129F0D)
        # Thumb-2 PUSH prologue at the native MPS getter; call entry is odd.
        self.assertEqual(rom[0x1E6098:0x1E609C], bytes.fromhex('2de93041'))


if __name__ == '__main__':
    unittest.main()
