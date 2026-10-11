"""T0 host runner tests; fake memory and a fake EP83 socket. No camera, no USB.

The camera side is modelled: writing 1 to the parameter block's op word is what
makes the fake return the buffer's bytes, exactly as the real sender would after
its transfer completes. Passing here proves the host sequence and its refusals,
not that any byte ever crossed the wire.
"""
import contextlib
import io as textio
import json
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import af_hook_trial as trial
import ep83_t0 as t0
import user_alloc

PARAM, CODE, BUFFER = 0xC072E400, 0xC072E440, 0x45001000
HELPER, HELPER_PARAM = 0xC072E600, 0xC072EC00
RAW = 0x45000C80
POOL, WORKER = 0x46000000, 0x47000000
NONCE = 0x0BADF00D


class FakeIO(t0.T0IO):
    """Real T0IO read/word/put over an explicit memory and socket model."""

    def __init__(self):
        super().__init__()
        self.memory = {t0.ECHO: t0.ORIGINAL}
        self.operations, self.writes = [], []
        self.sends = 0
        self.corrupt = self.short = self.no_terminal = False
        self.status = 0
        self.allocations = 0
        self.helper_at = None
        self.mapping = 1
        self.raw = RAW
        self.base_override = None
        self.memory.update({trial.WORKER: POOL, trial.WORKER + 4: 0x100000,
                            trial.WORKER + 8: WORKER})

    def store(self, address, data):
        for offset in range(0, len(data), 4):
            self.memory[address + offset] = struct.unpack_from('<I', data, offset)[0]

    def blob(self, address, length):
        return struct.pack('<%dI' % (length // 4),
                           *(self.memory.get(at, 0) for at in range(address, address + length, 4)))

    def shell(self, command, timeout_ms=1000):
        if self.transport_faulted:
            raise AssertionError('new exchange after latched fault')
        self.operations.append(command)
        if command.startswith('mem get '):
            address, _, size = command.split()[2].partition(',,')
            address, size = int(address, 0), int(size, 0)
            return '\n'.join(f'get : A:0x{at:08X}, D:0x{self.memory.get(at, 0):08X}'
                             for at in range(address, address + size, 4))
        if command.startswith('mem set '):
            _, _, address, value = command.split()
            address, value = int(address, 0), int(value, 0)
            self.memory[address] = value
            self.writes.append((address, value))
            return ''
        if command != 'echo':
            raise AssertionError('unexpected shell command: ' + command)
        target = self.memory[t0.ECHO]
        if target in (t0.DCACHE, t0.ICACHE):
            return ''
        if target == self.helper_at:
            # What af_probe_helper.S leaves behind for one allocation attempt.
            self.allocations += 1
            base = self.base_override
            if base is None:
                base = (self.raw + 127) & ~127
            self.store(HELPER_PARAM, struct.pack('<16I', 0, 0, 1, self.raw, base,
                                                 user_alloc.ALLOC_BYTES, 0, 0, 0, 0,
                                                 HELPER_PARAM + 0x30, self.mapping,
                                                 self.raw, 0, self.raw,
                                                 user_alloc.ALLOC_BYTES))
            return ''
        raise AssertionError('echo outside cache publication uses the EP83 path')

    def ep83(self, length, line='echo', *, timeout=4.0):
        if self.transport_faulted:
            raise AssertionError('EP83 after fault')
        self.operations.append(('ep83', length))
        if self.memory[t0.ECHO] != CODE:
            raise AssertionError('EP83 dispatched without the sender in echo')
        if self.memory.get(PARAM, 0) != 1:
            raise AssertionError('EP83 dispatched before the op word was set')
        self.sends += 1
        self.memory[PARAM] = 0                       # the sender clears it
        self.memory[PARAM + 4] = self.status
        if self.no_terminal:
            self._latch_transport_fault()
            raise TimeoutError('EP83 outcome uncertain')
        body = self.blob(BUFFER, length)
        if self.corrupt:
            body = body[:8] + bytes([body[8] ^ 1]) + body[9:]
        if self.short:
            raise t0.BridgeError('EP83 header/body mismatch')
        return body, 42, 0.01


def allocator(io, emit):
    io.regions += [(PARAM, PARAM + 32), (CODE, CODE + t0.SENDER_MAX),
                   (BUFFER, BUFFER + t0.MAX_BYTES)]
    io.special.setdefault(t0.ECHO, set()).add(CODE)
    return PARAM, CODE, BUFFER


class BootAllocatorTests(unittest.TestCase):
    """The wiring of the shared claim/allocate path; the cave register is not touched."""

    def setUp(self):
        self.io, self.events = FakeIO(), []
        self.io.helper_at = HELPER
        self.claims = []
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)

        def claim(io, emit, claims, retained=None):
            self.claims.append(claims)
            addresses = [PARAM, CODE, HELPER, HELPER_PARAM]
            for (name, size), at in zip(claims, addresses):
                io.regions.append((at, at + size))
            return addresses
        self.stack.enter_context(mock.patch.object(user_alloc, 'claim', claim))
        self.stack.enter_context(mock.patch.object(
            trial, 'offline_sources',
            return_value=(b'', trial.build._assembler(), bytes(16))))

    def test_it_claims_four_blocks_and_returns_the_aligned_base(self):
        param, code, buffer = t0.boot_allocator(NONCE)(self.io, self.events.append)
        names = [name for name, _ in self.claims[0]]
        self.assertEqual(names, [f'ep83t0.{NONCE:08x}.param',
                                 f'ep83t0.{NONCE:08x}.sender',
                                 f'ep83t0.{NONCE:08x}.helper',
                                 f'ep83t0.{NONCE:08x}.helper_param'])
        self.assertEqual([size for _, size in self.claims[0]],
                         [t0.PARAM_BYTES, t0.sender_bytes(), 1536, 128])
        self.assertEqual((param, code), (PARAM, CODE))
        self.assertEqual(buffer, (RAW + 127) & ~127)
        self.assertEqual(self.io.allocations, 1)
        self.assertEqual(self.io.memory[t0.ECHO], t0.ORIGINAL)

    def test_the_caches_are_published_before_the_helper_runs(self):
        t0.boot_allocator(NONCE)(self.io, self.events.append)
        echoes = [value for address, value in self.io.writes if address == t0.ECHO]
        self.assertEqual(echoes[:2], [t0.DCACHE, t0.ICACHE])
        self.assertEqual(echoes.index(HELPER), 3)      # after both, and the restore
        self.assertEqual(echoes[-1], t0.ORIGINAL)

    def test_a_refused_mapping_stops_without_returning_a_buffer(self):
        self.io.mapping = 0
        with self.assertRaises(t0.BridgeError) as caught:
            t0.boot_allocator(NONCE)(self.io, self.events.append)
        self.assertIn('mapping refused', str(caught.exception))
        self.assertEqual(self.io.allocations, 1)       # and not a second attempt

    def test_an_allocation_inside_the_worker_pool_is_refused(self):
        self.io.memory[trial.WORKER] = RAW - 0x1000    # the pool overlaps it
        with self.assertRaises(t0.BridgeError) as caught:
            t0.boot_allocator(NONCE)(self.io, self.events.append)
        self.assertIn('existing worker region', str(caught.exception))

    def test_an_allocation_outside_the_dma_window_is_refused(self):
        for raw in (0xC0800000, 0x3FFFFF00, 0x80000000 - user_alloc.ALLOC_BYTES + 4):
            with self.subTest(raw=hex(raw)):
                self.io = FakeIO()
                self.io.helper_at, self.io.raw = HELPER, raw
                with self.assertRaises(t0.BridgeError) as caught:
                    t0.boot_allocator(NONCE)(self.io, self.events.append)
                self.assertIn('allocation result invalid', str(caught.exception))

    def test_a_base_that_is_not_the_aligned_raw_is_refused(self):
        self.io.base_override = ((RAW + 127) & ~127) + 4
        with self.assertRaises(t0.BridgeError) as caught:
            t0.boot_allocator(NONCE)(self.io, self.events.append)
        self.assertIn('allocation result invalid', str(caught.exception))

    def test_the_borrow_refuses_an_unknown_echo_owner(self):
        self.io.memory[t0.ECHO] = 0xC0123450
        with self.assertRaises(t0.BridgeError):
            t0.Borrow(self.io).echo(t0.DCACHE)
        self.assertEqual(self.io.memory[t0.ECHO], 0xC0123450)


