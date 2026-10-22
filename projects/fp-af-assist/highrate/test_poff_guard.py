"""RETIRED 2026-09-28. The object these tests cover is no longer installed:
the shared loader journals and restores run-time hook sites declared as
four-byte card sections. Kept with the code it tests; not run.

Original description:
Run the real power-off guard bytes in Unicorn, with ROM-faithful stubs.

`POFF_ADD` is modelled from the decompiled C0024118: ten slots at mgr+0x0C
(ordinary) and mgr+0x34 (forced), fill the first zero, refuse when full. The
lists live in emulated memory, so the tests read the effect rather than the
guard's own bookkeeping. Nothing here touches a camera, and none of it shows
what the real power-off manager does with the object afterwards. Missing Unicorn
or a restricted JIT is an ERROR, not a skip.
"""
import unittest

raise unittest.SkipTest('af_poff_guard retired 2026-09-28; the shared loader journal replaces it (notes/AF_LOADER_CONVENTION_FINDING_2026-09-28.md)')

from pathlib import Path
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
sys.path.insert(0, str(HERE.parent))
import af_batch as fmt
import build_poff_guard as build
import shutdown_restore as check

BLOCK = 0xC072E100
HELPER = 0xC072E400
ARMED = 0xEA001234
MANAGER = check.MANAGER
POFF_MGR, POFF_ADD = 0xC0023A98, 0xC0024118
DCACHE, ICACHE = build.DCACHE, build.ICACHE
STACK, SP, RETURN = 0x43000000, 0x43008000, 0x44000000
SCRATCH_FILL, SCRATCH_FAR = 0xC072EF10, 0xC072EF00   # free cave words, for the bound test
REGS = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
        UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
        UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
        UC_ARM_REG_R12]
STUBS = (POFF_MGR, POFF_ADD, DCACHE, ICACHE)


def assemble(source=None, **kw):
    options = dict(block_base=BLOCK, armed_branch=ARMED, helper=HELPER)
    options.update(kw)
    if source is None:
        return build.assemble(**options)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / 'af_poff_guard.S'
        src.write_text(source)
        original, build.SOURCE = build.SOURCE, src
        try:
            return build.assemble(**options)
        finally:
            build.SOURCE = original


