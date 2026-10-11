"""Offline tests of compiled ARM bytes and finite-batch framing.

Synthetic addresses below are NOT a camera memory reservation. This narrow
instruction model is not a CPU/IRQ/cache/USB emulator and proves no timing.
"""
import array
import random
import struct
import unittest

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
from capstone.arm import ARM_OP_IMM, ARM_OP_MEM, ARM_OP_REG, ARM_SFT_LSL

if __package__:
    from . import af_batch as fmt
    from . import build_publication as build
else:
    import af_batch as fmt
    import build_publication as build

CODE, STATE, RECORDS, NONCE = 0xC0800000, 0xD0000000, 0xD0001000, 0x12345678
# Independent expected source map; not extracted from the payload under test.
SOURCES = {
    16: (0xC32985E8, 100), 20: (0xC32986B4, 200),
    24: (0xC3476418, 10807), 28: (0xC31F8CB4, 2),
    32: (0xC31F8CB8, 1), 36: (0xC3291514, 0), 40: (0xC3291534, 0),
    44: (0xC32915B0, 14), 48: (0xC343B5A0, 1024),
    52: (0xC343B5A8, 128), 56: (0xC343B5B4, 1024),
    60: (0xC343B5BC, 1), 64: (0xC32915B4, 1024),
    68: (0xC3291694, 100), 72: (0xC329169C, 60), 76: (0xC32916B0, 28),
    80: (0xC30338C8, 0), 84: (0xC30338D0, 0), 88: (0xC3033A6C, 0),
    92: (0xC32046A4, 0), 96: (0xC32065A0, 0), 100: (0xC3298918, 1),
    104: (0xC343B7BC, 11), 108: (0xC343B7C0, 22),
    112: (0xC31F8CB4, 2), 116: (0xC31F8CB8, 1),
    120: (0xC32914E0, 10707),
}


# Tight bound on the recorder: it must stay a short straight-line leaf. Raised
# from 200 when the staged level and the re-entrancy mark were added.
BOUND = 216


