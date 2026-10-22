#!/usr/bin/env python3
"""The MODE list (sl_modes.c) against the real firmware mode tables, offline.

sl_modes.c + sl_modes_fixture.c on the host.  The fixture holds the image's
70 metadata / timing records and the plan's RATETAB / TMGTAB at their real
addresses, and a model with stock modelCSV semantics.  Asserted:
  - the scan is the recipe's own acceptance: every listed mode, put in AXIS
    (its raster, forced), solves in imx410_block.expected_recipe, and every
    mode left out does not;
  - the model ends holding exactly those rows ("M<id> WxH", xx, blank, 1, 2 --
    the lab list's columns), best guessed quality first, or one
    greyed "No matching"; SL_ModeCount follows; views notified once;
  - the MODE list follows bit depth and FILTER FPS, independent of the user's
    frame-rate setting; changing only that setting does not rebuild the list;
  - any native step that fails stops there, records the step, never notifies,
    and leaves SL_ModeCount at 1; a model that is not modelCSV's is not touched;
  - imx410_fmt's donor record is read from RECIPE's stock copy.
No camera.
"""
import ctypes as ct
import re
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import imx410_plan as PL  # noqa: E402
import imx410_block as K  # noqa: E402
import imx410_rate_native as RN  # noqa: E402
from imx410_full import Registry, META, TIMING  # noqa: E402

IMG = PL.FIRMWARE.read_bytes()
B = 0xC0000000
REG = Registry(IMG)
DESC = 0xC2F1E654                     # the imager descriptor, as read on camera
COUNT_DESC = 0x51000000
N_RATE = len(K.RATE_KEYS)
ROWS, OOB, NOTIFIED, STEP, NROWS, RUNS, KEY, CALLS, LOADED = range(9)
OK, NOT_INSTALLED, NO_IMAGER, FIND, COUNT, LOAD, GET, IFACE, NOT_CSV, DELETE, INSERT, WRITE, \
    NOTIFY = range(13)
BITS = (8, 10, 12, 14)
# the menu's frame-rate setting (internal enum) per RATE_KEYS index; 239.76 is
# stored as 119.88 (7) plus the RAM flag RATE240 (SETTINGS_AREA_FIRST_RULE)
INTERNAL = {0: 1, 1: 12, 2: 2, 3: 3, 4: 13, 5: 4, 6: 5, 7: 6, 8: 7, 9: 7}


def menu(lib, bit, ridx):
    lib.slm_settings(1 if bit == 14 else 0, INTERNAL[ridx])
    lib.slm_word(RN.RATE240, 1 if ridx == 9 else 0)
IFACE_AT = 0x53000000
# modelCSV's interface slots -> its wrappers (the image's table at 0xC2E01DB0)
WRAPPERS = {o: struct.unpack_from('<I', IMG, 0xC2E01DB0 - B + o)[0] for o in (0x14, 0x18, 0x30, 0x34, 0x38)}


def build(directory, replace=None, calc_only=False):
    source = HERE / 'sl_modes.c'
    if replace:
        old, new = replace
        text = source.read_text()
        if text.count(old) != 1:
            raise AssertionError('mutation seam not found once: ' + old[:60])
        source = pathlib.Path(directory) / 'mut.c'
        source.write_text(text.replace(old, new))
    if calc_only:
        calc = pathlib.Path(directory) / 'calc_only.c'
        calc.write_text(source.read_text() + '\nstatic uint32_t sl_menu_export(struct sl_menu *m) { (void)m; return 0; }\nstatic uint32_t sl_menu_apply(struct sl_menu *m) { (void)m; return 0; }\n')
        source = calc
    out = pathlib.Path(directory) / ('slmodes%d-%d.dylib' % (abs(hash(replace)), calc_only))
    subprocess.run([shutil.which('clang') or 'clang', '-shared', '-fPIC', '-O1', '-std=c11',
                    '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', '-DSL_MENU_HOST_TEST',
                    f'-DSL_AXIS={PL.AXIS:#x}u', f'-DSL_RECIPE={PL.RECIPE:#x}u', f'-DSL_GTAB={PL.GTAB:#x}u',
                    f'-DSL_FLAG=0xC0731C08u', f'-DSL_ASPTAB={PL.ASPTAB:#x}u',
                    f'-DSL_COLTAB={PL.COLTAB:#x}u', f'-DSL_MAPPING_SLOT={PL.MAPPING + PL.PRIVATE_PROFILE * 4:#x}u',
                    f'-DSL_RATETAB={PL.RATETAB:#x}u', f'-DSL_TMGTAB={PL.TMGTAB:#x}u',
                    f'-DSL_NRATE={N_RATE}u', f'-DSL_RATE240={RN.RATE240:#x}u',
                    *(['-DSL_CALC_ONLY'] if calc_only else []), '-I', str(HERE), str(source),
                    str(HERE / 'sl_modes_fixture.c'), '-o', str(out)],
                   check=True, capture_output=True, text=True, timeout=60)
    lib = ct.CDLL(str(out))
    for fn, args, ret in (('reset', [], None), ('word', [ct.c_uint32] * 2, None),
                          ('peek', [ct.c_uint32], ct.c_uint32),
                          ('bytes', [ct.c_uint32, ct.c_char_p, ct.c_uint32], None),
                          ('install', [ct.c_uint32], None), ('fail_at', [ct.c_uint32], None),
                          ('iface', [ct.c_uint32], None), ('loaded', [ct.c_uint32], None),
                          ('found', [ct.c_uint32], None),
                          ('modes', [], ct.c_uint32), ('get', [ct.c_uint32], ct.c_uint32),
                          ('scan', [ct.c_uint32, ct.c_uint32, ct.c_char_p], ct.c_uint32),
                          ('cell', [ct.c_uint32, ct.c_uint32], ct.c_char_p),
                          ('log', [], ct.c_char_p), ('id', [ct.c_uint32], ct.c_uint32),
                          ('seen_iface', [], ct.c_uint32),
                          ('pages', [ct.c_uint32] * 3, None), ('reg_result', [ct.c_uint32], None),
                          ('ui', [ct.c_uint32], ct.c_uint32), ('pages_get', [ct.c_uint32], ct.c_uint32),
                          ('live', [], ct.c_uint32), ('settings', [ct.c_uint32] * 2, None),
                          ('no_settings', [], None),
                          ('panel_value', [ct.c_uint32] * 2, None), ('subs', [], ct.c_uint32),
                          ('sub_name', [ct.c_uint32], ct.c_char_p), ('fire', [ct.c_uint32], ct.c_uint32),
                          ('posts', [], ct.c_char_p), ('clear_posts', [], None), ('panel_size', [ct.c_uint32, ct.c_uint32], None), ('aux_cell', [ct.c_uint32] * 3, ct.c_char_p), ('aux_notified', [ct.c_uint32], ct.c_uint32), ('readout', [ct.c_uint32, ct.c_uint32], None), ('rec_cap', [ct.c_uint32, ct.c_uint32], None), ('fit', [ct.c_uint32], None),
                          ('tick', [ct.c_uint32], None)):
        f = getattr(lib, 'slm_' + fn)
        f.argtypes, f.restype = args, ret
    return lib


def reference(bit, ridx):
    """Modes the recipe solves when that mode is forced with its own raster."""
    out = []
    for m in REG.modes:
        if m.mid == 0:
            continue                    # 0 is also AXIS's "auto"; checked apart
        ax = K.axis_words(bit=bit, rate=K.RATE_KEYS[ridx], raster=m.raw, mode=m.mid)
        r = K.expected_recipe(REG, ax)
        if r[K.R_VALID] == 1:
            assert r[K.R_MODE] == m.mid
            out.append(m.mid)
    return sorted(out, key=quality)


def reference_any(bit):
    """Modes that solve at least one supported rate, in MODE quality order."""
    return sorted(set().union(*(reference(bit, ridx) for ridx in range(N_RATE))), key=quality)


def quality(mid):
    """The list's order (the user: guessed quality, best first): less reduction,
    slower rolling shutter (larger HMAX), lower design rate, larger raster, id."""
    m = REG.by_id[mid]
    i = REG.modes.index(m)
    row = META - B + 0x64 * i
    w = lambda o: struct.unpack_from('<I', IMG, row + o)[0]
    hmax = struct.unpack_from('<I', IMG, TIMING - B + 0x20 * i + 4)[0] & 0xFFFF
    return (w(0x4C) * w(0x50), -hmax, w(0x40), -w(4) * w(8), mid)


def mode_fps100(mid):
    """The fastest readout rate used by FILTER FPS, in hundredths of a frame."""
    m = REG.by_id[mid]
    i = REG.modes.index(m)
    vblank = struct.unpack_from('<I', IMG, META - B + 0x64 * i + 0x5C)[0]
    return 72000000 * 100 // ((m.raw[1] + vblank) * m.hmax)


