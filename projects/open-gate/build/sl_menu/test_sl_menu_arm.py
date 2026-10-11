#!/usr/bin/env python3
"""Run the real ARM blob (sl_menu_launch.S + compiled sl_menu.c/ui_pool.c) in
unicorn against the pinned firmware image with the boot-time UI objects laid
out as read from the camera (fixture layout of fpSup/lossless). The firmware
services it calls (allocator, caches, file API, variable registry) are
Python stubs; everything else -- the launcher's copy, the installer, the
shared pool convention -- is the camera's instructions. No camera.
"""
import pathlib
import struct
import sys
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_INVALID
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
                               UC_ARM_REG_LR, UC_ARM_REG_SP, UC_ARM_REG_PC,
                               UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC)

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import build_sl_menu as BSM  # noqa: E402
import sl_b25_page as SP  # noqa: E402
import sl_lists as SL  # noqa: E402

IMAGE = (SP.ROOT / 'out/MAIN_c0000000.bin').read_bytes()
BASE = 0xC0000000
NBU, POOL, POOL_LEN = 0xC18C0460, 0xC18C0474, 176152
GUIW = 0xC37B7048
HEAP = 0x10000000
APP, SCREENS, SCREEN_AT, READER, ENTRIES, NAMES, REGISTRY = (
    HEAP, HEAP + 0x1000, HEAP + 0x2000, HEAP + 0x4000, HEAP + 0x5000, HEAP + 0x7000, HEAP + 0x8000)
STAGE = 0x20000000
ALLOC = 0x30000000
STOP = 0x40000000
B25_OFFSET = 0x19C130
SCREEN_NAMES = ['MenuItem_SelectJump', 'MainB1', 'MainB2', 'MainY4']
ENTRY_NAMES = SCREEN_NAMES + ['B2_5']
ENTRY_OFFSETS = [0x10, 0x74D796, 0x76FF04, 0x889C60, B25_OFFSET]
ARM_STUBS = {0xC0057AE8: 'settings', 0xC005BF28: 'get_bit', 0xC005C0F0: 'get_rate', 0xC005C058: 'get_res',
             0xC001D740: 'h_get', 0xC001D7F0: 'h_addr', 0xC000E91C: 'dcache', 0xC000EABC: 'icache',
             0xC0365E90: 'f_ctor', 0xC0365FB0: 'f_open', 0xC0366060: 'f_read',
             0xC0366020: 'f_close', 0xC0365ED0: 'f_dtor',
             # sl_modes.c: OUTPUT's info panel (subscribe to a variable's writes, post an integer)
             0xC0560FB0: 'subscribe', 0xC0593F30: 'post_int', 0xC0593FE0: 'post_str', 0xC002B920: 'tick_ms'}
THUMB_STUBS = {0xC05DB418: 'lookup', 0xC05DB308: 'reg',
               # sl_modes.c: resource / model natives, and the modelCSV interface
               # wrappers the REAL table at 0xC2E01DB0 points to
               0xC05E0320: 'res_find', 0xC05D8BD8: 'res_count', 0xC05D8B78: 'res_load',
               0xC05D8BF8: 'res_get', 0xC05D8358: 'model_iface', 0xC05D83A8: 'notify',
               0xC05F4860: 'm_rows', 0xC05F4878: 'm_current', 0xC05F4928: 'm_string',
               0xC05F4940: 'm_insert', 0xC05F4958: 'm_delete',
               0xC05E84D8: 'nbr_register'}

RES = SP.build()
PACK = SL.build_pack(IMAGE)
import sl_pages as PG  # noqa: E402
PAGES = PG.build_pack(PG.test_pages(IMAGE))
FILE = bytes((i * 5 + 7) & 0xFF for i in range(0xF000)) + SP.pack(RES, PACK, PAGES)
BLOB, FACTS = BSM.build_blob()


