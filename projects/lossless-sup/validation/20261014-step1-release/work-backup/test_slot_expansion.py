"""Exact optional LOSS binary + native pool, registry, and SD cookie routines.

Only OS locks, media I/O and frame payload destructors are substituted. No
camera transport is imported. The real free list, bounds, registry scans,
native release accounting, and completion loop execute in Unicorn.
"""
import json
import hashlib
import os
import pathlib
import struct
import tempfile
import unittest
import test_v3_lossless as V
from unicorn import UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.arm_const import *

OLD_POOL = 0xc3600000
REG = 0xc351ff44
VOLUME, SCATTER = 0x45730000, 0x45721000
CALLBACK, TRANSFER = 0xc03a55d0, 0xc0646c60
FREE_ARENA, GET_ARENA = 0xc0100100, 0xc0100120
ENDS = [int(a) for a in json.loads((pathlib.Path(__file__).resolve().parent / 'native' /
                                    'slot_sites.json').read_text())['ends']]


class SlotCamera(V.LosslessCamera):
    def __init__(self, *args, **kwargs):
        self.runtime = False
        self.stop_at = None
        self.c_entries = []
        self.cookies, self.transfers, self.released = [], [], []
        super().__init__(*args, **kwargs)
        self.put(0xc2f1f3d8, OLD_POOL)
        self.put(OLD_POOL, 0xc0b99474)
        self.put(OLD_POOL + 0x112c, 96)
        self.put(REG, 0x1234)
        self.put(0xc35200e0, 0)
        # getter's already-constructed guard; return its patched final pair.
        self.stubs = {0xc0013090: 0, 0xc001cce0: 0, 0xc001cd18: 0,
                      0xc0019dc0: 0x1234, 0xc001a048: 0, 0xc001a288: 0,
                      0xc036dcc8: 1, 0xc00101c0: 0, 0xc0010210: 0,
                      0xc0010298: 0, 0xc00102d0: 0,
                      0xc037aed8: 1, 0xc037d580: 1, 0xc037dd08: 1,
                      0xc037b1f0: 0, 0xc037d880: 0, 0xc037e008: 0,
                      0xc001cf18: 3, 0xc037dd50: 1,
                      FREE_ARENA: 0, GET_ARENA: 0x45722000}
        for a in self.stubs:
            self.put(a, 0xe12fff1e)
        self.put(CALLBACK, 0xe12fff1e)
        self.put(TRANSFER, 0xe12fff1e)

    def _hook(self, mu, addr, size, data):
        if addr in getattr(self, 'stubs', {}): return self._ret(self.stubs[addr])
        if addr == 0xc0011100 or addr == 0xc0011130:
            raise AssertionError(f'native assertion, lr={self.r(UC_ARM_REG_LR):08x}')
        if self.runtime:
            if addr == self.stop_at:
                mu.emu_stop(); return
            if addr in self.c_entries and self.r(UC_ARM_REG_SP) & 7:
                raise AssertionError('new cookie C call is not 8-byte aligned')
            if addr == CALLBACK:
                self.cookies.append((self.r(UC_ARM_REG_R0), self.r(UC_ARM_REG_R1)))
                return self._ret(0)
            if addr == TRANSFER:
                self.transfers.append(self.w(VOLUME + 0x4a58))
                return self._ret(0)
            if addr == 0xc0380580:
                frame = self.r(UC_ARM_REG_R0)
                self.released.append(frame)
                # Substitute payload destruction; use the REAL pool free.
                mu.reg_write(UC_ARM_REG_R0, self.pool)
                mu.reg_write(UC_ARM_REG_R1, frame)
                mu.reg_write(UC_ARM_REG_PC, 0xc0380c80)
                return
            if addr == 0xc063f888:
                mu.emu_stop(); return
            allowed = (0xc03739c0 <= addr < 0xc03739f0 or
                       0xc0374220 <= addr < 0xc0374268 or
                       0xc0375030 <= addr < 0xc0376b58 or
                       0xc037df40 <= addr < 0xc037e008 or      # writer completion
                       addr in getattr(self, 'allow', ()) or
                       0xc03806e8 <= addr < 0xc0380f20 or
                       0xc063f140 <= addr < 0xc063f220 or
                       0xc063f6c6 <= addr < 0xc063f6f8 or
                       0xc063f81c <= addr < 0xc063f888 or
                       self.blob <= addr < self.blob_end or
                       self.cave <= addr < self.cave + 120 or
                       addr in self.by_addr or addr == V.T.DONE)
            if not allowed: raise AssertionError(f'unexpected execution {addr:#x}')
        return super()._hook(mu, addr, size, data)


class ExpandedSlotsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The production CLI runs once per process; tests must not leak its
        # candidate options into baseline test discovery or another module.
        lists = [V.L.C.CFLAGS, V.L.C.UNITS, V.L.C.FIELDS]
        maps = [V.L.C.SITES, V.L.WANT_KIND, V.L.C.ENTRIES]
        saved_lists, saved_maps = [list(x) for x in lists], [dict(x) for x in maps]
        expanded = V.L.EXPAND_SLOTS
        try:
            V.L.enable_slot_expansion()
            cls.sites = dict(V.L.C.SITES)
            directory = os.environ.get('FPL_SLOT_CANDIDATE')
            if directory:
                d = pathlib.Path(directory)
                cls.sup = (d / '10LOSS.BIN').read_bytes()
                meta = json.loads((d / 'build.json').read_text())
                assert meta['expanded_slots'] and meta['sha256'] == hashlib.sha256(cls.sup).hexdigest()
                cls.facts = meta['blob']
                cls.facts['layout'] = json.loads((d / 'layout.json').read_text())['fields']
            else:
                with tempfile.TemporaryDirectory(prefix='fpl-slots-') as td:
                    cls.sup, cls.facts = V.L.sup_file(pathlib.Path(td))
            cls.capacity = cls.facts.get('slot_capacity', 768)
        finally:
            for target, source in zip(lists, saved_lists): target[:] = source
            for target, source in zip(maps, saved_maps): target.clear(); target.update(source)
            V.L.EXPAND_SLOTS = expanded

    camera_type = SlotCamera

    def boot(self, items=()):
        if not items and hasattr(type(self), '_booted'):
            cam, context, memory = type(self)._booted
            for address, data in memory: cam.mu.mem_write(address, data)
            cam.mu.ctl_remove_cache(0xc0000000, 0xc4000000)
            cam.mu.context_restore(context)
            cam.cookies, cam.transfers, cam.released = [], [], []
            cam.error = None; cam.runtime = True
            cam.stop_at = None
            return cam
        cam = self.camera_type(*V.T.card(('10LOSS.BIN', self.sup), *items))
        cam.boot()
        # This candidate reserves several MiB; the unchanged loader's byte
        # zero loop needs more than the small-product harness's 20M budget.
        for _ in range(4):
            if cam.r(UC_ARM_REG_PC) == V.T.DONE: break
            pc = cam.r(UC_ARM_REG_PC) | ((cam.r(UC_ARM_REG_CPSR) >> 5) & 1)
            cam.mu.emu_start(pc, V.T.DONE, count=20000000)
            if cam.error: raise cam.error
        self.assertEqual(cam.r(UC_ARM_REG_PC), V.T.DONE, 'bounded loader execution completed')
        loaded = [a for kind, a, _, name in cam.log() if kind == 'LOADED' and name == '10LOSS.BIN']
        self.assertEqual(len(loaded), 1, cam.log())
        self.assertLess(loaded[0] + 32 + self.facts['block_bytes'], SCATTER,
                        'synthetic media scratch must not overlap the resident block')
        # the card runs from the block's cached alias (VA + 0x80000000)
        cam.blob = loaded[0] + 32 + 0x80000000
        cam.blob_end = cam.blob + self.facts['blob_len']
        cam.card_state = cam.blob + self.facts['state_off']
        cam.cave = cam.w(V.T.cave.CAVE_BUMP) - 120
        cam.pool = self.field(cam, 'slots.pool_ptr')
        cam.reg = cam.card_state + self.facts['layout']['slots.registry']
        cam.runtime = True
        cam.c_entries = [self.entry(cam, n) & ~1 for n in
                         ('fpl_card_cookie_get', 'fpl_card_cookie_put')
                         if n in self.facts['entries']]     # cookies not ported (2026-10-13)
        memory = [(a, bytes(cam.mu.mem_read(a, n))) for a, n in
                  [(0xc0000000, 0x04000000), (V.T.HEAP, V.T.HEAP_SIZE),
                   (V.T.STACK - 0x20000, 0x20000)]]
        if not items: type(self)._booted = (cam, cam.mu.context_save(), memory)
        return cam

    def field(self, cam, name): return cam.w(cam.card_state + self.facts['layout'][name])
    def put_field(self, cam, name, value): cam.put(cam.card_state + self.facts['layout'][name], value)
    def entry(self, cam, name): return cam.blob + self.facts['c_base'] + self.facts['entries'][name]
    def invoke(self, cam, name, *args):
        if len(args) == 4: cam.mu.reg_write(UC_ARM_REG_R3, args[3])
        return cam.call(self.entry(cam, name), *args[:3], sp=V.T.STACK - 0x1000)[0]

    def prepare(self, cam, w=1936, h=1090, fps=60):
        for name, value in [('width', w), ('height', h), ('bits', 12), ('fps_num', fps), ('fps_den', 1)]:
            self.put_field(cam, 'rec.facts.seen.' + name, value)
        self.assertEqual(self.invoke(cam, 'fpl_card_slots_prepare', cam.card_state), 1)
        return self.field(cam, 'slots.active')

    def test_exact_arrival_reads_raw_used_counter_and_applies_memory_gate(self):
        cam = self.boot()
        # A constructed native class-10 channel with distinct used/peak;
        # no codec lane is initialized, so downstream enqueue is substituted.
        channel = 0xc3100000
        cam.put(0xc3073a04, channel)
        cam.put(channel, 10)
        cam.put(channel + 8, 742520320)
        cam.put(channel + 0x18, 75126144)
        cam.put(channel + 0x1c, 700000000)
        values = {'hold_live': 1, 'take_frames': 1, 'slots.completion_budget_us': 500000,
                  'memory_budget.enabled': 1, 'memory_budget.frame_charge': 1103872,
                  'memory_budget.raw_batch_frames': 62, 'memory_budget.fps_ceil': 120,
                  'memory_budget.latency_us': 500000, 'memory_budget.reserve_frames': 190,
                  'memory_budget.reserve_bytes': 190 * 1103872,
                  'memory_budget.min_free': 0xffffffff}
        for name, value in values.items(): self.put_field(cam, name, value)
        self.assertEqual(self.invoke(cam, 'fpl_card_arrive', 0xc3300000, 7, 1, cam.card_state), 1)
        self.assertEqual(self.field(cam, 'memory_budget.last_free'), 742520320 - 75126144 - 2048)
        self.assertEqual(self.field(cam, 'memory_budget.admitted'), 1)
        reserve = self.field(cam, 'memory_budget.reserve_bytes')
        cam.put(channel + 0x18, 742520320 - reserve - 2048)
        self.invoke(cam, 'fpl_card_arrive', 0xc3300000, 8, 1, cam.card_state)
        self.assertEqual(self.field(cam, 'memory_budget.pressure_raw'), 1)
        cam.put(channel, 11)  # unrelated or changing memory map: fail to RAW
        self.invoke(cam, 'fpl_card_arrive', 0xc3300000, 9, 1, cam.card_state)
        self.assertEqual(self.field(cam, 'memory_budget.unknown_raw'), 1)
        self.assertEqual(cam.w(0xc0b9e5d8), 64 << 20)

    def test_same_capacity_reuses_idle_pool_without_patching_or_republishing(self):
        cam = self.boot()
        n = self.prepare(cam, 1008, 672, 30)
        # Leave a valid free list with a different order than pool_make.
        frames = [cam.call(0xc0380ae0, cam.pool, 0x111c)[0] for _ in range(3)]
        for f in frames: cam.call(0xc0380c80, cam.pool, f)
        writes = []
        def record(mu, access, addr, size, value, data):
            if cam.pool <= addr < cam.pool + 0x1130 + self.capacity * 0x1128 or addr in self.sites:
                writes.append(addr)
        hook = cam.mu.hook_add(UC_HOOK_MEM_WRITE, record)
        try:
            self.assertEqual(self.prepare(cam, 1008, 672, 30), n)
            self.assertEqual(writes, [], 'same capacity must not rebuild or rewrite code')
        finally:
            cam.mu.hook_del(hook)
        # An unchanged capacity is not permission to reuse a busy pool.
        frame = cam.call(0xc0380ae0, cam.pool, 0x111c)[0]
        self.assertNotEqual(frame, 0)
        self.assertEqual(self.invoke(cam, 'fpl_card_slots_prepare', cam.card_state), 0)
        cam.call(0xc0380c80, cam.pool, frame)
        self.assertEqual(cam.call(0xc03739c0)[0], n)

    def test_exact_writer_uses_only_the_indexed_record_and_never_writes_dng_bytes(self):
        """Exercise the saved BIN, including id 1015 and the second lane.

        Every unselected slot is poisoned. Record-read addresses prove that
        growing the descriptor pool cannot turn this lookup into a scan.
        The final length is already aligned by the producer; no DNG parser
        or tile table should run in the writer.
        """
        frame, writer, file = 0x45700000, 0x45702000, 0x45703000
        for lane, native_id in [('hold', 0), ('hold', self.capacity - 1),
                                ('hold_b', self.capacity - 1)]:
            with self.subTest(lane=lane, native_id=native_id):
                cam = self.boot()
                rings = [cam.card_state + self.facts['layout'][n + '.ring']
                         for n in ('hold', 'hold_b')]
                for name, ring in zip(('hold', 'hold_b'), rings):
                    self.put_field(cam, name + '.magic', 0x444c4f48)
                    self.put_field(cam, name + '.pipeline', frame + 0x1800)
                    self.put_field(cam, name + '.facts', frame + 0x1900)
                    cam.mu.mem_write(ring, b'\xa5' * (20 * self.capacity))
                    # Other lane's current id is empty, so lane B must be tried.
                    cam.put(ring + 20 * native_id, 0)
                record = rings[lane == 'hold_b'] + 20 * native_id
                cam.mu.mem_write(record, struct.pack('<5I', file, 123904, 400384, frame, 77))
                cam.put(frame + 0x10fc, native_id)
                cam.put(frame + 0x1100, 77)
                cam.put(writer + 0x90, 1)
                cam.put(writer + 0x8c, writer + 0x0c)
                cam.put(writer + 0x10, file)
                cam.put(writer + 0x14, 400384)
                cam.mu.mem_write(file, b'\x5a' * 4096)
                read_addresses, file_writes = [], []
                def read(mu, access, addr, size, value, data):
                    if any(r <= addr < r + 20 * self.capacity for r in rings):
                        read_addresses.append(addr)
                def write(mu, access, addr, size, value, data):
                    if file <= addr < file + 4096: file_writes.append(addr)
                # Unicorn 2.1.4 global MEM_READ tracing changes Thumb IT
                # execution at hold_valid's conditional facts load (isolated
                # with this exact helper, with/without the hook). Restrict
                # tracing to the records under test, outside that IT load.
                hooks = [cam.mu.hook_add(UC_HOOK_MEM_READ, read, begin=r,
                                         end=r + 20 * self.capacity - 1) for r in rings]
                hooks.append(cam.mu.hook_add(UC_HOOK_MEM_WRITE, write,
                                             begin=file, end=file + 4095))
                try:
                    self.invoke(cam, 'fpl_card_flush', writer, frame, cam.card_state)
                finally:
                    for hook in hooks: cam.mu.hook_del(hook)
                allowed = {r + 20 * native_id + k for r in rings for k in range(0, 20, 4)}
                self.assertTrue(read_addresses)
                self.assertLessEqual(set(read_addresses), allowed)
                self.assertLessEqual(len(read_addresses), 12)
                self.assertEqual(file_writes, [])
                self.assertEqual(cam.w(writer + 0x14), 123904)
                self.assertEqual(cam.w(record), 0)
                self.assertEqual(self.field(cam, 'flush.applied'), 1)
                self.assertEqual(cam.w(0xc0b9e5d8), 64 << 20)

    def test_m12240_low_and_high_fps_are_admitted(self):
        # M12240 RAW is 1008x672 (992x662 is the active crop). Two 64 MiB
        # batches at 2 bits/sample need more than 96 slots, under the RAM cap.
        for fps, expected in [(24, 552), (30, 552), (60, 556), (120, 560), (240, 572)]:
            cam = self.boot()
            self.assertEqual(self.prepare(cam, 1008, 672, fps), expected)
            self.assertEqual(cam.call(0xc03739c0)[0], expected)
            self.assertEqual(cam.w(0xc0b9e5d8), 64 << 20)

    def test_maximum_pool_and_registry_recover_above_old_768_boundary(self):
        cam = self.boot()
        # Tiny frames clamp to the table maximum instead of refusing.
        self.assertEqual(self.prepare(cam, 320, 240, 60), 1016)
        frames = []
        for i in range(1016):
            f = cam.call(0xc0380ae0, cam.pool, 0x111c)[0]
            self.assertTrue(cam.pool < f < cam.pool + 0x1130 + 1016 * 0x1128)
            cam.put(f + 4, 1); cam.put(f + 0x1118, 0xffffffff)
            ident = cam.call(0xc0376488, cam.reg, f)[0]
            self.assertEqual(cam.call(0xc03753c0, cam.reg, ident)[0], f)
            frames.append((ident, f))
        self.assertEqual(len({ident for ident, _ in frames}), 1016)
        self.assertEqual(cam.call(0xc03739c0)[0], 0)
        self.assertEqual(cam.w(cam.reg + 4 + self.capacity * 4 + 8), 1016)
        for ident, f in frames:
            cam.call(0xc0375030, cam.reg, ident)
        self.assertEqual(cam.call(0xc03739c0)[0], 1016)
        self.assertEqual(cam.w(cam.reg + 4 + self.capacity * 4 + 8), 0)
        self.assertEqual(len(cam.released), 1016)
        self.assertEqual(len(set(cam.released)), 1016)
        # A slow completion budget is absorbed by a smaller count batch.
        self.put_field(cam, 'slots.completion_budget_us', 1000000)
        self.assertEqual(self.prepare(cam, 1008, 672, 240), 680)
        limit = self.field(cam, 'slots.plan.frame_limit')
        arrivals = self.field(cam, 'slots.plan.arrival_slots')
        self.assertEqual((limit, arrivals), (217, 240))
        self.assertLessEqual(2 * limit + arrivals + 6, 680)

    def test_cookie_extension_tail_above_old_capacity(self):
        cam = self.boot(); self.prepare(cam, 1008, 672, 240)
        cam.put(VOLUME + 0x4834, CALLBACK)
        cam.put(VOLUME + 0x4a54, 1024)
        self.put_field(cam, 'bulk_policy.enabled', 2)
        self.put_field(cam, 'bulk_policy.frame_limit', self.capacity)
        self.put_field(cam, 'bulk_writer_frame', 0x45750000)
        self.invoke(cam, 'fpl_card_bulk', VOLUME, 0x45750000, 0, cam.card_state)
        for count in (767, 768, 1015):
            # Execute the real put/get shims at the old boundary and new tail.
            cam.put(VOLUME + 0x4850, count)
            cam.mu.reg_write(UC_ARM_REG_R2, count * 4)
            cam.mu.reg_write(UC_ARM_REG_R3, VOLUME + 0x4854)
            cam.mu.reg_write(UC_ARM_REG_R12, 0x45750000 + count * 4)
            cam.mu.reg_write(UC_ARM_REG_SP, V.T.STACK - 0x1000)
            cam.stop_at = 0xc063f858
            cam.mu.emu_start(0xc063f855, 0, count=100000)
            if cam.error: raise cam.error
            cam.mu.reg_write(UC_ARM_REG_R4, VOLUME)
            cam.mu.reg_write(UC_ARM_REG_R5, count)
            cam.mu.reg_write(UC_ARM_REG_R10, VOLUME + 0x4854)
            cam.stop_at = 0xc063f1bc
            cam.mu.emu_start(0xc063f1b9, 0, count=100000)
            if cam.error: raise cam.error
            self.assertEqual(cam.r(UC_ARM_REG_R0), 0x45750000 + count * 4)
            self.assertEqual(cam.w(VOLUME + 0x4a54), 1024)
            self.assertEqual(self.field(cam, 'slots.cookies[0].pending'), 0)
            cam.stop_at = None
            self.invoke(cam, 'fpl_card_bulk', VOLUME, 0x45750000, 0, cam.card_state)

    def test_formula_pool_registry_over_96_and_full_recovery(self):
        cam = self.boot(); n = self.prepare(cam)
        self.assertEqual(n, 236)
        pointers = []
        for i in range(n):
            f = cam.call(0xc0380ae0, cam.pool, 0x111c)[0]
            self.assertTrue(cam.pool < f < cam.pool + 0x1130 + n * 0x1128)
            pointers.append(f)
            cam.put(f + 4, 1); cam.put(f + 0x1118, 0xffffffff)
            slot = cam.call(0xc0376488, cam.reg, f)[0]
            self.assertLess(slot, self.capacity)
            self.assertEqual(cam.call(0xc03753c0, cam.reg, slot)[0], f)
        self.assertEqual(len(set(pointers)), n)
        self.assertEqual(cam.call(0xc03739c0)[0], 0)
        # A live table must not be rebuilt or resized.
        self.assertEqual(self.invoke(cam, 'fpl_card_slots_prepare', cam.card_state), 0)
        for f in pointers:
            slot = cam.w(f + 0x10fc)
            cam.call(0xc0375030, cam.reg, slot)
            self.assertEqual(cam.call(0xc03753c0, cam.reg, slot)[0], 0)
        self.assertEqual(cam.call(0xc03739c0)[0], n)
        self.assertEqual(len(cam.released), n)
        self.assertEqual(cam.w(cam.reg + 4 + self.capacity * 4 + 8), 0)
        # OG3K needs no more than stock: every scan end returns to its stock word.
        self.assertEqual(self.prepare(cam, 3024, 2010, 100), 96)
        for a in ENDS: self.assertEqual(cam.w(a), self.sites[a][0], hex(a))
        self.assertEqual(cam.w(0xc0b9e5d8), 64 << 20)

    def test_native_cookie_129_and_completion_loop(self):
        cam = self.boot(); self.prepare(cam)
        for offset, value in [(0x4834, CALLBACK), (0x4838, GET_ARENA), (0x4848, FREE_ARENA),
                              (0x484c, 0x45722000), (0x4828, 64 << 20),
                              (0x4a54, 1024), (0x4a58, 32 << 20)]: cam.put(VOLUME + offset, value)
        frame = 0x45750000
        cam.put(SCATTER + 8, frame)
        self.put_field(cam, 'bulk_writer_frame', frame)
        for name, value in [('enabled', 2), ('frame_limit', self.capacity), ('free_watermark', 2)]:
            self.put_field(cam, 'bulk_policy.' + name, value)
        # The old policy flushed at 42. This candidate must append through
        # both old 96 and 128 boundaries, with no media transfer.
        sp = V.T.STACK - 0x1000
        for count in range(197):
            cam.put(SCATTER + 8, frame + count * 4)
            self.put_field(cam, 'bulk_writer_frame', frame + count * 4)
            cam.put(sp + 20, VOLUME)
            cam.mu.reg_write(UC_ARM_REG_R11, SCATTER)
            cam.mu.reg_write(UC_ARM_REG_SP, sp)
            cam.mu.reg_write(UC_ARM_REG_LR, V.T.DONE)
            cam.mu.emu_start(0xc063f81d, 0, count=100000)
            if cam.error: raise cam.error
            self.assertEqual(cam.w(VOLUME + 0x4850), count + 1)
        self.assertEqual(cam.transfers, [])
        self.assertEqual(cam.w(VOLUME + 0x4a54), 1024, 'no write beyond original cookie array')
        cam.put(VOLUME + 0x4a58, 64 << 20)
        cam.call(0xc063f141, VOLUME)
        self.assertEqual(cam.transfers, [64 << 20])
        self.assertEqual(cam.cookies, [(frame + i * 4, 0) for i in range(197)])
        self.assertEqual(cam.w(VOLUME + 0x4850), 0)
        self.assertEqual(self.field(cam, 'slots.cookies[0].pending'), 0)
        self.assertEqual(self.field(cam, 'slots.cookies[0].volume'), 0)

    def test_native_byte_trigger_still_waits_for_64_mib(self):
        for total in ((64 << 20) - 512, 64 << 20):
            cam = self.boot(); self.prepare(cam)
            for offset, value in [(0x4834, CALLBACK), (0x4838, GET_ARENA),
                                  (0x4848, FREE_ARENA), (0x484c, 0x45722000),
                                  (0x4828, 64 << 20), (0x4a54, 1024),
                                  (0x4a58, total - 512)]: cam.put(VOLUME + offset, value)
            sp = V.T.STACK - 0x1000
            cam.put(sp + 20, VOLUME); cam.put(sp + 0x7c, 512)
            cam.mu.reg_write(UC_ARM_REG_SP, sp)
            cam.stop_at = 0xc063f7c4
            cam.mu.emu_start(0xc063f6c7, 0, count=100000)
            if cam.error: raise cam.error
            self.assertEqual(cam.r(UC_ARM_REG_PC), cam.stop_at)
            self.assertEqual(cam.transfers, [total] if total == 64 << 20 else [])

    def test_cookie_hooks_preserve_registers_flags_and_both_stack_alignments(self):
        cam = self.boot(); self.prepare(cam)
        cam.put(VOLUME + 0x4834, CALLBACK)
        self.put_field(cam, 'bulk_policy.enabled', 2)
        self.put_field(cam, 'bulk_policy.frame_limit', self.capacity)
        self.put_field(cam, 'bulk_writer_frame', 0x45750000)
        self.invoke(cam, 'fpl_card_bulk', VOLUME, 0x45750000, 0, cam.card_state)
        regs = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
                UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
                UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11,
                UC_ARM_REG_R12, UC_ARM_REG_LR]
        for delta in (0, 4):
            for site, end in [(0xc063f854, 0xc063f858), (0xc063f1b8, 0xc063f1bc)]:
                before = [0x12340000 + i for i in range(len(regs))]
                if site == 0xc063f854:
                    before[2], before[3], before[12] = 128 * 4, VOLUME + 0x4854, 0x45750000
                else:
                    before[4], before[5], before[10] = VOLUME, 128, VOLUME + 0x4854
                for r, v in zip(regs, before): cam.mu.reg_write(r, v)
                sp = V.T.STACK - 0x1000 - delta
                cam.mu.reg_write(UC_ARM_REG_SP, sp)
                cam.mu.reg_write(UC_ARM_REG_CPSR, (cam.r(UC_ARM_REG_CPSR) & 0x0fffffff) | 0xa0000000)
                cam.stop_at = end
                cam.mu.emu_start(site | 1, 0, count=100000)
                if cam.error: raise cam.error
                if site == 0xc063f1b8: before[0] = 0x45750000
                self.assertEqual([cam.r(r) for r in regs], before)
                self.assertEqual(cam.r(UC_ARM_REG_SP), sp)
                self.assertEqual(cam.r(UC_ARM_REG_CPSR) & 0xf0000000, 0xa0000000)
                # Last completion released the binding; bind before next run.
                cam.stop_at = None
                self.invoke(cam, 'fpl_card_bulk', VOLUME, 0x45750000, 0, cam.card_state)

    def test_mutation_original_cookie_store_corrupts_next_native_field(self):
        cam = self.boot(); self.prepare(cam)
        cam.put(VOLUME + 0x4a54, 1024)
        cam.put(0xc063f854, self.sites[0xc063f854][0])
        cam.mu.ctl_remove_cache(0xc063f850, 0xc063f860)
        cam.mu.reg_write(UC_ARM_REG_R2, 128 * 4)
        cam.mu.reg_write(UC_ARM_REG_R3, VOLUME + 0x4854)
        cam.mu.reg_write(UC_ARM_REG_R12, 0x45750000)
        cam.stop_at = 0xc063f858
        cam.mu.emu_start(0xc063f855, 0, count=1000)
        if cam.error: raise cam.error
        with self.assertRaises(AssertionError):
            self.assertEqual(cam.w(VOLUME + 0x4a54), 1024)
        self.assertEqual(cam.w(VOLUME + 0x4a54), 0x45750000)

    def test_busy_or_oversized_plan_retains_previous_capacity(self):
        cam = self.boot(); self.prepare(cam)
        cam.put(cam.reg + 4 + 200 * 4, 0x45750000)
        self.put_field(cam, 'rec.facts.seen.width', 3024)
        self.put_field(cam, 'rec.facts.seen.height', 2010)
        self.assertEqual(self.invoke(cam, 'fpl_card_slots_prepare', cam.card_state), 0)
        self.assertEqual(self.field(cam, 'slots.plan.slots'), 236)
        self.assertEqual(self.field(cam, 'slots.active'), 236)
        self.assertEqual(self.field(cam, 'slots.refused'), 1)
        cam.put(cam.reg + 4 + 200 * 4, 0)
        self.put_field(cam, 'rec.facts.seen.width', 320)
        self.put_field(cam, 'rec.facts.seen.height', 240)
        self.assertEqual(self.invoke(cam, 'fpl_card_slots_prepare', cam.card_state), 1)
        self.assertEqual(self.field(cam, 'slots.active'), 1016)

    def test_loading_during_native_pool_use_refuses_without_patches(self):
        cam = SlotCamera(*V.T.card(('10LOSS.BIN', self.sup)))
        cam.put(OLD_POOL + 0x112c, 95)
        cam.boot()
        for _ in range(4):
            if cam.r(UC_ARM_REG_PC) == V.T.DONE: break
            pc = cam.r(UC_ARM_REG_PC) | ((cam.r(UC_ARM_REG_CPSR) >> 5) & 1)
            cam.mu.emu_start(pc, V.T.DONE, count=20000000)
            if cam.error: raise cam.error
        self.assertEqual(cam.r(UC_ARM_REG_PC), V.T.DONE)
        self.assertIn('10LOSS.BIN', [name for kind, _, _, name in cam.log() if kind == 'RELEASED'])
        self.assertFalse(cam.tasks)
        for a, (word, _) in self.sites.items(): self.assertEqual(cam.w(a), word, hex(a))
        self.assertEqual(cam.w(OLD_POOL + 0x112c), 95)

    def test_claims_restore_every_added_word(self):
        cam = self.boot(); self.prepare(cam)
        self.assertEqual(len(cam.journal()), len(self.sites))
        cam.runtime = False
        cam.power_off()
        for a, (word, _) in self.sites.items(): self.assertEqual(cam.w(a), word, hex(a))

    def scan_reads(self, cam, function):
        # Count registry-table reads only; a global MEM_READ hook perturbs
        # Unicorn's Thumb IT handling (20261012-early-dng-handoff).
        reads = []
        table = cam.reg + 4
        h = cam.mu.hook_add(UC_HOOK_MEM_READ, lambda mu, access, a, size, value, d: reads.append(a),
                            begin=table, end=table + self.capacity * 4 - 1)
        try: cam.call(function, cam.reg)
        finally: cam.mu.hook_del(h)
        return len(set(reads)), max(reads) - table if reads else -1

    def test_registry_scans_stop_at_the_active_count(self):
        # FUN_c0375900 / C0375BE0 / C0375DE8: full-table state scans under
        # the registry lock. They must touch n entries, not FPL_SLOT_MAX.
        for (w, h, fps), n in [((1936, 1090, 60), 236), ((1008, 672, 240), 572),
                               ((3024, 2010, 30), 96)]:
            cam = self.boot(); self.assertEqual(self.prepare(cam, w, h, fps), n)
            for function in (0xc0375900, 0xc0375be0, 0xc0375de8):
                self.assertEqual(self.scan_reads(cam, function), (n, (n - 1) * 4), hex(function))
            for a in ENDS:
                want = self.sites[a][0] if n == 96 else (self.sites[a][0] & ~0xfff) | 0xe00 | (n >> 2)
                self.assertEqual(cam.w(a), want, hex(a))

    def test_mutation_full_table_scan_end_reads_past_active(self):
        cam = self.boot(); self.assertEqual(self.prepare(cam), 236)
        a = 0xc0375920                      # FUN_c0375900's end
        cam.put(a, (self.sites[a][0] & ~0xfff) | 0xefe)   # the old fixed #0xFE0
        cam.mu.ctl_remove_cache(0xc0375900, 0xc0375a68)
        self.assertEqual(self.scan_reads(cam, 0xc0375900), (self.capacity, (self.capacity - 1) * 4))

    def test_mutation_stock_lookup_bound_cannot_find_slot_200(self):
        cam = self.boot(); self.prepare(cam)
        cam.put(cam.reg + 4 + 200 * 4, 0x45750000)
        self.assertEqual(cam.call(0xc03753c0, cam.reg, 200)[0], 0x45750000)
        cam.put(0xc03753cc, self.sites[0xc03753cc][0])
        cam.mu.ctl_remove_cache(0xc03753c0, 0xc0375400)
        with self.assertRaises(AssertionError):
            self.assertEqual(cam.call(0xc03753c0, cam.reg, 200)[0], 0x45750000)

    def writer_complete(self, cam, active, ident):
        """Runs the patched C037DF40(creator, ident) with the writer's active
        id `active`; returns (released nodes, re-dispatch calls, r0)."""
        from unicorn import UC_HOOK_CODE
        creator, vtable, v3 = V.T.HEAP + 0x1000, V.T.HEAP + 0x1100, V.T.HEAP + 0x1200
        cam.put(creator, vtable); cam.put(creator + 0x1c, active & 0xffffffff)
        cam.put(vtable + 0x14, v3)
        released, dispatched = [], []
        def hook(mu, address, size, data):
            if address == 0xc037e008:
                released.append((mu.reg_read(UC_ARM_REG_R0), mu.reg_read(UC_ARM_REG_R1)))
            elif address == v3:
                dispatched.append(mu.reg_read(UC_ARM_REG_R0)); mu.reg_write(UC_ARM_REG_R0, 7)
            else:
                return
            mu.reg_write(UC_ARM_REG_PC, mu.reg_read(UC_ARM_REG_LR))
        cam.allow = {v3, 0xc037e008}
        stub = cam.stubs.pop(0xc037e008)     # this hook records, then returns
        h1 = cam.mu.hook_add(UC_HOOK_CODE, hook, begin=0xc037e008, end=0xc037e008)
        h2 = cam.mu.hook_add(UC_HOOK_CODE, hook, begin=v3, end=v3)
        try:
            r0 = cam.call(0xc037df40, creator, ident & 0xffffffff, sp=V.T.STACK - 0x1000)[0]
        finally:
            cam.mu.hook_del(h1); cam.mu.hook_del(h2)
            cam.stubs[0xc037e008] = stub
        return released, dispatched, r0

    def test_writer_completion_redispatches_only_for_its_active_frame(self):
        # slot_sites.json 'writer_guard'. Camera 2026-10-13: stock re-dispatched
        # on event 8 AND 9; under a backlog the 128 writer tickets ran out and
        # 99 frames were left in 0xB, the stop never finishing.
        cam = self.boot(); self.prepare(cam)
        node = 0x45750000
        cam.put(cam.reg + 4 + 200 * 4, node)
        creator = V.T.HEAP + 0x1000
        # another frame is active: release only, no second writer message
        self.assertEqual(self.writer_complete(cam, 201, 200), ([(creator, node)], [], 1))
        # the active frame itself, or an idle writer: stock path
        self.assertEqual(self.writer_complete(cam, 200, 200), ([(creator, node)], [creator], 7))
        self.assertEqual(self.writer_complete(cam, -1, 200), ([(creator, node)], [creator], 7))
        # event 8 (id -1) always moves the writer on
        self.assertEqual(self.writer_complete(cam, 201, -1), ([], [creator], 7))

    def test_mutation_stock_writer_completion_dispatches_twice(self):
        cam = self.boot(); self.prepare(cam)
        cam.put(cam.reg + 4 + 200 * 4, 0x45750000)
        for a in range(0xc037df50, 0xc037df8c, 4): cam.put(a, self.sites[a][0])
        cam.mu.ctl_remove_cache(0xc037df40, 0xc037e008)
        released, dispatched, _ = self.writer_complete(cam, 201, 200)
        self.assertEqual(len(dispatched), 1, 'stock re-dispatches for a frame that is not active')

    def test_high_id_parent_released_only_after_last_child(self):
        cam = self.boot(); n = self.prepare(cam)
        frames = [cam.call(0xc0380ae0, cam.pool, 0x111c)[0] for _ in range(3)]
        for ident, f in zip((200, 201, 202), frames):
            cam.put(cam.reg + 4 + ident * 4, f)
            cam.put(f + 0x10fc, ident)
            cam.put(f + 0x1118, 0xffffffff if ident == 200 else 200)
        cam.put(frames[0] + 0x1110, 2)
        cam.put(cam.reg + 4 + self.capacity * 4 + 8, 3)
        cam.call(0xc0375030, cam.reg, 201)
        self.assertEqual(cam.call(0xc03753c0, cam.reg, 200)[0], frames[0])
        self.assertEqual(cam.w(frames[0] + 0x1110), 1)
        cam.call(0xc0375030, cam.reg, 202)
        self.assertEqual(cam.call(0xc03739c0)[0], n)
        self.assertEqual(cam.released, [frames[1], frames[2], frames[0]])


if __name__ == '__main__': unittest.main()
