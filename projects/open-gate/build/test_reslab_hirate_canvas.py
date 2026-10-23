"""239.76/279.72: the calculator's own RCD must give the record-tap canvas.

Reference: the archived Sensor Lab r10 card's complete 65-word M12 240 canvas
(executed offline from its exact BIN; the user's 10/01 sustained 240p), and
the firmware's own CRCT route selector. 8/10/12-bit must agree. 120p keeps r78.
"""
import json, struct, unittest
import test_virtual_rcd as V
from test_reslab_preview_route import native_route, OFFSETS

ROOT = V.HERE.parents[2]
R10 = json.loads((ROOT/'projects/res-lab/validation/20261011-virtual-rate-context-live/'
                  'sensorlab-r10-exact-reference.json').read_text())
_R = next(c for c in R10['cases'] if c['rate240'] == 1)['canvas']
R10_240 = [_R[hex(4*i)] for i in range(65)]
PROFILES = json.loads((ROOT/'research/other/external/FP3K-technical-handoff-2026-09-10/'
                       'analysis/firmware/raw-profiles.json').read_text())
P83 = next(r['words'] for r in PROFILES['rows'] if 83 in r['profile_ids'])
# Owned by the entry/bit latch, not by geometry: engine FPS, preview/RAW planes.
LATCHED = {0x30, 0x80, 0x84}

class HighRateCanvas(unittest.TestCase):
    def canvas(self, cam, rank, table):
        cam.put(cam.s()+V.L.S['VRATE'], rank)
        cam.mu.mem_write(V.RC.KEYBUF, b'VRC000120\0'.ljust(16, b'\0'))
        hit, _ = cam.call(V.RC.PICKER, r1=table, r2=V.RC.KEYBUF)
        self.assertNotEqual(hit, 0)
        native = V.RC.CANVAS_IN+0x5c
        cam.mu.mem_write(native, struct.pack('<65I', *P83))
        fn = cam.w(cam.s()+V.L.S['FN']+V.L.FNS.index('CANVAS')*4)
        self.assertEqual(cam.call(fn, cam.s(), native, cam.w(hit+4), thumb=True, sp=V.T.STACK-0x1000)[0], 1)
        return list(struct.unpack('<65I', cam.mu.mem_read(native, 260)))

    def test_m12_high_rates_equal_r10_for_every_depth_and_route_record_tap(self):
        out, f = V.built(); t = V.VirtualTests('test_contract_abi_and_status'); t.out, t.f = out, f
        cam = t.boot(fr=7); cam.geometry(12, 992, 662); self.assertEqual(cam.apply(), 0)
        low = self.canvas(cam, 0, V.RC.TAB3)
        for rank in (23976, 27972):
            for name, table in (('12', V.RC.TAB3), ('10', V.RC.TAB2), ('8', V.RC.TAB1)):
                with self.subTest(rank=rank, bit=name):
                    got = self.canvas(cam, rank, table)
                    diff = {hex(4*i): (got[i], R10_240[i]) for i in range(65)
                            if 4*i not in LATCHED and got[i] != R10_240[i]}
                    self.assertEqual(diff, {}, 'differs from archived r10 240 canvas')
                    route = native_route(cam, {o: got[o//4] for o in range(0, 260, 4)})
                    self.assertEqual((route['enabled'], route['mux'], route['record']), ([0, 1, 0], [1, 4], 0))
                    self.assertEqual(route['main_zoom'], [2048, 1024])
        # 119.88 is untouched: still the r78 separate-preview route.
        route = native_route(cam, {o: low[o//4] for o in range(0, 260, 4)})
        self.assertEqual((route['enabled'], route['mux'], route['record']), ([0, 0, 1], [1, 3], 1))
        self.assertEqual(low[0x0C//4], 2000)

if __name__ == '__main__':
    unittest.main()


class SavedFileCanvas(unittest.TestCase):
    """The deployed HS280-hirate.RCD through the real consumer: same r10 canvas."""
    boot = V.VirtualTests.boot
    canvas = HighRateCanvas.canvas

    def test_hs280_file_10bit_and_12bit_240_equal_r10(self):
        self.out, self.f = V.built()
        blob = (ROOT/'projects/res-lab/validation/20261014-unified-hirate/HS280-hirate.RCD').read_bytes()
        record = V.RC.CoreTests.record(self, 'HS280', enable=('HS280',))
        cam = self.boot(fr=3, record=record, rcds={'HS280.RCD': blob})
        for table in (V.RC.TAB2, V.RC.TAB3):
            cam.put(cam.s()+V.L.S['VRATE'], 23976)
            cam.mu.mem_write(V.RC.KEYBUF, b'HS280120\0'.ljust(16, b'\0'))
            hit, _ = cam.call(V.RC.PICKER, r1=table, r2=V.RC.KEYBUF)
            self.assertNotEqual(hit, 0)
            e = cam.s()+cam.w(cam.s()+V.L.S['LAST_ENT'])
            if cam.w(e+V.L.ENT['VRATE']) != 23976: continue
            native = V.RC.CANVAS_IN+0x5c
            cam.mu.mem_write(native, struct.pack('<65I', *P83))
            fn = cam.w(cam.s()+V.L.S['FN']+V.L.FNS.index('CANVAS')*4)
            self.assertEqual(cam.call(fn, cam.s(), native, cam.w(hit+4), thumb=True, sp=V.T.STACK-0x1000)[0], 1)
            got = list(struct.unpack('<65I', cam.mu.mem_read(native, 260)))
            diff = {hex(4*i): (got[i], R10_240[i]) for i in range(65) if 4*i not in LATCHED and got[i] != R10_240[i]}
            self.assertEqual(diff, {})
            self.checked = getattr(self, 'checked', 0) + 1
        self.assertEqual(getattr(self, 'checked', 0), 2)
