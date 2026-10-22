"""Run the real EP83 sender bytes in Unicorn, with address-based ROM stubs.

The arm sequence is checked against the maintained worker's own (`arm_in_block`
in camera/worker.S) with EP 0x83's table slot and physical number. What this
cannot show: whether the stock PTP event sender contends for the same TRB,
whether the controller actually moves the bytes, DMA completion, or any timing.
`StartTransfer` and `Wait` are stubs here; on the camera they are firmware.
Missing Unicorn or a restricted JIT is an ERROR, not a skip.
"""
from pathlib import Path
import re
import struct
import sys
import tempfile
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
    UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
    UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11, UC_ARM_REG_R12,
    UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_CPSR)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / 'fpSup/fp_usb_shell'))
import armasm
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM


def source_code():
    """The source with its comments removed: what the assembler actually sees."""
    text = (HERE / 'ep83_send.S').read_text()
    return re.sub(r'/\*.*?\*/', '', text, flags=re.S)

CODE, PARAM = 0xC0800000, 0xC072E400
TRB_TABLE, TRB = 0xC31E3270, 0xC3200100
DALEPENA = 0x2100C720
STARTX, WAIT = 0xC01E6B80, 0xC01E4E80        # the stubs; the source calls |1
BUFFER, BUFFER_BYTES = 0x45000000, 0x10000
STACK, SP, RETURN = 0x43000000, 0x43008000, 0x44000000
REGS = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
        UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
        UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
        UC_ARM_REG_R12]
OK, BAD_OP, USED, NOT_ENABLED, BAD_BUFFER, NO_TRB, START_FAILED, WAIT_FAILED = range(8)


def assemble(source=None, param=PARAM):
    if source is None:
        return armasm.assemble(HERE / 'ep83_send.S', [f'EP83_P={param}'])
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / 'ep83_send.S'
        src.write_text(source)
        return armasm.assemble(src, [f'EP83_P={param}'])


class Sender:
    def __init__(self, code, *, dalepena=0xA7, trb=TRB, start=0, wait=0):
        self.code, self.calls, self.writes = code, [], []
        self.start_rc, self.wait_rc = start, wait
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        pages = set()
        for address, size in ((CODE, len(code)), (PARAM, 32), (TRB_TABLE, 4), (TRB, 16),
                              (DALEPENA, 4), (STACK, 0x10000), (RETURN, 4),
                              (STARTX, 4), (WAIT, 4), (BUFFER, 0x1000)):
            for page in range(address & ~0xFFF, (address + size + 0xFFF) & ~0xFFF, 4096):
                if page not in pages:
                    self.uc.mem_map(page, 4096)
                    pages.add(page)
        self.uc.mem_write(CODE, code)
        self.word(DALEPENA, dalepena)
        self.word(TRB_TABLE, trb)
        for offset in range(0, 16, 4):
            self.word(TRB + offset, 0xDEAD0000 + offset)
        self.uc.hook_add(UC_HOOK_CODE, self.on_code)
        self.uc.hook_add(UC_HOOK_MEM_WRITE, self.on_write)

    def word(self, address, value=None):
        if value is None:
            return struct.unpack('<I', self.uc.mem_read(address, 4))[0]
        self.uc.mem_write(address, struct.pack('<I', value))

    def put(self, offset, value):
        self.word(PARAM + offset, value)

    def get(self, offset):
        return self.word(PARAM + offset)

    def on_write(self, uc, access, address, size, value, _):
        allowed = ((PARAM, PARAM + 32), (TRB, TRB + 16), (SP - 64, SP))
        assert any(lo <= address and address + size <= hi for lo, hi in allowed), \
            f'write outside the parameter block, the TRB or the stack: {address:#x}'
        self.writes.append((address, value))

    def on_code(self, uc, address, size, _):
        if CODE <= address < CODE + len(self.code):
            return
        if address == RETURN:
            self.returned = True
            uc.emu_stop()
            return
        assert address in (STARTX, WAIT), f'unapproved execution {address:#x}'
        args = tuple(uc.reg_read(reg) for reg in REGS[:2])
        self.calls.append((address, args))
        result = self.start_rc if address == STARTX else self.wait_rc
        if address == WAIT and self.wait_rc == 0:
            self.word(TRB + 12, 0x0812)          # the controller cleared HWO
        for index in (0, 1, 2, 3, 12):
            uc.reg_write(REGS[index], 0xBAD00000 + index)
        uc.reg_write(UC_ARM_REG_R0, result)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR) & ~1)

    def run(self, *, op=1, buffer=BUFFER, length=4096, timeout=200, sp=SP,
            set_params=True):
        if set_params:
            self.put(0, op)
            self.put(8, buffer)
            self.put(0xC, length)
            self.put(0x10, timeout)
        self.calls, self.writes, self.returned = [], [], False
        initial = [0x33440000 + index * 0x1001 for index in range(13)]
        self.uc.reg_write(UC_ARM_REG_CPSR, 0x13)
        for reg, value in zip(REGS, initial):
            self.uc.reg_write(reg, value)
        self.uc.reg_write(UC_ARM_REG_SP, sp)
        self.uc.reg_write(UC_ARM_REG_LR, RETURN)
        self.uc.emu_start(CODE, RETURN + 4, count=500)
        assert self.returned, 'sender did not return within its instruction bound'
        assert self.uc.reg_read(UC_ARM_REG_SP) == sp, 'SP not restored'
        for index in range(4, 12):
            assert self.uc.reg_read(REGS[index]) == initial[index], f'r{index} clobbered'
        status = self.uc.reg_read(UC_ARM_REG_R0)
        assert status == self.get(4), 'return value and status word disagree'
        return status

    def trb(self):
        return [self.word(TRB + offset) for offset in range(0, 16, 4)]


