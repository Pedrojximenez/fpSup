"""Read-only memory-guard predicate tests. No camera memory/USB access."""
import ctypes as c
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from highrate import build_publication


class Snapshot(c.Structure):
    _fields_ = [(n, c.c_uint32) for n in
                ('sctlr', 'ttbcr', 'ttbr0', 'dacr', 'pool', 'bytes', 'type')]
    _fields_ += [('first', c.c_uint32 * 16), ('last', c.c_uint32 * 16)]


def snapshot(pool=0x44F6FE00):
    s = Snapshot(sctlr=0x1005, ttbcr=0, ttbr0=0x44300040,
                 dacr=0x55555555, pool=pool, bytes=0x100000, type=0)
    s.first[:] = [(pool & 0xFF000000) | 0x44C02] * 16
    s.last[:] = [((pool + 0x65000 - 1) & 0xFF000000) | 0x44C02] * 16
    return s


class MemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='ep83-memory-test-')
        cls.addClassCleanup(cls.temp.cleanup)
        lib = Path(cls.temp.name) / 'memory.dylib'
        source = Path(__file__).parent / 'highrate/af_ep83_memory.c'
        flags = ['-dynamiclib'] if sys.platform == 'darwin' else ['-shared', '-fPIC']
        subprocess.run(['clang', *flags, '-O2', '-std=c11', '-Wall', '-Wextra',
                        '-Werror', str(source), '-o', str(lib)], check=True,
                       capture_output=True, text=True)
        cls.lib = c.CDLL(str(lib))
        cls.lib.af_ep83_memory_snapshot_ok.argtypes = [c.c_uint32, c.POINTER(Snapshot)]
        cls.lib.af_ep83_memory_snapshot_ok.restype = c.c_int32
        cls.lib.af_ep83_mapping_snapshot_ok.argtypes = [c.c_uint32, c.c_uint32, c.POINTER(Snapshot)]
        cls.lib.af_ep83_mapping_snapshot_ok.restype = c.c_int32

    def accepts(self, s, pool=None):
        return self.lib.af_ep83_memory_snapshot_ok(s.pool if pool is None else pool, c.byref(s))

    def test_exact_mapping_and_cross_supersection_mapping(self):
        self.assertEqual(self.accepts(snapshot()), 1)
        self.assertEqual(self.accepts(snapshot(0x44FF0000)), 1)

    def test_all_descriptor_words_checked_and_no_cached_or_alias_mapping(self):
        for field in ('first', 'last'):
            for index in range(16):
                for mask in (0x100, 0x1000, 4, 0x40000000, 0x40000, 0x10):
                    s = snapshot()
                    getattr(s, field)[index] ^= mask
                    self.assertEqual(self.accepts(s), 0, (field, index, mask))

    def test_register_modes_rejected_before_trusting_table(self):
        for name, mask in (('sctlr', 1), ('sctlr', 1 << 28), ('sctlr', 1 << 25),
                           ('ttbcr', 1), ('ttbcr', 1 << 31), ('ttbcr', 1 << 4),
                           ('ttbr0', 0x4000), ('ttbr0', 1), ('dacr', 1)):
            s = snapshot()
            setattr(s, name, getattr(s, name) ^ mask)
            self.assertEqual(self.accepts(s), 0, (name, mask))

    def test_pool_identity_bounds_allocation_and_type(self):
        for pool in (0, 0x3FFFFFC0, 0x44F6FE01, 0x7FFFFFF0, 0x80000000, 0xC4F6FE00):
            self.assertEqual(self.accepts(snapshot(pool)), 0)
        s = snapshot()
        self.assertEqual(self.accepts(s, pool=s.pool + 64), 0)
        for name, value in (('bytes', 0x65000), ('bytes', 0xFFFFFFFF), ('type', 1)):
            s = snapshot()
            setattr(s, name, value)
            self.assertEqual(self.accepts(s), 0)
        self.assertEqual(self.lib.af_ep83_memory_snapshot_ok(0x44F6FE00, None), 0)

    def test_host_fixed_binding_cannot_assert_hardware_evidence(self):
        self.assertEqual(self.lib.af_ep83_memory_ok(0x44F6FE00), 0)
        self.assertEqual(self.lib.af_ep83_build_identity_ok(), 0)
        self.assertEqual(self.lib.af_ep83_noncache_span_ok(0x431E32F0, 16), 0)

    def test_native_trb_span_requires_its_own_noncached_table_group(self):
        s = snapshot(0x431E32C0)
        self.assertEqual(self.lib.af_ep83_mapping_snapshot_ok(0x431E32F0, 16, c.byref(s)), 1)
        self.assertEqual(self.lib.af_ep83_mapping_snapshot_ok(0x441E32F0, 16, c.byref(s)), 0)
        for address, length in ((0x431E32F0, 0), (0x431E32F0, 0x100001),
                                (0xC31E32F0, 16), (0x7FFFFFF0, 32)):
            self.assertEqual(self.lib.af_ep83_mapping_snapshot_ok(address, length, c.byref(s)), 0)

    def test_rom_boot_table_source_matches_predicate(self):
        import hashlib
        import struct
        rom = (build_publication.root() / 'out/seg0_c0000000.bin').read_bytes()
        self.assertEqual(hashlib.sha256(rom).hexdigest(), build_publication.ROM_SHA256)
        self.assertEqual(struct.unpack_from('<I', rom, 0xEBF8)[0], 0x44300000)
        self.assertEqual(struct.unpack_from('<5I', rom, 0x725F60),
                         (0x40000000, 0x800, 3, 0, 0x400000))
        # Exact C000E7B0 descriptor construction, including bit18 supersection.
        ap, cache, phys = 3, 0, 0x400000
        descriptor = (ap << 10) | (cache << 2) | ((cache | 4) << 12) | 0x40002
        descriptor |= ((phys & 0xFF0000) << 8) | ((phys & 0xF000000) >> 4) | ((phys & 0xF0000000) >> 19)
        descriptor += (0x4F00000 & 0xFF000000)
        self.assertEqual(descriptor, 0x44044C02)
        self.assertEqual(rom[0x725F94:0x725FBD], b'13aa621060efff11aaba9b21ad925005302605cf\0')


if __name__ == '__main__':
    unittest.main()