def ratio_label(w, h):
    """" (16:9)": the common name within 1 %, else " (1.92:1)" (sl_modes.c ratio_label)."""
    a = (w * 1000 + h // 2) // h
    for v, name in ((1000, '1:1'), (1333, '4:3'), (1500, '3:2'), (1778, '16:9'), (1850, '1.85:1'),
                    (2000, '2:1'), (2390, '2.39:1'), (3000, '3:1')):
        if abs(a - v) * 100 <= v:
            return f' ({name})'
    c = (a + 5) // 10
    return f' ({c // 100}.{c % 100:02d}:1)'


def mm(px):
    v = (px * 359 + 3032) // 6064
    return f'{v // 10}.{v % 10}'


def max_out(w, h, bw=1, bh=1, cap=None):
    """the largest visible output: (raster / bin) aligned, less the record
    matrix's margins (16 x 10) -- sl_modes.c max_w / max_h"""
    w, h = w // bw, h // bh
    cw, ch = cap or CAP
    if w > cw and w * ch >= h * cw:
        w, h = cw, h * cw // w
    elif h > ch:
        w, h = w * ch // h, ch
    return (w & ~15) - 16, (h & ~1) - 10


REC_MAX = (0xFFFF, 0xFFFF)   # sl_modes.c REC_MAX_W/H: no envelope since 2026-10-04 (the user)
UHD_CAP = (4176, 2182)       # the old per-side stock maximum, still exercised through the seam
LIFTED = (1 << 20, 1 << 20)
CAP = LIFTED             # the geometry tests run without the envelope; test_the_record_envelope with it


def label(mid):
    """A MODE row's text: "M98 3032x2012" (the mode's raster)."""
    m = REG.by_id[mid]
    row = META - B + 0x64 * REG.modes.index(m)
    w, h = struct.unpack_from('<II', IMG, row + 4)
    return f'M{mid} {w}x{h}'


class Modes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='sl-modes-')
        cls.lib = build(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def camera(self, lib=None, bit=12, ridx=0, rec_cap=LIFTED):
        lib = lib or self.lib
        lib.slm_reset()
        lib.slm_rec_cap(*rec_cap)
        lib.slm_bytes(META, IMG[META - B:META - B + 70 * 0x64], 70 * 0x64)
        lib.slm_bytes(TIMING, IMG[TIMING - B:TIMING - B + 70 * 0x20], 70 * 0x20)
        lib.slm_word(DESC, TIMING); lib.slm_word(DESC + 8, META); lib.slm_word(DESC + 12, 70)
        lib.slm_word(0xC343B588, DESC)
        rt, tt = K.rate_table(), K.timing_table()
        lib.slm_bytes(PL.RATETAB, rt, len(rt))
        lib.slm_bytes(PL.TMGTAB, tt, len(tt))
        lib.slm_bytes(PL.RECIPE, bytes(4 * K.RECIPE_WORDS), 4 * K.RECIPE_WORDS)
        menu(lib, bit, ridx)
        lib.slm_word(0xC37B7048, 0x52000000)                # the UI app
        for off, w in WRAPPERS.items():                       # the interface table, in RAM
            lib.slm_word(IFACE_AT + off, w)
        lib.slm_word(COUNT_DESC + 8, 0)
        lib.slm_install(COUNT_DESC)
        return lib

    def scan(self, bit, ridx, lib=None):
        buf = ct.create_string_buffer(80)
        n = (lib or self.lib).slm_scan(bit, ridx, buf)
        return list(buf.raw[:n])

    def rows(self, lib=None):
        lib = lib or self.lib
        return [[lib.slm_cell(r, c).decode() for c in range(6)] for r in range(lib.slm_get(ROWS))]

    # ---- the scan ----------------------------------------------------------
    def test_scan_is_the_recipes_acceptance(self):
        self.camera()
        for bit in BITS:
            for ridx in range(N_RATE):
                with self.subTest(bit=bit, rate=K.RATE_KEYS[ridx]):
                    got = self.scan(bit, ridx)
                    self.assertEqual([i for i in got if i], [i for i in reference(bit, ridx) if i])
                    self.assertEqual(got, sorted(got, key=quality))

    def test_mode_0_is_listed_only_when_it_solves(self):
        """M0 shares AXIS's 'auto' value: listed when its own conditions pass,
        and then the recipe with raster 0's (auto) solves to a mode of that raster."""
        self.camera()
        m0 = REG.by_id[0]
        for ridx in range(N_RATE):
            if 0 in self.scan(12, ridx):
                r = K.expected_recipe(REG, K.axis_words(bit=12, rate=K.RATE_KEYS[ridx], raster=m0.raw))
                self.assertEqual(r[K.R_VALID], 1)

    def test_counts(self):
        self.camera()
        got = {bit: [len(self.scan(bit, r)) for r in range(N_RATE)] for bit in (12, 14)}
        self.assertEqual(self.scan(8, 3), self.scan(12, 3))     # 8 / 10 bit use the 12-bit modes
        self.assertTrue(all(n <= 70 for v in got.values() for n in v))

    def test_donor_timing_comes_from_the_stock_copy(self):
        lib = self.camera()
        base = self.scan(12, 3)
        i = next(k for k, m in enumerate(REG.modes) if m.mid == base[0])
        stock = struct.unpack_from('<I', IMG, TIMING - B + 0x20 * i + 4)[0]
        lib.slm_word(TIMING + 0x20 * i + 4, (stock & 0xFFFF0000) | 999)   # imx410_fmt's rewrite
        self.assertNotIn(base[0], self.scan(12, 3))                         # unknown hmax
        lib.slm_word(PL.RECIPE + 4 * K.R_VALID, 1)
        lib.slm_word(PL.RECIPE + 4 * K.R_IDX, i)
        lib.slm_word(PL.RECIPE + 4 * K.R_SAVE0, stock)
        self.assertEqual(self.scan(12, 3), base)

    def test_an_unsolvable_budget_cell_drops_the_mode(self):
        """With the shipped tables every cell a mode reaches is solvable, so this
        rule never bites today; og3krecipe still fails on a 0 cell, so must we."""
        lib = self.camera()
        ridx = 3
        first = self.scan(12, ridx)[0]
        hmax = struct.unpack_from('<I', IMG, TIMING - B + 0x20 * REG.modes.index(REG.by_id[first]) + 4)[0] & 0xFFFF
        lib.slm_word(PL.TMGTAB + 4 * (K.HMAX_SET.index(hmax) * N_RATE + ridx), 0)
        self.assertNotIn(first, self.scan(12, ridx))

    def test_any_rate_scan_is_the_union_and_bad_index_lists_nothing(self):
        lib = self.camera()
        for bit in (12, 14):
            got = self.scan(bit, N_RATE)
            self.assertEqual([i for i in got if i], [i for i in reference_any(bit) if i])
            self.assertEqual(got, sorted(got, key=quality))
        self.assertEqual(self.scan(12, N_RATE + 1), [])
        lib.slm_word(0xC343B588, 0)
        self.assertEqual(self.scan(12, N_RATE), [])

    # ---- the rewrite -------------------------------------------------------
    def test_rewrites_the_model_to_the_scan(self):
        lib = self.camera(bit=12, ridx=3)
        want = self.scan(12, N_RATE)
        self.assertEqual(lib.slm_modes(), OK)
        self.assertEqual(self.rows(), [[str(k + 1), label(i), 'xx', 'blank', '1', '2'] for k, i in enumerate(want)])
        self.assertEqual(lib.slm_peek(COUNT_DESC + 8), len(want))
        self.assertEqual([lib.slm_id(k) for k in range(len(want))], want)
        self.assertEqual((lib.slm_get(NOTIFIED), lib.slm_get(OOB)), (1, 0))
        log = lib.slm_log().decode().split(';')
        self.assertEqual(log[:7], ['find', 'count', 'load', 'get', 'iface', 'rows', 'delete'])
        self.assertEqual(log[-2], 'notify')

    def test_the_list_follows_bit_depth_but_not_the_user_rate(self):
        """sl_menu_live follows bit depth. The user's FPS changes the readout,
        but it does not narrow or rebuild the MODE list."""
        lib = self.camera(bit=12, ridx=3)
        lib.slm_modes()
        self.assertEqual(len(self.rows()), len(self.scan(12, N_RATE)))
        runs = lib.slm_get(RUNS)
        current_bit = 12
        for bit, key in ((12, '120'), (12, '240'), (14, '30'), (14, '120'), (10, '60')):
            with self.subTest(bit=bit, rate=key):
                ridx = K.RATE_KEYS.index(key)
                menu(lib, bit, ridx)
                self.assertEqual(lib.slm_live(), OK)
                want = self.scan(bit, N_RATE)
                self.assertEqual([r[1] for r in self.rows()], [label(i) for i in want] or ['No matching'])
                self.assertEqual(lib.slm_peek(COUNT_DESC + 8), max(1, len(want)))
                if (bit == 14) != (current_bit == 14):
                    runs += 1
                self.assertEqual(lib.slm_get(RUNS), runs)
                current_bit = bit

    def test_rate240_changes_the_readout_but_not_the_mode_list(self):
        lib = self.ui_camera()
        menu(lib, 12, 8)
        lib.slm_ui(0)
        rows = self.rows()
        runs, calls = lib.slm_get(RUNS), lib.slm_get(CALLS)
        lib.slm_word(RN.RATE240, 1)                       # same stored setting (7), 240 chosen
        lib.slm_clear_posts()
        lib.slm_live()
        self.assertEqual(self.rows(), rows)
        self.assertEqual((lib.slm_get(RUNS), lib.slm_get(CALLS)), (runs, calls))
        self.assertIn('SL_O_Rate=239.76p ', lib.slm_posts().decode())

    def test_the_hidden_15_fps_does_not_narrow_the_list(self):
        lib = self.camera()
        lib.slm_settings(0, 0)
        lib.slm_modes()
        self.assertEqual([r[1] for r in self.rows()], [label(i) for i in reference_any(12)])

    def test_no_settings_manager_touches_nothing(self):
        lib = self.camera()
        lib.slm_no_settings()
        lib.slm_modes()
        self.assertEqual((lib.slm_get(CALLS), self.rows()[0][1]), (0, 'No matching'))

    def test_an_instance_already_there_is_not_loaded_again(self):
        lib = self.camera()
        lib.slm_loaded(1)
        self.assertEqual(lib.slm_modes(), OK)
        self.assertNotIn('load', lib.slm_log().decode().split(';'))

    def test_nothing_matching_is_one_greyed_row(self):
        lib = self.camera(bit=14, ridx=K.RATE_KEYS.index('120'))
        self.assertEqual(self.scan(14, K.RATE_KEYS.index('120')), [])
        lib.slm_panel_value(13, 9)                         # FILTER FPS 119.88p+
        self.assertEqual(lib.slm_modes(), OK)
        self.assertEqual(self.rows(), [['1', 'No matching', 'xx', 'blank', '0', '0']])
        self.assertEqual(lib.slm_peek(COUNT_DESC + 8), 1)

    def test_only_user_fps_changed_does_not_rebuild(self):
        lib = self.camera()
        lib.slm_modes()
        calls = lib.slm_get(CALLS)
        self.assertEqual(lib.slm_modes(), OK)
        self.assertEqual((lib.slm_get(CALLS), lib.slm_get(RUNS)), (calls, 1))
        menu(lib, 12, K.RATE_KEYS.index('120'))
        self.assertEqual(lib.slm_modes(), OK)
        self.assertEqual((lib.slm_get(CALLS), lib.slm_get(RUNS)), (calls, 1))
        self.assertEqual(len(self.rows()), len(self.scan(12, N_RATE)))
        menu(lib, 14, K.RATE_KEYS.index('120'))
        self.assertEqual(lib.slm_modes(), OK)
        self.assertEqual(lib.slm_get(RUNS), 2)

    def test_not_installed_touches_nothing(self):
        lib = self.camera()
        lib.slm_install(COUNT_DESC)
        lib2 = self.lib
        lib2.slm_reset()
        self.assertEqual(lib2.slm_modes(), NOT_INSTALLED)
        self.assertEqual(lib2.slm_get(CALLS), 0)

    def test_every_failing_step_stops_there(self):
        lib = self.camera()
        lib.slm_modes()
        total = lib.slm_get(CALLS)
        expect = {1: FIND, 2: COUNT, 3: LOAD, 4: GET, 5: IFACE, 6: DELETE, 7: DELETE, 8: INSERT}
        for k in range(1, total + 1):
            with self.subTest(call=k):
                lib = self.camera()
                lib.slm_fail_at(k)
                step = lib.slm_modes()
                log = lib.slm_log().decode().split(';')
                if log[k - 1:k] == ['notify']:
                    self.assertEqual(step, NOTIFY)
                elif k in expect:
                    self.assertEqual(step, expect[k])
                else:
                    self.assertIn(step, (INSERT, WRITE))
                self.assertEqual(lib.slm_get(NOTIFIED), 0)
                self.assertEqual(lib.slm_peek(COUNT_DESC + 8), 1)
                self.assertEqual(lib.slm_get(STEP), step)
                self.assertEqual(lib.slm_get(OOB), 0)

    def test_the_interface_is_judged_by_its_slots_not_its_address(self):
        """r10 on camera: the interface was not at 0xC2E01DB0 and nothing was written."""
        lib = self.camera()
        self.assertEqual(lib.slm_modes(), OK)
        self.assertEqual(lib.slm_seen_iface(), IFACE_AT)
        self.assertEqual(WRAPPERS, {0x14: 0xC05F4861, 0x18: 0xC05F4879, 0x30: 0xC05F4929,
                                    0x34: 0xC05F4941, 0x38: 0xC05F4959})

    def test_a_model_that_is_not_modelcsv_is_not_touched(self):
        for off in WRAPPERS:
            with self.subTest(slot=hex(off)):
                lib = self.camera()
                lib.slm_word(IFACE_AT + off, WRAPPERS[off] + 0x100)
                self.assertEqual(lib.slm_modes(), NOT_CSV)
                self.assertEqual(self.rows()[0][1], 'No matching')
                self.assertNotIn('delete', lib.slm_log().decode())

    def test_a_list_not_found_is_not_touched(self):
        lib = self.camera()
        lib.slm_found(0)
        self.assertEqual(lib.slm_modes(), FIND)
        self.assertEqual(lib.slm_log().decode(), 'find;')

    # ---- the private pages (sl_pages.py) ----------------------------------
    APP, READER, PACK = 0x52000000, 0x55000000, 0x56000000
    STATE, NEW_RD, REG_CALLS, REG_APP, REG_PACK, REG_LEN = range(6)

    def ui_camera(self, screens=221, cap=224, reader_app=None, machines=17, mcap=24, rec_cap=LIFTED):
        lib = self.camera(rec_cap=rec_cap)
        lib.slm_word(self.APP + 0x80, screens); lib.slm_word(self.APP + 0x84, cap)
        lib.slm_word(self.APP + 0xF8, machines); lib.slm_word(self.APP + 0xFC, mcap)
        lib.slm_word(self.READER + 8, self.APP if reader_app is None else reader_app)
        lib.slm_word(self.READER + 0x10, 176241); lib.slm_word(self.READER + 0x14, 0x57000000)  # shared pool
        lib.slm_pages(self.READER, self.PACK, 481)
        return lib

    def test_pages_register_once_and_take_the_shared_pool(self):
        lib = self.ui_camera()
        self.assertEqual(lib.slm_ui(0), OK)                  # any resolution: pages, then MODE
        g = lib.slm_pages_get
        self.assertEqual((g(self.STATE), g(self.REG_CALLS), g(self.REG_APP), g(self.REG_PACK), g(self.REG_LEN)),
                         (1, 1, self.APP, self.PACK, 481))
        rd = g(self.NEW_RD)
        self.assertEqual((lib.slm_peek(rd + 0x10), lib.slm_peek(rd + 0x14)), (176241, 0x57000000))
        self.assertEqual(lib.slm_get(RUNS), 1)              # the MODE list kept current even outside CUSTOM
        self.assertEqual(lib.slm_ui(1), OK)                  # nothing changed: no work, pages not again
        self.assertEqual((g(self.REG_CALLS), lib.slm_get(RUNS)), (1, 1))

    def key(self, lib, code):
        """The page writes SL_O_Key; the GUI calls back (subscription 1)."""
        lib.slm_panel_value(18, code)
        lib.slm_clear_posts()
        self.assertEqual(lib.slm_fire(1), 0)
        lib.slm_panel_value(18, 0)
        return lib.slm_posts().decode()

    def test_the_panel_is_edited_in_place(self):
        """OUTPUT's info panel, the date / time page's way: subscribed once with the
        pages; keys step the field being edited, every value snapped to the rules
        (width x16, height even, within the sensor / binning); RWZM shown."""
        lib = self.ui_camera()
        lib.slm_ui(0)
        self.assertEqual([lib.slm_sub_name(i) for i in range(lib.slm_subs())],
                         [b'MV_SLScale', b'SL_O_Key', b'SL_M_Sel', b'SL_O_RFps',
                          b'SL_F_Bit', b'SL_F_Fps', b'SL_F_Width', b'SL_F_Prop', b'SL_F_Crop'])
        # as if the mode were just chosen: AUTO, the largest, 1 x 1; RWZM the scale, 1.00
        p = lib.slm_posts()
        # the readout is the first (best) mode's raster, M123 6064x3412 (the user:
        # the mode's largest output drives OUTPUT)
        self.assertIn(b'SL_ModeMax=61 SL_M_Text=M123 6064x3412 ', p)
        # the largest visible: 6064 x 3412 less the margins (16 x 10)
        self.assertIn(b'MV_SLScale=0 SL_O_W=6048 SL_O_H=3402 SL_O_BH=1 SL_O_BV=1 SL_O_BTxt=bin '
                      b'SL_O_SW=1.00 SL_O_SH=1.00 SL_O_A0=0 SL_O_A1=0 SL_O_A2=0 SL_O_A3=0 '
                      b'SL_C_Text=0x0 (6064x3412) SL_O_Rate=23.98p 740 MB/s ', p)   # 6048*3402 * 12 bit * 23.976 / 8
        lib.slm_readout(6080, 4050)                          # the arithmetic below: largest visible 6064 x 4040
        lib.slm_panel_value(7, 16); lib.slm_fire(0)          # Free: the sides step alone
        lib.slm_panel_size(1920, 1280)
        lib.slm_clear_posts(); lib.slm_fit(1)
        self.assertIn('SL_O_W=1920 SL_O_H=1280 ', lib.slm_posts().decode())
        p = self.key(lib, 5)                                 # Right / OK on the row: edit, W first
        self.assertIn('SL_O_A0=1 SL_O_A1=0', p)
        self.assertIn('SL_O_Key=0', p)                       # the key posted back to 0
        lib.slm_tick(5000)
        self.assertIn('SL_O_W=1936 ', self.key(lib, 3))      # Up: +16 (Free: H stays)
        lib.slm_tick(9000)
        self.assertIn('SL_O_W=1920 ', self.key(lib, 4))      # Down: -16
        self.assertIn('SL_O_W=2080 ', self.key(lib, 7))      # dial: x10
        self.assertIn('SL_O_A1=1', self.key(lib, 2))         # Right: H
        self.assertIn('SL_O_H=1282 ', self.key(lib, 3))      # +2
        # held: repeats inside 350 ms accelerate (x5 after 10, x20 after 25)
        t, h = 20000, 1282
        for n in range(30):
            t += 100
            lib.slm_tick(t)
            p = self.key(lib, 3)
            h += 2 * (20 if n >= 25 else 5 if n >= 10 else 1)
            self.assertIn(f'SL_O_H={h} ', p, n)
        self.key(lib, 2)                                     # binH
        p = self.key(lib, 3)
        self.assertIn('SL_O_BH=3 ', p)                       # binning: the largest output it allows
        self.assertIn('SL_O_W=2000 SL_O_H=4040 ', p)         # 6080/3 = 2026 -> 2016 (x16) - 16; 4040
        self.assertIn('SL_O_SW=1.00 SL_O_SH=1.00', p)        # output / (readout / bin): 2000 / 2026
        self.assertIn('SL_O_A0=1', (self.key(lib, 2), self.key(lib, 2))[1])   # binV, then wrap to W
        lib.slm_tick(60000)
        self.assertIn('SL_O_W=2000 ', self.key(lib, 3))      # at the binning's limit: stays
        self.key(lib, 1); self.key(lib, 1)                   # Left twice: back to binH
        self.assertIn('SL_O_A3=1', self.key(lib, 2))         # binV
        p = self.key(lib, 4)                                 # Down toggles 1 -> 3
        self.assertIn('SL_O_BV=3 ', p)
        self.assertIn('SL_O_H=1340 ', p)                     # 4050/3 = 1350 - 10 = 1340
        self.assertIn('SL_O_A0=1', self.key(lib, 2))         # Right wraps to W
        self.assertIn('SL_O_A0=0', self.key(lib, 6))         # OK: done, no arrow
        lib.slm_ui(0)                                        # not subscribed twice
        self.assertEqual(lib.slm_subs(), 9)

    def test_the_ratio_holds_width_and_height(self):
        """The Ratio row (sl_lists SCALE_ROWS) really holds W:H (the user): the edited
        side leads, the other follows, nearest legal shape; past a limit the other
        side leads."""
        lib = self.ui_camera()
        lib.slm_ui(0)
        lib.slm_readout(6080, 4050)                          # the arithmetic: largest visible 6064 x 4040
        lib.slm_panel_value(7, 5); lib.slm_fire(0)           # 2.39:1 (the row: the largest)
        lib.slm_panel_size(1920, 1280)
        lib.slm_clear_posts(); lib.slm_fit(1)                # at 1920: 803.3 -> 804 (camera r36 showed 802)
        self.assertIn('SL_O_W=1920 SL_O_H=804 ', lib.slm_posts().decode())
        lib.slm_panel_value(7, 6); lib.slm_fire(0)           # 2.40:1 = 12:5, written by the page
        lib.slm_panel_size(1920, 804)
        lib.slm_clear_posts(); lib.slm_fit(1)
        self.assertIn('SL_O_W=1920 SL_O_H=800 ', lib.slm_posts().decode())
        # an exact ratio steps by the common multiple (the user): 12:5 -> 48 x 20
        self.key(lib, 5)
        lib.slm_tick(5000)
        self.assertIn('SL_O_W=1968 SL_O_H=820 ', self.key(lib, 3))
        self.key(lib, 2)                                     # H: the same step, both sides move
        lib.slm_tick(9000)
        self.assertIn('SL_O_W=2016 SL_O_H=840 ', self.key(lib, 3))
        lib.slm_tick(12000)
        self.assertIn('SL_O_W=1968 SL_O_H=820 ', self.key(lib, 4))
        lib.slm_panel_value(7, 5); lib.slm_fire(0)           # 2.39:1 has no usable exact step (3824 x 1600): nearest
        lib.slm_panel_size(1968, 820)
        lib.slm_clear_posts(); lib.slm_fit(1)
        self.assertIn('SL_O_W=1968 SL_O_H=824 ', lib.slm_posts().decode())    # 1968/2.39 = 823.4
        lib.slm_tick(15000)
        self.assertIn('SL_O_W=1984 SL_O_H=830 ', self.key(lib, 3))   # H: the width's x16, H follows
        lib.slm_panel_value(7, 3); lib.slm_fire(0)           # 2:1 -> 16 x 8: 1984 = 124 steps
        lib.slm_panel_size(1984, 830)
        lib.slm_clear_posts(); lib.slm_fit(1)
        self.assertIn('SL_O_W=1984 SL_O_H=992 ', lib.slm_posts().decode())
        self.key(lib, 2); self.key(lib, 2)                   # binV
        p = self.key(lib, 3)                                 # binV 3: H max 1346 -> 168 steps, 2688 x 1344
        self.assertIn('SL_O_BV=3 ', p)
        self.assertIn('SL_O_W=2672 SL_O_H=1336 ', p)         # 4050 / 3 - 10 = 1340 high at most: 167 steps
        lib.slm_panel_value(7, 16); lib.slm_fire(0)          # Free: nothing held
        lib.slm_panel_size(2672, 1336)
        lib.slm_clear_posts(); lib.slm_fit(1)
        self.assertIn('SL_O_W=2672 SL_O_H=1336 ', lib.slm_posts().decode())

    def test_the_ratio_row_maximizes(self):
        """The Ratio row moved: the output is the largest at the new ratio (the user
        2026-10-04) -- one side at its maximum, the shape the ratio's."""
        lib = self.ui_camera()
        lib.slm_ui(0)
        lib.slm_readout(6080, 4050)                          # largest visible 6064 x 4040
        mw, mh = 6064, 4040
        for row in (2, 3, 4, 5, 6, 7, 9, 15, 0, 1):          # AUTO is where it starts: not first
            with self.subTest(row=row):
                lib.slm_panel_size(1920, 1080)               # something small first
                lib.slm_panel_value(7, row); lib.slm_clear_posts(); lib.slm_fire(0)
                p = lib.slm_posts().decode()
                w = int(p.split('SL_O_W=')[-1].split()[0]); h = int(p.split('SL_O_H=')[-1].split()[0])
                self.assertTrue(w <= mw and h <= mh, (w, h))
                self.assertTrue(w > mw - 1200 or h > mh - 500, (row, w, h))   # within one ratio step of a side
                self.assertGreater(w, 1920)

    def test_exact_steps(self):
        """W = num t, H = den t, W x16, H even: the step per ratio."""
        lib = self.ui_camera()
        lib.slm_ui(0)
        lib.slm_readout(6080, 4050)                          # the arithmetic: largest visible 6064 x 4040
        lib.slm_panel_size(1920, 1280)
        self.key(lib, 5)
        for row, (w, h) in ((2, (592, 320)), (3, (16, 8)), (4, (752, 320)), (6, (48, 20)), (7, (1104, 400))):
            with self.subTest(row=row):
                lib.slm_panel_value(7, row); lib.slm_fire(0)  # the row: the largest; then a size
                lib.slm_panel_size(1920, 1280)
                lib.slm_clear_posts(); lib.slm_fit(1)
                p0 = lib.slm_posts().decode()
                W0 = int(p0.split('SL_O_W=')[1].split()[0]); H0 = int(p0.split('SL_O_H=')[1].split()[0])
                self.assertEqual((W0 % w, H0 % h, W0 // w), (0, 0, H0 // h))
                lib.slm_tick(1000000 + 10000 * row)
                p1 = self.key(lib, 3)
                self.assertIn(f'SL_O_W={W0 + w} SL_O_H={H0 + h} ', p1)

    def test_auto_raw_and_the_squeezes(self):
        """AUTO keeps the readout's shape (both sides scaled alike), a squeeze is AUTO
        with the width stretched by it -- one choice with the ratios (the user) --
        and RAW is the whole binned readout, locked."""
        lib = self.ui_camera()
        lib.slm_ui(0)
        lib.slm_readout(6080, 4050)                          # the arithmetic: largest visible 6064 x 4040
        lib.slm_panel_value(7, 15); lib.slm_fire(0)          # 2.0x (the row: the largest)
        lib.slm_panel_size(1920, 1280)
        lib.slm_clear_posts(); lib.slm_fit(1)                # at 1920: H scale half of W's
        self.assertIn('SL_O_W=1920 SL_O_H=640 SL_O_BH=1 SL_O_BV=1 SL_O_BTxt=bin SL_O_SW=0.32 SL_O_SH=0.16 ',
                      lib.slm_posts().decode())
        lib.slm_panel_value(7, 9); lib.slm_fire(0)           # 1.33x: 1920 / 1.33 * 4040/6064 = 961.8
        lib.slm_panel_size(1920, 640)
        lib.slm_clear_posts(); lib.slm_fit(1)
        self.assertIn('SL_O_W=1920 SL_O_H=962 ', lib.slm_posts().decode())
        lib.slm_panel_value(7, 1)                            # RAW: the whole readout
        lib.slm_clear_posts(); lib.slm_fire(0)
        self.assertIn('SL_O_W=6064 SL_O_H=4040 SL_O_BH=1 SL_O_BV=1 SL_O_BTxt=bin SL_O_SW=1.00 SL_O_SH=1.00 ',
                      lib.slm_posts().decode())
        self.key(lib, 5)
        lib.slm_tick(5000)
        self.assertIn('SL_O_W=6064 SL_O_H=4040 ', self.key(lib, 4))   # locked: Down does nothing
        self.key(lib, 2); self.key(lib, 2)                   # binH 3: RAW follows
        self.assertIn('SL_O_W=2000 SL_O_H=4040 ', self.key(lib, 3))
        lib.slm_panel_value(7, 0)                            # AUTO under binH 3: the pixels' 6064:4040
        lib.slm_clear_posts(); lib.slm_fire(0)               # (the user: the ratio is the final pixels')
        self.assertIn('SL_O_W=2000 SL_O_H=1332 SL_O_BH=3 SL_O_BV=1 SL_O_BTxt=H(1,1,1) soft SL_O_SW=1.00 SL_O_SH=0.33 ',
                      lib.slm_posts().decode())
        lib.slm_panel_value(7, 15)                           # 2.0x under binH 3: still 2 x 6064:4040 in pixels
        lib.slm_clear_posts(); lib.slm_fire(0)
        self.assertIn('SL_O_W=2000 SL_O_H=666 ', lib.slm_posts().decode())
        lib.slm_panel_value(7, 0)                            # AUTO, then Up through every kernel
        lib.slm_fire(0)
        lib.slm_tick(90000)
        t = 91000                                            # every kernel, soft then r1, then 1
        for cap in ('H(1,2,1) soft', 'H(1,4,1) soft', 'H(1,6,1) soft', 'H(1,14,1) soft', 'H(0,1,0) soft',
                    'H(1,1,1) std', 'H(1,2,1) std', 'H(1,4,1) std', 'H(1,6,1) std', 'H(1,14,1) std', 'H(0,1,0) std'):
            self.assertIn(f'SL_O_BH=3 SL_O_BV=1 SL_O_BTxt={cap} ', self.key(lib, 3), cap)   # the kernel only (no x5)
            t += 1000
            lib.slm_tick(t)
        self.assertIn('SL_O_BH=1 SL_O_BV=1 SL_O_BTxt=bin ', self.key(lib, 3))

    def test_a_mode_chosen_resets_the_output(self):
        """MODE row changed (SL_M_Sel): the largest output at AUTO, binning 1 x 1,
        and the Ratio row back to AUTO (the user 2026-10-03)."""
        lib = self.ui_camera()
        lib.slm_ui(0)
        lib.slm_panel_value(7, 3)                            # 16:9
        lib.slm_fire(0)
        self.key(lib, 5); self.key(lib, 2); self.key(lib, 2)
        self.assertIn('SL_O_BH=3 ', self.key(lib, 3))        # binH 3
        lib.slm_tick(50000)
        self.assertIn('SL_O_BTxt=H(1,2,1) soft ', self.key(lib, 3))   # and another kernel
        lib.slm_panel_value(16, 1)                           # another mode: M124 4176x2174
        lib.slm_clear_posts()
        self.assertEqual(lib.slm_fire(2), 0)
        p = lib.slm_posts().decode()
        w, h = REG.by_id[reference(12, 0)[1]].raw
        self.assertIn('MV_SLScale=0 ', p)
        mw, mh = max_out(w, h)
        self.assertIn(f'SL_O_W={mw} SL_O_H={mh} SL_O_BH=1 SL_O_BV=1 SL_O_BTxt=bin SL_O_SW=1.00 SL_O_SH=1.00 ', p)
        lib.slm_clear_posts(); lib.slm_fire(0)               # the row now reads AUTO: nothing moves
        self.assertIn(f'SL_O_W={mw} SL_O_H={mh} ', lib.slm_posts().decode())
        lib.slm_tick(70000)
        p = self.key(lib, 3)                                 # still on binH: hbin 3 = the mode's raster / 3
        self.assertIn(f'SL_O_W={max_out(w, h, 3)[0]} ', p)
        self.assertIn('SL_O_BTxt=H(1,1,1) soft ', p)             # the kernel was reset with the mode
        lib.slm_clear_posts(); lib.slm_fire(2)               # the same mode again: no reset
        self.assertNotIn('MV_SLScale', lib.slm_posts().decode())

    def test_no_static_name_is_a_field_name(self):
        """The ARM build prefixes sl_modes.c's statics (sl_modes__x), and a field
        of struct sl_menu with the same name stops compiling -- three times so far
        (rwzm_text, ro_w, area_w).  Caught here, before the ARM build."""
        fields = set(re.findall(r'\b(\w+)\s*(?:\[[^\]]*\])*\s*[;,]',
                                re.search(r'struct sl_menu \{(.*?)\n\};', (HERE / 'sl_menu.h').read_text(), re.S)[1]))
        statics = set(re.findall(r'^static [\w\s\*]*?\b(\w+)\(', (HERE / 'sl_modes.c').read_text(), re.M))
        self.assertEqual(fields & statics, set())

    def test_auto_is_the_area_shape(self):
        """AUTO holds the shape of the sensor area the mode covers, not its raster's
        (the user: M12, 2016 x 672 reduced 3 x 6, covers 3:2 -- the width squeezes)."""
        lib = self.ui_camera()
        lib.slm_ui(0)
        for ridx in range(N_RATE):                           # a rate whose list has M12
            if 12 in reference(12, ridx):
                break
        menu(lib, 12, ridx)
        lib.slm_live()
        k = reference(12, ridx).index(12)
        lib.slm_panel_value(16, k)
        lib.slm_clear_posts(); lib.slm_fire(2)
        p = lib.slm_posts().decode()
        self.assertIn('SL_M_Text=M12 2016x672 ', p)
        # 2016 - 16 = 2000 wide at most; 3:2 from 672 - 10 = 662 high: 992 x 662 (the width squeezed)
        self.assertIn('SL_O_W=992 SL_O_H=662 SL_O_BH=1 SL_O_BV=1 SL_O_BTxt=bin SL_O_SW=0.50 SL_O_SH=1.00 ', p)

    def test_the_data_rate(self):
        """W x H x bits x fps / 8 in MB/s, from the bit-depth and frame-rate settings."""
        lib = self.ui_camera()
        lib.slm_ui(0)
        lib.slm_readout(6080, 4050)                          # the arithmetic: largest visible 6064 x 4040
        lib.slm_panel_value(7, 16); lib.slm_fire(0)          # Free: the size stays
        lib.slm_panel_size(1920, 1080)
        lib.slm_clear_posts(); lib.slm_fit(1)
        self.assertIn('SL_O_Rate=23.98p 75 MB/s ', lib.slm_posts().decode())    # 1920*1080*1.5*23.976 = 74.6
        lib.slm_settings(1, 7)            # 14-bit, 119.88
        lib.slm_clear_posts(); lib.slm_fire(0)
        self.assertIn('SL_O_Rate=119.88p 435 MB/s ', lib.slm_posts().decode())   # *1.75 *119.88 = 435.1
        lib.slm_settings(4, 13)            # 8-bit, 48
        lib.slm_clear_posts(); lib.slm_fire(0)
        self.assertIn('SL_O_Rate=48p 100 MB/s ', lib.slm_posts().decode())   # *1 *48 = 99.5
        # the row picks another rate (the user: every rate's result): 1 + rate_index
        lib.slm_settings(0, 1)
        lib.slm_panel_value(26, 10)                          # 239.76
        lib.slm_clear_posts(); lib.slm_fire(3)
        self.assertIn('SL_O_Rate=239.76p 745 MB/s ', lib.slm_posts().decode())
        lib.slm_panel_value(26, 4)                           # 29.97
        lib.slm_clear_posts(); lib.slm_fire(3)
        self.assertIn('SL_O_Rate=29.97p 93 MB/s ', lib.slm_posts().decode())
        lib.slm_panel_size(6064, 4040); lib.slm_settings(1, 1); lib.slm_panel_value(26, 10)
        lib.slm_clear_posts(); lib.slm_fire(3)                # 14-bit full at 239.76: five digits
        self.assertIn('SL_O_Rate=239.76p 10279 MB/s ', lib.slm_posts().decode())

    def test_the_mode_row_text_and_cap(self):
        """SL_ModeMax = rows - 1 (the lists' caps), SL_M_Text = the chosen row's
        label; a chosen row past a shorter list goes back to the first."""
        lib = self.ui_camera()
        lib.slm_ui(0)
        want = reference(12, 0)
        lib.slm_panel_value(16, 7)                           # the eighth row
        lib.slm_clear_posts(); lib.slm_fire(2)
        p = lib.slm_posts().decode()
        self.assertIn(f'SL_ModeMax={len(want) - 1} SL_M_Text={label(want[7])} ', p)
        mw, mh = max_out(*REG.by_id[want[7]].raw)
        self.assertIn(f'SL_O_W={mw} SL_O_H={mh} ', p)   # and the output reset: that mode's largest
        menu(lib, 14, 9)                                     # depth change shortens and clamps the list
        lib.slm_clear_posts(); lib.slm_live()
        short = reference_any(14)
        self.assertLess(len(short), 8)
        self.assertIn(f'SL_M_Sel=0 SL_ModeMax={len(short) - 1} SL_M_Text={label(short[0])} ',
                      lib.slm_posts().decode())
        runs = lib.slm_get(RUNS)
        menu(lib, 14, 0)                                     # user's FPS does not change the rows
        lib.slm_live()
        self.assertEqual((lib.slm_get(RUNS), [r[1] for r in self.rows()]),
                         (runs, [label(i) for i in short]))

    def test_the_mode_diagram(self):
        """White = the sensor drawn 420 x 280 at (40, 180); green = the area the chosen
        mode uses (raster x reduction), centred; red = its largest output (the
        raster, x16 / even) at the sensor's pixel scale, centred (the user); labels
        name them, then the mode's rate (72 MHz / (hmax (vmax - 1) + tail)) and
        rolling shutter (hmax x raster height / 72 MHz)."""
        lib = self.ui_camera()
        lib.slm_ui(0)
        lib.slm_panel_size(1920, 1080); lib.slm_panel_value(7, 16); lib.slm_fire(0)    # Free
        want = reference(12, 0)
        lib.slm_panel_value(16, 30)
        lib.slm_clear_posts(); lib.slm_fire(2)
        p = dict(x.split('=', 1) for x in lib.slm_posts().decode().replace('MB/s', 'MB_s').split(' ')
                 if '=' in x)
        m = REG.by_id[want[30]]
        px = lambda v: (v * 420 + 3032) // 6064
        cw, ch = min(m.raw[0] * m.scale[0], 6064), min(m.raw[1] * m.scale[1], 4040)
        gw, gh = px(cw), px(ch)
        self.assertEqual([int(p[k]) for k in ('SL_D_GX', 'SL_D_GY', 'SL_D_GW', 'SL_D_GH')],
                         [40 + (420 - gw) // 2, 180 + (280 - min(gh, 280)) // 2, gw, gh])   # the true area
        self.assertEqual(lib.slm_posts().decode().split('SL_D_GTxt=')[1].split(' SL_D_RTxt')[0],
                         f'Sensor {mm(cw)}x{mm(ch)}mm' + ratio_label(cw, ch))
        mw, mh = m.raw[0] & ~15, m.raw[1] & ~1
        rw, rh = px(mw), px(mh)
        self.assertEqual([int(p[k]) for k in ('SL_D_RX', 'SL_D_RY', 'SL_D_RW', 'SL_D_RH')],
                         [40 + (420 - rw) // 2, 180 + (280 - rh) // 2, rw, rh])
        self.assertEqual(lib.slm_posts().decode().split('SL_D_RTxt=')[1].split(' SL_D_Fps')[0],
                         f'Native {mw}x{mh}' + ratio_label(mw, mh))
        self.assertLess(rw, gw + 1)                          # inside the area
        lib.slm_panel_value(7, 16); lib.slm_fire(0)          # Free, then a smaller output:
        lib.slm_panel_size(1920, 1080)
        lib.slm_clear_posts(); lib.slm_fire(0)               # red stays the mode's largest
        self.assertIn(f"SL_D_RW={rw} ", lib.slm_posts().decode())
        cyc = m.hmax * (m.vmax - 1) + m.tail
        q = 72000000 // cyc
        self.assertEqual(lib.slm_posts().decode().split('SL_D_Fps=')[1].split(' SL_D_Rs')[0],
                         f'{q}.{(72000000 - q * cyc) * 100 // cyc:02d} fps')
        rs = (m.hmax * m.raw[1] + 360) // 720
        self.assertIn(f'SL_D_Rs=RS {rs // 100}.{rs % 100:02d} ms', lib.slm_posts().decode())
        s35 = reference(12, 0)[1]                            # M124 4176x2174: not a common shape
        self.assertEqual(REG.by_id[s35].raw, (4176, 2174))
        lib.slm_panel_value(16, 1)
        lib.slm_clear_posts(); lib.slm_fire(2)
        self.assertIn('SL_D_RTxt=Native 4176x2174 (1.92:1) ', lib.slm_posts().decode())

    def test_filter_narrows_the_mode_list(self):
        """FILTER's rows narrow the MODE list for the menu bit depth, across
        supported rates; each change rebuilds it."""
        lib = self.ui_camera()
        lib.slm_ui(0)
        base = reference(12, 0)

        def meta(mid):
            m = REG.by_id[mid]
            i = REG.modes.index(m)
            w = lambda o: struct.unpack_from('<I', IMG, META - B + 0x64 * i + o)[0]
            return m, w

        def nearest(a):
            return min(range(1, 6), key=lambda k: abs(a - (1500, 1778, 1850, 2000, 2390)[k - 1]))
        cases = [  # (variable index, subscription, value, keep)
            (39, 8, 2, lambda i: 4100 <= meta(i)[0].raw[0] * meta(i)[0].scale[0] <= 4300),      # Super35
            (39, 8, 3, lambda i: 3900 <= meta(i)[0].raw[0] * meta(i)[0].scale[0] <= 4000),      # APS-C
            (13, 5, 9, lambda i: mode_fps100(i) >= 11988),                                       # 119.88p+
            (14, 6, 3, lambda i: meta(i)[0].raw[0] >= 3840),                                     # 3840+
            (15, 7, 2, lambda i: nearest(meta(i)[0].raw[0] * meta(i)[0].scale[0] * 1000 //
                                         (meta(i)[0].raw[1] * meta(i)[0].scale[1])) == 2),       # 16:9
        ]
        for var, sub, value, keep in cases:
            with self.subTest(var=var, value=value):
                lib.slm_panel_value(var, value)
                lib.slm_clear_posts(); lib.slm_fire(sub)
                want = [i for i in base if keep(i)]
                self.assertTrue(0 < len(want) < len(base))
                self.assertEqual([r[1] for r in self.rows()], [label(i) for i in want])
                self.assertIn(f'SL_ModeMax={len(want) - 1} SL_M_Text={label(want[0])} SL_M_Tab=MODES ({len(want)}) ',
                              lib.slm_posts().decode())                                  # the tab counts them
                lib.slm_panel_value(var, 0); lib.slm_fire(sub)                                   # back to Any
        self.assertEqual([r[1] for r in self.rows()], [label(i) for i in base])
        lib.slm_panel_value(12, 2)                           # 14-bit at a 12-bit menu: the 14-bit modes
        lib.slm_clear_posts(); lib.slm_fire(4)               # (the user: "14bit mode只有0個")
        want = reference(14, 0)
        self.assertTrue(want)
        self.assertEqual([r[1] for r in self.rows()], [label(i) for i in want])
        self.assertIn(f'SL_M_Tab=MODES ({len(want)}) ', lib.slm_posts().decode())
        m = REG.by_id[want[0]]                               # the data rate at 14 bits
        w, h = max_out(*m.raw)
        self.assertIn(f'SL_O_W={w} ', lib.slm_posts().decode())
        out_w = int(lib.slm_posts().decode().split('SL_O_W=')[-1].split()[0])
        out_h = int(lib.slm_posts().decode().split('SL_O_H=')[-1].split()[0])
        mb = ((out_w * out_h // 1000) * 14 // 8 * 2398 + 50000) // 100000
        self.assertIn(f'SL_O_Rate=23.98p {mb} MB/s ', lib.slm_posts().decode())

    def test_filter_fps_is_the_only_rate_narrowing_of_modes(self):
        """Any and explicit FILTER FPS keep the same MODE rows as the user's
        FPS moves from 23.98 through 119.88 to 239.76, without a model rebuild."""
        lib = self.ui_camera()
        lib.slm_ui(0)
        base = reference_any(12)
        for filter_row, threshold in ((0, 0), (9, 11988), (10, 23976)):
            with self.subTest(filter_fps=filter_row):
                if filter_row:
                    lib.slm_panel_value(13, filter_row)
                    lib.slm_fire(5)
                want = [i for i in base if mode_fps100(i) >= threshold]
                if filter_row:
                    self.assertLess(len(want), len(base))
                rows = [label(i) for i in want]
                self.assertEqual([r[1] for r in self.rows()], rows)
                runs, calls = lib.slm_get(RUNS), lib.slm_get(CALLS)
                for ridx in (0, 8, 9):
                    menu(lib, 12, ridx)
                    self.assertEqual(lib.slm_live(), OK)
                    self.assertEqual([r[1] for r in self.rows()], rows)
                    self.assertEqual((lib.slm_get(RUNS), lib.slm_get(CALLS)), (runs, calls))

    def test_ratio_names(self):
        """Every label names its shape, or a decimal (the user): full-width 16:9 is
        (16:9), M12's area (3:2) and output (3:1), Super35's 4176x2174 (1.92:1);
        6064 px = 35.9 mm."""
        self.assertEqual(ratio_label(6064, 3412), ' (16:9)')
        self.assertEqual(ratio_label(6048, 4032), ' (3:2)')
        self.assertEqual(ratio_label(2016, 672), ' (3:1)')
        self.assertEqual(ratio_label(4176, 2174), ' (1.92:1)')
        self.assertEqual(ratio_label(3024, 1708), ' (16:9)')
        self.assertEqual((mm(6064), mm(4040), mm(4176)), ('35.9', '23.9', '24.7'))

    def test_the_crop_row(self):
        """Crop: pixels cut from the readout, centred (the user): its editor writes
        10 + the panel's codes; width 16 px / height 2 px a step; with a ratio held
        the other side's cut follows so what is left is the output at the ratio
        (AUTO: the uncut shape), 1:1; in Free each side alone; both what is cut and
        what is left shown; a mode chosen sets it back to none."""
        lib = self.ui_camera()
        lib.slm_ui(0)                                        # M123 6064x3412, AUTO (16:9)
        p = self.key(lib, 15)                                # Right / OK on the Crop row: edit, width
        self.assertIn('SL_C_Text=[0]x0 (6064x3412) ', p)
        t = 100000
        for _ in range(64):                                  # 64 x 16 = 1024 off the width
            t += 1000; lib.slm_tick(t)
            p = self.key(lib, 13)
        # AUTO: 5040 wide at 6064:3412 is 2836 high -> 576 cut off the height too, 1:1
        self.assertIn('SL_C_Text=[-1024]x-576 (5040x2836) ', p)
        self.assertIn('SL_O_W=5024 SL_O_H=2826 SL_O_BH=1 SL_O_BV=1 SL_O_BTxt=bin SL_O_SW=1.00 SL_O_SH=1.00 ', p)   # left - margins
        self.assertIn('SL_D_CTxt=Crop 29.8x16.8mm (16:9) ', p)   # the diagram's yellow frame and label
        lib.slm_panel_value(7, 16); lib.slm_fire(0)          # Free: each side alone
        self.key(lib, 12)                                    # Right: the height
        for _ in range(10):
            t += 1000; lib.slm_tick(t)
            p = self.key(lib, 14)                            # Down: cut 20 less
        self.assertIn('SL_C_Text=-1024x[-556] (5040x2856) ', p)
        self.assertIn('SL_O_W=5024 SL_O_H=2846 ', p)
        self.key(lib, 11)                                    # Left: the width again
        t += 1000; lib.slm_tick(t)
        p = self.key(lib, 14)                                # Down: 16 less (Free: nothing follows)
        self.assertIn('SL_C_Text=[-1008]x-556 (5056x2856) ', p)
        p = self.key(lib, 16)                                # OK: done
        self.assertIn('SL_C_Text=-1008x-556 (5056x2856) ', p)
        lib.slm_panel_value(16, 3)                           # another mode: no cut
        lib.slm_clear_posts(); lib.slm_fire(2)
        self.assertIn('SL_C_Text=0x0 (', lib.slm_posts().decode())

    def test_the_crop_goes_back_to_zero(self):
        """A ratio held (AUTO; 2.76:1 steps 1104 px): every Down makes the cut asked for
        smaller and it reaches 0x0 again (the user 2026-10-04: once adjusted it never
        went back -- both sides were rebuilt from the output, which the fit rounds down
        to a legal size, so a smaller cut came back as the old one)."""
        def cut(p, side):
            t = p.split('SL_C_Text=')[-1].split(' (')[0]
            w, h = t.split('x')
            return abs(int(re.sub(r'[\[\]]', '', [w, h][side])))
        for ratio in (0, 7):                                     # AUTO, 2.76:1
            for side in (0, 1):                                  # cut the width / the height
                with self.subTest(ratio=ratio, side=side):
                    lib = self.ui_camera()
                    lib.slm_ui(0)
                    lib.slm_panel_value(7, ratio); lib.slm_fire(0)
                    p = self.key(lib, 15)                        # edit
                    if side:
                        p = self.key(lib, 12)                    # the height
                    t = 100000
                    for _ in range(20):
                        t += 1000; lib.slm_tick(t); p = self.key(lib, 13)
                    up = cut(p, side)
                    self.assertGreater(up, 0)
                    seen = [up]
                    for _ in range(40):
                        t += 1000; lib.slm_tick(t); p = self.key(lib, 14)
                        seen.append(cut(p, side))
                        if seen[-1] == 0:
                            break
                    self.assertEqual(seen[-1], 0, seen)
                    self.assertTrue(all(b < a for a, b in zip(seen, seen[1:])), seen)   # every Down smaller
                    self.assertIn('SL_C_Text=', p)
                    self.assertTrue(p.split('SL_C_Text=')[-1].startswith(('[0]x0 ', '0x[0] ')), p.split('SL_C_Text=')[-1][:30])

    def test_record_settings_follow_the_mode(self):
        """The record settings' Frame rate and Bit depth rows grey (0,0) what the
        chosen mode cannot do (the user): a rate where the recipe does not solve
        it, 14 bit for a 12-bit mode and 8 / 10 / 12 for a 14-bit one; rewritten
        only when the mode changes."""
        lib = self.ui_camera()
        lib.slm_ui(0)

        def enabled(k, n):
            return [(lib.slm_aux_cell(k, r, 3).decode(), lib.slm_aux_cell(k, r, 4).decode()) for r in range(n)]
        mid = reference(12, 0)[0]                            # M123, the first
        want = [('1', '2') if mid in reference(12, r) else ('0', '0') for r in range(10)]
        self.assertEqual(enabled(0, 10), want)
        self.assertIn(('0', '0'), want)                      # it cannot run everywhere
        self.assertEqual(enabled(1, 4), [('1', '2')] * 3 + [('0', '0')])   # 12-bit: no 14 bit
        n = lib.slm_aux_notified(0)
        lib.slm_ui(0)                                        # the same mode: not rewritten
        self.assertEqual(lib.slm_aux_notified(0), n)
        lib.slm_panel_value(12, 2); lib.slm_fire(4)          # FILTER 14-bit: a 14-bit mode
        m14 = reference(14, 0)[0]
        self.assertEqual(enabled(1, 4), [('0', '0')] * 3 + [('1', '2')])
        self.assertEqual(enabled(0, 10), [('1', '2') if m14 in reference(14, r) else ('0', '0') for r in range(10)])

    def axis(self, lib, ridx):
        """AXIS as the native side left it, with imx410_fmt's bit / rate (the menu's)"""
        w = [lib.slm_peek(PL.AXIS + 4 * i) for i in range(K.AXIS_WORDS)]
        w[K.A_BIT], w[K.A_RATE] = 12, ridx
        return w

    def test_the_record_envelope(self):
        """The envelope seam, at the old per-side stock maximum (4176 x 2182): the
        largest output keeps the record matrix inside it, scaled alike on both sides
        (RWZM H = V); a mode inside it stays at unity.  The shipped default has no
        envelope (2026-10-04, the user): the whole M123 readout at unity."""
        for mid in reference(12, 0):
            with self.subTest(mode=mid):
                lib = self.ui_camera(rec_cap=UHD_CAP)
                lib.slm_ui(0)
                rows = reference(12, 0)
                lib.slm_panel_value(16, rows.index(mid)); lib.slm_clear_posts(); lib.slm_fire(2)
                p = lib.slm_posts().decode()
                w = int(p.split('SL_O_W=')[-1].split()[0]); h = int(p.split('SL_O_H=')[-1].split()[0])
                rw, rh = REG.by_id[mid].raw
                mw, mh = max_out(rw, rh, cap=UHD_CAP)
                self.assertTrue(w <= mw and h <= mh and (w == mw or h >= mh - 16), (w, h, mw, mh))
                r = K.expected_recipe(REG, self.axis(lib, 0))
                self.assertEqual((r[K.R_VALID], r[K.R_MODE]), (1, mid))
                self.assertLessEqual(r[K.R_RECW], UHD_CAP[0])
                self.assertLessEqual(r[K.R_RECH], UHD_CAP[1])
                if mid == rows[0]:                           # M123, the whole sensor: scaled alike
                    self.assertLessEqual(abs(r[K.R_ZH] - r[K.R_ZV]), 16)
                    self.assertGreater(r[K.R_ZH], 1024)
        lib = self.ui_camera(rec_cap=REC_MAX)                 # shipped: no envelope
        lib.slm_ui(0)
        lib.slm_panel_value(16, 0); lib.slm_clear_posts(); lib.slm_fire(2)   # M123
        lib.slm_panel_value(7, 1); lib.slm_fire(0)                            # RAW
        r = K.expected_recipe(REG, self.axis(lib, 0))
        self.assertEqual((r[K.R_RECW], r[K.R_RECH], r[K.R_ZH], r[K.R_ZV]), (6064, 3412, 1024, 1024))
        # M98 at RAW: the card's own shipped recipe (OG3K's), word for word
        lib = self.ui_camera(rec_cap=REC_MAX)
        lib.slm_ui(0)
        lib.slm_panel_value(16, reference(12, 0).index(98)); lib.slm_fire(2)
        lib.slm_panel_value(7, 1); lib.slm_fire(0)           # Ratio RAW
        shipped = K.expected_recipe(REG, [12, 0, 3032, 2012, 65537, 1024, 1024, 0, 0])
        self.assertEqual(K.expected_recipe(REG, self.axis(lib, 0))[K.AXIS_WORDS:], shipped[K.AXIS_WORDS:])

    def test_live_view_follows_the_shape(self):
        """Camera r69: M7 (16:9) squeezed in live view, the six preview profiles
        still at the card's 3:2 1334.  2026-10-04: the shape is the recorded
        pixels' (M12 RAW 2000x662 -> 21:9, 857), not the sensor area's.  The panel sets GTAB's selected value to
        imx410_plan.preview_visible_height of the recipe it writes (the aspect
        enum og3krecipe declares), and the profiles too while CUSTOM is on
        (FLAG); with FLAG off only the table (og3ksel writes it on selecting)."""
        prof = PL.PREV_PROFILES
        for flag in (1, 0):
            for mid, ratio, want in ((98, 1, 1334), (7, 1, 1125), (7, 0, 1125), (12, 1, 857)):
                with self.subTest(flag=flag, mode=mid, ratio=ratio):
                    lib = self.ui_camera(rec_cap=REC_MAX)
                    q = K.aspect_q_table()
                    lib.slm_bytes(PL.ASPTAB, q, len(q))
                    widths = PL.prev_width_addrs()
                    for i, w in enumerate((2, len(prof), 1334, 1125) + tuple(prof) + (len(prof), 2000, 2000) + widths):
                        lib.slm_word(PL.GTAB + 4 * i, w)
                    for a in prof:
                        lib.slm_word(a, 1334)
                    lib.slm_word(0xC0731C08, flag)
                    lib.slm_ui(0)
                    lib.slm_panel_value(16, reference(12, 3).index(mid)); lib.slm_fire(2)
                    lib.slm_panel_value(7, ratio); lib.slm_fire(0)
                    ax = self.axis(lib, 3)
                    self.assertEqual(PL.preview_visible_height(ax), want)        # the plan's own rule
                    self.assertEqual(lib.slm_peek(PL.GTAB + 8), want)
                    self.assertEqual([lib.slm_peek(a) for a in prof], [want if flag else 1334] * len(prof))
                    if mid == 7 and ratio == 1 and flag:
                        # M98 squeezed into 1920 x 1080 (Free): the recorded pixels are 16:9,
                        # so live view shows 16:9 (the pixels' shape, 2026-10-04 the user)
                        lib.slm_panel_value(16, reference(12, 3).index(98)); lib.slm_fire(2)
                        lib.slm_panel_value(7, 16); lib.slm_fire(0)
                        lib.slm_panel_size(1920, 1080); lib.slm_fire(0)
                        ax = self.axis(lib, 3)
                        self.assertNotEqual(ax[K.A_ZH], ax[K.A_ZV])
                        self.assertEqual(PL.preview_visible_height(ax), 1125)
                        self.assertEqual(lib.slm_peek(PL.GTAB + 8), 1125)

    def test_the_panel_declares_our_profile(self):
        """OUTPUT -> our own profile row (sl_modes.c declare_post): every field the
        panel owns is written into the row not in use (6 / 7, p13 / p14) of the
        65 column tables, exactly as imx410_profile.declare computes it for the
        recipe the same panel writes into AXIS, then mapping[87] flips to it.
        M98 RAW, M7 RAW (r69's freeze: the preview is now stock UHD30's), the M7
        capped largest, M98 Free 1920x1080, hbin 3."""
        import imx410_profile as PR
        img = (HERE.parent.parent.parent.parent / "out/MAIN_c0000000.bin").read_bytes()
        cols = PL.column_tables(img)
        slot = PL.MAPPING + PL.PRIVATE_PROFILE * 4
        base = PL._img_word(img, PL.MAPPING + PL.PROFILE * 4)

        prof, widths = PL.PREV_PROFILES, PL.prev_width_addrs(img)

        def camera():
            lib = self.ui_camera(rec_cap=REC_MAX)
            for i, w in enumerate((2, len(prof), 1334, 1125) + tuple(prof) + (len(prof), 2000, 2000) + widths):
                lib.slm_word(PL.GTAB + 4 * i, w)
            lib.slm_word(0xC0731C08, 1)                           # CUSTOM on: the profiles follow
            for i, o in enumerate(PR.DECLARED_BY_PANEL):
                lib.slm_word(PL.COLTAB + 4 * i, cols[o // 4])
            for t in cols:
                for row in (base,) + PL.DECL_ROWS:
                    lib.slm_word(t + 4 * row, PL._img_word(img, t + 4 * row))
            lib.slm_word(slot, base)
            lib.slm_ui(0)
            return lib

        def check(lib, label):
            ax = self.axis(lib, 3)
            r = K.expected_recipe(REG, ax)
            mid = ax[K.A_MODE]
            meta = next(i for i in range(70) if PL._img_word(img, 0xC0B59DC0 + i * 0x64) == mid)
            sx, sy = (PL._img_word(img, 0xC0B59DC0 + meta * 0x64 + o) for o in (0x4C, 0x50))
            hb, vb = ax[K.A_BIN] & 0xFFFF, ax[K.A_BIN] >> 16
            w = PR.Want(window=(ax[K.A_RW], ax[K.A_RH]), rec=(r[K.R_RECW], r[K.R_RECH]),
                        act=(r[K.R_ACTW], r[K.R_ACTH]),
                        zoom=tuple(z if z > 1024 else PR.RWZM_UNITY_STOCK for z in (ax[K.A_ZH], ax[K.A_ZV])),
                        scale=(float(sx), float(sy)), bin=(hb, vb))
            want = PR.declare(w, [0] * 65)
            row = lib.slm_peek(slot)
            with self.subTest(label):
                self.assertIn(row, PL.DECL_ROWS)
                got = {hex(o): lib.slm_peek(cols[o // 4] + 4 * row) for o in PR.DECLARED_BY_PANEL}
                self.assertEqual(got, {hex(o): want[o // 4] for o in PR.DECLARED_BY_PANEL})
                sb = PR.standby_visible(w)                        # standby = what recording shows
                if sb:
                    self.assertEqual((lib.slm_peek(widths[0]), lib.slm_peek(prof[0])), sb)
                    self.assertEqual(lib.slm_peek(PL.GTAB + 8), sb[1])
            return row, want

        lib = camera()
        rows = reference(12, 3)
        lib.slm_panel_value(16, rows.index(98)); lib.slm_fire(2)
        lib.slm_panel_value(7, 1); lib.slm_fire(0)                # RAW
        r1, _ = check(lib, 'M98 RAW')
        lib.slm_panel_value(16, rows.index(7)); lib.slm_fire(2)   # M7, AUTO (the capped largest)
        r2, _ = check(lib, 'M7 largest')
        self.assertNotEqual(r1, r2)                               # double-buffered
        lib.slm_panel_value(7, 1); lib.slm_fire(0)                # M7 RAW
        _, want = check(lib, 'M7 RAW')
        st = PL._img_word
        uhd = [st(img, cols[o // 4] + 4 * 78) for o in range(0, 0x104, 4)]   # p131 row: stock UHD30
        for o in (0x0C, 0x10, 0x20, 0x28, 0x58, 0xC4, 0x60, 0xD0, 0xD8, 0xE0, 0xF4, 0xF8, 0x38, 0x1C):
            self.assertEqual(want[o // 4], uhd[o // 4], hex(o))   # previews like stock UHD30
        lib.slm_panel_value(7, 16); lib.slm_fire(0)               # M7 Free 3856 x 2172:
        lib.slm_panel_size(3856, 2172); lib.slm_fire(0)           # 1.775, the visible height snaps to 1125
        _, want = check(lib, 'M7 Free 3856x2172')
        self.assertEqual(want[0x28 // 4], 1125)
        lib.slm_panel_value(16, rows.index(98)); lib.slm_fire(2)
        lib.slm_panel_value(7, 16); lib.slm_fire(0)               # Free
        lib.slm_panel_size(1920, 1080); lib.slm_fire(0)
        check(lib, 'M98 Free 1920x1080')
        lib.slm_panel_value(7, 0); lib.slm_fire(0)                # AUTO; binning 3 x 1
        self.key(lib, 5); self.key(lib, 2); self.key(lib, 2)
        lib.slm_tick(500000); self.key(lib, 3)
        check(lib, 'hbin 3')
        # M12 (2016 x 672, reduction 3 x 6): RAW previews the squeezed pixels, AUTO
        # (RWZM 2048 / 1024) keeps the r78 isotropic preview.
        lib.slm_panel_value(16, rows.index(12)); lib.slm_fire(2)
        lib.slm_panel_value(7, 1); lib.slm_fire(0)                # RAW
        _, want = check(lib, 'M12 RAW')
        self.assertEqual((want[0x0C // 4], want[0x10 // 4]), (2016, 672))
        lib.slm_panel_value(7, 0); lib.slm_fire(0)                # AUTO
        _, want = check(lib, 'M12 AUTO')
        self.assertEqual((want[0x60 // 4], want[0xD0 // 4], want[0x0C // 4], want[0x10 // 4]), (1023, 1023, 2000, 672))
        self.assertEqual((lib.slm_peek(widths[0]), lib.slm_peek(prof[0])), (1984, 1324))
        lib.slm_panel_value(7, 16); lib.slm_fire(0)
        lib.slm_panel_size(480, 326); lib.slm_fire(0)
        _, want = check(lib, 'M12 Free zoom above 3x without bin')
        self.assertEqual((want[0x58 // 4], want[0x5C // 4]), (0, 0))
        lib.slm_panel_value(16, rows.index(102)); lib.slm_fire(2)
        lib.slm_panel_value(7, 16); lib.slm_fire(0)
        lib.slm_panel_size(2640, 916); lib.slm_fire(0)
        _, want = check(lib, 'M102 unequal record wider than preview limit')
        self.assertEqual((want[0x60 // 4], want[0xD0 // 4]), (2048, 2048))
        lib.slm_calc_seed.argtypes = [ct.c_uint32] * 12
        # Unequal preview factors on a binned tap: cap in PREVIEW coordinates.
        lib.slm_calc_seed(124,4176,2174,1,1,1,3,0,0,16,2064,714)
        lib.slm_fit(1)
        _, want = check(lib, 'M124 vertical bin capped preview')
        self.assertEqual((want[0x20//4],want[0x28//4]),(2000,691))
        # A horizontal 4x zoom plus vertical bin must retain the exact pair.
        lib.slm_calc_seed(12,2016,672,3,6,1,3,0,0,16,480,102)
        lib.slm_fit(1)
        _, want = check(lib, 'M12 vertical bin and horizontal zoom above 3x')
        self.assertEqual(want[0x58//4],0)
        self.assertEqual(want[0x60//4],want[0x64//4])
        self.assertGreater(want[0x60//4],3072)

    def test_the_panel_drives_axis(self):
        """OUTPUT -> AXIS (sl_modes.c axis_post): raster / mode = the chosen mode,
        binning, the visible size as A_CROP and RWZM such that the recipe
        (imx410_block.expected_recipe, og3krecipe's spec) solves to that very mode
        with the visible size the panel shows and a record matrix of it + the
        margins -- unity, a smaller output, binning 3x1 and a cut readout."""
        lib = self.ui_camera()
        lib.slm_ui(0)
        self.assertEqual([lib.slm_peek(PL.AXIS + 4 * i) for i in range(K.AXIS_WORDS)][2:], [0] * 7)  # boot: untouched
        lib.slm_clear_posts(); lib.slm_fire(2)               # the user acts (the MODE row): armed

        def check(label, mid):
            p = lib.slm_posts().decode()
            out_w = int(p.split('SL_O_W=')[-1].split()[0]); out_h = int(p.split('SL_O_H=')[-1].split()[0])
            r = K.expected_recipe(REG, self.axis(lib, 0))
            with self.subTest(label):
                self.assertEqual((r[K.R_VALID], r[K.R_MODE]), (1, mid))
                self.assertEqual((r[K.R_ACTW], r[K.R_ACTH]), (out_w, out_h))
                self.assertGreaterEqual(r[K.R_RECW], out_w + 16)
                self.assertGreaterEqual(r[K.R_RECH], out_h + 10)
                self.assertLess(r[K.R_RECW], out_w + 16 + 16)     # no more than one alignment step over
                self.assertLess(r[K.R_RECH], out_h + 10 + 2)
            return r
        mid = reference(12, 0)[0]
        r = check('unity', mid)
        self.assertEqual((r[K.R_ZH], r[K.R_ZV]), (1024, 1024))
        lib.slm_panel_value(7, 16); lib.slm_fire(0)          # Free, then 1920 x 1080
        lib.slm_panel_size(1920, 1080); lib.slm_clear_posts(); lib.slm_fire(0)
        r = check('scaled', mid)
        self.assertGreater(r[K.R_ZH], 1024)
        lib.slm_panel_value(7, 0); lib.slm_fire(0)           # AUTO; binning 3 x 1 from the panel
        self.key(lib, 5); self.key(lib, 2); self.key(lib, 2)
        lib.slm_tick(500000); lib.slm_clear_posts(); self.key(lib, 3)
        r = check('hbin 3', mid)
        self.assertEqual(r[K.R_HBIN_E], 1)                   # CRCT's enum for 3
        # a cut readout (the Crop row, fresh): the record matrix still holds the
        # whole raster, scaled -- the visible output is its centre (A_CROP), so the
        # cut part of rec matches the output + margins; the data is not reduced
        lib = self.ui_camera()
        lib.slm_ui(0)
        self.key(lib, 15)                                    # 512 off the width (AUTO: the height follows)
        t = 600000
        for _ in range(32):
            t += 1000; lib.slm_tick(t); self.key(lib, 13)
        lib.slm_clear_posts(); self.key(lib, 16)
        p = lib.slm_posts().decode()
        out_w = int(p.split('SL_O_W=')[-1].split()[0])
        r = K.expected_recipe(REG, self.axis(lib, 0))
        raster_w = REG.by_id[mid].raw[0]
        self.assertEqual((r[K.R_VALID], r[K.R_MODE], r[K.R_ACTW]), (1, mid, out_w))
        self.assertLessEqual(abs(r[K.R_RECW] * (raster_w - 512) // raster_w - (out_w + 16)), 16)

    def test_no_pages_no_panel(self):
        lib = self.ui_camera()
        lib.slm_reg_result(2)
        lib.slm_ui(0)
        self.assertEqual(lib.slm_subs(), 0)
        self.assertNotIn(b'SL_O_W', lib.slm_posts())          # no panel (the MODE list's cap / text: yes)

    def test_a_full_screen_vector_is_not_grown(self):
        lib = self.ui_camera(screens=224, cap=224)
        lib.slm_ui(0)
        self.assertEqual((lib.slm_pages_get(self.STATE), lib.slm_pages_get(self.REG_CALLS)), (4, 0))

    def test_a_full_state_machine_vector_is_not_grown(self):
        lib = self.ui_camera(machines=24, mcap=24)
        lib.slm_ui(0)
        self.assertEqual((lib.slm_pages_get(self.STATE), lib.slm_pages_get(self.REG_CALLS)), (4, 0))

    def test_a_reader_of_another_app_registers_nothing(self):
        lib = self.ui_camera(reader_app=0x52001000)
        lib.slm_ui(0)
        self.assertEqual((lib.slm_pages_get(self.STATE), lib.slm_pages_get(self.REG_CALLS)), (5, 0))

    def test_a_refused_pack_is_not_retried(self):
        lib = self.ui_camera()
        lib.slm_reg_result(2)
        lib.slm_ui(0); lib.slm_ui(0)
        self.assertEqual((lib.slm_pages_get(self.STATE), lib.slm_pages_get(self.REG_CALLS),
                          lib.slm_pages_get(self.NEW_RD)), (3, 1, 0))

    def test_no_pages_in_the_file_registers_nothing(self):
        lib = self.ui_camera()
        lib.slm_pages(self.READER, 0, 0)
        lib.slm_ui(0)
        self.assertEqual((lib.slm_pages_get(self.STATE), lib.slm_pages_get(self.REG_CALLS)), (0, 0))

    # ---- the tests can fail ------------------------------------------------
    MUTATIONS = {
        'no budget check': ('    if (!peek(SL_ADDR(m, TMGTAB) + 4u * (hi * SL_NRATE + ridx))) return 0;\n', ''),
        'blanking ignored': ('(peek(row + 8u) + peek(row + 0x5Cu)) * hmax', 'peek(row + 8u) * hmax'),
        'live donor word': ('        return peek(recipe + R_SAVE0);', '        (void)0;'),
        'no csv check': ('        peek(iface + IF_DELETE) != W_DELETE)', '        0)'),
        'no key': ('    if (key == m->modes_key && filter == m->filter_key) return m->modes_step;\n', ''),
        'user fps in key': ('    key = (bit & 0xFFu) | 1u << 31;',
                            '    key = (bit & 0xFFu) | rate_index(m, get_rate(mgr)) << 8 | 1u << 31;'),
        'count not set': ('    if (m->count_desc) poke(m->count_desc + DESC_VALUE, n ? n : 1u);\n', ''),
        'no room check': ('    if (peek(app + SCREENS_COUNT) >= peek(app + SCREENS_CAP)) return m->pages_state = PAGES_NO_ROOM;\n', ''),
        'no machine room check': ('    if (peek(app + MACHINES_COUNT) >= peek(app + MACHINES_CAP)) return m->pages_state = PAGES_NO_ROOM;\n', ''),
        'stock pool kept': ('    poke(rd + READER_POOL, peek(m->reader + READER_POOL));\n', ''),
        'rate240 ignored': ('    case 7: return peek(SL_ADDR(m, RATE240)) ? 9u : 8u;', '    case 7: (void)m; return 8u;'),
        'axis not menu': ('    bit = get_bit(mgr) == 1u ? 14u : 12u;', '    bit = 12u;'),
        'pages every call': ('    if (m->pages && m->pages_state == PAGES_NONE) {', '    if (m->pages) {'),
        'width not x16': ('    m->out_w = clamp_step((int32_t)m->out_w, W_STEP, max_w(m, m->bin_h));', '    (void)0;'),
        'no binning limit': ('    m->out_w = clamp_step((int32_t)m->out_w, W_STEP, max_w(m, m->bin_h));', '    m->out_w = clamp_step((int32_t)m->out_w, W_STEP, readout_w(m));'),
        'no acceleration': ('        mult = m->key_run >= 25u ? 20u : m->key_run >= 10u ? 5u : 1u;', '        mult = 1u;'),
        'ratio ignored': ('    if (!num) return;', '    return;'),
        'height steps alone': ('        if (m->edit_field == 0u || (m->edit_field == 1u && held)) m->out_w',
                               '        if (m->edit_field == 0u) m->out_w'),
        'no common step': ('    if (ws > EXACT_MAX_W) return 0;', '    return 0;'),
        'mode not watched': ('            subscribe(m->names[V_MODE], panel_changed);\n', ''),
        'mode keeps binning': ('    m->bin_h = m->bin_v = 1u;\n    m->bin_kh', '    m->bin_kh'),
        'bin steps skip the std kernels': ('    uint32_t n = 1u + 2u * BIN_KERNELS;', '    uint32_t n = 1u + BIN_KERNELS;'),
        'ratio row not reset': ('    post_int(m->names[V_SCALE], R_AUTO);\n', ''),
        'rate row ignored': ('    fps = rate_fps100(sel ? sel - 1u : rate_index(m, get_rate(mgr)));', '    fps = rate_fps100(rate_index(m, get_rate(mgr))); (void)sel;'),
        'rate ignores the bits': ('    return raw == 1u ? 14u : raw == 3u ? 10u : raw == 4u ? 8u : 12u;', '    (void)raw; return 12u;'),
        'no cap posted': ('    post_int(m->names[24], n ? n - 1u : 0u);               /* SL_ModeMax */\n', ''),
        'selection not clamped': ('    if (n && sel >= n) {', '    if (0) {'),
        'quality ignores hmax': ('(0xFFFu - (hmax > 0xFFFu ? 0xFFFu : hmax)) << 12', '0u << 12'),
        'red is the output': ('            r[2] = diag_px(w & ~15u); r[3] = diag_px(h & ~1u);', '            r[2] = diag_px(m->out_w); r[3] = diag_px(m->out_h);'),
        'ratio within 10 %': ('        if ((a > v ? a - v : v - a) * 100u > v) continue;', '        if ((a > v ? a - v : v - a) * 10u > v) continue;'),
        'diagram ignores reduction': ('            cw = w * peek(row + 0x4Cu); ch = h * peek(row + 0x50u);', '            cw = w; ch = h;'),
        'filter ignored': ('    n = filter_modes(m, scan_modes(m, bit, SL_NRATE, m->mode_ids));',
                           '    n = scan_modes(m, bit, SL_NRATE, m->mode_ids);'),
        'user fps in scan': ('    n = filter_modes(m, scan_modes(m, bit, SL_NRATE, m->mode_ids));',
                             '    n = filter_modes(m, scan_modes(m, bit, rate_index(m, get_rate(mgr)), m->mode_ids));'),
        'filter not watched': ('            subscribe(m->names[V_FCROP], panel_changed);\n', ''),
        'crop bounds': ('            if (fc == 2u && (aw < 4100u || aw > 4300u)) keep = 0;', '            if (fc == 2u && aw < 4100u) keep = 0;'),
        'raw not locked': ('    if (m->ratio == R_RAW) {', '    if (0) {'),
        'binning drops the ratio': ('        if (m->edit_field >= 2u) {           /* binning: the largest output it allows (the user) */',
                                    '        if (m->edit_field >= 2u) { m->ratio = R_FREE;'),
        'auto follows binning': ('        *num = udiv(auto_w(m) * x * 100u, auto_h(m));',
                                 '        *num = udiv(auto_w(m) * x * 100u, auto_h(m) * (row == R_AUTO ? 3u : 1u));'),
        'auto is the raster': ('        *num = udiv(auto_w(m) * x * 100u, auto_h(m));',
                               '        *num = udiv(readout_w(m) * x * 100u, readout_h(m));'),
        'output ignores the mode': ('    if (w != m->ro_w || h != m->ro_h || sx != m->ro_sx || sy != m->ro_sy) {', '    if (0) {'),
        'crop ignored': ('static uint32_t readout_w(const struct sl_menu *m) { return raster_w(m) - m->crop_w; }',
                         'static uint32_t readout_w(const struct sl_menu *m) { return raster_w(m); }'),
        'filter bit not listed': ('        else if (fb == 2u) bit = 14u;', '        else if (0) bit = 14u;'),
        'rate at the menu depth': ('uint32_t bits = mode_depth14(m) ? 14u : rate_bits(get_bit(mgr));',
                                   'uint32_t bits = rate_bits(get_bit(mgr));'),
        'bit rows open': ('            bits = peek(row + 0x3Cu) == 1u ? 0x8u : 0x7u;', '            bits = 0xFu;'),
        'excl every call': ('    if (key == m->excl_key) return;', '    (void)0;'),
        'axis not written': ('    poke(SL_ADDR(m, AXIS) + AX_MODE, m->mode_ids[m->mode_sel]);\n', ''),
        'axis margins ignored': ('m->bin_h, m->out_w + MARGIN_W, W_STEP);', 'm->bin_h, m->out_w, W_STEP);'),
        'preview height not followed': ('    preview_post(m, zh, zv);\n', ''),
        'preview ignores FLAG': ('    if (peek(SL_ADDR(m, FLAG)) != 1u) return;\n', ''),
        'crop rebuilt from the output': ("            if (!asked) m->crop_w = m->crop_h = 0;\n            else if (m->crop_field == 0u) m->crop_h = raster_h(m) > lh ? raster_h(m) - lh : 0;\n            else m->crop_w = raster_w(m) > lw ? raster_w(m) - lw : 0;",
                                         "            (void)asked;\n            m->crop_w = raster_w(m) > lw ? raster_w(m) - lw : 0;\n            m->crop_h = raster_h(m) > lh ? raster_h(m) - lh : 0;"),
        'standby ignores the recorded region': ("        m->sb_vis_w = sbw > 2000u ? 2000u : sbw;", "        m->sb_vis_w = sbw > 2000u ? 2000u : sbw * 0u;"),
        'aspect undoes the reduction': ('    r = udiv(m->out_w * 1024u, m->out_h);',
                                        '    r = udiv(m->out_w * 1024u * (m->ro_sx ? m->ro_sx : 1u), m->out_h * (m->ro_sy ? m->ro_sy : 1u));'),
        'declared row in use': ("    row = peek(SL_MAPPING_SLOT) == DECL_ROW_A ? DECL_ROW_B : DECL_ROW_A;", "    row = DECL_ROW_A;"),
        'declared preview follows record zoom': ("        ph = pv = 3u * RWZM_UNITY;", "        ph = pv = fh;"),
        'declared r77 unequal preview regression': ("if ((m->bin_h > 1u || m->bin_v > 1u) && udiv(ww * RWZM_UNITY, fh) <= PREV_SRC_MAX) {\n        /* branch C", "if ((m->bin_h > 1u || m->bin_v > 1u || fh != fv) && udiv(ww * RWZM_UNITY, fh) <= PREV_SRC_MAX) {\n        /* branch C"),
        'declared cap ignores preview factors': ("ph != pv ? udiv(cap * vis_h, vis_w) :", "0 ? udiv(cap * vis_h, vis_w) :"),
        'declared no branch C': ("        ph = fh; pv = fv;", "        ph = pv = 3u * RWZM_UNITY;"),
        'declared preview from the larger factor': ("        uint32_t c = fh < fv ? fh : fv;", "        uint32_t c = fh > fv ? fh : fv;"),
        'declared record preview decomposes zoom': ("        binh = m->bin_h == 3u; binv = m->bin_v == 3u;", "        preview_axis(ph, &binh, &zph); binv = m->bin_v == 3u;"),
        'declared visible ignores the record factor': ("uint32_t vis_w = udiv(aw * fh, ph)", "uint32_t vis_w = udiv(aw * RWZM_UNITY, ph)"),
        'declared no snap': ("        if (near(vh, 1125u) && 1125u <= sh) vh = 1125u;          /* 16:9, stock UHD */", "        if (0) vh = 1125u;"),
        'declared snap past the source': ("        else if (near(vh, 1334u) && 1334u <= sh) vh = 1334u;", "        else if (near(vh, 1334u)) vh = 1334u;"),
        'declared scale ignores the mode': ("    v[27] = f32_bits(m->ro_sx ? m->ro_sx : 1u);", "    v[27] = f32_bits(1u);"),
        'declared order off by one': ("    v[25] = ww; v[26] = wh;", "    v[25] = wh; v[26] = ww;"),
        'axis written at boot': ('    if (!m->axis_armed) return;\n', ''),
        'no record envelope': ('    if (*w > cw && *w * ch >= *h * cw)', '    if (0)'),
        'envelope not alike': ('{ *h = udiv(*h * cw, *w); *w = cw; }', '{ *w = cw; }'),
        'axis crop ignored': ('    poke(SL_ADDR(m, AXIS) + AX_CROP, m->out_w | m->out_h << 16);', '    poke(SL_ADDR(m, AXIS) + AX_CROP, 0);'),
        'crop ignores the ratio': ('        held = num != 0u;\n        if (held) {                          /* the other side follows: start it uncut */',
                                   '        held = 0;\n        if (held) {                          /* the other side follows: start it uncut */'),
        'crop kept on a mode': ('    m->crop_w = m->crop_h = 0;                 /* a mode chosen: no cut (the user) */\n', ''),
        'crop not aligned': ('        v = (int32_t)m->crop_w + n * (int32_t)W_STEP;', '        v = (int32_t)m->crop_w + n * 10;'),
        'rwzm not rounded': ('    uint32_t c = udiv(out * bin * 100u + sensor / 2u, sensor);', '    uint32_t c = udiv(out * bin * 100u, sensor);'),
        'binning keeps the size': ('        if (m->edit_field >= 2u) {           /* binning: the largest output it allows (the user) */\n            m->out_w = max_w(m, m->bin_h);\n            m->out_h = max_h(m, m->bin_v);\n',
                                   '        if (m->edit_field >= 2u) {           /* binning: the largest output it allows (the user) */\n'),
        'ratio keeps the width': ('            m->out_w = max_w(m, m->bin_h);\n            m->out_h = max_h(m, m->bin_v);\n            fit(m, 1u);\n        }\n        if (key) {',
                                  '            fit(m, 1u);\n        }\n        if (key) {'),
        'key not reset': ('            panel_key(m, key);\n            post_int(m->names[V_KEY], 0u);\n',
                          '            panel_key(m, key);\n'),
        'keys not watched': ('            subscribe(m->names[V_KEY], panel_changed);\n', ''),
    }

    def test_every_mutation_is_caught(self):
        names = [n for n in unittest.TestLoader().getTestCaseNames(type(self))
                 if n != 'test_every_mutation_is_caught']
        saved = type(self).lib
        try:
            for label, seam in self.MUTATIONS.items():
                with self.subTest(mutation=label):
                    type(self).lib = build(self.tmp.name, seam)
                    result = unittest.TestResult()
                    for n in names:          # TestCase.run: no class fixtures (they would rebuild lib)
                        type(self)(n).run(result)
                    self.assertTrue(result.failures or result.errors, f'mutation "{label}" survived')
        finally:
            type(self).lib = saved

if __name__ == '__main__':
    unittest.main(verbosity=2)
