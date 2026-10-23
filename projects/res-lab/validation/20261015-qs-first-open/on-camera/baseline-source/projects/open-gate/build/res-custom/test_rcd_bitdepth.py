"""RCD-owned depth policy: real consumer/loader ARM, modeled native UI boundaries.

The two native bit CSVs are checked independently of the consumer's state flags.
No camera, recording device or card is accessed.
"""
import struct
import unittest

import test_v3_rescustom as C
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R7, UC_ARM_REG_SP

L, rcd, T = C.L, C.rcd, C.T
CLASS_SITE, NORM_SITE = 0xC04A13E4, 0xC00A7FFC
ENUM = {8: 4, 10: 3, 12: 0}


class BitPolicyTests(unittest.TestCase):
    setUpClass = classmethod(C.CoreTests.setUpClass.__func__)
    # Reuse the maintained loader/consumer fixture without inheriting its tests.
    decoded = classmethod(C.CoreTests.decoded.__func__)
    for _helper in ('stock', 'sw', 'record', 'core_with', 'boot', 'outcome',
                    's_addr', 'S', 'rowa', 'row', 'go', 'commit', 'pick', 'canvas', 'shim_base', 'variant'):
        locals()[_helper] = getattr(C.CoreTests, _helper)

    def pick(self, cam, key, bd=0):
        return C.CoreTests.pick(self, cam, key, table={4: C.TAB1, 3: C.TAB2, 0: C.TAB3}[bd])

    def bit_csvs(self, cam):
        copies = {a: (p, n) for a, p, n in cam.fv}
        return [[','.join(line.split(',')[-2:]) for line in
                 bytes(cam.mu.mem_read(*copies[a])).decode('utf-8-sig').splitlines()[1:]]
                for a, _, _ in rcd.BIT_CSV]

    def bit_class(self, cam, stock):
        frame = C.KEYBUF + 0x1800
        cam.mu.mem_write(frame, struct.pack('<2I', 0x44444444, T.DONE))
        out = cam.callr(CLASS_SITE, r1=stock, r2=0x22222222, r3=0x33333333,
                        r5=0x55555555, r6=0x66666666, sp=frame)
        self.assertEqual(out['r4'], 0x44444444)
        self.assertEqual((out['r2'], out['r3'], out['r5'], out['r6']),
                         (0x22222222, 0x33333333, 0x55555555, 0x66666666))
        self.assertEqual(out['r1'], out['r0'])                 # adjusted class, replayed mov r0,r1
        self.assertEqual(cam.r(UC_ARM_REG_SP), frame + 8)
        return out['r0']

    def bit_norm(self, cam, requested, stock):
        # Real native v8 join: its sub sp,#4 plus eight saved callee registers.
        frame = C.KEYBUF + 0x1804
        cam.mu.mem_write(frame, struct.pack('<9I', 0xAAAAAAAA, 4, 5, 6, 7, 8, 10, 11, T.DONE))
        cam.mu.reg_write(UC_ARM_REG_R7, requested)
        out = cam.callr(NORM_SITE, r1=0x11111111, r2=0x22222222, r3=stock, sp=frame)
        self.assertEqual((out['r4'], out['r5'], out['r6'], out['fp']), (4, 5, 6, 11))
        self.assertEqual(cam.r(UC_ARM_REG_R7), 7)
        self.assertEqual(cam.r(UC_ARM_REG_SP), frame + 36)
        return out['r0']

    def test_each_rcd_controls_both_media_and_both_native_csv_variants(self):
        masks = ((8,), (10,), (12,), (8, 10), (8, 12), (10, 12))
        files = {f'D{i}.RCD': self.variant('OG3K.RCD', label=f'D{i}', enum=100+i,
                                          bit_depths=depths) for i, depths in enumerate(masks)}
        cam = self.boot(rcds=files)
        rows = self.decoded(files)
        original = [['1,2'] * 3, ['1,2', '0,0', '0,0']]
        self.assertEqual(self.bit_csvs(cam), original)
        # Catch a shim that calls C on a 4-byte-only aligned stack.
        fn = cam.w(cam.S + L.S['FN'] + 4*L.FNS.index('BIT')) & ~1
        alignment = []
        cam.mu.hook_add(UC_HOOK_CODE, lambda mu, a, n, d: alignment.append(cam.r(UC_ARM_REG_SP) & 7),
                        begin=fn, end=fn)
        for i, depths in enumerate(masks):
            self.go(cam, rows, f'D{i}')
            want = ['1,2' if depth in depths else '0,0' for depth in L.BIT_DEPTHS]
            self.assertEqual(self.bit_csvs(cam), [want, want])
            self.assertEqual(self.row(cam, i, L.ROW['BITMASK']),
                             sum(1 << L.BIT_DEPTHS.index(d) for d in depths))
            for native_class in (1, 0):                       # SD, SSD
                self.assertEqual(self.bit_class(cam, native_class), 0)
                for depth in L.BIT_DEPTHS:
                    request = ENUM[depth]
                    native = 4 if native_class else request
                    self.assertEqual(self.bit_norm(cam, request, native),
                                     request if depth in depths else ENUM[depths[0]])
                    self.assertEqual(bool(self.pick(cam, f'D{i}24', bd=request)), depth in depths)
        self.assertTrue(alignment)
        self.assertEqual(set(alignment), {0})
        cam.call(C.FMTSET, r1=C.MOV, r2=1)
        self.assertEqual(self.bit_csvs(cam), original)
        self.assertEqual(self.bit_class(cam, 1), 1)
        self.assertEqual(self.bit_norm(cam, 0, 4), 4)
        self.go(cam, rows, 'D2')
        self.commit(cam, 0)
        cam.call(C.SETTER, r1=3, r2=1)
        self.assertEqual(self.bit_csvs(cam), original)
        self.assertEqual(self.bit_class(cam, 1), 1)
        for a, n, _ in rcd.BIT_CSV:
            self.assertEqual(bytes(cam.mu.mem_read(a, n)), self.stock(a, n))
        cam.power_off()
        for site in (CLASS_SITE, NORM_SITE, C.FV_SITE):
            self.assertEqual(bytes(cam.mu.mem_read(site, 4)), self.stock(site))
        self.assertEqual(cam.misaligned, [])

    def test_built_formats_declare_all_depths_and_uhd_keys_preserve_them(self):
        cam = self.boot(rcds=self.all_rcds)
        rows = self.decoded(self.all_rcds)
        hits = 0
        for row, data in zip(rows, (self.all_rcds[name] for name in sorted(self.all_rcds))):
            self.assertEqual(row['bit_depths'], (8, 10, 12))
            self.assertGreaterEqual(struct.unpack_from('<I', data, L.RCD['MINCORE'])[0], 4)
        for label in ('OG35K', 'OG4K'):
            self.go(cam, rows, label)
            self.assertEqual(self.bit_csvs(cam), [['1,2'] * 3] * 2)
            for native_class in (1, 0):
                self.assertEqual(self.bit_class(cam, native_class), 0)
                for depth, enum in ENUM.items():
                    self.assertEqual(self.bit_norm(cam, enum, 4 if native_class else enum), enum)
                    for entry in next(r for r in rows if r['label'] == label)['entries']:
                        if entry['vrate']:
                            continue
                        hit = self.pick(cam, entry['key'], bd=enum)
                        self.assertNotEqual(hit, 0, (label, native_class, depth, entry['key']))
                        self.assertEqual(self.S(cam, L.S['BITLATCH']), enum)
                        canvas = self.canvas(cam, cam.w(hit + 4))
                        self.assertEqual(struct.unpack_from('<2I', canvas, 0x80),
                                         (7 if depth == 12 else 10, {8: 10, 10: 9, 12: 7}[depth]))
                        hits += 1
        self.assertEqual(hits, 96)                            # 48 key/depth pairs on each medium

    def test_legacy_rcd_keeps_native_policy(self):
        data = self.rcds['OG3K.RCD']
        row = rcd.decode(data, self.img, self.stock_ids)
        off, size = row['pack']
        del row['bit_depths']
        legacy = rcd.encode(row, data[off:off+size], mincore=3)
        cam = self.boot(rcds={'LEGACY.RCD': legacy}, vr=True)
        self.go(cam, self.decoded({'LEGACY.RCD': legacy}), 'OG3K')
        self.assertEqual(self.bit_csvs(cam), [['1,2'] * 3, ['1,2', '0,0', '0,0']])
        self.assertEqual(self.bit_class(cam, 1), 1)
        self.assertEqual(self.bit_norm(cam, 0, 4), 4)
        C.CoreTests.stub_gates(self, cam)
        self.assertEqual(C.CoreTests.gates(self, cam)['frmax'], {7: 6, 6: 6, 5: 5, 3: 3, 2: 2})

    def test_complete_native_quality_functions_for_sd_and_ssd(self):
        """Execute both original firmware functions, modeling only their getters.
        The request must travel through the native r7 path before our final join.
        """
        cam = self.boot(rcds=self.all_rcds)
        rows = self.decoded(self.all_rcds)
        obj, table, var, vtable = (C.KEYBUF + x for x in (0x2000, 0x2100, 0x2500, 0x2600))
        getter, value = T.DONE + 0x300, T.DONE + 0x320
        cam.put(0xC31CAA80, obj)
        cam.put(obj + 4, table)
        for off in (0x194, 0x1A0, 0x354):
            cam.put(table + off, getter)
        cam.put(var + 0xC, vtable)
        cam.put(vtable + 0x1C, value)
        cam.mu.mem_write(getter, struct.pack('<3I', 0xE59F0000, 0xE12FFF1E, var))
        cam.mu.mem_write(value, struct.pack('<2I', 0xE3A00000, 0xE12FFF1E))
        boundaries = {0xC0518410: 0, 0xC00913F8: 1, 0xC0068E38: 0,
                      0xC0068A38: 3, 0xC006D530: 1, 0xC04FBDF8: 0, 0xC00633B8: 0}
        def getters(ssd):
            for at, result in boundaries.items():
                if at in (0xC0518410, 0xC00633B8):
                    result = ssd
                cam.mu.mem_write(at, struct.pack('<2I', 0xE3A00000 | result, 0xE12FFF1E))
                cam.mu.ctl_remove_cache(at, at + 8)
        veneers = []
        for site in (CLASS_SITE, NORM_SITE):
            delta = cam.w(site) & 0xFFFFFF
            if delta & 0x800000:
                delta -= 0x1000000
            veneer = site + 8 + 4*delta
            veneers.append((veneer, veneer + 8))
        allowed = ((0xC00A7EE0, 0xC00A8008), (0xC04A13A0, 0xC04A13EC)) + tuple((a,a+8) for a in boundaries) + tuple(veneers)
        def strict(mu, at, n, data):
            if 0xC0000000 <= at < 0xC3000000 and not any(a <= at < b for a,b in allowed):
                cam.error = AssertionError(f'unmodeled quality firmware execution {at:#x}')
                mu.emu_stop()
        self.go(cam, rows, 'OG4K')
        hook = cam.mu.hook_add(UC_HOOK_CODE, strict)
        for ssd in (0, 1):
            getters(ssd)
            self.assertEqual(cam.callr(0xC04A13A0, r0=obj)['r0'], 0)
            for request in ENUM.values():
                self.assertEqual(cam.callr(0xC00A7EE0, r0=obj, r1=request)['r0'], request)
        cam.mu.hook_del(hook)
        self.commit(cam, 0)
        cam.call(C.SETTER, r1=3, r2=1)
        hook = cam.mu.hook_add(UC_HOOK_CODE, strict)
        for ssd in (0, 1):
            getters(ssd)
            self.assertEqual(cam.callr(0xC04A13A0, r0=obj)['r0'], 0 if ssd else 1)
            for request in ENUM.values():
                self.assertEqual(cam.callr(0xC00A7EE0, r0=obj, r1=request)['r0'], request if ssd else 4)
        cam.mu.hook_del(hook)

    def test_damaged_policy_is_rejected_by_both_validators(self):
        good = self.rcds['OG3K.RCD']
        sec, = [p for p in range(L.RCD_HDR, L.RCD_HDR + 16*struct.unpack_from('<I', good, L.RCD['NSEC'])[0], 16)
                if struct.unpack_from('<I', good, p)[0] == L.SEC_BITDEPTH]
        off = struct.unpack_from('<I', good, sec + 4)[0]
        cases = [(off, 0), (off, 8), (off, 0xFFFFFFFF), (sec+8, 8), (sec+12, 0), (L.RCD['MINCORE'], 3)]
        files = {}
        for i, (at, value) in enumerate(cases):
            damaged = bytearray(good)
            struct.pack_into('<I', damaged, at, value)
            damaged = rcd.reseal(damaged)
            with self.assertRaises(rcd.RcdError) as exc:
                rcd.decode(damaged, self.img, self.stock_ids)
            self.assertEqual(exc.exception.why, 'BITDEPTH')
            files[f'BAD{i}.RCD'] = damaged
        files['GOOD.RCD'] = good
        cam = self.boot(rcds=files)
        self.assertEqual(self.S(cam, L.S['RCD_OK']), 1)
        for i in range(len(cases)):
            self.assertEqual(cam.mu.mem_read(cam.S+L.S['RCD_WHYS']+i, 1)[0], L.RCD_WHY['BITDEPTH'])
        row = rcd.decode(good)
        pack = good[row['pack'][0]:sum(row['pack'])]
        for depths in ((), (14,), (8, 8)):
            with self.assertRaises(rcd.RcdError):
                rcd.encode(dict(row, bit_depths=depths), pack)

    def test_failed_bit_ui_install_rolls_back_consumer(self):
        cam = self.boot(uia_fail={'BIT'})
        self.assertEqual(self.outcome(cam, '32RESCUS.BIN'), 'RELEASED')
        for _, site, _ in L.HOOKS:
            self.assertEqual(bytes(cam.mu.mem_read(site, 4)), self.stock(site))

    def test_policy_assertions_detect_missing_native_hooks(self):
        cam = self.boot()
        self.go(cam, self.rows, 'OG3K')
        # Bounded mutations only in this emulator. Each change reproduces the
        # original SD restriction and must trip the independent behavior check.
        self.assertEqual(self.bit_class(cam, 1), 0)
        cam.mu.mem_write(CLASS_SITE, self.stock(CLASS_SITE))
        cam.mu.ctl_remove_cache(CLASS_SITE, CLASS_SITE + 4)
        with self.assertRaises(AssertionError):
            self.assertEqual(self.bit_class(cam, 1), 0)
        self.assertEqual(self.bit_norm(cam, 0, 4), 0)
        cam.mu.mem_write(NORM_SITE, self.stock(NORM_SITE))
        cam.mu.ctl_remove_cache(NORM_SITE, NORM_SITE + 4)
        with self.assertRaises(AssertionError):
            self.assertEqual(self.bit_norm(cam, 0, 4), 0)


if __name__ == '__main__':
    unittest.main()