class Guard:
    """One emulated boot: the object in the cave, the manager's lists in memory."""

    def __init__(self, code, manifest):
        self.code, self.manifest = code, manifest
        self.uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        self.pages = set()
        self.calls, self.writes = [], []
        self.manager = MANAGER
        for address, size in ((BLOCK, len(code)), (fmt.CALLSITE, 4), (build.ECHO, 4),
                              (MANAGER, 0x60), (STACK, 0x10000), (RETURN, 4),
                              *((stub, 4) for stub in STUBS)):
            for page in range(address & ~0xFFF, (address + size + 0xFFF) & ~0xFFF, 4096):
                if page not in self.pages:
                    self.uc.mem_map(page, 4096)
                    self.pages.add(page)
        self.uc.mem_write(BLOCK, code)
        self.word(fmt.CALLSITE, fmt.ORIGINAL_WORD)
        self.word(build.ECHO, build.ECHO_ORIGINAL)
        self.uc.hook_add(UC_HOOK_CODE, self.on_code)
        self.uc.hook_add(UC_HOOK_MEM_WRITE, self.on_write)

    # --- memory -----------------------------------------------------------
    def read(self, address, count=1):
        return list(struct.unpack('<%dI' % count, self.uc.mem_read(address, count * 4)))

    def word(self, address, value=None):
        if value is None:
            return self.read(address)[0]
        self.uc.mem_write(address, struct.pack('<I', value))

    def entry(self, at, address, original, allowed):
        for offset, value in ((0, address), (4, original), (8, allowed),
                              (12, 0), (16, 0), (20, 0)):
            self.word(at + offset, value)

    def lists(self):
        return {name: self.read(at, build.HEADER_WORDS + 4)
                for name, at in (('ordinary', check.ORDINARY_LIST),
                                 ('forced', check.FORCED_LIST))}

    def fill(self, name, count, first=0x11110000):
        at = check.ORDINARY_LIST if name == 'ordinary' else check.FORCED_LIST
        for index in range(count):
            self.word(at + index * 4, first + index)

    # --- hooks ------------------------------------------------------------
    def on_write(self, uc, access, address, size, value, _):
        allowed = ((BLOCK, BLOCK + len(self.code)), (SP - 64, SP),
                   (fmt.CALLSITE, fmt.CALLSITE + 4), (build.ECHO, build.ECHO + 4),
                   (check.ORDINARY_LIST, check.ORDINARY_LIST + 40),
                   (check.FORCED_LIST, check.FORCED_LIST + 40),
                   (SCRATCH_FAR, SCRATCH_FAR + 4), (SCRATCH_FILL, SCRATCH_FILL + 4))
        assert any(lo <= address and address + size <= hi for lo, hi in allowed), \
            f'write outside the object, its words, the lists or the stack: {address:#x}'
        self.writes.append((address, value))

    def on_code(self, uc, address, size, _):
        if BLOCK <= address < BLOCK + len(self.code):
            return
        if address == RETURN:
            self.returned = True
            uc.emu_stop()
            return
        assert address in STUBS, f'unapproved execution {address:#x}'
        assert uc.reg_read(UC_ARM_REG_SP) % 8 == 0, 'unaligned external-call SP'
        args = tuple(uc.reg_read(reg) for reg in REGS[:4])
        self.calls.append((address, args))
        if address == POFF_MGR:
            result = self.manager
        elif address == POFF_ADD:
            result = self.poff_add(*args[:3])
        else:
            result = 0
        for index in (0, 1, 2, 3, 12):
            uc.reg_write(REGS[index], 0xBAD00000 + index)
        uc.reg_write(UC_ARM_REG_R0, result)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    def poff_add(self, mgr, obj, forced):
        """C0024118, as decompiled: first free of ten slots, else refuse."""
        at = mgr + (0x34 if forced else 0x0C)
        for index in range(build.list_slots if hasattr(build, 'list_slots') else 10):
            if not self.word(at + index * 4):
                self.word(at + index * 4, obj)
                return 1
        return 0

    # --- running ----------------------------------------------------------
    def run(self, pc, r0=0, r1=0, sp=SP):
        self.calls, self.writes, self.returned = [], [], False
        initial = [0x22330000 + index * 0x1001 for index in range(13)]
        self.uc.reg_write(UC_ARM_REG_CPSR, 0x13)
        for reg, value in zip(REGS, initial):
            self.uc.reg_write(reg, value)
        self.uc.reg_write(UC_ARM_REG_R0, r0)
        self.uc.reg_write(UC_ARM_REG_R1, r1)
        self.uc.reg_write(UC_ARM_REG_SP, sp)
        self.uc.reg_write(UC_ARM_REG_LR, RETURN)
        self.uc.emu_start(pc, RETURN + 4, count=4000)
        assert self.returned, 'guard did not return within its instruction bound'
        assert self.uc.reg_read(UC_ARM_REG_SP) == sp, 'SP not restored'
        for index in range(4, 12):
            assert self.uc.reg_read(REGS[index]) == initial[index], f'r{index} clobbered'
        return self.uc.reg_read(UC_ARM_REG_R0)

    def register(self, **kw):
        return self.run(self.manifest['register_entry'], **kw)

    def power_off(self, reason=4, **kw):
        # Exactly what the manager does: [ [obj] + 0xC ](obj, reason).
        vtbl = self.word(BLOCK)
        return self.run(self.word(vtbl + 0xC), r0=BLOCK, r1=reason, **kw)

    def state(self):
        return check.read_guard(self.read, self.manifest, self.code)


def fresh(**kw):
    code, manifest = assemble(**kw)
    return Guard(code, manifest)


