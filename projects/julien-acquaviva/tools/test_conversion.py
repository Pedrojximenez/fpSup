"""Whole catalogue checks, and exact-byte core/virtual sensor execution."""
from pathlib import Path
import json
import struct
import sys
import unittest

from extract_r168 import PROJECT, ROOT, RC, IMAGE, Planner, sections, rows, TABLES, PIN, sha
sys.path.insert(0, str(RC))
import rcd
import ogc_layout as L
import test_v3_rescustom as C

OUT = PROJECT / 'build/r168-rescustom'


class ConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads((PROJECT / 'extracted/r168.json').read_text())
        cls.index = json.loads((OUT / 'index.json').read_text())
        cls.img = IMAGE.read_bytes()
        cls.ids = {struct.unpack_from('<I', cls.img, 0xB59500 + i * 32)[0] for i in range(70)}

        # Keep the existing harness' tests separate; borrow its actual loader,
        # native readers, hooks and register writer for the exact built artifact.
        class Harness(C.ProgrammingTests):
            pass
        Harness.img = cls.img
        Harness.stock_ids = cls.ids
        Harness.core = (OUT / '32RESCUS.BIN').read_bytes()
        Harness.f = json.loads((OUT / 'core-build/build.json').read_text())['files']['32RESCUS.BIN']['facts']
        Harness.rcds = {p.name: p.read_bytes() for p in (OUT / 'RESCUS').glob('*.RCD')}
        Harness.all_rcds = Harness.rcds
        Harness.rows = Harness.decoded(Harness.rcds)
        cls.h = Harness('runTest')

    def choose(self, cam, row):
        self.h.commit(cam, self.h.row(cam, row, L.ROW['MROW']))
        cam.call(C.SETTER, r0=0, r1=3, r2=1)

    def ratio(self, cam, enum):
        from unicorn.arm_const import UC_ARM_REG_R7, UC_ARM_REG_SP
        cam.mu.reg_write(UC_ARM_REG_R7, 0x789A)
        out = cam.callr(0xC02DAFA0, r0=enum, r1=0x1234, r2=0x2345, r3=0x3456,
                        r4=0x4567, r5=0x5678, r6=0x6789, fp=0xABCD, sp=C.T.STACK - 0x1000)
        out['r7'] = cam.mu.reg_read(UC_ARM_REG_R7)
        out['sp'] = cam.mu.reg_read(UC_ARM_REG_SP)
        return out

    def test_all_public_states_execute_in_the_upstream_planner(self):
        planner = Planner()
        states, modes = planner.extract()
        self.assertEqual(states, self.doc['states'])
        # JSON changes tuples to lists; compare its stable serialized form.
        self.assertEqual(json.loads(json.dumps(modes)), self.doc['modes'])
        self.assertEqual(len(states), 1552)
        self.assertEqual(len(rows(states, modes)), 984)
        self.assertGreater(planner.stub_calls, 0)

    def test_every_rcd_preserves_its_sources_record_canvas_and_sensor_overrides(self):
        self.assertEqual(len(self.index['formats']), 984)
        by = {f['row']['label']: f for f in self.doc['formats']}
        for info in self.index['formats']:
            data = (OUT / info['path']).read_bytes()
            self.assertEqual(sha(data), info['sha256'])
            actual = rcd.decode(data, self.img, self.ids)
            wanted = by[info['label']]
            self.assertEqual(actual['canvas_rec'], [tuple(x) for x in wanted['row']['canvas_rec']])
            self.assertEqual(actual['overrides'], [tuple(x) for x in wanted['row']['overrides']])
            for si in wanted['states']:
                state = self.doc['states'][si]
                self.assertEqual(actual['act'], tuple(state['output']))
                canvas = dict(actual['canvas_rec'])
                for i, value in enumerate(state['canvas'][:66]):
                    if i * 4 not in (0x30, 0x80, 0x84):
                        self.assertEqual(canvas[i * 4], value, info['label'])
                entry = next(e for e in actual['entries'] if e['rank'] == L.RATES[state['fps_index']][7])
                hmax, tail, vmax = entry['w0'] & 65535, entry['w0'] >> 16, entry['w1'] & 65535
                self.assertEqual(hmax * (vmax - 1) + tail, L.RATES[state['fps_index']][3])
                self.assertGreaterEqual(tail, L.MIN_TAIL)
                self.assertGreater(vmax, state['canvas'][0xF8 // 4])

    def test_host_formula_matches_every_binary_output_without_firmware_execution(self):
        from planner import plan
        for state in self.doc['states']:
            got = plan(state['media'], state['ratio'], state['crop'], state['fps'])
            self.assertEqual(got['output'], state['output'])
            self.assertEqual(got['rwzm_raw'], state['rwzm_raw'])
            self.assertEqual(got['one'], state['one'])
        for media, ratio, crop, fps in (('SSD', '3:2', 1.05, 24), ('SSD', '3:2', 1, 100),
                                        ('v30', '3:2', 1, 240), ('SSD', '4:3', 1, 24)):
            with self.assertRaises(ValueError):
                plan(media, ratio, crop, fps)

    def test_six_selected_formats_load_and_record_the_expected_canvas(self):
        h = self.h
        cam = h.boot(res=3)
        self.assertEqual(h.S(cam, L.S['NROWS']), 6)
        for i, row in enumerate(h.rows):
            self.choose(cam, i)
            entry = h.pick(cam, row['label'] + '24')
            self.assertNotEqual(entry, 0)
            pid = cam.w(entry + 4)
            canvas = h.canvas(cam, pid)
            wanted = dict(row['canvas_rec'])
            wanted.update({0x30: L._f32(24), 0x80: 7, 0x84: 7})
            for off, value in wanted.items():
                self.assertEqual(struct.unpack_from('<I', canvas, off)[0], value, row['label'])
            self.assertEqual(h.S(cam, L.S['ASPECT']), row['aspect'])
        # The original mode tables remain untouched, even with our overrides.
        for base, stride in TABLES:
            self.assertEqual(bytes(cam.mu.mem_read(base, stride * 70)), h.stock(base, stride * 70))

    def test_2to1_ratio_is_owned_bounded_and_preserves_the_callers_registers(self):
        h, cam = self.h, self.h.boot(res=3)
        i = next(i for i, row in enumerate(h.rows) if row['aspect'] == 9)
        self.choose(cam, i)
        h.pick(cam, h.rows[i]['label'] + '24')
        out = self.ratio(cam, 9)
        self.assertEqual(struct.unpack('<2I', cam.mu.mem_read(out['r0'], 8)), (2, 1))
        for reg, value in dict(r1=0x1234, r2=0x2345, r3=0x3456, r4=0x4567,
                               r5=0x5678, r6=0x6789, r7=0x789A, fp=0xABCD).items():
            self.assertEqual(out[reg], value)
        self.assertEqual(out['sp'], C.T.STACK - 0x1000)
        # Real stock getter for every stock aspect; no settings stub for it.
        for enum in range(1, 9):
            got = self.ratio(cam, enum)['r0']
            self.assertEqual(bytes(cam.mu.mem_read(got, 8)), h.stock(0xC0B4CAB8 + enum * 8, 8))
        # A declared lower-layer sentinel lets an unowned invalid enum prove
        # passthrough without running Sigma's intentional assert loop.
        stub = C.KEYBUF + 0x700
        cam.mu.mem_write(stub, struct.pack('<2I', 0xE3A0004E, 0xE12FFF1E))
        cam.put(cam.S + L.S['NEXT'] + 4 * L.HOOK_INDEX['ratio'], stub)
        cam.call(C.FMTSET, r0=0, r1=C.MOV, r2=1)
        for playback in (0, len(h.rows) + 1, 0xFFFFFFFF):
            cam.put(cam.S + L.S['PBROW'], playback)
            self.assertEqual(self.ratio(cam, 9)['r0'], 78)
        # Recognized 2:1 playback through the real name hook, independently
        # of a live format, followed by the playback canvas hook.
        sizes = C.KEYBUF + 0x100
        cam.put(sizes + 8, h.rows[i]['act'][0])
        cam.put(sizes + 12, h.rows[i]['act'][1])
        cam.call(0xC0437B48, r0=0, r1=C.KEYBUF + 0x200, r2=sizes)
        self.assertEqual(h.S(cam, L.S['PBROW']), i + 1)
        cam.mu.mem_write(C.CANVAS_IN, bytes([0x11]) * 0x200)
        cam.put(C.CANVAS_IN + 0x5C + 0x80, 0x10007)
        cam.callr(h.shim_base(cam) + h.f['shims']['canvas'], r4=C.CANVAS_IN, r5=51)
        for off, value in h.rows[i]['canvas_pb']:
            self.assertEqual(cam.w(C.CANVAS_IN + 0x5C + off), value)
        got = self.ratio(cam, 9)['r0']
        self.assertEqual(struct.unpack('<2I', cam.mu.mem_read(got, 8)), (2, 1))

    def test_ratio_guard_and_pair_mutations_are_detected(self):
        from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
        h, cam = self.h, self.h.boot(res=3)
        i = next(i for i, row in enumerate(h.rows) if row['aspect'] == 9)
        self.choose(cam, i)
        h.pick(cam, h.rows[i]['label'] + '24')
        pair = self.ratio(cam, 9)['r0']
        original = bytes(cam.mu.mem_read(pair, 8))
        cam.mu.mem_write(pair, struct.pack('<2I', 16, 9))
        with self.assertRaises(AssertionError):
            self.assertEqual(struct.unpack('<2I', cam.mu.mem_read(self.ratio(cam, 9)['r0'], 8)), (2, 1))
        cam.mu.mem_write(pair, original)
        shim = h.shim_base(cam) + h.f['shims']['ratio']
        success = next(i.address for i in Cs(CS_ARCH_ARM, CS_MODE_ARM).disasm(
            bytes(cam.mu.mem_read(shim, 160)), shim) if i.mnemonic in ('add', 'sub') and i.op_str.startswith('r0, pc,'))
        guard = shim + 12                 # after cmp/bne and the preserved-register push
        old = bytes(cam.mu.mem_read(guard, 4))
        # Inject a branch that skips ownership checks into this emulator only.
        cam.put(guard, 0xEA000000 | ((success - guard - 8) // 4 & 0xFFFFFF))
        cam.mu.ctl_remove_cache(shim, shim + 160)
        cam.put(cam.S + L.S['ASPECT'], 0)
        cam.put(cam.S + L.S['PBROW'], 0)
        stub = C.KEYBUF + 0x700
        cam.mu.mem_write(stub, struct.pack('<2I', 0xE3A0004E, 0xE12FFF1E))
        cam.put(cam.S + L.S['NEXT'] + 4 * L.HOOK_INDEX['ratio'], stub)
        with self.assertRaises(AssertionError):
            self.assertEqual(self.ratio(cam, 9)['r0'], 78)
        cam.mu.mem_write(guard, old)
        cam.mu.ctl_remove_cache(shim, shim + 160)
        self.assertEqual(self.ratio(cam, 9)['r0'], 78)

    def test_2to1_cannot_claim_compatibility_with_core_v1(self):
        data = next(p.read_bytes() for p in (OUT / 'RESCUS').glob('*.RCD')
                    if rcd.decode(p.read_bytes())['aspect'] == 9)
        self.assertEqual(struct.unpack_from('<I', data, L.RCD['MINCORE'])[0], 2)
        bad = bytearray(data)
        struct.pack_into('<I', bad, L.RCD['MINCORE'], 1)
        with self.assertRaises(rcd.RcdError):
            rcd.decode(rcd.reseal(bad))
        h = self.h
        cam = h.boot(rcds={**h.rcds, 'ZZ.RCD': rcd.reseal(bad)}, res=3)
        self.assertEqual(h.S(cam, L.S['RCD_OK']), 6)
        self.assertEqual(h.S(cam, L.S['RCD_BAD']), 1 << 6)
        self.assertEqual(bytes(cam.mu.mem_read(cam.S + L.S['RCD_WHYS'] + 6, 1))[0], L.RCD_WHY['FIELD'])

    def test_all_six_donors_program_the_same_registers_as_the_upstream_overlay(self):
        h = self.h
        formats = self.doc['formats']
        for fps_index in (1, 4, 5, 6, 7, 8):
            si, state = next((i, s) for i, s in enumerate(self.doc['states']) if
                             s['media_index'] == 0 and s['fps_index'] == fps_index)
            info = next(f for f in formats if si in f['states'])
            lab, donor = info['row']['label'], state['donor']
            f = next(x for x in self.index['formats'] if x['label'] == lab)
            ours = h.boot(rcds={lab + '.RCD': (OUT / f['path']).read_bytes()}, res=3)
            self.choose(ours, 0)
            e = h.pick(ours, lab + L.RATES[fps_index][1])
            vid = ours.w(e + 8)
            reference = h.boot(rcds=None, res=3)
            for _, kind, off, value in info['row']['overrides']:
                if kind == 7:
                    idx = reference.modes.index(donor)
                    reference.put(0xC0B5B918 + idx * 8, value)
                else:
                    base, stride = TABLES[kind]
                    reference.put(base + reference.modes.index(donor) * stride + off, value)
            reference.mu.mem_write(TABLES[0][0] + reference.modes.index(donor) * 32 + 4,
                                   struct.pack('<2I', ours.w(e + L.ENT['W0']), ours.w(e + L.ENT['W1'])))
            # Materialize clones before the register-writer's observation hooks
            # (the existing harness documents Unicorn's dropped-store quirk).
            for cam, mode in ((ours, vid), (reference, donor)):
                cam.put(L.IMAGER + 4, mode)
                cam.callr(0xC0321290, r0=L.IMAGER, r1=mode)
            h.assertSameProgramming(h.programming(ours, vid, donor), h.programming(reference, donor, donor), lab)
            for base, stride in TABLES:
                self.assertEqual(bytes(ours.mu.mem_read(base, stride * 70)), h.stock(base, stride * 70))


if __name__ == '__main__':
    unittest.main()
