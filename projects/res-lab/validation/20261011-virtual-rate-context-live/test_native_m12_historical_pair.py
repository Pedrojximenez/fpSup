"""Offline v17 ARM contrast: native mode12 with the archived H2 engine value.

The earlier native12 trial kept the four processing30/nominal30 edits. It did
not test native12 plus the predecessor's inferred processing239.76/nominal240.
This test changes one owned entry word and preserves the ordinary2997 carrier.
It does not simulate capture scheduling, DMA, storage, or prove recording works.
"""
import hashlib
import json
import os
import pathlib
import struct
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CARD = HERE / 'reference-capture-header-v17'
os.environ['VIRTUAL_RCD_CARD'] = str(CARD)
sys.path.insert(0, str(HERE / 'reference-source-v17'))
import ogc_layout as L
assert hashlib.sha256(pathlib.Path(L.__file__).read_bytes()).hexdigest() == \
    json.loads((HERE / 'reference-source-v17/provenance.json').read_text())['sha256']
assert hashlib.sha256((CARD / 'fpSup/32RESCUS.BIN').read_bytes()).hexdigest() == \
    '37d3468e56dfbfc18a368200b305e278c18d404edf65702a2bada44a5a11942e'
sys.path.insert(0, str(ROOT / 'projects/open-gate/build'))
import test_reslab_header_copy as H
import test_virtual_rcd as V
from unicorn.arm_const import UC_ARM_REG_R3


class HistoricalNativePair(unittest.TestCase):
    setUpClass = classmethod(H.CaptureCarrierHeaderTests.setUpClass.__func__)
    boot = H.CaptureCarrierHeaderTests.boot
    camera = H.CaptureCarrierHeaderTests.camera
    copy = H.CaptureCarrierHeaderTests.copy

    def test_one_mode_word_preserves_h2_capture_and_carrier(self):
        cam, entry = self.camera()
        s = cam.s()
        expected = self.manifest['expected_canvas']
        engine = self.manifest['tested_entry']['engfps']
        self.assertEqual(engine, 0x436FC29F)
        self.assertEqual(cam.w(entry + L.ENT['ENGFPS']), engine)
        self.assertEqual(cam.w(entry + L.ENT['NOMINAL']), 240)
        self.assertGreaterEqual(cam.w(entry + L.ENT['MODE']), L.VMID0)
        before = bytes(cam.mu.mem_read(entry, L.ENT['SIZE']))
        cam.put(entry + L.ENT['MODE'], 12)
        after = bytearray(before)
        struct.pack_into('<I', after, L.ENT['MODE'], 12)
        self.assertEqual(bytes(cam.mu.mem_read(entry, L.ENT['SIZE'])), bytes(after))
        cam.mu.mem_write(V.RC.KEYBUF, b'H2S24030\0'.ljust(16, b'\0'))
        hit, _ = cam.call(V.RC.PICKER, r1=V.RC.TAB3, r2=V.RC.KEYBUF)
        self.assertEqual(hit, entry)
        self.assertEqual(cam.w(entry + L.ENT['MODE']), 12)
        self.assertEqual(cam.w(s + L.S['FPSLATCH']), engine)
        self.assertEqual(cam.w(s + L.S['VRATE']), 0)
        fn = lambda name: cam.w(s + L.S['FN'] + 4 * L.FNS.index(name))
        canvas = V.RC.CANVAS_IN + 0x5C
        # Independent native p13 defaults, rather than a pre-patched canvas.
        source = json.loads((HERE / 'success-version-audit/historical-h2-profile-difference.json').read_text())
        profiles = json.loads(pathlib.Path(source['profiles_source']).read_text())
        base = next(row['words'] for row in profiles['rows'] if 13 in row['profile_ids'])
        cam.mu.mem_write(canvas, struct.pack('<65I', *base))
        cam.call(fn('CANVAS'), s, canvas, cam.w(entry + L.ENT['PID']),
                 thumb=True, sp=V.T.STACK - 0x1000)
        self.assertEqual(list(struct.unpack('<65I', cam.mu.mem_read(canvas, 260))), expected)
        native = 0xC0B59A40
        self.assertEqual(cam.w(native), 12)
        self.assertEqual([cam.w(native + 4), cam.w(native + 8)],
                         [self.manifest['tested_entry']['w0'], self.manifest['tested_entry']['w1']])
        for kind in range(len(L.TABLES) + 1):
            # Includes the eighth R10 table. Native12 belongs to the original
            # firmware; virtual lookup must decline and leave its data intact.
            cam.mu.reg_write(UC_ARM_REG_R3, 12)
            self.assertEqual(cam.call(fn('VLOOK'), s, kind, L.IMAGER,
                                      thumb=True, sp=V.T.STACK - 0x1000)[0], 0)
        self.assertEqual(cam.call(fn('FPS'), s, 12, 240,
                                  thumb=True, sp=V.T.STACK - 0x1000)[0], 240)
        rational = H.PARAM + 0x100
        cam.mu.mem_write(rational, struct.pack('<2I', 30000, 1001))
        self.assertEqual(cam.call(fn('RECRATE'), s, rational,
                                  thumb=True, sp=V.T.STACK - 0x1000)[0], 0)
        self.assertEqual(bytes(cam.mu.mem_read(rational, 8)), struct.pack('<2I', 30000, 1001))
        self.assertEqual(self.copy(cam)[0], 0x42)
        self.assertEqual(cam.w(s + L.S['HDR_COPY_HITS']), 0)
        descriptor = struct.pack('<4I', 0x4000000, 0x49048000, 0x40000, 0xC03A55D0)
        cam.mu.mem_write(H.PARAM, descriptor)
        cam.call(fn('BULK'), s, H.PARAM, thumb=True, sp=V.T.STACK - 0x1000)
        self.assertEqual(bytes(cam.mu.mem_read(H.PARAM, 16)), descriptor)
        self.assertEqual(cam.w(s + L.S['BULK_HITS']), 0)
        cam.assert_tables(self)
        self.assertEqual(cam.misaligned, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
