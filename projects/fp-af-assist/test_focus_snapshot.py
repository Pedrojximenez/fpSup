"""Offline ARM assembly/disassembly and narrow instruction-model tests.

No camera, daemon, shell transport, or firmware function is invoked.  The small
instruction model executes only this handler's whitelisted integer/load/store
subset; it is not a CPU/cache/interrupt emulator or proof of optical alignment.
Capstone is used to inspect the actual compiled bytes, not the assembly text.
"""
import hashlib
import importlib.util
from pathlib import Path
import struct
import unittest
from unittest import mock

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
from capstone.arm import ARM_OP_IMM, ARM_OP_MEM, ARM_OP_REG


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
SOURCE = ROOT / 'focus_snapshot.S'
P = 0xC072F700
ENTRY = 0xC072F740
LIMIT = 0xC072F800
MAGIC = 0x31424641
SCHEDULER = 0xC31F8CB4
H = 0xC32985E8
L = 0xC32986B4


class InstructionModel:
    """Deliberately tiny model; unknown instructions/address accesses fail."""
    def __init__(self, code, instructions, *, magic=MAGIC, operation=9, nonce=0x12345678):
        self.instructions = {item.address: item for item in instructions}
        self.memory = {ENTRY + offset: struct.unpack_from('<I', code, offset)[0]
                       for offset in range(0, len(code), 4)}
        self.memory.update({P + offset: 0xA0000000 + offset for offset in range(0, 64, 4)})
        self.memory.update({P: magic, P + 4: nonce, P + 8: operation,
                            SCHEDULER: 1, SCHEDULER + 4: 1, H: 20536, L: 48700})
        self.regs = {'r%d' % i: 0x10000 + i * 4 for i in range(13)}
        self.regs.update(ip=self.regs.pop('r12'), sp=0x80001000, lr=0x90000000)
        self.initial_regs = dict(self.regs)
        self.reads = []
        self.writes = []
        self.trace = []
        self.hook = None
        self.zero = False

    def read(self, address):
        if self.hook is not None:
            self.hook(address)
        self.reads.append(address)
        if address not in self.memory:
            raise AssertionError('unknown read 0x%08x' % address)
        return self.memory[address]

    def reg(self, insn, operand):
        return insn.reg_name(operand.reg)

    def value(self, insn, operand):
        if operand.type == ARM_OP_IMM:
            return operand.imm & 0xffffffff
        if operand.type == ARM_OP_REG:
            name = self.reg(insn, operand)
            return insn.address + 8 if name == 'pc' else self.regs[name]
        raise AssertionError('unsupported operand')

    def address(self, insn, operand):
        if operand.type != ARM_OP_MEM or operand.mem.index:
            raise AssertionError('unsupported addressing')
        base = insn.reg_name(operand.mem.base)
        value = insn.address + 8 if base == 'pc' else self.regs[base]
        return (value + operand.mem.disp) & 0xffffffff

    def run(self):
        pc = ENTRY
        for _ in range(64):
            if pc not in self.instructions:
                raise AssertionError('execution left fixed code')
            insn = self.instructions[pc]
            self.trace.append((pc, insn.mnemonic))
            operands = insn.operands
            next_pc = pc + 4
            if insn.mnemonic == 'ldr':
                self.regs[self.reg(insn, operands[0])] = self.read(self.address(insn, operands[1]))
            elif insn.mnemonic == 'ldm':
                address = self.value(insn, operands[0])
                for index, operand in enumerate(operands[1:]):
                    self.regs[self.reg(insn, operand)] = self.read(address + 4 * index)
            elif insn.mnemonic == 'str':
                address = self.address(insn, operands[1])
                if not P <= address <= P + 0x38 or address & 3:
                    raise AssertionError('store outside parameter/output boundary')
                value = self.value(insn, operands[0])
                self.memory[address] = value
                self.writes.append((address, value))
            elif insn.mnemonic == 'cmp':
                self.zero = self.value(insn, operands[0]) == self.value(insn, operands[1])
            elif insn.mnemonic == 'mov':
                self.regs[self.reg(insn, operands[0])] = self.value(insn, operands[1])
            elif insn.mnemonic == 'bne':
                if not self.zero:
                    next_pc = self.value(insn, operands[0])
            elif insn.mnemonic == 'dmb':
                pass  # Structural check only; no memory-ordering claim.
            elif insn.mnemonic == 'bx':
                if self.reg(insn, operands[0]) != 'lr':
                    raise AssertionError('unexpected indirect branch')
                return self.regs['lr']
            else:
                raise AssertionError('unsupported instruction ' + insn.mnemonic)
            pc = next_pc
        raise AssertionError('instruction bound exceeded')


class FocusSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = REPO / 'fpSup' / 'fp_usb_shell' / 'armasm.py'
        spec = importlib.util.spec_from_file_location('snapshot_offline_armasm', path)
        assembler = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(assembler)
        cls.code = assembler.assemble(SOURCE)
        cls.symbols = assembler.symbols(SOURCE)
        disassembler = Cs(CS_ARCH_ARM, CS_MODE_ARM)
        disassembler.detail = True
        cls.instructions = list(disassembler.disasm(cls.code[:cls.symbols['code_end']], ENTRY))

    def setUp(self):
        guard = mock.patch('socket.socket', side_effect=AssertionError('socket/USB forbidden'))
        guard.start()
        self.addCleanup(guard.stop)

    def model(self, **kwargs):
        return InstructionModel(self.code, self.instructions, **kwargs)

    def test_compiled_image_fits_reserved_gap_with_entry_at_zero(self):
        self.assertEqual(self.symbols['entry'], 0)
        self.assertEqual(len(self.code), 152)
        self.assertEqual(ENTRY + len(self.code), 0xC072F7D8)
        self.assertLessEqual(ENTRY + len(self.code), LIMIT)
        self.assertEqual(len(self.code) % 4, 0)
        self.assertEqual(hashlib.sha256(self.code).hexdigest(),
                         'd3b3d49d8799c85a796ddb80ab5102e8058feedb41362173f8ac822a0dda37cd')

    def test_literal_pool_has_only_fixed_allowlisted_constants(self):
        constants = struct.unpack('<5I', self.code[self.symbols['code_end']:])
        self.assertEqual(constants, (P, MAGIC, SCHEDULER, H, L))
        for insn in self.instructions:
            if insn.mnemonic == 'ldr' and insn.operands[1].mem.base:
                operand = insn.operands[1]
                if insn.reg_name(operand.mem.base) == 'pc':
                    address = insn.address + 8 + operand.mem.disp
                    self.assertTrue(ENTRY + self.symbols['code_end'] <= address < ENTRY + len(self.code))

    def test_exact_instruction_stream_has_no_calls_loops_or_mmio(self):
        actual = [(item.mnemonic, item.op_str) for item in self.instructions]
        self.assertEqual(actual, [
            ('ldr', 'ip, [pc, #0x7c]'), ('ldr', 'r0, [ip]'),
            ('ldr', 'r1, [pc, #0x78]'), ('cmp', 'r0, r1'), ('bne', '#0xc072f7c0'),
            ('ldr', 'r0, [ip, #8]'), ('cmp', 'r0, #9'), ('bne', '#0xc072f7c0'),
            ('mov', 'r0, #0'), ('str', 'r0, [ip]'), ('ldr', 'r1, [ip, #4]'),
            ('str', 'r1, [ip, #0x18]'), ('mov', 'r1, #1'), ('str', 'r1, [ip, #0x1c]'),
            ('str', 'r0, [ip, #0x20]'), ('ldr', 'r2, [pc, #0x48]'),
            ('ldm', 'r2, {r0, r1}'), ('str', 'r0, [ip, #0x24]'), ('str', 'r1, [ip, #0x28]'),
            ('ldr', 'r3, [pc, #0x3c]'), ('ldr', 'r0, [r3]'), ('str', 'r0, [ip, #0x2c]'),
            ('ldr', 'r3, [pc, #0x34]'), ('ldr', 'r0, [r3]'), ('str', 'r0, [ip, #0x30]'),
            ('ldm', 'r2, {r0, r1}'), ('str', 'r0, [ip, #0x34]'), ('str', 'r1, [ip, #0x38]'),
            ('dmb', 'sy'), ('mov', 'r0, #2'), ('str', 'r0, [ip, #0x1c]'),
            ('mov', 'r0, #0'), ('bx', 'lr')])

    def test_every_store_is_ip_relative_within_only_requested_output_words(self):
        stores = [item for item in self.instructions if item.mnemonic == 'str']
        self.assertTrue(all(item.reg_name(item.operands[1].mem.base) == 'ip' for item in stores))
        self.assertEqual([item.operands[1].mem.disp for item in stores],
                         [0, 0x18, 0x1c, 0x20, 0x24, 0x28, 0x2c, 0x30, 0x34, 0x38, 0x1c])

    def test_valid_request_copies_exact_fields_then_publishes_complete(self):
        model = self.model()
        original = dict(model.memory)
        self.assertEqual(model.run(), model.initial_regs['lr'])
        self.assertEqual([model.memory[P + offset] for offset in range(0x18, 0x3c, 4)],
                         [0x12345678, 2, 0, 1, 1, 20536, 48700, 1, 1])
        self.assertEqual(model.memory[P], 0)
        self.assertEqual(model.writes[0], (P, 0))
        self.assertEqual(model.writes[-1], (P + 0x1c, 2))
        self.assertEqual([value for address, value in model.writes if address == P + 0x1c], [1, 2])
        for address, value in original.items():
            if address not in {item[0] for item in model.writes}:
                self.assertEqual(model.memory[address], value)

    def test_only_fixed_source_values_are_read_in_order(self):
        model = self.model()
        model.run()
        self.assertEqual([address for address in model.reads if address in (SCHEDULER, SCHEDULER + 4, H, L)],
                         [SCHEDULER, SCHEDULER + 4, H, L, SCHEDULER, SCHEDULER + 4])
        self.assertEqual([address for address in model.reads if P <= address < ENTRY], [P, P + 8, P + 4])

    def test_magic_and_running_nonce_are_published_before_any_statistics_read(self):
        model = self.model(nonce=0xFEDCBA98)
        def hook(address):
            if address in (SCHEDULER, SCHEDULER + 4, H, L):
                self.assertEqual(model.memory[P], 0)
                self.assertEqual(model.memory[P + 0x18], 0xFEDCBA98)
                self.assertEqual(model.memory[P + 0x1c], 1)
        model.hook = hook
        model.run()

    def test_invalid_magic_or_operation_does_not_write_or_read_statistics(self):
        cases = [{'magic': value} for value in (0, 1, 0xffffffff, MAGIC ^ 1)]
        cases += [{'operation': value} for value in (0, 1, 7, 8, 10, 0xffffffff)]
        for case in cases:
            with self.subTest(case=case):
                model = self.model(**case)
                before = dict(model.memory)
                model.run()
                self.assertEqual(model.writes, [])
                self.assertEqual(model.memory, before)
                self.assertFalse(set(model.reads) & {SCHEDULER, SCHEDULER + 4, H, L})

    def test_repeated_echo_without_rearming_is_inert(self):
        model = self.model()
        model.run()
        before = dict(model.memory)
        model.reads.clear()
        model.writes.clear()
        model.run()
        self.assertEqual(model.writes, [])
        self.assertEqual(model.memory, before)
        self.assertFalse(set(model.reads) & {SCHEDULER, SCHEDULER + 4, H, L})

    def test_new_nonce_and_rearm_produce_fresh_copy(self):
        model = self.model()
        model.run()
        model.memory.update({P: MAGIC, P + 4: 123, H: 456, L: 789})
        model.run()
        self.assertEqual(model.memory[P + 0x18], 123)
        self.assertEqual(model.memory[P + 0x2c], 456)
        self.assertEqual(model.memory[P + 0x30], 789)

    def test_phase_mode_change_is_recorded_not_hidden_or_validated(self):
        model = self.model()
        def hook(address):
            if address == L:
                model.memory[SCHEDULER] = 2
                model.memory[SCHEDULER + 4] = 3
        model.hook = hook
        model.run()
        self.assertEqual([model.memory[P + offset] for offset in (0x24, 0x28, 0x34, 0x38)],
                         [1, 1, 2, 3])

    def test_zero_and_saturated_statistics_are_copied_for_host_rejection(self):
        for h, l in ((0, 0), (0xffffffff, 0xffffffff)):
            with self.subTest(h=h, l=l):
                model = self.model()
                model.memory.update({H: h, L: l})
                model.run()
                self.assertEqual(model.memory[P + 0x2c], h)
                self.assertEqual(model.memory[P + 0x30], l)

    def test_abi_preserves_all_callee_saved_registers_stack_and_lr(self):
        for case in ({}, {'magic': 0}, {'operation': 8}):
            model = self.model(**case)
            model.run()
            for name in ['r%d' % i for i in range(4, 12)] + ['sp', 'lr']:
                self.assertEqual(model.regs[name], model.initial_regs[name])
            self.assertEqual(model.regs['sp'] % 8, 0)
        model = self.model()
        model.run()
        self.assertEqual(model.regs['r0'], 0)


if __name__ == '__main__':
    unittest.main()