def fresh(**kw):
    return Sender(assemble(), **kw)


class SendTests(unittest.TestCase):
    def test_one_send_arms_the_trb_the_way_the_worker_does(self):
        cam = fresh()
        self.assertEqual(cam.run(length=4096), OK)
        # bus address, high word, length, control -- exactly arm_in_block's four.
        self.assertEqual(cam.trb(), [BUFFER - 0x40000000, 0, 4096, 0x0812])
        self.assertEqual([address for address, _ in cam.calls], [STARTX, WAIT])
        self.assertEqual(cam.calls[0][1][0], 7)            # physical endpoint
        self.assertEqual(cam.calls[1][1], (3, 200))        # logical, timeout
        self.assertEqual((cam.get(0x14), cam.get(0x18)), (0, 0))
        self.assertEqual(cam.get(0x1C), 0x0812)            # the TRB read back

    def test_the_control_word_is_written_last_and_then_a_barrier(self):
        cam = fresh()
        cam.run()
        trb_writes = [address for address, _ in cam.writes if TRB <= address < TRB + 16]
        self.assertEqual(trb_writes, [TRB, TRB + 4, TRB + 8, TRB + 12])
        started = [index for index, (address, _) in enumerate(cam.writes)
                   if address == TRB + 12][0]
        self.assertTrue(all(index < started for index, (address, _) in enumerate(cam.writes)
                            if TRB <= address < TRB + 12))

    def test_a_second_use_is_refused_without_touching_the_endpoint(self):
        cam = fresh()
        self.assertEqual(cam.run(), OK)
        before = cam.trb()
        # Call it again with the block exactly as the first use left it: op was
        # cleared before the endpoint was touched, so this must refuse.
        self.assertEqual(cam.run(set_params=False), BAD_OP)
        self.assertEqual(cam.calls, [])
        self.assertEqual(cam.trb(), before)

    def test_an_endpoint_the_controller_does_not_have_is_refused(self):
        # DALEPENA 0xA7 has physical 7; 0x27 does not. EP 0x84 (physical 9) is
        # the case this guard exists for.
        cam = fresh(dalepena=0x27)
        self.assertEqual(cam.run(), NOT_ENABLED)
        self.assertEqual(cam.calls, [])
        self.assertFalse([w for w in cam.writes if TRB <= w[0] < TRB + 16])

    def test_only_a_dma_capable_buffer_is_accepted(self):
        for buffer, length in ((0xC0800000, 4096), (0x3FFFF000, 4096),
                               (0x80000000, 4096), (BUFFER + 1, 4096),
                               (0x7FFFF000, 0x2000), (BUFFER, 0), (BUFFER, 0x10001)):
            with self.subTest(buffer=hex(buffer), length=length):
                cam = fresh()
                self.assertEqual(cam.run(buffer=buffer, length=length), BAD_BUFFER)
                self.assertEqual(cam.calls, [])
                self.assertFalse([w for w in cam.writes if TRB <= w[0] < TRB + 16])

    def test_the_window_edges_are_accepted(self):
        for buffer, length in ((0x40000000, 4), (0x80000000 - 4096, 4096)):
            with self.subTest(buffer=hex(buffer)):
                cam = fresh()
                self.assertEqual(cam.run(buffer=buffer, length=length), OK)

    def test_an_empty_trb_slot_is_refused(self):
        cam = fresh(trb=0)
        self.assertEqual(cam.run(), NO_TRB)
        self.assertEqual(cam.calls, [])

    def test_a_failed_start_is_not_waited_on_or_retried(self):
        cam = fresh(start=-1)
        self.assertEqual(cam.run(), START_FAILED)
        self.assertEqual([address for address, _ in cam.calls], [STARTX])
        self.assertEqual(cam.get(0x14) & 0xffffffff, 0xffffffff)

    def test_a_failed_wait_keeps_the_trb_and_ends_nothing(self):
        cam = fresh(wait=-5)
        self.assertEqual(cam.run(), WAIT_FAILED)
        self.assertEqual([address for address, _ in cam.calls], [STARTX, WAIT])
        self.assertEqual(cam.trb()[3], 0x813)      # still armed: the DMA may own it
        self.assertEqual(cam.get(0x1C), 0x813)
        self.assertEqual(cam.get(0x18) & 0xffffffff, 0xfffffffb)

    def test_an_unknown_op_touches_nothing(self):
        for op in (0, 2, 0xffffffff):
            with self.subTest(op=op):
                cam = fresh()
                self.assertEqual(cam.run(op=op), BAD_OP)
                self.assertEqual(cam.calls, [])
                self.assertFalse([w for w in cam.writes if TRB <= w[0] < TRB + 16])

    def test_an_sp_four_off_still_returns_cleanly(self):
        cam = fresh()
        self.assertEqual(cam.run(sp=SP - 4), OK)