class RegistrationTests(unittest.TestCase):
    def test_registers_in_both_lists_once_each(self):
        cam = fresh()
        self.assertEqual(cam.register(), build.REGISTERED)
        # The manager is a singleton at a fixed address; it is fetched once and
        # reused for the forced add.
        self.assertEqual([address for address, _ in cam.calls],
                         [POFF_MGR, POFF_ADD, POFF_ADD])
        self.assertEqual([args[2] for address, args in cam.calls if address == POFF_ADD],
                         [0, 1])
        self.assertEqual([args[1] for address, args in cam.calls if address == POFF_ADD],
                         [BLOCK, BLOCK])
        self.assertEqual(cam.read(check.ORDINARY_LIST, 10)[:2], [BLOCK, 0])
        self.assertEqual(cam.read(check.FORCED_LIST, 10)[:2], [BLOCK, 0])
        state = cam.state()
        self.assertTrue(state['status_ordinary'] and state['status_forced'])
        self.assertEqual((state['runs'], state['restored_mask']), (0, 0))

    def test_vtable_indirection_reaches_the_routine(self):
        cam = fresh()
        self.assertEqual(cam.word(BLOCK), BLOCK - 8)
        self.assertEqual(cam.word(cam.word(BLOCK) + 0xC), cam.manifest['routine'])

    def test_a_second_attempt_does_not_register_again(self):
        cam = fresh()
        cam.register()
        self.assertEqual(cam.register(), build.REGISTERED)
        self.assertEqual(cam.calls, [])
        self.assertEqual(cam.read(check.ORDINARY_LIST, 10).count(BLOCK), 1)
        self.assertEqual(cam.read(check.FORCED_LIST, 10).count(BLOCK), 1)

    def test_a_full_ordinary_list_does_not_try_the_forced_one(self):
        cam = fresh()
        cam.fill('ordinary', 10)
        self.assertEqual(cam.register(), build.ATTEMPTED | build.ORDINARY_FULL)
        self.assertEqual([address for address, _ in cam.calls], [POFF_MGR, POFF_ADD])
        self.assertNotIn(BLOCK, cam.read(check.FORCED_LIST, 10))
        self.assertFalse(cam.state()['status_ordinary'])

    def test_a_full_forced_list_is_reported_not_hidden(self):
        cam = fresh()
        cam.fill('forced', 10)
        self.assertEqual(cam.register(), build.ORDINARY | build.FORCED_FULL)
        state = cam.state()
        self.assertTrue(state['status_ordinary'])
        self.assertFalse(state['status_forced'])
        verdict = check.verify(cam.read, cam.manifest, cam.code)
        self.assertFalse(verdict['complete'])          # half a registration is not one
        self.assertEqual(verdict['registered'], dict(ordinary=True, forced=False))

    def test_no_manager_registers_nothing(self):
        cam = fresh()
        cam.manager = 0
        self.assertEqual(cam.register(), build.ATTEMPTED | build.NO_MANAGER)
        self.assertEqual([address for address, _ in cam.calls], [POFF_MGR])
        self.assertEqual(cam.read(check.ORDINARY_LIST, 10), [0] * 10)

    def test_attempt_is_published_before_the_rom_call(self):
        cam = fresh()
        seen = []
        original = cam.poff_add

        def watching(mgr, obj, forced):
            seen.append(cam.word(BLOCK + 0x0C))
            return original(mgr, obj, forced)
        cam.poff_add = watching
        cam.register()
        self.assertEqual(seen[0] & build.ATTEMPTED, build.ATTEMPTED)

    def test_registration_keeps_other_objects(self):
        cam = fresh()
        cam.fill('ordinary', 3)
        cam.fill('forced', 2, first=0x22220000)
        before = check.read_lists(cam.read)
        cam.register()
        verdict = check.verify(cam.read, cam.manifest, cam.code, baseline_lists=before)
        self.assertTrue(verdict['others_kept'])
        self.assertTrue(verdict['complete'])
        self.assertEqual(verdict['lists']['ordinary']['objects'][-1], BLOCK)
        self.assertEqual(verdict['lists']['ordinary']['free'], 6)

    def test_an_sp_four_off_still_aligns_every_rom_call(self):
        cam = fresh()
        self.assertEqual(cam.register(sp=SP - 4), build.REGISTERED)


