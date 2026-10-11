#!/usr/bin/env python3
"""The Sensor Lab B2_5 installer (sl_menu.c) against a model of the camera.

sl_menu.c + sl_menu_fixture.c (ported from fpSup/lossless/native) on the host,
fed the REAL packed page from sl_b25_page.py. Asserted: all or nothing -- on
any mismatch B2_5's page offset does not change and no variable is registered
-- and, when installed, every private string the page names resolves through
the shared pool (fpSup/uishare) to that string, and the six integers are
registered 0 with resident (borrowed) names. No camera.
"""
import ctypes as ct
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
UISHARE = ROOT / 'fpSup/uishare'
sys.path.insert(0, str(HERE.parent))
import sl_b25_page as SP  # noqa: E402
import sl_lists as SL  # noqa: E402

INSTALLED, NO_GUI, NO_SCREEN, READER, NO_ENTRY, ROOM, FILE, FORMAT, REGISTER, VARIABLE, \
    POOL_REFUSED = range(1, 12)
(RESULT, PAGE, POOL, POOL_LEN, REGISTERED, OOB, CTORS, DTORS, OPENS, READS, CLOSES,
 VOLUME, REG_CALLS, WRITES_N, PUBLISHES, REG_PUBLISHES, DESC_N, OPEN_MODE, PAGE_LEN,
 FILE_LEN, PATH_OK, R_READER, R_ENTRIES, R_AREA, R_APP, R_SCREENS, R_NBU,
 BORROWED_BAD, NBR, NBR_LEN, PAGES_F, PAGES_LEN_F) = range(32)
AREA_BYTES = 0x80000
B25, B25_OFFSET = 4, 0x19C130
NAMES = [b'SL_O_W', b'SL_O_H', b'SL_O_In', b'SL_O_BH',
         b'SL_O_BV', b'SL_O_SW', b'SL_ModeCount',
         b'MV_SLScale', b'SL_O_SH', b'MV_SLBin', b'MV_SLRwzm',
         b'SL_LabFocus', b'SL_F_Bit', b'SL_F_Fps', b'SL_F_Width', b'SL_F_Prop', b'SL_M_Sel', b'SL_LabTab',
         b'SL_O_Key', b'SL_O_A0', b'SL_O_A1', b'SL_O_A2', b'SL_O_A3', b'SL_O_Rate', b'SL_ModeMax', b'SL_M_Text', b'SL_O_RFps',
         b'SL_D_GX', b'SL_D_GY', b'SL_D_GW', b'SL_D_GH', b'SL_D_RX', b'SL_D_RY', b'SL_D_RW', b'SL_D_RH',
         b'SL_D_GTxt', b'SL_D_RTxt', b'SL_D_Fps', b'SL_D_Rs', b'SL_F_Crop', b'SL_M_Tab',
         b'SL_C_Text', b'SL_D_CX', b'SL_D_CY', b'SL_D_CW', b'SL_D_CH', b'SL_D_CTxt', b'SL_N_Sel', b'SL_O_BTxt']
NVARS = len(NAMES)

import sl_pages as PG  # noqa: E402

RES = SP.build()
IMG = (SP.ROOT / 'out/MAIN_c0000000.bin').read_bytes()
PACK = SL.build_pack(IMG)
PAGES = PG.build_pack(PG.test_pages(IMG))
BLOCK = SP.pack(RES, PACK, PAGES)
HEAD = SP.SLMP_HEAD
REFS_END = HEAD + struct.unpack_from('<I', BLOCK, 8)[0] + struct.unpack_from('<I', BLOCK, 12)[0] + \
    8 * struct.unpack_from('<I', BLOCK, 16)[0]
NBR_AT = (REFS_END + 3) & ~3
PAGES_AT = (NBR_AT + len(PACK) + 3) & ~3
BODY = PAGES_AT + len(PAGES)