class SourceTests(unittest.TestCase):
    def test_it_starts_nothing_on_the_worker_s_endpoints(self):
        code = source_code()
        for address in ('0xC31E3268', '0xC31E326C'):     # EP01 OUT, EP82 IN
            self.assertNotIn(address, code)
        for physical in ('PHYS_EP83,   7', 'LOG_EP83,    3'):
            self.assertIn(physical, code)

    def test_it_never_ends_a_transfer(self):
        # EndTransfer from here would be a second owner acting on controller
        # state this routine cannot observe.
        code = source_code()
        for word in ('EndTransfer', 'FN_ENDX', 'C01E7780'):
            self.assertNotIn(word, code)

    def test_a_barrier_separates_the_armed_trb_from_the_start(self):
        # Unicorn does not model a barrier, so this is an instruction-order
        # check on the real bytes, not a behavioural one.
        dis = Cs(CS_ARCH_ARM, CS_MODE_ARM)
        instructions = list(dis.disasm(assemble(), CODE))
        control = max(index for index, i in enumerate(instructions)
                      if i.mnemonic == 'str' and i.op_str.endswith('#0xc]'))
        start = min(index for index, i in enumerate(instructions)
                    if i.mnemonic == 'blx')
        self.assertLess(control, start)
        self.assertIn('dsb', [i.mnemonic for i in instructions[control:start]])

    def test_the_bytes_are_position_dependent_on_their_parameter_block(self):
        self.assertNotEqual(assemble(), assemble(param=PARAM + 0x40))


class MutationTests(unittest.TestCase):
    """Each guard is shown to be load-bearing by removing it."""

    def run_suite(self, source):
        suite = unittest.TestLoader().loadTestsFromTestCase(SendTests)
        original = globals()['fresh']
        globals()['fresh'] = lambda **kw: Sender(assemble(source), **kw)
        try:
            with open('/dev/null', 'w') as quiet:
                return unittest.TextTestRunner(stream=quiet, verbosity=0).run(suite)
        finally:
            globals()['fresh'] = original

    def test_mutations_are_caught(self):
        source = (HERE / 'ep83_send.S').read_text()
        cases = {
            'endpoint check dropped': ('    tst r0, #(1 << PHYS_EP83)\n    beq not_enabled',
                                       '    tst r0, #(1 << PHYS_EP83)\n    nop'),
            'one-use latch dropped': ('    str r0, [r4]                  /* one use',
                                      '    nop                           /* one use'),
            'window upper bound dropped': ('    cmp r5, r0\n    bhi bad_buffer',
                                           '    cmp r5, r0\n    nop'),
            'zero length allowed': ('    cmp r6, #0\n    beq bad_buffer',
                                    '    cmp r6, #0\n    nop'),
            'null trb allowed': ('    cmp r7, #0\n    beq no_trb',
                                 '    cmp r7, #0\n    nop'),
            'start failure ignored': ('    cmp r0, #0\n    bne start_failed',
                                      '    cmp r0, #0\n    nop'),
        }
        for name, (old, new) in cases.items():
            with self.subTest(name):
                self.assertIn(old, source, name)
                result = self.run_suite(source.replace(old, new, 1))
                self.assertTrue(result.failures or result.errors,
                                f'mutation "{name}" changed nothing that is checked')


if __name__ == '__main__':
    unittest.main(verbosity=2)