class RestoreTests(unittest.TestCase):
    def arm(self, cam):
        cam.word(fmt.CALLSITE, ARMED)
        cam.word(build.ECHO, HELPER)

    def test_puts_both_borrowed_words_back_and_publishes(self):
        cam = fresh()
        cam.register()
        self.arm(cam)
        cam.power_off()
        self.assertEqual(cam.word(fmt.CALLSITE), fmt.ORIGINAL_WORD)
        self.assertEqual(cam.word(build.ECHO), build.ECHO_ORIGINAL)
        self.assertEqual([address for address, _ in cam.calls], [DCACHE, ICACHE])
        restores = [address for address, _ in cam.writes
                    if address in (fmt.CALLSITE, build.ECHO)]
        self.assertEqual(restores, [fmt.CALLSITE, build.ECHO])
        state = cam.state()
        self.assertEqual((state['runs'], state['restored_mask'], state['foreign_mask']),
                         (1, 0b11, 0))

    def test_running_twice_is_harmless(self):
        cam = fresh()
        cam.register()
        self.arm(cam)
        cam.power_off()
        cam.power_off()
        self.assertEqual(cam.word(fmt.CALLSITE), fmt.ORIGINAL_WORD)
        self.assertEqual(cam.word(build.ECHO), build.ECHO_ORIGINAL)
        self.assertEqual(cam.state()['runs'], 2)
        self.assertNotIn(fmt.CALLSITE, [address for address, _ in cam.writes])

    def test_each_allowed_echo_value_is_restored(self):
        for value in (DCACHE, ICACHE, HELPER):
            cam = fresh()
            cam.word(build.ECHO, value)
            cam.power_off()
            self.assertEqual(cam.word(build.ECHO), build.ECHO_ORIGINAL, hex(value))
            self.assertEqual(cam.state()['restored_mask'], 0b10)

    def test_an_unknown_owner_is_reported_not_overwritten(self):
        cam = fresh()
        cam.word(fmt.CALLSITE, 0xDEADBEEF)
        cam.power_off()
        self.assertEqual(cam.word(fmt.CALLSITE), 0xDEADBEEF)
        state = cam.state()
        self.assertEqual((state['restored_mask'], state['foreign_mask']), (0, 0b01))
        self.assertNotIn(fmt.CALLSITE, [address for address, _ in cam.writes])

    def test_already_stock_writes_nothing(self):
        cam = fresh()
        cam.power_off()
        self.assertEqual(cam.state()['restored_mask'], 0)
        self.assertEqual([address for address, _ in cam.writes
                          if address in (fmt.CALLSITE, build.ECHO)], [])
        self.assertEqual([address for address, _ in cam.calls], [DCACHE, ICACHE])

    def test_caches_are_published_after_the_writes(self):
        cam = fresh()
        self.arm(cam)
        order = []
        cam.uc.hook_add(UC_HOOK_MEM_WRITE,
                        lambda uc, a, addr, s, v, _: order.append(('write', addr))
                        if addr in (fmt.CALLSITE, build.ECHO) else None)
        real = cam.on_code

        def watching(uc, address, size, user):
            if address in (DCACHE, ICACHE):
                order.append(('call', address))
            return real(uc, address, size, user)
        cam.uc.hook_add(UC_HOOK_CODE, watching)
        cam.power_off()
        self.assertEqual(order, [('write', fmt.CALLSITE), ('write', build.ECHO),
                                 ('call', DCACHE), ('call', ICACHE)])

    def test_a_zero_word_is_not_ours(self):
        # Unused allowed slots are zero; a word that happens to hold zero must
        # not match one of them.
        cam = fresh()
        cam.word(fmt.CALLSITE, 0)
        cam.power_off()
        self.assertEqual(cam.word(fmt.CALLSITE), 0)
        state = cam.state()
        self.assertEqual((state['restored_mask'], state['foreign_mask']), (0, 0b01))

    def test_the_walk_stops_at_the_eighth_entry(self):
        # A ninth entry is out of reach even if it looks restorable, so a damaged
        # table cannot turn the routine loose on arbitrary addresses.
        cam = fresh()
        table = cam.manifest['pairs']
        cam.word(SCRATCH_FILL, 0x1234)                    # already stock: a no-op
        cam.word(SCRATCH_FAR, 0xBBBB0000)                 # entry 8 would restore it
        for index in range(2, 8):
            cam.entry(table + index * build.ENTRY_BYTES, SCRATCH_FILL, 0x1234, 0x5678)
        cam.entry(table + 8 * build.ENTRY_BYTES, SCRATCH_FAR, 0xAAAA0000, 0xBBBB0000)
        cam.word(table + 9 * build.ENTRY_BYTES, 0)        # terminate beyond it
        cam.word(build.ECHO, HELPER)
        cam.word(fmt.CALLSITE, ARMED)
        # The damaged table is outside the reviewed bytes, so the verifier
        # refuses the object; the routine's own bound is what is under test.
        with self.assertRaises(check.ShutdownRestoreError):
            cam.state()
        cam.power_off()
        self.assertEqual(cam.word(SCRATCH_FAR), 0xBBBB0000)  # entry 8 out of reach
        masks = cam.word(BLOCK + 0x14)
        self.assertEqual(masks & 0x100, 0)
        self.assertEqual(masks & 0xFF, 0b11)
        self.assertEqual(cam.word(build.ECHO), build.ECHO_ORIGINAL)   # by entry 1

    def test_masks_accumulate_across_both_lists(self):
        cam = fresh()
        cam.word(fmt.CALLSITE, ARMED)
        cam.power_off()                                  # ordinary list: site only
        cam.word(build.ECHO, HELPER)
        cam.power_off()                                  # forced list: echo as well
        state = cam.state()
        self.assertEqual((state['restored_mask'], state['runs']), (0b11, 2))


