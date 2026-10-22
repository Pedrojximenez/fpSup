"""Installer state-machine tests; fake memory only, no camera or ARM execution.

The real guards, upload/restore flow, capture decoder and transport boundaries
run here. State-machine cases explicitly assume a future shutdown-restore
contract in the model; the production guard is tested separately without that
patch. Allocation, native production and local assembly are explicit fakes.
Passing does not establish cache, scheduler, USB DMA, shutdown recovery or
optical behavior, and does not make the installer ready for a camera.
"""
import contextlib
import io as textio
import json
from pathlib import Path
import runpy
import struct
import sys
import tempfile
import types
import unittest
from unittest import mock

if __package__:
    from . import af_hook_trial as trial
else:
    import af_hook_trial as trial


HELPER, PARAM, VENEER = 0xC072E080, 0xC072E680, 0xC072E700
JOURNAL = 0xC0810000   # the loader's journal block, as the allocator placed it
POOL, WORKER, RAW = 0x46000000, 0x47000000, 0x45000004
BASE = (RAW + 127) & ~127
NONCE = 0x12345678
WORKER_BODY = struct.pack('<4I', 0xE1A00000, 0xE1A01001, 0xE1A02002, 0xE12FFF1E)


class FakeAssembler:
    def assemble(self, *args, **kwargs):
        return struct.pack('<I', 0xE12FFF1E)


