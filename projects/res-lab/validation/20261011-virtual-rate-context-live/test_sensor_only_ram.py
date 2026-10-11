"""Offline real ARM proof for RAM-only H2 rate separation; no live access."""
import pathlib
import struct
import sys
import unittest
from unicorn.arm_const import UC_ARM_REG_R1, UC_ARM_REG_R3

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'projects/open-gate/build'))
import test_reslab_header_copy as H
import test_virtual_rcd as V

ENGINE30 = 0x41F00000  # the native29.97 profile's processing FPS


class SensorOnlyRAM(H.CaptureCarrierHeaderTests):
    # Only this focused test is collected by the command below.
    def test_sensor239_app30_after_native_picker_reentry(self):
        cam, entry = self.camera()
        s = cam.s()
        vm = s + cam.w(s + V.L.S['VMS']) + cam.w(entry + V.L.ENT['VM']) * V.L.VM['SIZE']
        # Fill the real consumer-owned clones through the maintained hook.
        site = 0xC0320BA0
        self.assertTrue(any(int(h['site'], 16) == site for h in self.f['rescustom']['hooks']))
        cam.call(site, r0=V.L.IMAGER, r1=cam.w(entry + V.L.ENT['MODE']))
        tim = cam.w(vm + V.L.VM['PTR'])
        self.assertEqual(cam.w(vm + V.L.VM['FILLED']), 1)
        original_timing = bytes(cam.mu.mem_read(tim, 32))
        cam.put(entry + V.L.ENT['ENGFPS'], ENGINE30)
        cam.put(entry + V.L.ENT['NOMINAL'], 30)
        cam.put(s + V.L.S['FPSLATCH'], ENGINE30)
        cam.put(vm + V.L.VM['NOM'], 30)
        # A normal later picker hit must not reintroduce processing240.
        cam.mu.mem_write(V.RC.KEYBUF, b'H2S24030\0'.ljust(16, b'\0'))
        hit, _ = cam.call(V.RC.PICKER, r1=V.RC.TAB3, r2=V.RC.KEYBUF)
        self.assertEqual(hit, entry)
        self.assertEqual(bytes(cam.mu.mem_read(tim, 32)), original_timing)
        self.assertEqual(cam.w(s + V.L.S['FPSLATCH']), ENGINE30)
        self.assertEqual(cam.w(vm + V.L.VM['NOM']), 30)
        fn = lambda name: cam.w(s + V.L.S['FN'] + 4 * V.L.FNS.index(name))
        expected = self.manifest['expected_canvas'].copy()
        expected[0x30 // 4] = ENGINE30
        canvas = V.RC.CANVAS_IN + 0x5c
        cam.mu.mem_write(canvas, struct.pack('<65I', *expected))
        cam.call(fn('CANVAS'), s, canvas, cam.w(entry + V.L.ENT['PID']), thumb=True, sp=V.T.STACK-0x1000)
        self.assertEqual(list(struct.unpack('<65I', cam.mu.mem_read(canvas, 260))), expected)
        self.assertEqual(cam.call(fn('FPS'), s, cam.w(entry + V.L.ENT['MODE']), 30, thumb=True, sp=V.T.STACK-0x1000)[0], 30)
        rational = H.PARAM + 0x100
        cam.mu.mem_write(rational, struct.pack('<2I', 30000, 1001))
        self.assertEqual(cam.call(fn('RECRATE'), s, rational, thumb=True, sp=V.T.STACK-0x1000)[0], 0)
        self.assertEqual(bytes(cam.mu.mem_read(rational, 8)), struct.pack('<2I', 30000, 1001))
        # The original DMA header and 64MiB bulk paths are the requested baseline.
        self.assertEqual(self.copy(cam)[0], 0x42)
        descriptor = struct.pack('<4I', 0x4000000, 0x49048000, 0x40000, 0xC03A55D0)
        cam.mu.mem_write(H.PARAM, descriptor)
        cam.call(fn('BULK'), s, H.PARAM, thumb=True, sp=V.T.STACK-0x1000)
        self.assertEqual(bytes(cam.mu.mem_read(H.PARAM, 16)), descriptor)
        self.assertEqual(cam.misaligned, [])
        cam.assert_tables(self)
        # Reintroducing the old coupled value must be detectable.
        cam.put(entry + V.L.ENT['ENGFPS'], self.manifest['tested_entry']['engfps'])
        cam.call(V.RC.PICKER, r1=V.RC.TAB3, r2=V.RC.KEYBUF)
        self.assertNotEqual(cam.w(s + V.L.S['FPSLATCH']), ENGINE30)

    def test_native_m12_identity_keeps_exact_stock_timing(self):
        cam, entry = self.camera()
        s = cam.s()
        native = 0xC0B59A40
        self.assertEqual(cam.w(native), 12)
        self.assertEqual([cam.w(native+4),cam.w(native+8)],
                         [self.manifest['tested_entry']['w0'],self.manifest['tested_entry']['w1']])
        old_mode = cam.w(entry+V.L.ENT['MODE'])
        self.assertGreaterEqual(old_mode, V.L.VMID0)
        cam.put(entry+V.L.ENT['MODE'], 12)
        cam.put(entry+V.L.ENT['ENGFPS'], ENGINE30)
        cam.put(entry+V.L.ENT['NOMINAL'], 30)
        cam.mu.mem_write(V.RC.KEYBUF,b'H2S24030\0'.ljust(16,b'\0'))
        hit,_=cam.call(V.RC.PICKER,r1=V.RC.TAB3,r2=V.RC.KEYBUF)
        self.assertEqual(hit,entry)
        self.assertEqual(cam.w(hit+8),12)
        fn=lambda name:cam.w(s+V.L.S['FN']+4*V.L.FNS.index(name))
        # All virtual sensor lookups must decline native12. The firmware then
        # uses its own unchanged tables. This fixture proves the decline only.
        for kind in range(len(V.L.TABLES)):
            cam.mu.reg_write(UC_ARM_REG_R3,12)
            self.assertEqual(cam.call(fn('VLOOK'),s,kind,V.L.IMAGER,
                thumb=True,sp=V.T.STACK-0x1000)[0], 0)
            self.assertEqual(cam.r(UC_ARM_REG_R1),0)
        self.assertEqual(bytes(cam.mu.mem_read(native,32)),cam.img[native-0xc0000000:native-0xc0000000+32])
        cam.assert_tables(self)
        self.assertEqual(cam.misaligned,[])


if __name__ == '__main__':
    unittest.main(defaultTest='SensorOnlyRAM.test_sensor239_app30_after_native_picker_reentry', verbosity=2)