class CaveGuardTests(unittest.TestCase):
    """The injected transport lets the allocator move only its own bump pointer."""

    def run_claim(self, write_to, value):
        io_model = FakeIO()
        stub = types.ModuleType('cave')
        stub.CAVE_BUMP, stub.CAVE_ARENA, stub.CAVE_ARENA_END = 0xC072E060, 0xC072E064, 0xC072EFB4
        stub._check_agrees = lambda: None
        stub._sh = None
        stub.claims = lambda: {}

        def claim(name, size):
            stub._sh('mem', 'set', hex(write_to), hex(value))
            return 0xC072E100
        stub.claim = claim
        with mock.patch.dict(sys.modules, {'cave': stub}):
            return user_alloc.claim(io_model, lambda row: None, [('x', 4)])

    def test_a_write_to_the_bump_pointer_inside_the_arena_is_allowed(self):
        self.assertEqual(self.run_claim(0xC072E060, 0xC072E100), [0xC072E100])

    def test_any_other_destination_or_value_is_refused(self):
        for address, value in ((0xC022C858, 0xC072E100), (0xC072E064, 0xC072E100),
                               (0xC072E060, 0xC0000000), (0xC072E060, 0xC072F000)):
            with self.subTest(address=hex(address), value=hex(value)):
                with self.assertRaises(ValueError):
                    self.run_claim(address, value)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name)
        self.io, self.events = FakeIO(), []
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch('socket.socket',
                                            side_effect=AssertionError('real socket forbidden')))

    def go(self, **kw):
        args = dict(length=256, nonce=NONCE, allocate=allocator)
        args.update(kw)
        return t0.run(self.io, self.events.append, self.output, **args)

    def test_a_delivered_batch_matches_what_the_host_wrote(self):
        result = self.go()
        self.assertEqual(result['status'], 'delivered')
        self.assertEqual(result['received_sha256'], result['payload_sha256'])
        self.assertEqual((self.io.sends, result['sequence']), (1, 42))
        self.assertFalse(result['af_data'] or result['continuous_session'])
        self.assertFalse(result['reclamation_proven'])
        self.assertTrue(result['echo_restored'])
        self.assertEqual(self.io.memory[t0.ECHO], t0.ORIGINAL)
        self.assertEqual((self.output / 'received.bin').read_bytes(),
                         t0.pattern(256, NONCE))

    def test_the_payload_is_written_before_the_op_word(self):
        self.go()
        buffer_writes = [index for index, (address, _) in enumerate(self.io.writes)
                         if BUFFER <= address < BUFFER + 256]
        op_write = [index for index, (address, value) in enumerate(self.io.writes)
                    if address == PARAM and value == 1][0]
        self.assertTrue(buffer_writes and max(buffer_writes) < op_write)

    def test_the_caches_are_published_before_the_transfer(self):
        self.go()
        echoes = [index for index, command in enumerate(self.io.operations)
                  if command == 'echo']
        send = [index for index, command in enumerate(self.io.operations)
                if isinstance(command, tuple)][0]
        self.assertEqual(len(echoes), 2)          # D-cache then I-cache
        self.assertTrue(max(echoes) < send)

    def test_a_nonzero_sender_status_fails_and_keeps_the_bytes(self):
        self.io.status = 7                        # wait failed
        result = self.go()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('sender status 7', result['error'])
        self.assertTrue((self.output / 'received.bin').exists())
        self.assertTrue(result['echo_restored'])

    def test_a_corrupted_payload_is_reported_with_its_offset(self):
        self.io.corrupt = True
        result = self.go()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('payload mismatch at byte 8', result['error'])

    def test_a_borrowed_echo_stops_before_anything_is_claimed(self):
        self.io.memory[t0.ECHO] = 0xC0123450
        result = self.go()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('echo is borrowed', result['error'])
        self.assertEqual((self.io.writes, self.io.sends), ([], 0))
        self.assertEqual(result['resources_retained'], [])

    def test_an_uncertain_transfer_retains_everything_and_does_not_retry(self):
        self.io.no_terminal = True
        result = self.go()
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(result['transport_faulted'])
        self.assertEqual(self.io.sends, 1)
        self.assertEqual(len(result['resources_retained']), 3)
        self.assertFalse(result['echo_restored'])   # no new exchange after a fault
        self.assertFalse(result['reclamation_proven'])

    def test_the_pattern_is_nonce_specific_and_bounded(self):
        self.assertNotEqual(t0.pattern(256, NONCE), t0.pattern(256, NONCE + 1))
        self.assertEqual(len(t0.pattern(65536, NONCE)), 65536)
        for length in (0, 3, 5, 65540):
            with self.subTest(length=length):
                with self.assertRaises(ValueError):
                    t0.pattern(length, NONCE)

    def test_the_sender_image_is_bounded_and_placed_at_its_block(self):
        image = t0.sender_image(PARAM)
        self.assertLessEqual(len(image), t0.SENDER_MAX)
        self.assertNotEqual(image, t0.sender_image(PARAM + 0x40))

    def test_inspect_makes_no_transport_and_claims_no_delivery(self):
        out = self.output / 'inspect'
        with (mock.patch.object(t0, 'T0IO', side_effect=AssertionError('live constructor forbidden')),
              contextlib.redirect_stdout(textio.StringIO())):
            self.assertEqual(t0.main(['--inspect', '--output', str(out)]), 0)
        report = json.loads((out / 'inspect.json').read_text())
        self.assertTrue(report['offline_only'])
        self.assertFalse(report['delivery_verified'] or report['af_data'])
        self.assertIn(t0.DAEMON_REQUIREMENT, report['requires'])
        self.assertEqual(report['endpoint']['physical'], 7)
        self.assertEqual(self.io.operations, [])

    def test_run_live_refuses_from_the_command_line(self):
        out = self.output / 'live'
        with self.assertRaises(SystemExit) as caught:
            t0.main(['--run-live', '--output', str(out)])
        self.assertIn('no camera operation', str(caught.exception))


if __name__ == '__main__':
    unittest.main(verbosity=2)