def source_image():
    end = max(address + size for address, size in trial.ROM_GUARDS)
    rom = bytearray(end - 0xC0000000)
    for address, size in trial.ROM_GUARDS:
        for offset in range(0, size, 4):
            struct.pack_into('<I', rom, address - 0xC0000000 + offset,
                             0xE1A00000 + offset // 4)
    struct.pack_into('<I', rom, trial.fmt.CALLSITE - 0xC0000000, trial.fmt.ORIGINAL_WORD)
    return bytes(rom)


def completed_capture(capacity, nonce, level=None):
    level = trial.fmt.LEVEL_RECORD if level is None else level
    data = bytearray(trial.fmt.initial_capture(capacity, nonce, level))
    struct.pack_into('<3I', data, 20, 0, capacity, 1)
    struct.pack_into('<I', data, 52, capacity)              # hits
    for index in range(capacity):
        row = dict.fromkeys(trial.fmt.FIELDS, 0)
        row.update(commit=index + 1, nonce=nonce, sequence=index + 1,
                   model=trial.fmt.MODEL, h=100 + index, l=90 + index,
                   cached_lens_position_raw=300, af_manager_position_raw=300,
                   mode_before=1, mode_after=1, route=14, relative_gain=1,
                   analog_code=1, analog_ratio_raw=1, af_rgb_gain=1,
                   af_sensitivity=100, af_shutter=50, af_f_number=28, roi_count=1,
                   commit_complement=(index + 1) ^ 0xFFFFFFFF)
        struct.pack_into('<32I', data, 64 + index * 128,
                         *(row[key] for key in trial.fmt.FIELDS))
    return bytes(data)


class MemoryIO(trial.TrialIO):
    """Real TrialIO read/word/put over an explicit shell/memory model."""
    def __init__(self, rom):
        super().__init__()
        self.memory, self.operations, self.writes = {}, [], []
        self.allocations = self.exports = self.bulk_calls = self.claim_calls = 0
        self.count_hits = 5
        self.fill = True
        self.wrong_nonce = self.flip_mode = False
        self.place_journal()
        self.allocation_status, self.mapping_pass = 0, 1
        self.fault_at = None
        for address, size in trial.ROM_GUARDS:
            self.store(address, rom[address - 0xC0000000:address - 0xC0000000 + size])
        self.store(WORKER, WORKER_BODY)
        self.memory.update({trial.ECHO: trial.ORIGINAL, trial.BOOT_STAMP: 12345,
                            trial.WORKER: POOL, trial.WORKER + 4: 0x100000,
                            trial.WORKER + 8: WORKER,
                            0xC31C01B0: 1, 0xC31F86E0: 1})

    def store(self, address, data):
        for offset in range(0, len(data), 4):
            self.memory[address + offset] = struct.unpack_from('<I', data, offset)[0]

    def blob(self, address, length):
        return struct.pack('<%dI' % (length // 4),
                           *(self.memory.get(at, 0) for at in range(address, address + length, 4)))

    def place_journal(self, sites=None, *, lists=('ordinary', 'forced'), code=0x40):
        """The loader's journal block, as stage2 leaves it (asm/stage2.S)."""
        sites = {trial.fmt.CALLSITE: trial.fmt.ORIGINAL_WORD} if sites is None else sites
        self.memory[JOURNAL] = JOURNAL - 8
        self.memory[JOURNAL + 4] = JOURNAL + 12
        self.memory[JOURNAL + 8] = at = JOURNAL + 12 + code
        for address, word in sites.items():
            self.memory[at] = address
            self.memory[at + 4] = 4
            self.memory[at + 8] = word
            at += 12
        self.memory[at] = 0
        for name in lists:
            base = (trial.restore.ORDINARY_LIST if name == 'ordinary'
                    else trial.restore.FORCED_LIST)
            slot = next(index for index in range(10)
                        if not self.memory.get(base + index * 4, 0))
            self.memory[base + slot * 4] = JOURNAL

    def fault(self, label):
        if self.fault_at == label:
            self._latch_transport_fault()
            raise TimeoutError(label + ' outcome uncertain')

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
            if address == trial.fmt.CALLSITE and value != trial.fmt.ORIGINAL_WORD:
                if self.fill:
                    self.publish()
                self.fault('arm')
            return ''
        if command != 'echo':
            raise AssertionError('unexpected shell command: ' + command)
        target = self.memory[trial.ECHO]
        if target in (trial.DCACHE, trial.ICACHE):
            return ''
        if target != HELPER or self.memory.get(PARAM, 0) != 0:
            raise AssertionError('unexpected helper invocation')
        self.allocations += 1
        self.store(PARAM, struct.pack('<16I', 0, self.allocation_status, 1, RAW, BASE, trial.ALLOC_BYTES,
                                     0, 0, 0, 0, PARAM + 0x30, self.mapping_pass,
                                     RAW, 0, RAW, trial.ALLOC_BYTES))
        if self.flip_mode:
            self.memory[0xC31C01B0] = self.memory[0xC31F86E0] = 0
        self.fault('allocate')
        return ''

    def publish(self):
        """What the producer would leave behind for the level the host wrote."""
        state = BASE + trial.STATE_OFF
        capacity = self.memory[state + 12]
        nonce = self.memory[state + 16]
        level = self.memory[state + 48]
        if level == trial.fmt.LEVEL_RECORD:
            self.store(state, completed_capture(capacity, nonce, level))
        else:
            self.memory[state + 52] = self.count_hits        # counted, no record

    def bulk(self, length):
        if self.transport_faulted:
            raise AssertionError('bulk after fault')
        self.operations.append(('bulk', length))
        self.bulk_calls += 1
        if self.memory[trial.ECHO] != HELPER or self.memory[PARAM] != 1:
            raise AssertionError('bulk outside export helper')
        self.exports += 1
        self.fault('bulk')
        self.memory[PARAM + 4] = 0
        self.memory[PARAM + 0x20] = BASE + trial.STATE_OFF
        self.memory[PARAM + 0x24] = length
        if self.wrong_nonce:
            return completed_capture((length - 64) // 128, NONCE + 1), 0.01
        return self.blob(BASE + trial.STATE_OFF, length), 0.01


def fake_claim(probe, nonce):
    probe.io.claim_calls += 1
    probe.helper, probe.param, probe.veneer = HELPER, PARAM, VENEER
    for name, address, size in (('helper', HELPER, 1536), ('param', PARAM, 128),
                                ('veneer', VENEER, 8)):
        probe.io.regions.append((address, address + size))
        probe.retained.append(dict(name=name, address=address, bytes=size))
    probe.io.special[trial.ECHO].add(HELPER)


class InstallerFixture:
    """Shared fixture: fake payload/allocator, real power-off object."""
    @classmethod
    def setUpClass(cls):
        cls.rom = source_image()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name)
        self.io, self.events = MemoryIO(self.rom), []
        self.baseline = mock.Mock(return_value=dict(cine_baseline_verified=True, settings={'mode': 1}))
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch('socket.socket', side_effect=AssertionError('real socket forbidden')))
        for target, attribute, kwargs in (
            (trial, 'offline_sources', dict(return_value=(self.rom, FakeAssembler(), WORKER_BODY))),
            (trial.build, '_assembler', dict(return_value=FakeAssembler())),
            (trial.Probe, 'claim', dict(new=fake_claim)),
        ):
            self.stack.enter_context(mock.patch.object(target, attribute, **kwargs))

    def run_trial(self, emit=None, **kwargs):
        # The state-machine cases exercise the record level; the count level has
        # its own tests.
        args = dict(capacity=3, nonce=NONCE, baseline=self.baseline,
                    level=trial.fmt.LEVEL_RECORD, sleep=lambda _: None,
                    clock=lambda: 1.0)
        args.update(kwargs)
        return trial.run(self.io, emit or self.events.append, self.output, **args)

    def assert_retained(self, result):
        self.assertFalse(result['cleanup']['reclamation_proven'])
        retained = result['cleanup']['resources_retained']
        self.assertIn(RAW, [entry['address'] for entry in retained])
        self.assertEqual(len(retained), 4)   # helper, param, veneer, allocation
        self.assertTrue(all(isinstance(command, tuple) or command == 'echo' or
                            command.startswith(('mem get ', 'mem set '))
                            for command in self.io.operations))

class InstallerTests(InstallerFixture, unittest.TestCase):
    def test_success_uses_one_allocation_one_bulk_and_retains_all_memory(self):
        result = self.run_trial()
        self.assertEqual(result['status'], 'captured')
        self.assertEqual((self.io.allocations, self.io.exports, self.io.bulk_calls), (1, 1, 1))
        self.assertEqual(result['count'], 3)
        self.assertTrue(result['cleanup']['complete'])
        self.assertEqual(self.io.memory[trial.ECHO], trial.ORIGINAL)
        self.assertEqual(self.io.memory[trial.fmt.CALLSITE], trial.fmt.ORIGINAL_WORD)
        self.assertFalse(result['decoded']['optical_alignment_verified'])
        self.assertFalse(result['decoded']['detach_verified'])
        self.assert_retained(result)
        self.assertEqual((self.output / 'capture.afh').read_bytes(), completed_capture(3, NONCE))

    def test_all_rom_guards_reject_before_claim_or_ram_write(self):
        for address, _ in trial.ROM_GUARDS:
            with self.subTest(address=hex(address)):
                self.io = MemoryIO(self.rom)
                self.io.memory[address] ^= 1
                result = self.run_trial()
                self.assertEqual(result['status'], 'failed')
                self.assertIn('ROM guard mismatch', result['error'])
                self.assertEqual((self.io.claim_calls, self.io.writes), (0, []))

    def test_wrong_worker_rejected_before_claim_or_write(self):
        self.io.memory[WORKER] ^= 1
        result = self.run_trial()
        self.assertIn('running worker body differs', result['error'])
        self.assertEqual((self.io.claim_calls, self.io.writes), (0, []))

    def test_refused_mapping_retains_receipt_without_accessing_allocation(self):
        self.io.allocation_status, self.io.mapping_pass = 8, 0
        result = self.run_trial()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['allocation_receipt'][3], RAW)
        retained = result['cleanup']['resources_retained'][-1]
        self.assertEqual(retained['address'], RAW)
        self.assertFalse(retained['validated'])
        self.assertNotIn((RAW, RAW + trial.ALLOC_BYTES), self.io.regions)
        self.assertFalse(any(RAW <= address < RAW + trial.ALLOC_BYTES
                             for address, _ in self.io.writes))
        self.assertEqual((self.io.allocations, self.io.bulk_calls), (1, 0))
        self.assertTrue(result['cleanup']['complete'])

    def test_unknown_echo_owner_never_overwritten(self):
        self.io.memory[trial.ECHO] = 0xC0123450
        result = self.run_trial()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(self.io.writes, [])
        self.assertEqual(self.io.memory[trial.ECHO], 0xC0123450)

    def test_cine_mode_change_during_upload_refuses_arm(self):
        self.io.flip_mode = True
        result = self.run_trial()
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(any(address == trial.fmt.CALLSITE for address, _ in self.io.writes))
        self.assertEqual(self.io.bulk_calls, 0)
        self.assert_retained(result)

    def test_a_guard_changing_in_the_window_is_caught_before_the_export(self):
        # Guards are no longer polled: they are re-read once the window closes
        # and the site is restored, and the export never happens if one moved.
        for address, value in ((0xC30338D0, 1), (0xC31C01B0, 0), (0xC31F86E0, 0)):
            with self.subTest(address=hex(address)):
                self.io = MemoryIO(self.rom)
                windows = []

                def emit(row):
                    if row.get('event') == 'observation_window_open':
                        windows.append(row['seconds'])
                        self.io.memory[address] = value
                result = self.run_trial(emit=emit)
                self.assertEqual(len(windows), 1)
                self.assertEqual(result['status'], 'failed')
                self.assertIn('during the standby trial', result['error'])
                self.assertEqual((self.io.bulk_calls, self.io.exports), (0, 0))
                self.assertTrue(result['cleanup']['complete'])
                self.assertFalse((self.output / 'capture.afh').exists())
                self.assert_retained(result)

    def test_the_data_path_does_not_poll_the_camera_while_the_hook_runs(self):
        marks = []

        def emit(row):
            if row.get('event') in ('observation_window_open', 'observation_window_closed'):
                marks.append((row['event'], len(self.io.operations)))
        result = self.run_trial(emit=emit)
        self.assertEqual(result['status'], 'captured')
        self.assertFalse(result['data_path_polled'])
        self.assertEqual([name for name, _ in marks],
                         ['observation_window_open', 'observation_window_closed'])
        # Not one exchange between arming and restoring the site.
        self.assertEqual(marks[0][1], marks[1][1])
        self.assertEqual(self.io.bulk_calls, 1)

    def test_count_level_reports_producer_returns_and_commits_no_record(self):
        result = self.run_trial(level=trial.fmt.LEVEL_COUNT)
        self.assertEqual(result['status'], 'captured')
        self.assertEqual((result['hits'], result['count']), (5, 0))
        self.assertEqual(result['level'], trial.fmt.LEVEL_COUNT)
        self.assertTrue(result['serialization_verified'])
        self.assertEqual(self.io.bulk_calls, 1)
        self.assertTrue((self.output / 'capture.afh').exists())

    def test_a_silent_producer_fails_at_the_count_level(self):
        self.io.fill = False
        result = self.run_trial(level=trial.fmt.LEVEL_COUNT)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('did not run', result['error'])
        self.assertEqual(self.io.bulk_calls, 1)     # the bytes are still kept
        self.assertTrue(result['cleanup']['complete'])

    def test_re_entry_keeps_the_bytes_and_voids_the_sequence(self):
        state = BASE + trial.STATE_OFF

        def emit(row):
            if row.get('event') == 'observation_window_closed':
                self.io.memory[state + 60] = 2      # the producer was re-entered
        result = self.run_trial(emit=emit)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('re-entered', result['error'])
        self.assertEqual(result['overlaps'], 2)
        self.assertFalse(result['serialization_verified'])
        self.assertTrue((self.output / 'capture.afh').exists())
        self.assertTrue(result['cleanup']['complete'])

    def test_a_body_still_marked_after_restore_is_not_a_success(self):
        state = BASE + trial.STATE_OFF

        def emit(row):
            if row.get('event') == 'observation_window_closed':
                self.io.memory[state + 56] = 1
        result = self.run_trial(emit=emit)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('no quiescence claim', result['error'])

    def test_foreign_callsite_appearing_at_arm_intent_is_not_overwritten(self):
        def emit(row):
            self.events.append(row)
            if row.get('event') == 'hook_arm_intent':
                self.io.memory[trial.fmt.CALLSITE] = 0xEA000123
        result = trial.run(self.io, emit, self.output, capacity=3, nonce=NONCE,
                           baseline=self.baseline, clock=lambda: 1.0, sleep=lambda _: None)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(self.io.memory[trial.fmt.CALLSITE], 0xEA000123)
        self.assertFalse(any(address == trial.fmt.CALLSITE for address, _ in self.io.writes))
        self.assertFalse(result['cleanup']['complete'])

    def test_wrong_nonce_keeps_raw_evidence_but_never_succeeds(self):
        self.io.wrong_nonce = True
        result = self.run_trial()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('nonce mismatch', result['error'])
        self.assertTrue((self.output / 'capture.afh').exists())
        self.assertTrue(result['cleanup']['complete'])
        self.assertEqual(self.io.bulk_calls, 1)
        self.assert_retained(result)

    def test_uncertain_allocation_is_not_retried_or_cleaned_up(self):
        self.io.fault_at = 'allocate'
        result = self.run_trial()
        self.assertEqual((result['status'], self.io.allocations, self.io.bulk_calls), ('failed', 1, 0))
        self.assertFalse(result['cleanup']['complete'])
        self.assertEqual(self.baseline.call_count, 1)
        self.assertEqual(self.io.operations[-1], 'echo')
        self.assertEqual(self.io.memory[trial.ECHO], HELPER)
        self.assertEqual(len(result['cleanup']['resources_retained']), 3)

    def test_arm_and_bulk_faults_do_not_attempt_cleanup_exchanges(self):
        for fault in ('arm', 'bulk'):
            with self.subTest(fault=fault):
                self.io = MemoryIO(self.rom)
                self.io.fault_at = fault
                self.baseline.reset_mock()
                result = self.run_trial()
                self.assertEqual(result['status'], 'failed')
                self.assertTrue(result['transport_faulted'])
                self.assertFalse(result['cleanup']['complete'])
                self.assertEqual(self.baseline.call_count, 1)
                self.assertEqual(self.io.allocations, 1)
                self.assert_retained(result)

    def test_an_empty_record_window_exports_the_bytes_and_still_fails(self):
        # There is no fill deadline any more: a short window is a valid partial,
        # and at the record level an empty one is simply not a result.
        self.io.fill = False
        result = self.run_trial(wait_seconds=0.1)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('no record was committed', result['error'])
        self.assertEqual(self.io.bulk_calls, 1)
        self.assertTrue((self.output / 'capture.afh').exists())
        self.assertTrue(result['cleanup']['complete'])
        self.assertEqual(self.io.memory[BASE + trial.STATE_OFF + 20], 1)
        self.assert_retained(result)

    def test_postcheck_settings_change_downgrades_completed_capture(self):
        self.baseline.side_effect = [dict(cine_baseline_verified=True, settings={'mode': 1}),
                                     dict(cine_baseline_verified=True, settings={'mode': 2})]
        result = self.run_trial()
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(result['settings_equal'])
        self.assertEqual(result['count'], 3)
        self.assertTrue(result['cleanup']['complete'])

    def test_import_and_inspect_do_not_construct_transport_or_claim_camera(self):
        with (mock.patch('subprocess.run', side_effect=AssertionError('subprocess forbidden')),
              mock.patch('subprocess.Popen', side_effect=AssertionError('process forbidden')),
              mock.patch.object(sys, 'path', [str(Path(trial.__file__).parent), *sys.path])):
            namespace = runpy.run_path(str(Path(trial.__file__)), run_name='offline_import_test')
        self.assertIn('TrialIO', namespace)
        inspect_output = self.output / 'inspect'
        with (mock.patch.object(trial, 'TrialIO', side_effect=AssertionError('live constructor forbidden')),
              mock.patch.object(trial.Probe, 'claim', side_effect=AssertionError('claim forbidden')),
              contextlib.redirect_stdout(textio.StringIO())):
            self.assertEqual(trial.main(['--inspect', '--output', str(inspect_output)]), 0)
        report = json.loads((inspect_output / 'inspect.json').read_text())
        self.assertTrue(report['offline_only'])
        self.assertTrue(report['live_ready'])
        self.assertFalse(report['shutdown_restore_verified'])
        self.assertEqual(report['cave_claim_bytes'], 1536 + 128 + 8)
        self.assertIn('shared loader journal', report['shutdown_restore_mechanism'])
        self.assertEqual(self.io.operations, [])


