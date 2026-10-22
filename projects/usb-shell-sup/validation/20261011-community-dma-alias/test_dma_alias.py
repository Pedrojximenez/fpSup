#!/usr/bin/env python3
"""Execute native Thumb USB addressing instructions offline.

Only init pointer-table arithmetic, native bulk-send descriptor construction,
StartTransfer and DEPCMD parameter writes run. Endpoint selection, locks,
cache maintenance, USB wait and controller command completion are explicit
substitutes. All MMIO is local emulated memory, never hardware. These tests
prove software address values, not DMA access, image freshness or lifetime.
"""
import hashlib
import json
import pathlib
import struct
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'fpSup/raw/lossless_codec'))
from test_native_writer_contract import StockWriter, STOP, STACK

IMAGE = ROOT / 'out/seg0_c0000000.bin'
SHA = 'aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
CTX = 0xC31E3200
CPU_TABLE, DMA_TABLE = CTX + 0x64, CTX + 0x38
MMIO = 0x2100C800
EP = 5  # current EP82 IN, ctx2
RANGES = [(0xC01E30CE, 0xC01E315E), (0xC01E5880, 0xC01E5998),
          (0xC01E6A48, 0xC01E6B80), (0xC01E6B80, 0xC01E6CD8)]


class USB(StockWriter):
    def __init__(self):
        image = IMAGE.read_bytes()
        if hashlib.sha256(image).hexdigest() != SHA:
            raise AssertionError('firmware identity mismatch')
        super().__init__(image)
        self.mu.mem_map(0xC3000000, 0x1000000)
        self.mu.mem_map(0x431E3000, 0x4000)
        self.mu.mem_map(0x2100C000, 0x1000)
        self.cache_calls, self.commands, self.errors = [], [], []
        self.substitutes = {
            0xC01E4D88: lambda: self.ret(1),  # native bulk mode
            0xC01E6140: lambda: self.ret(EP >> 1),
            0xC01E3558: lambda: self.ret(0),
            0xC01E6098: lambda: self.ret(0x4000),
            0xC01E56F0: lambda: self.ret(0),
            0xC01E4C58: self.record_error,
            0xC01E6758: self.ret, 0xC01E67B0: self.ret,
            0xC01E6F98: self.ret, 0xC01E6008: self.ret,
            0xC000EB90: self.cache_boundary,
        }
        # The Thumb firmware calls ARM and Thumb substitutes; preserve the
        # callee mode and make the fallback instruction itself a safe return.
        for address in self.substitutes:
            if address == 0xC000EB90:
                self.put(address, 0xE12FFF1E)
            else:
                self.mu.mem_write(address, b'\x70\x47')  # Thumb bx lr

    def record_error(self):
        self.errors.append(self.r('r0'))
        self.ret(0)

    def cache_boundary(self):
        self.cache_calls.append((self.r('r0'), self.r('r1')))
        self.ret(0)

    def _instruction(self, mu, address, size, user):
        if address == 0xC01E6B0C:
            # Synthetic command acceptance: capture all actual parameter writes
            # before clearing CMDACT. This models no data DMA or USB completion.
            ep = self.r('r4')
            base = MMIO + 16 * ep
            self.commands.append((ep, self.get(base + 8), self.get(base + 4),
                                  self.get(base), self.get(base + 12)))
            self.put(base + 12, self.get(base + 12) & ~0x400)
        super()._instruction(mu, address, size, user)

    def invoke(self, start, stop=STOP, **registers):
        self.allowed, self.stops, self.stubs = RANGES, {stop}, self.substitutes
        self.reached = None
        self.setr('sp', STACK - 0x100)
        self.setr('lr', STOP)
        for name, value in registers.items():
            self.setr(name, value)
        self.mu.emu_start(start | 1, 0, count=20000)
        if self.reached != stop:
            raise AssertionError('native path did not reach approved stop')

    def initialize_tables(self):
        self.invoke(0xC01E30CE, 0xC01E315E, r4=CTX)

    def bulk(self, address):
        self.invoke(0xC01E5880, r0=address, r1=0x1000)
        ptr = self.get(CPU_TABLE + 4 * (EP >> 1))
        return tuple(self.get(ptr + 4 * i) for i in range(4))