class InstructionModel:
    def __init__(self, image, initial, instructions, capacity):
        self.capacity = capacity
        self.instructions = {i.address: i for i in instructions}
        self.memory = {}
        for base, blob in ((CODE, image), (STATE, initial[:64]), (RECORDS, initial[64:])):
            self.memory.update({base + n: struct.unpack_from('<I', blob, n)[0]
                                for n in range(0, len(blob), 4)})
        self.memory.update({address: value for address, value in SOURCES.values()})
        self.regs = {f'r{i}': 0xAB000000 + i for i in range(12)}
        self.regs.update(ip=0xAB00000C, sp=0x80000004, lr=fmt.CONTINUATION)
        self.regs['r4'] = fmt.MODEL
        self.regs.update(r0=self.regs['r4'], r1=0, r2=0)
        self.native_calls = 0
        self.events = []
        self.read_hook = None
        self.write_hook = None
        self.zero = self.carry = False

    def read(self, address, byte=False):
        if self.read_hook:
            self.read_hook(address)
        if address not in self.memory:
            raise AssertionError(f'unknown read {address:#x}')
        self.events.append(('read', address))
        return self.memory[address] & (255 if byte else 0xffffffff)

    def reg(self, ins, op):
        return ins.reg_name(op.reg)

    def value(self, ins, op):
        if op.type == ARM_OP_IMM:
            return op.imm & 0xffffffff
        if op.type != ARM_OP_REG:
            raise AssertionError('unsupported value')
        name = self.reg(ins, op)
        result = ins.address + 8 if name == 'pc' else self.regs[name]
        if op.shift.type:
            if op.shift.type != ARM_SFT_LSL:
                raise AssertionError('unsupported shift')
            result <<= op.shift.value
        return result & 0xffffffff

    def address(self, ins, op):
        if op.type != ARM_OP_MEM or op.mem.index:
            raise AssertionError('unsupported address')
        name = ins.reg_name(op.mem.base)
        base = ins.address + 8 if name == 'pc' else self.regs[name]
        return (base + op.mem.disp) & 0xffffffff

    def dump(self):
        return b''.join(struct.pack('<I', self.memory[base + n])
                        for base, size in ((STATE, 64), (RECORDS, self.capacity * 128))
                        for n in range(0, size, 4))

    def run(self):
        self.regs.update(r0=self.regs['r4'], r1=0, r2=0, lr=fmt.CONTINUATION)
        incoming = dict(self.regs)
        pc, steps = CODE, 0
        while pc != fmt.CONTINUATION:
            if pc == fmt.PRODUCER:
                # Exact native argument/SP entry. Simulated callee, never executed.
                for name in ('r0', 'r1', 'r2', 'sp'):
                    assert self.regs[name] == incoming[name], name
                self.native_calls += 1
                self.events.append(('native', self.native_calls))
                self.memory[SOURCES[16][0]] = 100 * self.native_calls
                self.memory[SOURCES[20][0]] = 200 * self.native_calls
                for i, name in enumerate(('r0', 'r1', 'r2', 'r3', 'ip')):
                    self.regs[name] = 0xBB000000 + i
                self.after_native = dict(self.regs)
                pc = self.regs['lr']
                continue
            steps += 1
            if steps > BOUND or pc not in self.instructions:
                raise AssertionError('instruction bound/code boundary exceeded')
            ins = self.instructions[pc]
            op, name, next_pc = ins.operands, ins.mnemonic, pc + 4
            if name in ('ldr', 'ldrb'):
                value = self.read(self.address(ins, op[1]), name == 'ldrb')
                dest = self.reg(ins, op[0])
                if dest == 'pc':
                    next_pc = value
                else:
                    self.regs[dest] = value
            elif name == 'str':
                address, value = self.address(ins, op[1]), self.value(ins, op[0])
                # The level word (STATE+48) is host-owned: the hook only reads it.
                if address & 3 or not (address in (STATE + 20, STATE + 24, STATE + 28,
                                                   STATE + 52, STATE + 56, STATE + 60)
                                       or RECORDS <= address < RECORDS + self.capacity * 128):
                    raise AssertionError('write outside finite output')
                self.memory[address] = value
                self.events.append(('write', address, value))
                if self.write_hook:
                    self.write_hook(address, value)
            elif name in ('mov', 'movw', 'movt', 'mvn', 'add', 'sub'):
                dest = self.reg(ins, op[0])
                value = self.value(ins, op[1])
                if name == 'movt':
                    value = (self.regs[dest] & 0xffff) | (value << 16)
                elif name == 'mvn':
                    value = ~value
                elif name == 'add':
                    value += self.value(ins, op[2])
                elif name == 'sub':
                    value -= self.value(ins, op[2])
                self.regs[dest] = value & 0xffffffff
            elif name == 'cmp':
                a, b = self.value(ins, op[0]), self.value(ins, op[1])
                self.zero, self.carry = a == b, a >= b
            elif name in ('bne', 'beq', 'bhs'):
                if {'bne': not self.zero, 'beq': self.zero, 'bhs': self.carry}[name]:
                    next_pc = self.value(ins, op[0])
            elif name == 'dmb':
                self.events.append(('barrier',))  # No cache/IRQ/DMA claim.
            else:
                raise AssertionError(f'unsupported instruction {name}')
            pc = next_pc
        return steps


class HighrateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builds = {}
        for capacity in (1, 256):
            code, initial, manifest = build.assemble(code_base=CODE, state_base=STATE,
                                  records_base=RECORDS, capacity=capacity, nonce=NONCE,
                                  level=fmt.LEVEL_RECORD)
            symbols = build._assembler().symbols(build.SOURCE, defines=build.defines(
                state_base=STATE, records_base=RECORDS, capacity=capacity))
            dis = Cs(CS_ARCH_ARM, CS_MODE_ARM)
            dis.detail = True
            instructions = list(dis.disasm(code[:symbols['code_end']], CODE))
            cls.builds[capacity] = code, initial, instructions, manifest, symbols

    def model(self, capacity=1):
        code, initial, ins, _, _ = self.builds[capacity]
        return InstructionModel(code, initial, ins, capacity)

    def capture(self, capacity=1):
        model = self.model(capacity)
        for _ in range(capacity):
            model.run()
        return model.dump()

    def test_compiled_abi_leaf_and_forward_only_recorder(self):
        for code, _, instructions, manifest, symbols in self.builds.values():
            self.assertEqual(symbols['entry'], 0)
            self.assertEqual(struct.unpack('<2I', code[symbols['code_end']:]),
                             (fmt.PRODUCER, fmt.CONTINUATION))
            self.assertFalse(manifest['deployment_ready'])
            self.assertLess(len(instructions), BOUND)
            for ins in instructions:
                self.assertIn(ins.mnemonic, ('add', 'sub', 'ldr', 'ldrb', 'movw', 'movt',
                              'cmp', 'beq', 'bne', 'bhs', 'str', 'mov', 'mvn', 'dmb'))
                if ins.mnemonic in ('bne', 'beq', 'bhs'):
                    self.assertGreater(ins.operands[0].imm & 0xffffffff, ins.address)
                if ins.mnemonic in ('add', 'sub', 'ldr', 'ldrb', 'movw', 'movt', 'mov', 'mvn'):
                    allowed = ('lr',) if ins.address == CODE else ('r0', 'r1', 'pc')
                    self.assertIn(ins.reg_name(ins.operands[0].reg), allowed)

    def test_original_once_and_native_stack_callee_state_preserved(self):
        for alignment in (0, 4):
            model = self.model()
            model.regs['sp'] = 0x80000000 + alignment
            self.assertLess(model.run(), BOUND)
            self.assertEqual(model.native_calls, 1)
            for name in [f'r{i}' for i in range(2, 12)] + ['ip', 'sp']:
                self.assertEqual(model.regs[name], model.after_native[name], name)

    def test_all_fixed_fields_and_byte_widths(self):
        model = self.model()
        model.memory[SOURCES[60][0]] = 0x12340001
        model.memory[SOURCES[84][0]] = 0x34560000
        model.run()
        record = fmt.decode_capture(model.dump(), expected_nonce=NONCE)['records'][0]
        for offset, (_, value) in SOURCES.items():
            self.assertEqual(record[fmt.FIELDS[offset // 4]], value, offset)
        self.assertEqual(record['context_issues'], [])
        self.assertNotEqual(record['cached_lens_position_raw'], record['af_manager_position_raw'])

    def writes(self, model):
        return [event for event in model.events if event[0] == 'write']

    def test_identity_rejections_touch_nothing_but_still_call_native(self):
        # Magic, schema, record size, capacity, nonce and the model word: a
        # buffer that is not ours is not even counted in.
        for offset, values in ((0, (0,)), (4, (0, 1, 3)), (8, (0, 64)),
                               (12, (0, 2)), (16, (0,))):
            for value in values:
                with self.subTest(offset=offset, value=value):
                    model = self.model()
                    model.memory[STATE + offset] = value
                    model.run()
                    self.assertEqual(model.native_calls, 1)
                    self.assertFalse(self.writes(model))
        model = self.model()
        model.regs['r4'] ^= 4
        model.run()
        self.assertEqual(model.native_calls, 1)
        self.assertFalse(self.writes(model))

    def test_state_rejections_count_the_return_but_publish_no_record(self):
        for offset, values in ((20, (0, 2)), (24, (1, 2, 0xffffffff)),
                               (28, (1, 2, 0xffffffff))):
            for value in values:
                with self.subTest(offset=offset, value=value):
                    model = self.model()
                    model.memory[STATE + offset] = value
                    model.run()
                    self.assertEqual(model.native_calls, 1)
                    self.assertEqual({event[1] for event in self.writes(model)},
                                     {STATE + 52, STATE + 56})
                    self.assertEqual(model.memory[STATE + 52], 1)   # counted
                    self.assertEqual(model.memory[STATE + 56], 0)   # mark cleared

    def test_off_and_unknown_levels_are_wholly_inert(self):
        for level in (0, 2, 4, 5, 0xffffffff):
            with self.subTest(level=level):
                model = self.model()
                model.memory[STATE + 48] = level
                model.run()
                self.assertEqual(model.native_calls, 1)
                self.assertFalse(self.writes(model))
                self.assertEqual(model.memory[STATE + 52], 0)   # not even counted

    def test_count_level_counts_returns_and_publishes_no_record(self):
        model = self.model()
        model.memory[STATE + 48] = fmt.LEVEL_COUNT
        for _ in range(3):
            model.run()
        self.assertEqual(model.native_calls, 3)
        self.assertEqual({event[1] for event in self.writes(model)},
                         {STATE + 52, STATE + 56})
        decoded = fmt.decode_capture(model.dump(), expected_nonce=NONCE)
        self.assertEqual((decoded['hits'], decoded['count'], decoded['level']),
                         (3, 0, fmt.LEVEL_COUNT))
        self.assertFalse(decoded['full'])
        self.assertTrue(decoded['serialization_verified'])
        self.assertEqual(decoded['missed_by_level'], 3)

    def test_a_second_body_latches_overlaps_and_publishes_nothing(self):
        model = self.model()
        model.memory[STATE + 56] = 1          # a body is already running
        model.run()
        self.assertEqual(model.native_calls, 1)
        self.assertEqual([event[1] for event in self.writes(model)], [STATE + 60])
        self.assertEqual(model.memory[STATE + 60], 1)
        self.assertEqual(model.memory[STATE + 52], 0)   # the intruder never counts
        self.assertEqual(model.memory[STATE + 56], 1)   # nor clears the owner's mark
        decoded = fmt.decode_capture(model.dump(), expected_nonce=NONCE)
        self.assertEqual((decoded['overlaps'], decoded['in_body']), (1, 1))
        self.assertFalse(decoded['serialization_verified'])

    def test_once_overlaps_is_latched_no_record_is_ever_published(self):
        model = self.model()
        model.memory[STATE + 60] = 1
        for _ in range(3):
            model.run()
        self.assertEqual({event[1] for event in self.writes(model)},
                         {STATE + 52, STATE + 56})
        self.assertEqual(model.memory[STATE + 24], 0)
        self.assertEqual(model.memory[STATE + 52], 3)   # returns still counted
        self.assertFalse(fmt.decode_capture(model.dump(),
                                            expected_nonce=NONCE)['serialization_verified'])

    def test_the_mark_is_held_across_the_body_and_cleared_at_the_end(self):
        model = self.model()
        seen = []
        model.write_hook = lambda address, value: seen.append(
            (address, model.memory[STATE + 56]))
        model.run()
        during = [mark for address, mark in seen
                  if RECORDS <= address < RECORDS + 128]
        self.assertTrue(during and all(mark == 1 for mark in during))
        self.assertEqual(model.memory[STATE + 56], 0)

    def test_the_hook_never_writes_the_host_owned_level_word(self):
        model = self.model(256)
        for _ in range(258):
            model.run()
        self.assertNotIn(STATE + 48, {event[1] for event in self.writes(model)})
        self.assertEqual(model.memory[STATE + 48], fmt.LEVEL_RECORD)

    def test_a_record_is_never_visible_before_its_body_completes(self):
        # A committed prefix is now decodable at any moment, so the invariant is
        # that a half-written record is never inside that prefix.
        model = self.model()
        committed = [0]

        def check(address, value):
            if address == STATE + 24:
                committed[0] = value     # the record is committed before this
            decoded = fmt.decode_capture(model.dump(), expected_nonce=NONCE)
            self.assertEqual(decoded['count'], committed[0])
            self.assertEqual(len(decoded['records']), committed[0])
        model.write_hook = check
        model.run()
        events = model.events
        complement = events.index(('write', RECORDS + 124, 0xfffffffe))
        self.assertEqual(events[complement:complement + 4], [
            ('write', RECORDS + 124, 0xfffffffe), ('barrier',),
            ('write', RECORDS, 1), ('barrier',)])
        committed_at = events.index(('write', RECORDS, 1))
        body_stores = [(index, event[1]) for index, event in enumerate(events)
                       if event[0] == 'write' and RECORDS < event[1] < RECORDS + 128]
        self.assertEqual({addr for _, addr in body_stores}, set(range(RECORDS + 4, RECORDS + 128, 4)))
        self.assertTrue(all(index < committed_at for index, _ in body_stores))
        self.assertGreater(events.index(('write', STATE + 24, 1)), committed_at)
        self.assertEqual(events[-7:], [('write', STATE + 24, 1),
            ('write', STATE + 20, 0), ('barrier',), ('write', STATE + 28, 1),
            ('barrier',), ('write', STATE + 56, 0),
            ('read', CODE + self.builds[1][4]['continuation_address'])])

    def test_a_committed_prefix_decodes_without_waiting_for_full(self):
        # Requirement of the one-shot export: no polling for full=1.
        model = self.model(256)
        for _ in range(7):
            model.run()
        decoded = fmt.decode_capture(model.dump(), expected_nonce=NONCE)
        self.assertEqual((decoded['count'], decoded['hits'], decoded['capacity']),
                         (7, 7, 256))
        self.assertFalse(decoded['full'])
        self.assertEqual(decoded['missed_by_level'], 0)
        self.assertEqual([r['sequence'] for r in decoded['records']], list(range(1, 8)))
        self.assertTrue(decoded['serialization_verified'])
        with self.assertRaises(fmt.CaptureError):
            fmt.decode_capture(model.dump(), expected_nonce=NONCE, require_full=True)

    def test_full_capture_never_wraps_or_overwrites(self):
        model = self.model(256)
        for _ in range(256):
            model.run()
        before = model.dump()
        model.events.clear()
        for _ in range(3):
            model.run()
        after = model.dump()
        # Records, count, enabled and full are frozen; only the return counter
        # and the transient body mark move.
        self.assertEqual(after[64:], before[64:])
        for offset in (20, 24, 28):
            self.assertEqual(after[offset:offset + 4], before[offset:offset + 4])
        self.assertEqual({event[1] for event in self.writes(model)},
                         {STATE + 52, STATE + 56})
        self.assertEqual(model.memory[STATE + 52], 259)
        self.assertEqual(model.native_calls, 259)
        decoded = fmt.decode_capture(before, expected_nonce=NONCE, require_full=True)
        self.assertEqual([r['h'] for r in decoded['records']], list(range(100, 25601, 100)))
        self.assertFalse(decoded['usable_for_af_control'])
        self.assertFalse(decoded['usable_for_dfd'])
        self.assertFalse(decoded['detach_verified'])
        self.assertIsNone(decoded['source_rate_hz'])

    def test_visible_phase_transition_is_flagged(self):
        model = self.model()
        def change(address):
            if address == SOURCES[20][0]:
                model.memory[SOURCES[28][0]] = 9
                model.memory[SOURCES[32][0]] = 3
        model.read_hook = change
        model.run()
        record = fmt.decode_capture(model.dump(), expected_nonce=NONCE)['records'][0]
        self.assertEqual(record['phase_before'], 2)
        self.assertEqual(record['phase_after'], 9)
        self.assertIn('visible_scheduler_boundary', record['context_issues'])
        self.assertIn('unsupported_or_changed_scheduler_mode', record['context_issues'])

    def test_context_errors_are_kept_visible_not_silently_usable(self):
        for field, value, reason in (
            ('model', 0, 'unsupported_model'),
            ('phase_before', 3, 'unsupported_scheduler_phase'),
            ('mode_before', 2, 'unsupported_or_changed_scheduler_mode'),
            ('reference_area', 1, 'unsupported_area_or_route'),
            ('capture_busy_word', 0x100, 'capture_busy'),
            ('roi_count', 0, 'unsupported_focus_context'),
            ('hcg', 2, 'invalid_gain_or_exposure_context'),
        ):
            with self.subTest(field=field):
                data = bytearray(self.capture())
                struct.pack_into('<I', data, 64 + 4 * fmt.FIELDS.index(field), value)
                decoded = fmt.decode_capture(data, expected_nonce=NONCE)
                self.assertIn(reason, decoded['records'][0]['context_issues'])
                self.assertFalse(decoded['usable_for_af_control'])
                self.assertFalse(decoded['native_l_identity_verified'])

    def test_cross_record_context_change_is_reported(self):
        model = self.model(256)
        for i in range(256):
            model.memory[SOURCES[48][0]] = 1024 + i
            model.run()
        decoded = fmt.decode_capture(model.dump(), expected_nonce=NONCE)
        self.assertEqual(decoded['changed_context_fields'], ['relative_gain'])

    def test_batch_accepts_arbitrary_chunks_at_max_capacity(self):
        batch = fmt.pack_batch(self.capture(256), expected_nonce=NONCE)
        self.assertEqual(len(batch), fmt.MAX_BATCH_BYTES)
        for size in (1, 63, 64, 511, 1024, 4096, 32896):
            receiver = fmt.BatchReceiver(expected_nonce=NONCE)
            for start in range(0, len(batch), size):
                result = receiver.feed(batch[start:start + size])
            receiver.finish()
            self.assertEqual(result['count'], 256)

    def test_batch_rejects_each_corrupt_byte_and_latches_fault(self):
        batch = fmt.pack_batch(self.capture(), expected_nonce=NONCE)
        for index in range(len(batch)):
            corrupt = bytearray(batch)
            corrupt[index] ^= 1
            receiver = fmt.BatchReceiver(expected_nonce=NONCE)
            with self.assertRaises(fmt.CaptureError):
                receiver.feed(corrupt)
            self.assertTrue(receiver.faulted)
            with self.assertRaises(fmt.CaptureError):
                receiver.feed(batch)

    def test_truncation_extra_data_wrong_nonce_and_terminal_use(self):
        batch = fmt.pack_batch(self.capture(), expected_nonce=NONCE)
        for length in (0, 1, 63, 64, 128, len(batch) - 1):
            receiver = fmt.BatchReceiver(expected_nonce=NONCE)
            if length:
                self.assertIsNone(receiver.feed(batch[:length]))
            with self.assertRaises(fmt.CaptureError):
                receiver.finish()
        for blob, nonce in ((batch + b'X', NONCE), (batch, NONCE + 1)):
            with self.assertRaises(fmt.CaptureError):
                fmt.BatchReceiver(expected_nonce=nonce).feed(blob)
        receiver = fmt.BatchReceiver(expected_nonce=NONCE)
        receiver.feed(batch)
        with self.assertRaises(fmt.CaptureError):
            receiver.feed(batch)
        with self.assertRaises(fmt.CaptureError):
            receiver.finish()

    def test_memoryview_limits_are_measured_in_bytes(self):
        batch = fmt.pack_batch(self.capture(), expected_nonce=NONCE)
        words = array.array('I')
        words.frombytes(batch)
        result = fmt.BatchReceiver(expected_nonce=NONCE).feed(memoryview(words))
        self.assertEqual(result['count'], 1)
        oversized = memoryview(array.array('I', [0] * (fmt.MAX_BATCH_BYTES // 4 + 1)))
        receiver = fmt.BatchReceiver(expected_nonce=NONCE)
        with self.assertRaises(fmt.CaptureError):
            receiver.feed(oversized)
        self.assertEqual(len(receiver.buffer), 0)

    def test_invalid_initial_and_capture_identity(self):
        for cap, nonce in ((0, NONCE), (257, NONCE), (True, NONCE), (1, 0), (1, -1)):
            with self.assertRaises(fmt.CaptureError):
                fmt.initial_capture(cap, nonce)
        for offset in (0, 4, 8, 12, 16, 20, 24, 32, 36, 40, 44, 48,
                       64, 68, 72, 188):
            data = bytearray(self.capture())
            data[offset] ^= 1
            with self.assertRaises(fmt.CaptureError):
                fmt.decode_capture(data, expected_nonce=NONCE)
        # The full marker is set a few instructions after enabled is cleared, so
        # a complete capture with that marker lost is indistinguishable from a
        # read landing in that window. The committed prefix is still sound, so it
        # decodes as not full; only require_full refuses it.
        data = bytearray(self.capture())
        data[28] ^= 1
        self.assertFalse(fmt.decode_capture(data, expected_nonce=NONCE)['full'])
        with self.assertRaises(fmt.CaptureError):
            fmt.decode_capture(data, expected_nonce=NONCE, require_full=True)

    def test_branch_encoding_roundtrip_and_rejections(self):
        for target in (CODE, fmt.CALLSITE + 8 - (1 << 25),
                        fmt.CALLSITE + 8 + (1 << 25) - 4):
            word = build.branch_word(target)
            immediate = word & 0xffffff
            signed = immediate - (1 << 24) if immediate & (1 << 23) else immediate
            self.assertEqual(fmt.CALLSITE + 8 + signed * 4, target)
        for target in (CODE + 1, fmt.CALLSITE + 8 + (1 << 25)):
            with self.assertRaises(ValueError):
                build.branch_word(target)

    def test_builder_rejects_overlap_alignment_and_address_wrap(self):
        for overrides in ({'code_base': CODE + 1}, {'state_base': STATE + 4},
                          {'records_base': RECORDS + 64}, {'state_base': CODE},
                          {'state_base': RECORDS}, {'records_base': 0xffffff80},
                          {'code_base': fmt.CALLSITE}, {'code_base': fmt.PRODUCER},
                          {'code_base': fmt.PRODUCER + 4},
                          {'records_base': 0xC3298580}):
            args = dict(code_base=CODE, state_base=STATE, records_base=RECORDS,
                        capacity=256, nonce=NONCE)
            args.update(overrides)
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                build.assemble(**args)
        for address, _ in SOURCES.values():
            self.assertTrue(any(start <= address < end for start, end in build.PROTECTED_RANGES))

    def test_pool_code_requires_explicit_near_veneer(self):
        args = dict(code_base=0x48050000, state_base=STATE, records_base=RECORDS,
                    capacity=1, nonce=NONCE)
        with self.assertRaisesRegex(ValueError, 'range'):
            build.assemble(**args)
        code, _, manifest = build.assemble(**args, veneer_base=CODE)
        veneer = bytes.fromhex(manifest['veneer_hex'])
        self.assertEqual(struct.unpack('<2I', veneer), (0xe51ff004, 0x48050000))
        self.assertEqual(manifest['candidate_branch_word'], build.branch_word(CODE))
        self.assertEqual(manifest['veneer_bytes'], 8)
        dis = Cs(CS_ARCH_ARM, CS_MODE_ARM)
        dis.detail = True
        ins = list(dis.disasm(veneer[:4], CODE))[0]
        self.assertEqual((ins.mnemonic, ins.op_str), ('ldr', 'pc, [pc, #-4]'))
        self.assertFalse(ins.update_flags)
        self.assertEqual(ins.address + 8 + ins.operands[1].mem.disp, CODE + 4)
        self.assertEqual(code, self.builds[1][0])  # position-independent wrapper
        self.assertFalse(manifest['ownership_verified'])

    def test_veneer_alignment_reach_and_overlaps_rejected(self):
        args = dict(code_base=CODE, state_base=STATE, records_base=RECORDS,
                    capacity=1, nonce=NONCE)
        for address in (0, True, CODE + 1, CODE, CODE + 4, STATE, RECORDS,
                        0x48040000, fmt.PRODUCER, fmt.CALLSITE):
            with self.subTest(address=address), self.assertRaises(ValueError):
                build.assemble(**args, veneer_base=address)

    def test_malformed_data_fuzz_stays_bounded(self):
        rng = random.Random(1)
        for _ in range(100):
            data = rng.randbytes(rng.randint(1, 512))
            receiver = fmt.BatchReceiver(expected_nonce=NONCE)
            try:
                receiver.feed(data)
                receiver.finish()
            except fmt.CaptureError:
                pass
            self.assertTrue(receiver.faulted)
            self.assertLessEqual(len(receiver.buffer), fmt.MAX_BATCH_BYTES)


if __name__ == '__main__':
    unittest.main()
