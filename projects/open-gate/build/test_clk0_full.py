"""Channel-0 clock gate: entry opens C0189440 to #0xFFFF; power-off restores stock."""
import struct, unittest
import test_virtual_rcd as V
SITE, STOCK, FULL = 0xC0189440, 0x2C49F241, 0x7CFFF64F

class Clk0(unittest.TestCase):
    def test_entry_writes_and_power_off_restores(self):
        out, f = V.built(); t = V.VirtualTests('test_contract_abi_and_status'); t.out, t.f = out, f
        cam = t.boot(fr=7)
        self.assertEqual(struct.unpack_from('<I', cam.img, SITE-0xC0000000)[0], STOCK)
        self.assertEqual(cam.w(SITE), FULL)
        self.assertEqual(cam.w(SITE+4), struct.unpack_from('<I', cam.img, SITE+4-0xC0000000)[0])
        cam.power_off()
        self.assertEqual(cam.w(SITE), STOCK)

if __name__ == '__main__':
    unittest.main()