class AddressReview(unittest.TestCase):
    def test_context_table_has_distinct_cpu_and_dma_addresses(self):
        r = USB()
        r.initialize_tables()
        for ctx in range(7):
            self.assertEqual(r.get(DMA_TABLE + 4 * ctx), 0x031E32C0 + 16 * ctx)
            self.assertEqual(r.get(CPU_TABLE + 4 * ctx), 0x431E32C0 + 16 * ctx)
        for ctx in range(4):
            self.assertEqual(r.get(CTX + 0x28 + 4 * ctx), 0x031E3280 + 16 * ctx)
            self.assertEqual(r.get(CTX + 0x54 + 4 * ctx), 0x431E3280 + 16 * ctx)

    def test_start_transfer_programs_low_trb_dma_address(self):
        r = USB()
        r.initialize_tables()
        r.invoke(0xC01E6B80, r0=EP)
        self.assertEqual(r.commands[0][0:4], (EP, 0, 0x031E32E0, 0))
        self.assertEqual(r.commands[0][4] & 0xF, 6)
        self.assertEqual(r.r('r0'), 0)

    def test_native_raw_address_is_subtracted_in_payload_trb(self):
        r = USB()
        r.initialize_tables()
        self.assertEqual(r.bulk(0x50000000), (0x10000000, 0, 0x1000, 0x813))
        self.assertEqual(r.commands[-1][2], 0x031E32E0)
        self.assertEqual(r.cache_calls, [])

    def test_native_allocator_and_cached_aliases(self):
        for source, expected in [(0x442F6FC0, 0x042F6FC0),
                                 (0x431E32C0, 0x031E32C0),
                                 (0xC31E32C0, 0x031E32C0),
                                 (0xD0000000, 0x10000000)]:
            with self.subTest(source=hex(source)):
                r = USB()
                r.initialize_tables()
                self.assertEqual(r.bulk(source)[0], expected)
                self.assertEqual(len(r.cache_calls), int(source >= 0xC0000000))

    def test_low_cpu_payload_address_is_refused(self):
        r = USB()
        r.initialize_tables()
        r.invoke(0xC01E5880, r0=0x10000000, r1=0x1000)
        self.assertEqual(r.r('r0'), 0xFFFFFFFF)
        self.assertEqual(r.commands, [])

    def test_swapped_table_interpretation_is_detected(self):
        r = USB()
        r.initialize_tables()
        # Private mutation: use the CPU table's 0x431e... value as DMA address.
        r.put(DMA_TABLE + 4 * (EP >> 1), 0x431E32E0)
        r.invoke(0xC01E6B80, r0=EP)
        with self.assertRaises(AssertionError):
            self.assertEqual(r.commands[-1][2], 0x031E32E0)
        self.assertEqual(r.commands[-1][2], 0x431E32E0)


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(AddressReview))
    (HERE / 'test-results.json').write_text(json.dumps({
        'firmware_sha256': SHA, 'tests_run': result.testsRun,
        'passed': result.wasSuccessful(), 'failures': len(result.failures),
        'errors': len(result.errors), 'skipped': len(result.skipped),
        'hardware_io_performed': False,
        'cpu_trb_address': '0x431E32E0', 'controller_trb_address': '0x031E32E0',
        'raw_source_cpu_address': '0x50000000', 'native_payload_trb_bufptr': '0x10000000',
        'limits': ['emulated MMIO only', 'substituted endpoint selection, locks, caches and command acceptance',
                   'no DMA reachability, frame ownership, USB completion or image alignment proof']
    }, indent=2) + '\n')
    sys.exit(not result.wasSuccessful())