def build(directory, replace=None, name='slmenu.dylib', dynamic=False):
    source = HERE / 'sl_menu.c'
    if replace:
        old, new = replace
        text = source.read_text()
        if text.count(old) != 1:
            raise AssertionError('mutation seam not found once: ' + old[:60])
        source = pathlib.Path(directory) / (name + '.c')
        source.write_text(text.replace(old, new))
    out = pathlib.Path(directory) / name
    subprocess.run([shutil.which('clang') or 'clang', '-shared', '-fPIC', '-O1', '-std=c11',
                    '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
                    '-DSL_MENU_HOST_TEST', '-DUIS_HOST_TEST',
                    *(['-DSL_DYNAMIC_CORE=1'] if dynamic else []),
                    '-I', str(HERE), '-I', str(UISHARE), str(source),
                    str(HERE / 'sl_menu_fixture.c'), str(UISHARE / 'ui_pool.c'), '-o', str(out)],
                   check=True, capture_output=True, text=True, timeout=60)
    lib = ct.CDLL(str(out))
    for fn, args, ret in (('reset', [], None), ('file', [ct.c_char_p, ct.c_uint32, ct.c_uint32], None),
                          ('word', [ct.c_uint32] * 2, None), ('peek', [ct.c_uint32], ct.c_uint32),
                          ('byte', [ct.c_uint32], ct.c_uint32), ('reg_result', [ct.c_uint32], None),
                          ('preregister', [ct.c_uint32], None), ('set_value', [ct.c_uint32], None),
                          ('install', [ct.c_uint32], ct.c_uint32), ('value', [ct.c_uint32], ct.c_uint32),
                          ('get', [ct.c_uint32], ct.c_uint32),
                          ('other_sup', [ct.c_char_p, ct.c_uint32], ct.c_uint32),
                          ('resolve_page', [ct.c_uint32, ct.c_char_p, ct.c_uint32], ct.c_uint32),
                          ('resolve_at', [ct.c_uint32, ct.c_char_p, ct.c_uint32], ct.c_uint32)):
        f = getattr(lib, 'sl_fixture_' + fn)
        f.argtypes = args
        f.restype = ret
    # the fixture's pool is a stand-in; make it the real stock pool so the
    # page's stock strings and the private ones both resolve truthfully
    return lib


class MenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='sl-menu-')
        cls.lib = build(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    HEAD = bytes((i * 5 + 7) & 0xFF for i in range(0xF000))   # the loader's part

    def setUp(self):
        self.lib.sl_fixture_reset()
        self.put(BLOCK)

    def test_dynamic_install_defers_private_page_until_hooks_arm(self):
        dynamic = build(self.tmp.name, name='slmenu-dynamic.dylib', dynamic=True)
        dynamic.sl_fixture_reset()
        data = self.HEAD + BLOCK
        dynamic.sl_fixture_file(data, len(data), 1)
        self.assertEqual(dynamic.sl_fixture_install(AREA_BYTES), INSTALLED)
        entry = dynamic.sl_fixture_get(R_ENTRIES) + 44 * B25 + 8
        self.assertEqual(dynamic.sl_fixture_peek(entry), B25_OFFSET)
        self.assertNotEqual(dynamic.sl_fixture_get(PAGE), 0)
        self.assertEqual(dynamic.sl_fixture_get(RESULT), INSTALLED)

    def put(self, data, present=1, head=None):
        data = (self.HEAD if head is None else head) + data
        self.lib.sl_fixture_file(data, len(data), present)

    def get(self, f): return self.lib.sl_fixture_get(f)
    def peek(self, a): return self.lib.sl_fixture_peek(a)

    def bytes_at(self, a, n):
        return bytes(self.lib.sl_fixture_byte(a + i) for i in range(n))

    def switched(self):
        r, e = self.get(R_READER), self.get(R_ENTRIES)
        return (self.peek(r + 0x14), self.peek(r + 0x10), self.peek(e + 44 * B25 + 8))

    STOCK = (0xC18C0474, 176152, B25_OFFSET)

    def resolved(self, page_off):
        buf = ct.create_string_buffer(64)
        return buf.value.decode() if self.lib.sl_fixture_resolve_page(page_off, buf, 64) else None

    def assert_untouched(self, result):
        self.assertEqual(self.lib.sl_fixture_install(AREA_BYTES), result)
        self.assertEqual(self.switched(), self.STOCK, 'a word was switched')
        self.assertEqual(self.get(REG_CALLS), 0, 'a variable was registered')

    # ---- installed ---------------------------------------------------------
    def test_installs_and_every_private_string_resolves(self):
        self.assertEqual(self.lib.sl_fixture_install(AREA_BYTES), INSTALLED)
        page = self.get(PAGE)
        self.assertEqual((0xC18C0460 + self.switched()[2]) & 0xFFFFFFFF, page)
        self.assertEqual(self.get(PAGE_LEN), len(RES['page']))
        for at, text in RES['abs_refs']:
            self.assertEqual(self.resolved(at), text, f'page word {at:#x}')
        # every other byte of the page is the builder's
        refs = {a for a, _ in RES['abs_refs']}
        got = self.bytes_at(page, len(RES['page']))
        diff = [i for i in range(len(got)) if got[i] != RES['page'][i]]
        self.assertTrue(all(any(a <= i < a + 4 for a in refs) for i in diff))
        self.assertEqual(self.get(OOB), 0)

    def test_the_private_nbr_is_recorded_not_registered(self):
        self.assertEqual(self.lib.sl_fixture_install(AREA_BYTES), INSTALLED)
        nbr, n = self.get(NBR), self.get(NBR_LEN)
        self.assertEqual(n, len(PACK))
        self.assertEqual(nbr % 4, 0)
        self.assertEqual(self.bytes_at(nbr, len(PACK)), PACK)
        self.assertEqual(SL.inspect_pack(self.bytes_at(nbr, len(PACK))).keys(),
                         {'SL_RATE', 'SL_BIT', 'SL_MODE', 'SL_SIZE', 'SL_SCALE', 'SL_WH', 'SL_BINS', 'SL_RWZM',
                          'SL_F_BIT', 'SL_F_FPS', 'SL_F_WIDTH', 'SL_F_PROP', 'SL_F_CROP', 'SL_RFPS', 'SL_O_CROP', 'SL_N_PRESET'})

    def test_the_pages_pack_is_recorded_not_registered(self):
        self.assertEqual(self.lib.sl_fixture_install(AREA_BYTES), INSTALLED)
        at, n = self.get(PAGES_F), self.get(PAGES_LEN_F)
        self.assertEqual((n, at % 4), (len(PAGES), 0))
        self.assertEqual(self.bytes_at(at, n), PAGES)
        self.assertEqual(PG.inspect_pack(self.bytes_at(at, n)).keys(), {'SL_TEST'})

    def test_size_page_strings_resolve_in_the_pages_pack(self):
        """(v4) the SIZE sub page's private strings sit in the pages pack: flagged
        references are patched there, from the same shared pool."""
        res = SP.build()
        plist, prefs = PG.size_pages(IMG, res['pool'])
        pages = PG.build_pack(plist)
        prefs_abs = PG.pack_refs(pages, plist, {plist[0][0]: prefs})
        block = SP.pack(res, PACK, pages, 0x50000, prefs_abs)
        self.put(block)
        self.assertEqual(self.lib.sl_fixture_install(0x60000), INSTALLED)
        at = self.get(PAGES_F)
        self.assertEqual(self.get(PAGES_LEN_F), len(pages))
        buf = ct.create_string_buffer(64)
        self.assertGreater(len(prefs_abs), 10)
        for off, text in prefs_abs:
            self.assertEqual(self.lib.sl_fixture_resolve_at(at + off, buf, 64), 1)
            self.assertEqual(buf.value.decode(), text, f'pack word {off:#x}')
        # and the B2_5 page's own refs still resolve
        for off, text in res['abs_refs'][:5]:
            self.assertEqual(self.resolved(off), text)

    def test_a_pages_ref_past_the_pack_is_refused(self):
        res = SP.build()
        block = bytearray(SP.pack(res, PACK, PAGES))
        n = struct.unpack_from('<I', block, 16)[0]
        refs_at = HEAD + struct.unpack_from('<I', block, 8)[0] + struct.unpack_from('<I', block, 12)[0]
        struct.pack_into('<I', block, refs_at, 0x80000000 | (len(PAGES) - 2))
        body = bytes(block[HEAD:])
        struct.pack_into('<I', block, 0x18, SP.fnv(body[:BODY - HEAD]))
        self.put(bytes(block))
        self.assert_untouched(FORMAT)

    def test_a_block_without_nbr_still_installs(self):
        self.put(SP.pack(RES))
        self.assertEqual(self.lib.sl_fixture_install(AREA_BYTES), INSTALLED)
        self.assertEqual((self.get(NBR), self.get(NBR_LEN)), (0, 0))

    def test_only_b2_5_changes(self):
        e = self.get(R_ENTRIES)
        before = [self.peek(e + 44 * i + 8) for i in range(5)]
        self.lib.sl_fixture_install(AREA_BYTES)
        after = [self.peek(e + 44 * i + 8) for i in range(5)]
        self.assertEqual(before[:B25] + before[B25 + 1:], after[:B25] + after[B25 + 1:])
        self.assertNotEqual(before[B25], after[B25])

    def test_the_page_is_switched_last_and_once(self):
        self.lib.sl_fixture_install(AREA_BYTES)
        e = self.get(R_ENTRIES)
        log = [self.get(1000 + i) for i in range(self.get(WRITES_N))]
        self.assertLess(self.get(WRITES_N), 512)            # the log did not saturate
        self.assertEqual(log[-1], e + 44 * B25 + 8 - 0x10000000)
        self.assertEqual(log.count(e + 44 * B25 + 8 - 0x10000000), 1)
        self.assertGreaterEqual(self.get(PUBLISHES), 2)

    def test_seven_integers_registered_zero_with_resident_names(self):
        self.assertEqual(self.lib.sl_fixture_install(AREA_BYTES), INSTALLED)
        self.assertEqual((self.get(REG_CALLS), self.get(REGISTERED), self.get(DESC_N)), (NVARS,) * 3)
        names = [self.bytes_at(self.peek(0x10009000 + 32 * i + 4), 20).split(b'\0')[0] for i in range(NVARS)]
        self.assertEqual(names, NAMES)
        text = {NAMES.index(n) for n in (b'SL_O_BTxt', b'SL_O_SW', b'SL_O_SH', b'SL_O_Rate', b'SL_M_Text',
                                         b'SL_D_GTxt', b'SL_D_RTxt', b'SL_D_Fps', b'SL_D_Rs', b'SL_M_Tab', b'SL_C_Text', b'SL_D_CTxt')}   # text (type 2), "1.00"
        self.assertEqual([self.peek(0x10009000 + 32 * i) for i in range(NVARS)],
                         [2 if i in text else 0 for i in range(NVARS)])
        self.assertEqual([self.peek(0x10009000 + 32 * i + 8) for i in range(NVARS) if i not in text], [0] * (NVARS - len(text)))
        for i in text:
            self.assertEqual(self.bytes_at(self.peek(0x10009000 + 32 * i + 8), 5), b'1.00\0')
        self.assertEqual(self.get(BORROWED_BAD), 0)
        self.assertEqual([self.lib.sl_fixture_value(i) for i in range(NVARS) if i not in text], [0] * (NVARS - len(text)))
        self.lib.sl_fixture_set_value(3)
        self.assertEqual(self.lib.sl_fixture_value(0), 3)
        self.assertEqual(self.lib.sl_fixture_value(NVARS), 0xFFFFFFFF)

    def test_an_existing_variable_is_used_not_registered_again(self):
        self.lib.sl_fixture_preregister(0)
        self.assertEqual(self.lib.sl_fixture_install(AREA_BYTES), INSTALLED)
        self.assertEqual((self.get(REG_CALLS), self.get(REGISTERED)), (NVARS - 1,) * 2)

    def test_the_file_is_read_once_and_the_object_destroyed(self):
        self.lib.sl_fixture_install(AREA_BYTES)
        self.assertEqual((self.get(VOLUME), self.get(OPEN_MODE), self.get(PATH_OK)), (1, 1, 1))
        self.assertEqual((self.get(CTORS), self.get(OPENS), self.get(READS), self.get(CLOSES),
                          self.get(DTORS)), (1, 1, 2, 1, 1))
        self.assertEqual(self.lib.sl_fixture_install(AREA_BYTES), INSTALLED)
        self.assertEqual(self.get(OPENS), 1)

    def test_shares_the_pool_with_another_sup(self):
        theirs = self.lib.sl_fixture_other_sup(b'OG3K', 4)
        same = self.lib.sl_fixture_other_sup(b'SL_RATE', 7)
        pool = self.switched()[0]
        self.assertEqual(self.lib.sl_fixture_install(AREA_BYTES), INSTALLED)
        self.assertEqual(self.switched()[0], pool, 'a second copy of the pool')
        at = next(a for a, t in RES['abs_refs'] if t == 'SL_RATE')
        self.assertEqual(int.from_bytes(self.bytes_at(self.get(PAGE) + at, 4), 'big'), same)
        self.assertEqual(self.bytes_at(self.switched()[0] + theirs, 5), b'OG3K\0')

    # ---- nothing installed -------------------------------------------------
    def test_a_camera_whose_objects_differ_gets_nothing(self):
        app, scr, r, e = self.get(R_APP), self.get(R_SCREENS), self.get(R_READER), self.get(R_ENTRIES)
        cases = {
            'no GUI app': (0xC37B7048, 0, NO_GUI),
            'MainB2 of another app': (scr + 0x40 * 2 + 4, app + 0x100, NO_SCREEN),
            'reader not the NBU': (r + 0x24, 0xC18C0000, READER),
            'pool moved already': (r + 0x14, 0x12345678, READER),
            'B2_5 already switched': (e + 44 * B25 + 8, 0x1B8E9B, NO_ENTRY),
            'B2_5 missing': (r + 0xA8, 4, NO_ENTRY),
        }
        for name, (addr, value, result) in cases.items():
            with self.subTest(case=name):
                self.setUp()
                self.lib.sl_fixture_word(addr, value)
                self.assertEqual(self.lib.sl_fixture_install(AREA_BYTES), result)
                self.assertEqual(self.get(REG_CALLS), 0)
                self.assertEqual(self.get(OPENS), 0, 'the card was read before the checks')
                self.assertEqual(self.get(WRITES_N), 0)

    def test_a_damaged_or_foreign_block(self):
        good = bytearray(BLOCK)
        cases = {
            'magic': (0, b'FPLM'),
            'version 1': (4, struct.pack('<I', 1)),
            'nbr magic': (NBR_AT, b'NBX'),
            'one nbr byte': (NBR_AT + 30, bytes([good[NBR_AT + 30] ^ 1])),
            'pages magic': (PAGES_AT, b'NBX'),
            'pages version 1.5': (PAGES_AT + 5, b'\x05'),
            'one pages byte': (BODY - 9, bytes([good[BODY - 9] ^ 1])),
            'pages longer than the file': (0x20, struct.pack('<I', 0x30000)),
            'nbr longer than the file': (0x1C, struct.pack('<I', 0x30000)),
            'page offset of MainB2': (0x14, struct.pack('<I', 0x76FF04)),
            'one page byte': (HEAD + 5000, bytes([good[HEAD + 5000] ^ 1])),
            'one reference byte': (REFS_END - 3, bytes([good[REFS_END - 3] ^ 1])),
        }
        for name, (off, patch) in cases.items():
            with self.subTest(case=name):
                self.setUp()
                bad = bytearray(good)
                bad[off:off + len(patch)] = patch
                self.put(bytes(bad))
                self.assert_untouched(FORMAT)

    def test_no_file_truncated_file_or_none_past_the_loader(self):
        for name, (data, present, head, results) in {
                'absent': (BLOCK, 0, None, (FILE,)),
                'truncated': (BLOCK[:BODY - 1], 1, None, (FORMAT,)),
                'truncated in the refs': (BLOCK[:REFS_END - 1], 1, None, (FORMAT,)),
                'loader only': (b'', 1, None, (FILE, FORMAT)),
                'block at offset 0': (b'', 1, BLOCK, (FILE, FORMAT))}.items():
            with self.subTest(case=name):
                self.setUp()
                self.put(data, present, head)
                self.assertIn(self.lib.sl_fixture_install(AREA_BYTES), results)
                self.assertEqual(self.switched(), self.STOCK)
                self.assertEqual(self.get(REG_CALLS), 0)

    def test_a_stale_tail_after_an_unpadded_block_is_ignored(self):
        """The block is written unpadded; putfile over an older, longer fpSup.BIN
        leaves its tail behind.  The header's lengths and the checksum decide."""
        self.assertEqual(len(BLOCK) % 4, 0)
        self.assertLess(len(BLOCK), SP.SLMP_BYTES)
        self.put(BLOCK + bytes((i * 13 + 1) & 0xFF for i in range(0x3000)))
        self.assertEqual(self.lib.sl_fixture_install(AREA_BYTES), INSTALLED)

    def test_too_little_room(self):
        self.assertEqual(self.lib.sl_fixture_install(0x1000 + len(BLOCK)), ROOM)     # exactly full: may be cut
        self.assertEqual(self.switched(), self.STOCK)

    def test_a_registration_that_fails_switches_nothing(self):
        self.lib.sl_fixture_reg_result(3)
        self.assertEqual(self.lib.sl_fixture_install(AREA_BYTES), REGISTER)
        self.assertEqual(self.switched()[2], B25_OFFSET)
        self.assertEqual(self.get(REG_CALLS), 1)

    def test_a_variable_of_another_type_switches_nothing(self):
        self.lib.sl_fixture_preregister(1)
        self.assertEqual(self.lib.sl_fixture_install(AREA_BYTES), VARIABLE)
        self.assertEqual(self.switched()[2], B25_OFFSET)


class MutationTests(unittest.TestCase):
    MUTATIONS = {
        'skips the checksum': ('2166136261u) != peek(file + 0x18))', '2166136261u) != peek(file + 0x18) && 0)'),
        'leaves the builder offsets': ('            else put_be(page + at, offs[k]);', '            else put_be(page + at, s + 176152u);'),
        'little-endian offset': ('            else put_be(page + at, offs[k]);', '            else put_be(page + at, __builtin_bswap32(offs[k]));'),
        'any entry offset': ('    if (!entry || peek(entry + ENTRY_OFFSET) != B25_OFFSET)', '    if (!entry)'),
        'switches MainB2': ('        if (same(peek(e + ENTRY_NAME), PAGE)) entry = e;',
                            '        if (same(peek(e + ENTRY_NAME), SCREEN) && PAGE) entry = e;'),
        'accepts any pool': ('        !uis_pool_known(reader))', '        0)'),
        'stack name': ('            def[1] = (uint32_t)(uintptr_t)NAME;',
                       '            def[1] = (uint32_t)(uintptr_t)screen_words;'),
        'nonzero default': ('                     n == SL_MENU_LAB_FOCUS ? SL_LAB_FOCUS0 : 0u;', '                     1u;'),
        'text as integer': ('        uint32_t type = SL_MENU_IS_TEXT(n) ? VARIABLE_TEXT : VARIABLE_INT;',
                            '        uint32_t type = VARIABLE_INT;'),
        'registers fewer': ('    for (uint32_t n = 0; n < SL_MENU_VARIABLES; ++n) {\n        const char *NAME',
                            '    for (uint32_t n = 0; n < 5; ++n) {\n        const char *NAME'),
        'reads from the start of the BIN': (
            '        ok = f_read(fobj, file, SL_MENU_AT, &actual) && actual == SL_MENU_AT;\n', ''),
    }

    def test_every_mutation_is_caught(self):
        with tempfile.TemporaryDirectory(prefix='sl-menu-mut-') as tmp:
            for index, (name, seam) in enumerate(self.MUTATIONS.items()):
                with self.subTest(mutation=name):
                    lib = build(tmp, seam, f'm{index}.dylib')

                    class Against(MenuTests):
                        @classmethod
                        def setUpClass(cls):
                            cls.lib = lib

                        @classmethod
                        def tearDownClass(cls):
                            pass
                    result = unittest.TestResult()
                    unittest.defaultTestLoader.loadTestsFromTestCase(Against).run(result)
                    self.assertFalse(result.wasSuccessful(), f'{name} was not caught')


if __name__ == '__main__':
    unittest.main(verbosity=1)