class Camera:
    def __init__(self, file=FILE, b25_offset=B25_OFFSET):
        uc = self.uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        size = (len(IMAGE) + 0xFFF) & ~0xFFF
        uc.mem_map(BASE, size)
        uc.mem_write(BASE, IMAGE)
        uc.mem_map(GUIW & ~0xFFF, 0x1000)
        uc.mem_map(HEAP, 0x100000)
        uc.mem_map(STAGE, 0x10000)
        uc.mem_map(ALLOC, 0x400000)
        uc.mem_map(STOP, 0x1000)
        uc.mem_map(0x50000000, 0x10000)                          # stack
        uc.reg_write(UC_ARM_REG_C1_C0_2, 0x00F00000)
        uc.reg_write(UC_ARM_REG_FPEXC, 0x40000000)
        for a in ARM_STUBS:
            uc.mem_write(a, struct.pack('<I', 0xE12FFF1E))       # bx lr
        for a in THUMB_STUBS:
            uc.mem_write(a, struct.pack('<H', 0x4770))           # bx lr
        self.file, self.pos, self.bump = file, 0, ALLOC
        self.calls, self.registry, self.oob = [], {}, []
        self.stock_names = {'EXCL_FrameRate', 'EXCL_CinemaDNGQuality'}
        self.w(MARK := BSM.MARK, 0)
        del MARK
        self.w(GUIW, APP)
        self.w(APP + 0x80, len(SCREEN_NAMES)); self.w(APP + 0x8C, SCREENS); self.w(APP + 0x888, REGISTRY)
        for i, n in enumerate(SCREEN_NAMES):
            s = SCREEN_AT + 0x40 * i
            self.w(SCREENS + 4 * i, s); self.w(s + 4, APP); self.w(s + 8, NAMES + 0x40 * i); self.w(s + 0x24, READER)
        for i, n in enumerate(ENTRY_NAMES):
            uc.mem_write(NAMES + 0x40 * i, n.encode() + b'\0')
            self.w(ENTRIES + 44 * i + 4, NAMES + 0x40 * i)
            self.w(ENTRIES + 44 * i + 8, ENTRY_OFFSETS[i] if n != 'B2_5' else b25_offset)
        self.w(READER + 0x10, POOL_LEN); self.w(READER + 0x14, POOL); self.w(READER + 0x24, NBU)
        self.w(READER + 0xA8, len(ENTRY_NAMES)); self.w(READER + 0xAC, ENTRIES)
        # the two stock variables sl_excl.S needs, registered by stock
        for i, name in enumerate(('EXCL_FrameRate', 'EXCL_CinemaDNGQuality')):
            d, n = HEAP + 0xA000 + 32 * i, HEAP + 0xA800 + 64 * i
            uc.mem_write(n, name.encode() + b'\0')
            self.w(d, 0); self.w(d + 4, n); self.w(d + 8, i + 3)
            self.registry[name] = d
        uc.mem_write(STAGE, BLOB)
        uc.hook_add(UC_HOOK_CODE, self.stub, begin=0xC0000000, end=0xC2FFFFFF)
        uc.hook_add(UC_HOOK_MEM_INVALID, self.invalid)

    def w(self, a, v): self.uc.mem_write(a, struct.pack('<I', v & 0xFFFFFFFF))
    def r(self, a): return struct.unpack('<I', self.uc.mem_read(a, 4))[0]
    def cstr(self, a): return bytes(self.uc.mem_read(a, 64)).split(b'\0')[0].decode()

    def invalid(self, uc, access, address, size, value, data):
        self.oob.append(hex(address))
        return False

    def stub(self, uc, address, size, data):
        name = ARM_STUBS.get(address) or THUMB_STUBS.get(address)
        if not name:
            return
        a = [uc.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
        self.calls.append(name)
        ret = 0
        if name == 'h_get':
            self.bump = (self.bump + 0xFFF) & ~0xFFF
            self.w(a[0], self.bump); self.w(a[0] + 4, a[2])
            self.bump += a[2]
        elif name == 'h_addr':
            ret = self.r(a[0])
        elif name == 'f_open':
            self.path = self.cstr(a[1]); self.pos = 0
            ret = 1
        elif name == 'f_read':
            n = max(0, min(a[2], len(self.file) - self.pos))
            uc.mem_write(a[1], self.file[self.pos:self.pos + n])
            self.pos += n
            self.w(a[3], n)
            ret = 1
        elif name == 'lookup':
            d = self.registry.get(self.cstr(a[1]), 0)
            self.w(a[2], d)
        elif name in MODEL_STUBS:
            ret = MODEL_STUBS[name](self, a)
        elif name == 'reg':
            t, namep, value = struct.unpack('<3I', uc.mem_read(a[2], 12))
            d = HEAP + 0x9000 + 32 * len(self.registry)
            self.w(d, t); self.w(d + 4, namep); self.w(d + 8, value)
            self.registry[self.cstr(namep)] = d
        uc.reg_write(UC_ARM_REG_R0, ret)

    def run(self):
        uc = self.uc
        uc.reg_write(UC_ARM_REG_SP, 0x5000F000)
        uc.reg_write(UC_ARM_REG_LR, STOP)
        uc.emu_start(STAGE, STOP, count=400_000_000)
        return self


RES_H, INST = HEAP + 0xC000, HEAP + 0xC100
IFACE = HEAP + 0xC200            # r10 camera: not the image's 0xC2E01DB0; a copy of its slots


def _rows(cam, a):
    cam.w(a[1], len(cam.model)); return 0


def _current(cam, a):
    if 0 <= a[1] < len(cam.model):
        cam.cur = a[1]
    return 0


def _string(cam, a):
    assert a[0] == INST and 0 <= a[1] < 6              # the lab list's six columns
    cam.model[cam.cur][a[1]] = cam.cstr(a[2]); return 0


def _insert(cam, a):
    assert a[0] == INST and a[2] == 1
    cam.model.insert(a[1], [''] * 6); return 0


def _delete(cam, a):
    assert a[0] == INST
    del cam.model[a[1]:a[1] + a[2]]; return 0


def _find(cam, a):
    assert a[0] == APP
    name = cam.cstr(a[1])
    cam.finds = getattr(cam, 'finds', []) + [name]
    if name != 'SL_MODE':                    # the record settings' lists (sl_modes.c list_enable):
        cam.w(a[2], 0); return 1             # host-tested; here: not found, nothing written
    cam.w(a[2], RES_H); return 0


MODEL_STUBS = {
    'res_find': _find,
    'res_count': lambda cam, a: cam.w(a[1], 0) or 0,
    'res_load': lambda cam, a: 0,
    'res_get': lambda cam, a: cam.w(a[1], INST) or 0,
    'model_iface': lambda cam, a: cam.w(a[1], IFACE) or 0,
    'notify': lambda cam, a: cam.calls.append(('notify', cam.r(a[1]))) or 0,
    'm_rows': _rows, 'm_current': _current, 'm_string': _string, 'm_insert': _insert, 'm_delete': _delete,
    'nbr_register': lambda cam, a: _register(cam, a),
    'subscribe': lambda cam, a: cam.calls.append(('subscribe', a[0], cam.cstr(a[1]), a[2])) or 0,
    'post_int': lambda cam, a: cam.calls.append(('post', cam.cstr(a[1]), a[2])) or 0,
    'post_str': lambda cam, a: cam.calls.append(('post', cam.cstr(a[1]), cam.cstr(a[2]))) or 0,
    'tick_ms': lambda cam, a: 1000,
    # the settings the menu committed: 12-bit, 119.88 (internal 7, RATE240 left 0)
    'settings': lambda cam, a: MGR,
    'get_bit': lambda cam, a: 0,
    'get_rate': lambda cam, a: 7,
    'get_res': lambda cam, a: 4,
}
MGR = HEAP + 0xF000
NEW_READER = HEAP + 0xE000


def _register(cam, a):
    assert a[0] == APP
    cam.registered = (a[1], a[2])
    cam.w(NEW_READER + 0x10, 0x1234); cam.w(NEW_READER + 0x14, 0x5678)
    cam.w(a[3], NEW_READER)
    return 0


class ArmTests(unittest.TestCase):
    def test_the_mode_list_builder_runs_from_the_mark(self):
        """The launcher records sl_menu_modes; called the way sl_excl.S ROLE 7 calls
        it, the ARM build rewrites the model through the real interface table."""
        import imx410_plan as PL
        import imx410_block as K
        from imx410_full import META, TIMING
        cam = Camera().run()
        block = cam.r(BSM.MARK + 4)
        fn = cam.r(BSM.MARK + 0x50)
        self.assertEqual(fn, block + FACTS['c_base'] + FACTS['ui'])
        self.assertEqual(cam.r(BSM.MARK + 0x54), block + FACTS['c_base'] + FACTS['live'])
        self.assertTrue(fn & 1)
        cam.uc.mem_map(0xC343B000, 0x1000)
        desc = HEAP + 0xD000
        cam.w(0xC343B588, desc); cam.w(desc, TIMING); cam.w(desc + 8, META); cam.w(desc + 12, 70)
        for at, data in ((PL.RATETAB, K.rate_table()), (PL.TMGTAB, K.timing_table()),
                         (PL.RECIPE, bytes(4 * K.RECIPE_WORDS))):
            cam.uc.mem_write(at, data)
        ridx = K.RATE_KEYS.index('120')
        cam.w(PL.AXIS, 12); cam.w(PL.AXIS + 4, ridx)             # (the list follows the menu, not AXIS)
        cam.model, cam.cur = [['1', 'No matching', 'xx', 'blank', '0', '0']], -1
        cam.uc.mem_write(IFACE, IMAGE[0xC2E01DB0 - BASE:0xC2E01DB0 - BASE + 0x40])
        uc = cam.uc
        cam.w(APP + 0x80, 221); cam.w(APP + 0x84, 224)          # screens: room for three
        cam.w(APP + 0xF8, 17); cam.w(APP + 0xFC, 24)            # state machines (camera)
        cam.w(READER + 8, APP)                                   # the reader's ctx is the UI app
        uc.reg_write(UC_ARM_REG_R0, cam.r(BSM.MARK + 8))
        uc.reg_write(UC_ARM_REG_R1, 1)                            # CUSTOM
        uc.reg_write(UC_ARM_REG_SP, 0x5000F000)
        uc.reg_write(UC_ARM_REG_LR, STOP)
        uc.emu_start(fn, STOP, count=20_000_000)
        self.assertEqual(uc.reg_read(UC_ARM_REG_R0), 0)                 # SL_MODES_OK
        self.assertEqual(cam.oob, [])
        from test_sl_modes import label, quality, reference
        ids = [int(r[1][1:].split()[0]) for r in cam.model]
        # the MODE catalogue across every supported rate (scan_modes(.., SL_NRATE, ..)),
        # not the menu's rate: the record settings grey what the chosen mode cannot do
        catalogue = {mid for r in range(len(K.RATE_KEYS)) for mid in reference(12, r)}
        self.assertEqual(sorted(ids), sorted(catalogue))
        self.assertEqual(cam.model[0], ['1', label(ids[0]), 'xx', 'blank', '1', '2'])
        self.assertEqual(ids, sorted(ids, key=quality))                  # best guessed quality first
        self.assertIn(('notify', 1), cam.calls)
        self.assertEqual(cam.r(cam.registry['SL_ModeCount'] + 8), len(catalogue))
        # OUTPUT's info panel: subscribed with the pages, through the binding context
        # {app, 0, 1} at 0xC37B7048, and its six integers posted
        subs = [c for c in cam.calls if c[0] == 'subscribe']
        self.assertEqual([(c[1], c[2]) for c in subs], [(0xC37B7048, 'MV_SLScale'), (0xC37B7048, 'SL_O_Key'),
                                                     (0xC37B7048, 'SL_M_Sel'), (0xC37B7048, 'SL_O_RFps')] +
                         [(0xC37B7048, n) for n in ('SL_F_Bit', 'SL_F_Fps', 'SL_F_Width', 'SL_F_Prop', 'SL_F_Crop')])
        self.assertTrue(all(c[3] & 1 for c in subs))                    # Thumb callbacks
        posts = [c[1:] for c in cam.calls if c[0] == 'post']
        self.maxDiff = None
        self.assertEqual([x for x in posts if not x[0].startswith('SL_D_')][:16], [('MV_SLScale', 0),               # as if a mode were chosen: AUTO, largest
                                 ('SL_O_W', 6048), ('SL_O_H', 4030), ('SL_O_BH', 1), ('SL_O_BV', 1), ('SL_O_BTxt', 'bin'),  # the whole readout (no envelope)
                                 ('SL_O_SW', '1.00'), ('SL_O_SH', '1.00'),  # RWZM text, the software divide
                                 ('SL_O_A0', 0), ('SL_O_A1', 0), ('SL_O_A2', 0), ('SL_O_A3', 0),
                                 ('SL_C_Text', '0x0 (6064x4040)'),
                                 ('SL_O_Rate', '119.88p 4383 MB/s'),
                                 ('SL_ModeMax', len(catalogue) - 1), ('SL_M_Text', label(ids[0]))])
        # then the list's first mode is OUTPUT's readout: the panel reset to its largest
        from test_sl_modes import REG, REC_MAX, max_out
        w, h = REG.by_id[ids[0]].raw
        (_, W), (_, H) = [x for x in posts if x[0] in ('SL_O_W', 'SL_O_H')][-2:]
        self.assertEqual(W, max_out(w, h, cap=REC_MAX)[0])               # the width x16, less the margin ...
        self.assertLessEqual(abs(H - W * h / w), 2)                      # ... and AUTO: the raster's shape
        diagram = dict(x for x in posts if x[0].startswith('SL_D_'))        # the MODE tab's diagram, from ARM
        self.assertTrue(diagram['SL_D_RTxt'].startswith('Native ') and diagram['SL_D_RTxt'].endswith(')'))
        self.assertTrue(diagram['SL_D_GTxt'].startswith('Sensor ') and 'mm (' in diagram['SL_D_GTxt'])
        self.assertTrue(diagram['SL_D_Fps'].endswith(' fps') and diagram['SL_D_Rs'].startswith('RS '))   # the MODE list               # 12-bit, 119.88: 6048*4030*1.5*119.88
        # the page writes SL_O_Key (5: edit) and the GUI calls back; then Down (4)
        for code, want in ((5, ('post', 'SL_O_A0', 1)), (4, ('post', 'SL_O_W', (w & ~15) - 32))):
            cam.w(cam.registry['SL_O_Key'] + 8, code)
            cam.calls.clear()
            uc.reg_write(UC_ARM_REG_R0, cam.registry['SL_O_Key']); uc.reg_write(UC_ARM_REG_R1, 0)
            uc.reg_write(UC_ARM_REG_SP, 0x5000F000); uc.reg_write(UC_ARM_REG_LR, STOP)
            uc.emu_start(subs[1][3], STOP, count=1_000_000)
            self.assertEqual(uc.reg_read(UC_ARM_REG_R0), 0)
            self.assertIn(want, cam.calls)
            self.assertIn(('post', 'SL_O_Key', 0), cam.calls)
        # the pages pack, registered first, with the stock reader's (shared) pool
        at, n = cam.registered
        self.assertEqual(bytes(cam.uc.mem_read(at, n)), PAGES)
        self.assertEqual((cam.r(NEW_READER + 0x10), cam.r(NEW_READER + 0x14)),
                         (cam.r(READER + 0x10), cam.r(READER + 0x14)))

    def test_installs_on_the_modelled_camera(self):
        cam = Camera().run()
        self.assertEqual(cam.oob, [])
        mark = [cam.r(BSM.MARK + 4 * i) for i in range(4)]
        self.assertEqual(mark[0], 0x534D4C53)
        self.assertEqual(mark[3], 1, f'installer result {mark[3]}')
        block, state = mark[1], mark[2]
        self.assertEqual(state, block + FACTS['state_off'])
        # B2_5 switched to the page; the other entries untouched
        page = (NBU + cam.r(ENTRIES + 44 * 4 + 8)) & 0xFFFFFFFF
        self.assertTrue(block + FACTS['area_off'] < page < block + FACTS['block_bytes'])
        self.assertEqual([cam.r(ENTRIES + 44 * i + 8) for i in range(4)], ENTRY_OFFSETS[:4])
        got = bytes(cam.uc.mem_read(page, len(RES['page'])))
        pool, plen = cam.r(READER + 0x14), cam.r(READER + 0x10)
        self.assertNotEqual(pool, POOL)                         # the shared pool's copy
        self.assertEqual(bytes(cam.uc.mem_read(pool, 4096)), IMAGE[POOL - BASE:POOL - BASE + 4096])
        for at, text in RES['abs_refs']:
            off = struct.unpack_from('>I', got, at)[0]
            self.assertLess(off, plen)
            self.assertEqual(cam.cstr(pool + off), text, f'page word {at:#x}')
        refs = {a for a, _ in RES['abs_refs']}
        self.assertTrue(all(any(a <= i < a + 4 for a in refs)
                            for i in range(len(got)) if got[i] != RES['page'][i]))
        # six integers, 0, names resident in the block
        mine = {k: v for k, v in cam.registry.items() if k not in cam.stock_names}
        self.assertEqual(sorted(mine), sorted(['SL_O_W', 'SL_O_H', 'SL_O_In',
                                               'SL_O_BH', 'SL_O_BV', 'SL_O_SW', 'SL_ModeCount',
                                               'MV_SLScale', 'SL_O_SH', 'MV_SLBin', 'MV_SLRwzm',
                                               'SL_LabFocus', 'SL_F_Bit', 'SL_F_Fps', 'SL_F_Width', 'SL_F_Prop', 'SL_M_Sel', 'SL_LabTab',
                                               'SL_O_Key', 'SL_O_A0', 'SL_O_A1', 'SL_O_A2', 'SL_O_A3', 'SL_O_Rate', 'SL_ModeMax', 'SL_M_Text', 'SL_O_RFps',
                                               'SL_D_GX', 'SL_D_GY', 'SL_D_GW', 'SL_D_GH', 'SL_D_RX', 'SL_D_RY',
                                               'SL_D_RW', 'SL_D_RH', 'SL_D_GTxt', 'SL_D_RTxt', 'SL_D_Fps', 'SL_D_Rs',
                                               'SL_F_Crop', 'SL_M_Tab', 'SL_C_Text', 'SL_D_CX', 'SL_D_CY',
                                               'SL_D_CW', 'SL_D_CH', 'SL_D_CTxt', 'SL_N_Sel', 'SL_O_BTxt']))
        # the stock variant variables, found for sl_excl.S
        self.assertEqual((cam.r(BSM.MARK + 0x34), cam.r(BSM.MARK + 0x38)),
                         (cam.registry['EXCL_FrameRate'], cam.registry['EXCL_CinemaDNGQuality']))
        import sl_lab_page as LAB
        for name, d in mine.items():                 # all 0 but the lab page's focus: its tab bar
            if name in ('SL_O_BTxt', 'SL_O_SW', 'SL_O_SH', 'SL_O_Rate', 'SL_M_Text', 'SL_D_GTxt', 'SL_D_RTxt', 'SL_D_Fps', 'SL_D_Rs', 'SL_M_Tab', 'SL_C_Text', 'SL_D_CTxt'):       # RWZM: text variables (type 2), "1.00" to start
                self.assertEqual((cam.r(d), cam.cstr(cam.r(d + 8))), (2, '1.00'), name)
                continue
            self.assertEqual((cam.r(d), cam.r(d + 8)), (0, LAB.TAB_ITEM if name == 'SL_LabFocus' else 0), name)
            self.assertTrue(block <= cam.r(d + 4) < block + FACTS['block_bytes'])
        self.assertEqual(cam.path, '\\fpSup.BIN')
        # for sl_excl.S: the private NBR, its length and the reader, not yet registered
        nbr, n, reader = (cam.r(BSM.MARK + o) for o in (0x10, 0x14, 0x18))
        self.assertEqual((n, reader), (len(PACK), READER))
        self.assertEqual(bytes(cam.uc.mem_read(nbr, n)), PACK)
        self.assertEqual(cam.calls.count('f_dtor'), 1)
        self.assertIn('dcache', cam.calls)

    def test_an_already_switched_b2_5_gets_nothing(self):
        cam = Camera(b25_offset=0x1B8E9B).run()
        self.assertEqual(cam.r(BSM.MARK + 12), 5)               # NO_ENTRY
        self.assertEqual(cam.r(ENTRIES + 44 * 4 + 8), 0x1B8E9B)
        self.assertEqual(set(cam.registry), cam.stock_names)
        self.assertNotIn('f_open', cam.calls)

    def test_a_bin_without_the_block_gets_nothing(self):
        cam = Camera(file=FILE[:0xF000]).run()
        self.assertIn(cam.r(BSM.MARK + 12), (7, 8))
        self.assertEqual(cam.r(ENTRIES + 44 * 4 + 8), B25_OFFSET)
        self.assertEqual(cam.r(READER + 0x14), POOL)
        self.assertEqual(set(cam.registry), cam.stock_names)


if __name__ == '__main__':
    unittest.main(verbosity=2)