class ShutdownRestoreGateTests(InstallerFixture, unittest.TestCase):
    """The site is armed only while the shared loader journal holds its stock word."""

    def clear_lists(self):
        for base in (trial.restore.ORDINARY_LIST, trial.restore.FORCED_LIST):
            for index in range(10):
                self.io.memory[base + index * 4] = 0

    def assert_never_armed(self, result):
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(result['shutdown_restore_verified'])
        self.assertEqual(self.io.memory[trial.fmt.CALLSITE], trial.fmt.ORIGINAL_WORD)
        self.assertFalse(any(address == trial.fmt.CALLSITE
                             for address, _ in self.io.writes))
        self.assertEqual((self.io.bulk_calls, self.io.exports), (0, 0))

    def test_an_unjournalled_site_installs_nothing_at_all(self):
        self.clear_lists()
        self.io.place_journal({0xC03DA420: 0xEB0000CC})
        result = self.run_trial()
        self.assert_never_armed(result)
        self.assertFalse(result['installation_performed'])
        self.assertEqual((self.io.claim_calls, self.io.writes), (0, []))
        self.assertIn('four-byte section', result['error'])

    def test_a_journal_without_a_loader_block_installs_nothing(self):
        self.clear_lists()
        result = self.run_trial()
        self.assert_never_armed(result)
        self.assertFalse(result['installation_performed'])
        self.assertIn('both power-off lists', result['error'])

    def test_a_block_in_only_one_list_is_refused(self):
        for lists in (('ordinary',), ('forced',)):
            with self.subTest(lists=lists):
                self.io = MemoryIO(self.rom)
                self.clear_lists()
                self.io.place_journal(lists=lists)
                result = self.run_trial()
                self.assert_never_armed(result)
                self.assertIn('both power-off lists', result['error'])

    def test_a_journalled_patched_word_is_refused(self):
        # A missed power-off leaves a patched word, and the next load records it
        # as if it were stock: restoring that would put the hook back, not remove it.
        self.clear_lists()
        self.io.place_journal({trial.fmt.CALLSITE: 0xEA001234})
        result = self.run_trial()
        self.assert_never_armed(result)
        self.assertIn('not the stock', result['error'])

    def test_the_gate_is_re_checked_immediately_before_arming(self):
        def emit(row):
            if row.get('event') == 'allocation_intent':
                self.clear_lists()          # something else tore the journal out
        result = self.run_trial(emit=emit)
        self.assert_never_armed(result)
        self.assertIn('shutdown_restore', result)
        self.assertNotIn('shutdown_restore_at_arm', result)

    def test_a_verified_journal_records_the_word_and_the_block(self):
        result = self.run_trial()
        self.assertEqual(result['status'], 'captured')
        self.assertTrue(result['shutdown_restore_verified'])
        verdict = result['shutdown_restore']
        self.assertTrue(verdict['complete'] and verdict['journalled'])
        self.assertEqual(verdict['recorded_word'], trial.fmt.ORIGINAL_WORD)
        self.assertEqual(verdict['journal']['block'], JOURNAL)
        self.assertFalse(verdict['quiescence_proven'] or verdict['covers_battery_pull'])
        self.assertTrue(result['shutdown_restore_at_arm']['complete'])

    def test_nothing_is_registered_and_no_list_slot_is_spent(self):
        before = trial.restore.read_lists(self.io.read)
        result = self.run_trial()
        self.assertEqual(result['status'], 'captured')
        after = trial.restore.read_lists(self.io.read)
        self.assertEqual(after['ordinary']['objects'], before['ordinary']['objects'])
        self.assertEqual(after['forced']['objects'], before['forced']['objects'])
        for base in (trial.restore.ORDINARY_LIST, trial.restore.FORCED_LIST):
            self.assertFalse(any(base <= address < base + 40
                                 for address, _ in self.io.writes))

    def test_the_card_is_cross_checked_when_it_is_supplied(self):
        result = self.run_trial()
        self.assertIsNone(result['shutdown_restore']['card'])
        card = (b'VBIN' + struct.pack('<III', 1, 0, 4)
                + struct.pack('<II', trial.fmt.CALLSITE, 4)
                + struct.pack('<I', trial.fmt.ORIGINAL_WORD))
        self.io = MemoryIO(self.rom)
        result = self.run_trial(vbin=card)
        self.assertTrue(result['shutdown_restore']['card']['exact'])
        self.assertTrue(result['shutdown_restore']['card']['matches'])

    def test_no_command_line_option_skips_the_gate(self):
        with contextlib.redirect_stderr(textio.StringIO()):
            with self.assertRaises(SystemExit):
                trial.main(['--run-live-hook', '--output', str(self.output / 'x'),
                            '--skip-shutdown-restore'])
        source = Path(trial.__file__).read_text()
        for word in ('--force', '--skip', '--no-verify', 'allow_unverified'):
            self.assertNotIn(word, source)


