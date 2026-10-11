import unittest
from pathlib import Path

from extract_isp_map import ROOT, routes, functions


class IspMapTests(unittest.TestCase):
    def test_named_functions_delimit_bodies(self):
        src = '/* ==== FUN_c0101000 @ c0101000 ==== */ a /* ==== Native__v2 @ c0101100 ==== */ b'
        self.assertEqual([f[0] for f in functions(src)], ['FUN_c0101000', 'Native__v2'])
        self.assertNotIn(' b', functions(src)[0][2])

    def test_explicit_name_mmio_descriptor_join(self):
        rom = bytearray(128)
        rom[16:23] = b'CUVAREA'
        src = '''/* ==== FUN_c0101000 @ c0101000 ==== */
        FUN_c01f57f4(0xc31d9c9c,s_CUVAREA_c0000010);
        FUN_c015c1d8(0x30116600);
        /* ==== Native__v2 @ c0101100 ==== */
        FUN_c019df90(iVar1 + 0x30212ed0,0x30116600,0x11,iVar1 + 0x30211024);
        '''
        result = routes(src, bytes(rom))
        self.assertEqual(result[0]['name'], 'CUVAREA')
        self.assertEqual(result[0]['mappings'][0]['shadow_start'], '0x30211024')
        self.assertEqual(result[0]['mappings'][0]['words'], 17)
        extra = src.replace('FUN_c015c1d8(0x30116600)',
                            'FUN_c015c1d8(0x30116600,0x30160640)')
        self.assertEqual(routes(extra, bytes(rom)), result)
        # Explicit address mismatch must never fall back to name/order guessing.
        bad = src.replace('FUN_c015c1d8(0x30116600)', 'FUN_c015c1d8(0x30126600)')
        self.assertEqual(routes(bad, bytes(rom))[0]['mappings'], [])

    def test_real_firmware_color_routes(self):
        root = Path(ROOT)
        rom = (root / 'out/MAIN_c0000000.bin').read_bytes()
        src = (root / 'out/decomp/full/blk_c01.c').read_text()
        result = {r['name']: r for r in routes(src, rom)}
        expected = {'GAM_TOP RGBMAT_PL': ('0x30115b80', '0x30210ee0', 9),
                    'PST_TOP CUVAREA CARE_SEL': ('0x30116600', '0x30211024', 17),
                    'PST_TOP CUVCONT': ('0x30116700', '0x30211068', 8),
                    'YMED_TOP C_SAT_C': ('0x30117b00', '0x3021127c', 24),
                    'TMAP': ('0x30130600', '0x30212828', 17)}
        for name, (mmio, shadow, words) in expected.items():
            row = result[name]
            self.assertEqual(row['diagnostic_mmio'][0], mmio)
            self.assertEqual(row['mappings'][0]['shadow_start'], shadow)
            self.assertEqual(row['mappings'][0]['words'], words)


if __name__ == '__main__':
    unittest.main()