class VerdictTests(unittest.TestCase):
    """The host verifier, against the same emulated boot."""

    def vbin(self, *sections):
        out = bytearray(b'VBIN' + struct.pack('<III', len(sections), 0, 0))
        for dest, length in sections:
            out += struct.pack('<II', dest, length)
        return bytes(out)

    def test_complete_only_when_both_lists_hold_it(self):
        cam = fresh()
        self.assertFalse(check.verify(cam.read, cam.manifest, cam.code)['complete'])
        cam.register()
        verdict = check.require(cam.read, cam.manifest, cam.code)
        self.assertTrue(verdict['complete'])
        self.assertTrue(all(word['restored_by_guard'] for word in verdict['words']))
        self.assertFalse(verdict['quiescence_proven'])

    def test_a_changed_object_is_refused(self):
        cam = fresh()
        cam.register()
        cam.word(cam.manifest['pairs'] + 4, 0xC0DEC0DE)   # a different "original"
        with self.assertRaises(check.ShutdownRestoreError):
            check.require(cam.read, cam.manifest, cam.code)

    def test_runtime_words_are_allowed_to_change(self):
        cam = fresh()
        cam.register()
        self.arm(cam) if hasattr(self, 'arm') else None
        cam.word(fmt.CALLSITE, ARMED)
        cam.power_off()
        self.assertTrue(check.require(cam.read, cam.manifest, cam.code)['complete'])

    def test_a_word_past_the_terminator_is_not_a_list(self):
        cam = fresh()
        cam.register()
        cam.word(check.ORDINARY_LIST + 8, 0x33330000)
        verdict = check.verify(cam.read, cam.manifest, cam.code)
        self.assertTrue(verdict['lists']['ordinary']['trailing_nonzero'])
        self.assertFalse(verdict['complete'])

    def test_require_room_refuses_a_full_list(self):
        cam = fresh()
        cam.fill('forced', 10)
        with self.assertRaises(check.ShutdownRestoreError):
            check.require_room(check.read_lists(cam.read))
        for index in range(10):
            cam.word(check.FORCED_LIST + index * 4, 0)
        self.assertTrue(check.require_room(check.read_lists(cam.read)))

    def test_the_loader_journal_does_not_cover_these_words(self):
        # The real card patches firmware words; these two are not among them,
        # which is the whole reason this object exists.
        card = self.vbin((0xC03DA420, 4), (0xC072DE64, 0x200), (0x1000, 64))
        self.assertEqual(check.journaled_sections(card), [(0xC03DA420, 4)])
        self.assertFalse(check.journal_covers(card, fmt.CALLSITE))
        self.assertFalse(check.journal_covers(card, build.ECHO))
        cam = fresh()
        cam.register()
        verdict = check.verify(cam.read, cam.manifest, cam.code, vbin=card)
        self.assertEqual([word['restored_by_loader_journal'] for word in verdict['words']],
                         [False, False])
        self.assertTrue(verdict['complete'])            # by the guard, not the journal

    def test_a_cave_section_is_not_journaled(self):
        self.assertEqual(check.journaled_sections(self.vbin((0xC072E100, 468))), [])

    def test_bad_images_are_refused(self):
        for bad in (b'', b'VBIN' + bytes(12), b'NOPE' + struct.pack('<III', 1, 0, 0)):
            with self.assertRaises(check.ShutdownRestoreError):
                check.journaled_sections(bad)