class TransportAndClaimTests(unittest.TestCase):
    def test_unowned_write_rejected_before_any_exchange(self):
        io = trial.TrialIO()
        with mock.patch.object(io, 'read') as read, mock.patch.object(io, 'shell') as shell:
            with self.assertRaises(ValueError):
                io.word(0xC0000000, 0)
        read.assert_not_called()
        shell.assert_not_called()

    def test_known_destination_does_not_authorize_overwriting_unknown_owner(self):
        for address, destination in ((trial.ECHO, trial.DCACHE),
                                     (trial.fmt.CALLSITE, trial.fmt.ORIGINAL_WORD)):
            io = trial.TrialIO()
            with self.subTest(address=hex(address)), mock.patch.object(io, 'read', return_value=[0xBAD0BAD0]), \
                 mock.patch.object(io, 'shell') as shell:
                with self.assertRaises(trial.BridgeError):
                    io.word(address, destination)
                shell.assert_not_called()

    def test_write_mismatch_and_read_fault_have_no_retry(self):
        io = trial.TrialIO()
        io.regions = [(BASE, BASE + 4)]
        with mock.patch.object(io, 'read', side_effect=[[0], [0]]) as read, \
             mock.patch.object(io, 'shell', return_value='') as shell:
            with self.assertRaises(trial.BridgeError):
                io.word(BASE, 1)
            self.assertEqual(read.call_count, 2)
            self.assertEqual(shell.call_count, 1)
        with mock.patch.object(io, 'shell', side_effect=TimeoutError('uncertain')) as shell:
            with self.assertRaises(TimeoutError):
                io.read(BASE, 32)
            self.assertEqual(shell.call_count, 1)

    def test_bulk_rejects_bad_or_short_reply_once_and_latches_fault(self):
        for reply in (b'ERR bulk timeout\n', b'OKX 0000\n'):
            io = trial.TrialIO()
            connection = mock.MagicMock()
            connection.__enter__.return_value = connection
            connection.recv.side_effect = [reply, b'']
            with self.subTest(reply=reply), mock.patch('socket.socket', return_value=connection) as create:
                with self.assertRaises(trial.BridgeError):
                    io.bulk(64)
                self.assertTrue(io.transport_faulted)
                self.assertEqual(create.call_count, 1)
                self.assertEqual(connection.sendall.call_count, 1)

    def test_same_nonce_claim_refused_before_initialization_and_allocator_restored(self):
        io = trial.TrialIO()
        original_sh = object()
        cave = types.SimpleNamespace(_sh=original_sh, _check_agrees=lambda: None,
                    claims=lambda: {f'afhook.{NONCE:08x}.param': [PARAM, 128]}, claim=mock.Mock())
        probe = trial.Probe(io, lambda _: None)
        with mock.patch.dict(sys.modules, {'cave': cave}), mock.patch.object(io, 'word') as write:
            with self.assertRaises(trial.BridgeError):
                probe.claim(NONCE)
            cave.claim.assert_not_called()
            write.assert_not_called()
        self.assertIs(cave._sh, original_sh)
        self.assertEqual(probe.retained, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
