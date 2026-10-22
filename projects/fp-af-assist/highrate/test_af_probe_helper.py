"""Run the real helper bytes in Unicorn, with strict, address-based ROM stubs.

No camera/socket operations. The model proves helper bounds, call ABI, sticky
allocation attempts and publication order, not heap/DMA/cache hardware behavior
or detach quiescence. CP15 reads are explicitly stubbed so the emulator's own
MMU configuration cannot substitute for camera mapping evidence. Missing
Unicorn or a restricted JIT is an ERROR, not a skip.
"""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
    UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
    UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11, UC_ARM_REG_R12,
    UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_CPSR)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'fpSup/fp_usb_shell'))
import armasm

CODE, PARAM = 0xC0800000, 0xC072E400
CAP_LEN, CAP_PTR = 0xC072F040, 0xC072F04C
H_GET, H_ADDR, DCACHE = 0xC001D740, 0xC001D7F0, 0xC000E91C
HEAP, HEAP_BYTES = 0x45000000, 0x20000
STACK, SP, RETURN = 0x43000000, 0x43008000, 0x44000000
NONCE = 0x31415926
TABLE = 0x44300000
CP_READS = {0xEE110F10: 'sctlr', 0xEE120F50: 'ttbcr',
            0xEE120F10: 'ttbr0', 0xEE130F10: 'dacr'}
REGS = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
        UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
        UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
        UC_ARM_REG_R12]


def assemble(source=None, param=PARAM):
    if source is None:
        return armasm.assemble(HERE / 'af_probe_helper.S', [f'AF_PROBE_P={param}'])
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / 'mutant.S'
        src.write_text(source)
        return armasm.assemble(src, [f'AF_PROBE_P={param}'])