class BuilderTests(unittest.TestCase):
    def test_header_and_table_are_checked_against_the_request(self):
        code, manifest = assemble()
        self.assertEqual(manifest['block_bytes'], len(code))
        self.assertEqual(manifest['vtable'], BLOCK - 8)
        self.assertEqual([entry['address'] for entry in manifest['entries']],
                         [fmt.CALLSITE, build.ECHO])
        self.assertFalse(manifest['deployment_ready'] or manifest['registered'])

    def test_a_block_moved_after_assembly_is_detectable(self):
        code, manifest = assemble()
        other, _ = assemble(block_base=BLOCK + 0x40)
        self.assertNotEqual(code, other)               # absolute words, not relocatable

    def test_the_echo_may_hold_this_object_s_own_register_entry(self):
        # The installer reaches the register entry through the same borrow, so a
        # power-off during registration must recognise that value as ours.
        code, manifest = assemble()
        echo = manifest['entries'][1]
        self.assertIn(manifest['register_entry'], echo['allowed'])
        self.assertEqual(echo['allowed'], [DCACHE, ICACHE, HELPER,
                                           manifest['register_entry']])
        cam = Guard(code, manifest)
        cam.word(build.ECHO, manifest['register_entry'])
        cam.power_off()
        self.assertEqual(cam.word(build.ECHO), build.ECHO_ORIGINAL)

    def test_rejects_an_armed_word_equal_to_the_original(self):
        with self.assertRaises(ValueError):
            assemble(armed_branch=fmt.ORIGINAL_WORD)

    def test_rejects_misaligned_addresses(self):
        with self.assertRaises(ValueError):
            assemble(block_base=BLOCK + 1)
        with self.assertRaises(ValueError):
            assemble(helper=HELPER + 2)

    def test_table_decoder_bounds(self):
        with self.assertRaises(ValueError):
            build.decode_table(struct.pack('<6I', 0xC0000000, 1, 2, 0, 0, 0)[:20])
        entry = struct.pack('<6I', 0xC0000004, 0x11, 0x11, 0, 0, 0)
        with self.assertRaises(ValueError):            # original inside allowed
            build.decode_table(entry + bytes(4))
        packed = b''.join(struct.pack('<6I', 0xC0000000 + index * 4, 1, 2, 0, 0, 0)
                          for index in range(9)) + bytes(4)
        with self.assertRaises(ValueError):            # past the routine's bound
            build.decode_table(packed)


class MutationTests(unittest.TestCase):
    """Every protection is shown to be load-bearing by removing it."""

    def run_suite(self, source):
        code, manifest = assemble(source)
        suite = unittest.TestSuite()
        loader = unittest.TestLoader()
        for case in (RegistrationTests, RestoreTests, VerdictTests):
            suite.addTests(loader.loadTestsFromTestCase(case))
        original = globals()['fresh']
        globals()['fresh'] = lambda **kw: Guard(*assemble(source, **kw))
        try:
            with open('/dev/null', 'w') as quiet:
                result = unittest.TextTestRunner(stream=quiet, verbosity=0).run(suite)
        finally:
            globals()['fresh'] = original
        return result

    def mutate(self, old, new):
        source = build.SOURCE.read_text()
        self.assertIn(old, source, old)
        return source.replace(old, new, 1)

    def test_mutations_are_caught(self):
        cases = {
            'no forced list': ('    mov r2, #1                       /* the forced',
                               '    mov r2, #0                       /* the forced'),
            'no restore write': ('    str r3, [r1]                     /* ours',
                                 '    nop                              /* ours'),
            'zero matches an unused slot': (
                '    beq foreign                      /* the list ended',
                '    nop                              /* the list ended'),
            'no i-cache publish': ('    LDA r3, F_ICACHE\n    blx r3', '    nop\n    nop'),
            'no attempt latch': ('    str r5, [r4, #0x0C]              /* attempted',
                                 '    nop                              /* attempted'),
            'already-stock check dropped': ('    cmp r2, r3\n    beq next_entry',
                                            '    cmp r2, r3\n    nop'),
            'masks not published': ('    str r7, [r8, #0x14]', '    nop'),
            'entry bound dropped': ('    cmp r5, #MAX_ENTRY\n    bhs walked',
                                    '    nop\n    nop'),
        }
        for name, (old, new) in cases.items():
            with self.subTest(name):
                result = self.run_suite(self.mutate(old, new))
                self.assertTrue(result.failures or result.errors,
                                f'mutation "{name}" changed nothing that is checked')


if __name__ == '__main__':
    unittest.main(verbosity=2)
