"""Exact v40 code with two owned entry data words set to 30 in emulation.

The real native publication, >99 gate and near-60 predicate execute. OS and
hardware configuration are stubbed; no DMA or picture validity is modeled.
"""
import hashlib
import os
import pathlib
import struct
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
NATIVE_CARRIER = int(os.environ.get('TEST_ENGINE30_CARRIER', '3'))
assert NATIVE_CARRIER in (3, 7)
CARD_NAME, EXPECTED_SHA = {
    3: ('20261011-m12-native30-v40', '4358fce4127aedebbff0b93ea9db91f0a2805ae4cc013552dabc2f43e31c99dc'),
    7: ('20261011-m12-engine60-v39', '650c6fa0f27d216adba551cbec777741d42b39f4374e8b76db0f71dfbfe1cb85'),
}[NATIVE_CARRIER]
CARD = ROOT/'projects/res-lab/cards'/CARD_NAME/'debug'
assert hashlib.sha256((CARD/'fpSup/32RESCUS.BIN').read_bytes()).hexdigest() == EXPECTED_SHA
os.environ['VIRTUAL_RCD_CARD'] = str(CARD)
sys.path.insert(0, str(ROOT/'projects/open-gate/build'))
import test_virtual_rcd as V
from test_reslab_preview_route import native_engine_gate


def near60_switch(cam):
    for start, end in ((0xc01cef08, 0xc01cf220), (0xc01d3558, 0xc01d3580),
                       (0xc01d49d0, 0xc01d49f0), (0xc01d10d0, 0xc01d10f8)):
        cam.mu.mem_write(start, cam.img[start-0xc0000000:end-0xc0000000])
        cam.test_code.update(range(start, end, 2))
    # Model a native state that goes directly to its configuration tail. All
    # sensor/hardware routines are explicit boundaries, rather than executed.
    for at, value in ((0xc01d6610, 0), (0xc01d3b10, 3), (0xc01d3888, 0),
                      (0xc0156b90, 0), (0xc0156ae0, 0), (0xc01a5f50, 0)):
        code = struct.pack('<HHI', 0x4800, 0x4770, value)
        cam.mu.mem_write(at, code)
        cam.by_addr.pop(at, None)
        cam.test_code.update(range(at, at+len(code), 2))
    # Its temporary local descriptor clears are outside the predicate; the
    # modeled descriptor consumers above do not inspect those local bytes.
    cam.mu.mem_write(0xc0015058, struct.pack('<2I', 0xe3a00000, 0xe12fff1e))
    cam.by_addr.pop(0xc0015058, None)
    cam.test_code.update((0xc0015058, 0xc001505c))
    cam.put(0xc31dfb78, 1)
    cam.put(0xc31df5e8, 1)
    cam.put(0xc2f16594, 0xff)
    param = V.RC.KEYBUF+0x3000
    cam.mu.mem_write(param, bytes(0x500))
    cam.call(0xc01cef08, r0=0, r1=param, thumb=True, sp=V.T.STACK-0x1000)
    return cam.w(0xc2f16594)


class Engine30(unittest.TestCase):
    def test_data_only_high_entries_and_native_switch(self):
        out, facts = V.built()
        fixture = V.VirtualTests('test_contract_abi_and_status')
        fixture.out, fixture.f = out, facts
        cam = fixture.boot(fr=NATIVE_CARRIER)
        cam.geometry(12, 992, 662)
        self.assertEqual(cam.apply(), 0)
        state = cam.s()
        start = cam.w(state+V.L.S['ENTS'])
        targets = {}
        row = cam.w(state+V.L.S['CUR'])-1
        for index in range(cam.w(state+V.L.S['NENT'])):
            entry = state+start+index*V.L.ENT['SIZE']
            rank = cam.w(entry+V.L.ENT['VRATE'])
            if cam.w(entry+V.L.ENT['ROW']) == row and rank in (23976, 27972):
                self.assertEqual(cam.w(entry+V.L.ENT['ENGFPS']), V.L._f32(60.0))
                targets[rank] = entry
        self.assertEqual(sorted(targets), [23976, 27972])
        profiles = __import__('json').loads((ROOT/'research/other/external/FP3K-technical-handoff-2026-09-10/analysis/firmware/raw-profiles.json').read_text())
        donor = next(r['words'] for r in profiles['rows'] if 83 in r['profile_ids'])
        fn = cam.w(state+V.L.S['FN']+V.L.FNS.index('CANVAS')*4)
        canvas = V.RC.CANVAS_IN+0x5c
        for rank, entry in targets.items():
            before = bytes(cam.mu.mem_read(entry, V.L.ENT['SIZE']))
            cam.put(state+V.L.S['VRATE'], rank)
            key = b'VRC000120\0' if NATIVE_CARRIER == 7 else b'VRC00030\0'
            cam.mu.mem_write(V.RC.KEYBUF, key.ljust(16, b'\0'))
            hit, _ = cam.call(V.RC.PICKER, r1=V.RC.TAB3, r2=V.RC.KEYBUF)
            self.assertNotEqual(hit, 0)
            self.assertEqual(state+cam.w(state+V.L.S['LAST_ENT']), entry)
            reference = None
            for engine, expected_switch in ((60.0, 1), (30.0, 0)):
                cam.put(entry+V.L.ENT['ENGFPS'], V.L._f32(engine))
                # The picker latches ENGFPS. A data change alone deliberately
                # leaves the current latch untouched until normal selection.
                hit, _ = cam.call(V.RC.PICKER, r1=V.RC.TAB3, r2=V.RC.KEYBUF)
                self.assertNotEqual(hit, 0)
                cam.mu.mem_write(canvas, struct.pack('<65I', *donor))
                self.assertEqual(cam.call(fn, state, canvas, cam.w(hit+4), thumb=True, sp=V.T.STACK-0x1000)[0], 1)
                self.assertEqual(native_engine_gate(cam, canvas), 0)
                data = list(struct.unpack('<65I', cam.mu.mem_read(canvas, 260)))
                self.assertEqual(data[0x30//4], V.L._f32(engine))
                self.assertEqual(near60_switch(cam), expected_switch)
                data[0x30//4] = 0
                if reference is None:
                    reference = data
                else:
                    self.assertEqual(data, reference, 'geometry changed')
            after = bytes(cam.mu.mem_read(entry, V.L.ENT['SIZE']))
            off = V.L.ENT['ENGFPS']
            self.assertEqual(after[:off]+after[off+4:], before[:off]+before[off+4:])
        cam.assert_tables(self)
        self.assertEqual(cam.misaligned, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