class ArmHelper:
    def __init__(self, code, *, raw=HEAP + 4, param=PARAM, code_base=CODE):
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.raw, self.param, self.code_base, self.code = raw, param, code_base, code
        self.calls, self.events, self.pages = [], [], set()
        self.cp = dict(sctlr=1, ttbcr=0, ttbr0=0x44300040, dacr=0x55555555)
        areas = [(code_base, len(code)), (param, 64), (CAP_LEN, 16),
                              (HEAP, HEAP_BYTES), (STACK, 0x10000), (RETURN, 4),
                              (H_GET, 4), (H_ADDR, 4), (DCACHE, 4), (TABLE, 0x4000)]
        if 0x40000000 <= raw <= 0x7FFF0000:
            areas.append((raw, 0x10000))
        for address, size in areas:
            for page in range(address & ~0xFFF, (address + size + 0xFFF) & ~0xFFF, 4096):
                if page not in self.pages:
                    self.uc.mem_map(page, 4096)
                    self.pages.add(page)
        self.uc.mem_write(code_base, code)
        self.uc.mem_write(param + 0x30, bytes([0xD6]) * 16)
        self.uc.mem_write(HEAP, bytes([0xA5]) * HEAP_BYTES)
        if 0x40000000 <= raw <= 0x7FFF0000:
            for address in (raw, raw + 0xFFFF):
                first = (address >> 20) & ~15
                descriptor = (address & 0xFF000000) | 0x00044C02
                self.uc.mem_write(TABLE + first * 4, struct.pack('<16I', *([descriptor] * 16)))
        self.uc.hook_add(UC_HOOK_CODE, self.on_code)
        self.uc.hook_add(UC_HOOK_MEM_WRITE, self.on_write)

    def word(self, address):
        return struct.unpack('<I', self.uc.mem_read(address, 4))[0]

    def put(self, offset, value):
        self.uc.mem_write(self.param + offset, struct.pack('<I', value))

    def get(self, offset):
        return self.word(self.param + offset)

    def on_write(self, uc, access, address, size, value, _):
        allowed = ((self.param, self.param + 64), (SP - 48, SP),
                   (CAP_LEN, CAP_LEN + 4), (CAP_PTR, CAP_PTR + 4))
        assert any(lo <= address and address + size <= hi for lo, hi in allowed), \
            f'write outside owned parameters/stack/reply words: {address:#x}+{size}'
        self.events.append(('write', address, size, value))

    def on_code(self, uc, address, size, _):
        if self.code_base <= address < self.code_base + len(self.code):
            instruction = self.word(address)
            if instruction in CP_READS:
                name = CP_READS[instruction]
                self.events.append(('cp15', name, self.cp[name]))
                uc.reg_write(UC_ARM_REG_R0, self.cp[name])
                uc.reg_write(UC_ARM_REG_PC, address + 4)
            return
        if address == RETURN:
            self.returned = True
            uc.emu_stop()
            return
        assert address in (H_GET, H_ADDR, DCACHE), f'unapproved execution {address:#x}'
        assert uc.reg_read(UC_ARM_REG_SP) % 8 == 0, 'unaligned external-call SP'
        args = tuple(uc.reg_read(reg) for reg in REGS[:4])
        self.calls.append(address)
        self.events.append(('call', address, args))
        if address == H_GET:
            assert args == (self.param + 0x30, 0, 0x10000, 0), 'allocator ABI'
            assert self.get(8) == 1, 'allocation attempt not published before ROM call'
            assert bytes(uc.mem_read(args[0], 16)) == bytes(16), 'descriptor not zero'
            uc.mem_write(args[0], struct.pack('<4I', 0xDE5C0001, 2, 3, 4))
            result = 0xF1234567  # Deliberately not an assumed bool/error convention.
        elif address == H_ADDR:
            assert args[0] == self.param + 0x30
            assert self.get(0x30) == 0xDE5C0001
            result = self.raw
        else:
            assert self.word(CAP_PTR) == self.word(CAP_LEN) == 0, 'DMA published before clean'
            result = 0xDEADBEEF
        for i in (0, 1, 2, 3, 12):
            uc.reg_write(REGS[i], 0xBAD00000 + i)
        uc.reg_write(UC_ARM_REG_R0, result)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    def run(self, op):
        self.put(0, op)
        self.uc.mem_write(CAP_LEN, struct.pack('<I', 0x5555))
        self.uc.mem_write(CAP_PTR, struct.pack('<I', 0xDEADC0DE))
        self.events, self.calls, self.returned = [], [], False
        initial = [0x11220000 + i * 0x1001 for i in range(13)]
        self.uc.reg_write(UC_ARM_REG_CPSR, 0x13)
        for reg, value in zip(REGS, initial):
            self.uc.reg_write(reg, value)
        self.uc.reg_write(UC_ARM_REG_SP, SP)
        self.uc.reg_write(UC_ARM_REG_LR, RETURN)
        self.uc.emu_start(self.code_base, RETURN + 4, count=1000)
        assert self.returned, 'helper did not return within its instruction bound'
        assert self.uc.reg_read(UC_ARM_REG_SP) == SP, 'SP not restored'
        for i in range(4, 12):
            assert self.uc.reg_read(REGS[i]) == initial[i], f'r{i} not restored'
        assert self.uc.reg_read(UC_ARM_REG_R0) == self.get(4), 'return/status disagreement'
        return self

    def completed_capture(self, capacity=64):
        self.put(0x18, NONCE)
        self.put(0x1C, capacity)
        ptr = self.get(0x10) + 0x1040
        header = (0x31464841, 1, 128, capacity, NONCE, 0, capacity, 1,
                  0xC022C858, 0xC023E9D0, 0xC022C85C, 64, 0, 0, 0, 0)
        self.uc.mem_write(ptr, struct.pack('<16I', *header))
        records = bytearray(capacity * 128)
        for i in range(capacity):
            struct.pack_into('<4I', records, i * 128, i + 1, NONCE, i + 1, 0xC32044D8)
            struct.pack_into('<I', records, i * 128 + 124, (i + 1) ^ 0xFFFFFFFF)
        self.uc.mem_write(ptr + 64, bytes(records))
        return ptr


class HelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        probe = subprocess.run([sys.executable, '-B', '-c',
            'from unicorn import Uc,UC_ARCH_ARM,UC_MODE_ARM; '
            'u=Uc(UC_ARCH_ARM,UC_MODE_ARM); u.mem_map(0x1000,0x1000)'], capture_output=True)
        if probe.returncode:
            raise RuntimeError(f'Unicorn JIT unavailable ({probe.returncode}); no ARM validation')
        cls.code = assemble()

    def helper(self, **kwargs):
        return ArmHelper(self.code, **kwargs)

    def assert_denied(self, h, status):
        self.assertEqual(h.get(4), status)
        self.assertEqual((h.word(CAP_PTR), h.word(CAP_LEN), h.get(0x20), h.get(0x24)), (0, 0, 0, 0))
        self.assertNotIn(DCACHE, h.calls)

    def assert_exported(self, h, ptr, capacity):
        n = 64 + capacity * 128
        self.assertEqual(h.get(4), 0)
        self.assertEqual((h.get(0x20), h.get(0x24), h.word(CAP_PTR), h.word(CAP_LEN)),
                         (ptr, n, ptr, n))
        self.assertEqual(h.calls, [DCACHE])
        cache_i = next(i for i, e in enumerate(h.events) if e[:2] == ('call', DCACHE))
        ptr_i = next(i for i, e in enumerate(h.events) if e == ('write', CAP_PTR, 4, ptr))
        len_i = next(i for i, e in enumerate(h.events) if e == ('write', CAP_LEN, 4, n))
        self.assertLess(cache_i, ptr_i)
        self.assertLess(ptr_i, len_i)

    def test_allocate_zeros_descriptor_preserves_abi_and_aligns_within_owned_extent(self):
        for raw in (HEAP, HEAP + 4, HEAP + 127):
            with self.subTest(raw=hex(raw)):
                h = self.helper(raw=raw).run(0)
                self.assertEqual(h.calls, [H_GET, H_ADDR])
                self.assertEqual((h.get(4), h.get(8), h.get(0x0C), h.get(0x14), h.get(0x28)),
                                 (0, 1, raw, 0x10000, 0xF1234567))
                self.assertEqual(h.get(0x10), (raw + 127) & ~127)
                self.assertEqual(h.get(0x2C), 1)
                self.assertEqual((h.word(CAP_PTR), h.word(CAP_LEN)), (0, 0))

    def test_allocation_failure_is_sticky_and_never_retries_or_frees(self):
        for raw, status in ((0, 3), (0x3FFFFFFC, 4), (0x7FFF0001, 4), (0xC0000000, 4)):
            with self.subTest(raw=hex(raw)):
                h = self.helper(raw=raw).run(0)
                self.assert_denied(h, status)
                self.assertEqual(h.get(8), 1)
                h.run(0)
                self.assert_denied(h, 2)
                self.assertEqual(h.calls, [])

    def test_successful_allocation_cannot_be_repeated(self):
        h = self.helper().run(0)
        owner = tuple(h.get(i) for i in (8, 0x0C, 0x10, 0x14))
        h.run(0)
        self.assert_denied(h, 2)
        self.assertEqual(h.calls, [], 'allocator invoked twice')
        self.assertEqual(tuple(h.get(i) for i in (8, 0x0C, 0x10, 0x14)), owner)

    def test_nonempty_owner_cannot_be_allocated(self):
        for off in (8, 0x0C, 0x10):
            h = self.helper()
            h.put(off, 1)
            h.run(0)
            self.assert_denied(h, 2)
            self.assertEqual(h.calls, [])

    def test_unknown_operations_clear_stale_reply_without_calls(self):
        for op in (2, 0xFFFFFFFF):
            h = self.helper().run(op)
            self.assert_denied(h, 1)
            self.assertEqual(h.calls, [])

    def test_export_requires_owned_allocation(self):
        for offset, bad in ((8, 0), (8, 2), (0x0C, 0), (0x0C, 0xC0000000),
                            (0x10, HEAP + 0x100), (0x14, 0x20000)):
            with self.subTest(offset=offset, value=bad):
                h = self.helper().run(0)
                h.completed_capture()
                h.put(offset, bad)
                h.run(1)
                self.assert_denied(h, 4)
                self.assertEqual(h.calls, [])

    def test_export_configuration_bounded_before_capture_read(self):
        for nonce, capacity in ((0, 64), (NONCE, 0), (NONCE, 257), (NONCE, 0xFFFFFFFF)):
            h = self.helper().run(0)
            h.put(0x18, nonce)
            h.put(0x1C, capacity)
            h.run(1)
            self.assert_denied(h, 5)

    def test_mapping_register_failure_is_sticky_before_owner_base_publication(self):
        bad_registers = (('sctlr', 0), ('sctlr', 0x10000001), ('sctlr', 0x02000001),
                         ('ttbcr', 1), ('ttbr0', 0x44300000), ('dacr', 0xFFFFFFFF))
        for key, value in bad_registers:
            with self.subTest(register=key, value=value):
                h = self.helper()
                h.cp[key] = value
                h.run(0)
                self.assert_denied(h, 8)
                self.assertEqual((h.get(8), h.get(0x10), h.get(0x2C)), (1, 0, 0))
                h.run(0)
                self.assert_denied(h, 2)
                self.assertEqual(h.calls, [])

    def test_every_first_and_last_supersection_descriptor_is_checked(self):
        raw = 0x45FF8000  # 64 KiB crosses the 0x46000000 supersection boundary.
        for boundary in (raw, raw + 0xFFFF):
            for index in range(16):
                with self.subTest(boundary=hex(boundary), index=index):
                    h = self.helper(raw=raw)
                    at = TABLE + (((boundary >> 20) & ~15) + index) * 4
                    h.uc.mem_write(at, struct.pack('<I', h.word(at) ^ 4))
                    h.run(0)
                    self.assert_denied(h, 8)
                    self.assertEqual(h.get(0x10), 0)
        h = self.helper(raw=raw).run(0)
        ptr = h.completed_capture()
        h.run(1)
        self.assert_exported(h, ptr, 64)

    def test_mapping_is_revalidated_before_export(self):
        for change in ('register', 'table'):
            h = self.helper().run(0)
            h.completed_capture()
            if change == 'register':
                h.cp['sctlr'] = 0
            else:
                at = TABLE + (((h.raw >> 20) & ~15) + 15) * 4
                h.uc.mem_write(at, struct.pack('<I', h.word(at) ^ 0x1000))
            h.run(1)
            self.assert_denied(h, 8)
            self.assertEqual(h.get(0x2C), 0)

    def test_partial_enabled_or_mismatched_count_cannot_export(self):
        for off, value in ((28, 0), (28, 2), (20, 1), (24, 63), (24, 65)):
            h = self.helper().run(0)
            ptr = h.completed_capture()
            h.uc.mem_write(ptr + off, struct.pack('<I', value))
            h.run(1)
            self.assert_denied(h, 6)

    def test_header_source_identity_nonce_and_reserved_words_are_guarded(self):
        for word in (0, 1, 2, 3, 4, 8, 9, 10, 11, 12, 13, 14, 15):
            with self.subTest(word=word):
                h = self.helper().run(0)
                ptr = h.completed_capture()
                value = h.word(ptr + word * 4) ^ 1
                h.uc.mem_write(ptr + word * 4, struct.pack('<I', value))
                h.run(1)
                self.assert_denied(h, 7)

    def test_full_capture_export_publishes_only_after_clean_and_never_mutates_capture(self):
        for capacity in (1, 64, 256):
            with self.subTest(capacity=capacity):
                h = self.helper().run(0)
                ptr = h.completed_capture(capacity)
                before = bytes(h.uc.mem_read(HEAP, HEAP_BYTES))
                h.run(1)
                self.assert_exported(h, ptr, capacity)
                self.assertEqual(bytes(h.uc.mem_read(HEAP, HEAP_BYTES)), before)

    def test_repeat_export_does_not_reallocate_or_recycle_capture(self):
        h = self.helper().run(0)
        ptr = h.completed_capture()
        for _ in range(2):
            h.run(1)
            self.assert_exported(h, ptr, 64)
        self.assertEqual(h.get(8), 1)

    def test_claimed_parameter_and_code_locations_are_not_fixed(self):
        param, code_base = PARAM + 0x300, CODE + 0x4000
        h = ArmHelper(assemble(param=param), param=param, code_base=code_base).run(0)
        ptr = h.completed_capture()
        h.run(1)
        self.assert_exported(h, ptr, 64)

    def test_mutation_missing_full_guard_is_detected(self):
        source = (HERE / 'af_probe_helper.S').read_text()
        source = source.replace('    bne incomplete\n    dmb sy', '    nop\n    dmb sy', 1)
        h = ArmHelper(assemble(source)).run(0)
        ptr = h.completed_capture()
        h.uc.mem_write(ptr + 28, struct.pack('<I', 0))
        h.run(1)
        with self.assertRaises(AssertionError):
            self.assert_denied(h, 6)

    def test_mutation_omitted_cache_call_is_detected(self):
        source = (HERE / 'af_probe_helper.S').read_text()
        marker = '    LDA ip, F_DCACHE              /* once per full export, never in the AF hook */\n    blx ip'
        self.assertIn(marker, source)
        h = ArmHelper(assemble(source.replace(marker, '    nop\n    nop'))).run(0)
        ptr = h.completed_capture()
        h.run(1)
        with self.assertRaises(AssertionError):
            self.assert_exported(h, ptr, 64)

    def test_mutation_repeated_allocation_guard_is_detected(self):
        source = (HERE / 'af_probe_helper.S').read_text()
        source = source.replace('    bne repeated', '    nop', 1)
        h = ArmHelper(assemble(source)).run(0).run(0)
        with self.assertRaises(AssertionError):
            self.assert_denied(h, 2)


if __name__ == '__main__':
    unittest.main()
