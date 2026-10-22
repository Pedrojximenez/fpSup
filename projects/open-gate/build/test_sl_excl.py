#!/usr/bin/env python3
"""sl_excl.S in unicorn: the assembled hooks, branched to from their real sites
in the pinned image; firmware services they call are Python stubs (set a GUI
variable, settings manager, resolution getter, the NBR loader, the notifier's
own converters).  The stock bodies after each site run as the camera's code.
No camera."""
import pathlib
import struct
import sys
import unittest

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_MEM_INVALID
from unicorn.arm_const import *  # noqa: F403

import imx410_plan as PL
import sl_excl as SLX

IMAGE = PL.FIRMWARE.read_bytes()
B = 0xC0000000
RAM, STOP = 0x10000000, 0x20000000
NOTIFIER, VTABLE = RAM + 0x100, 0xC2DEE900          # a menu notifier object, the real vtable
READER, APP = RAM + 0x9000, RAM + 0xA000            # reader+8 = the UI app = [C37B7048]
DESC = {'EXCL_FrameRate': RAM + 0xB000, 'EXCL_CinemaDNGQuality': RAM + 0xB100}
GUIW = 0xC37B7048
NAMES = {0xC2DF26EC: 'EXCL_FrameRate', 0xC2DF2950: 'EXCL_CinemaDNGQuality',
         0xC2DEE522: 'MV_Resolution', 0xC2DF3448: 'LV_Resolution', 0xC2DF3D0C: 'LV_Resolution2'}
ARM_STUBS = (0xC0593F30, 0xC0057AE8, 0xC005C058, 0xC06CC068, 0xC06CBBE0, 0xC06BD988, 0xC06BD9E0,
             0xC005BF28, 0xC005BEF0)
GETSET, SETRES = RAM + 0xE000, RAM + 0xE010         # [C37B7538]->vtable+0x44, settings->+0x13C
THUMB_STUBS = (0xC05E84D8,)


class Cam:
    def __init__(self, installed=True, resolution=4, nbr_result=0):
        uc = self.uc = Uc(UC_ARCH_ARM, UC_MODE_ARM)
        uc.mem_map(B, (len(IMAGE) + 0xFFF) & ~0xFFF)
        uc.mem_write(B, IMAGE)
        uc.mem_map(RAM, 0x100000)
        uc.mem_map(GUIW & ~0xFFF, 0x1000)
        uc.mem_map(STOP, 0x1000)
        for a in ARM_STUBS:
            uc.mem_write(a, struct.pack('<I', 0xE12FFF1E))
        for a in THUMB_STUBS:
            uc.mem_write(a, struct.pack('<H', 0x4770))
        blobs = SLX.blobs()
        for name, _src, addr in SLX.payloads():
            uc.mem_write(addr, blobs[name])
        for site, word, _ in SLX.patches(IMAGE):
            uc.mem_write(site, struct.pack('<I', word))
        for a, v, _ in SLX.state_words():
            self.w(a, v)
        if installed:
            self.w(SLX.MARK, 0x534D4C53)
            self.w(SLX.MARK + 0x0C, 1)
            self.w(SLX.MARK + 0x10, RAM + 0x8000)       # the pack
            self.w(SLX.MARK + 0x14, 596)
            self.w(SLX.MARK + 0x18, READER)
            self.w(SLX.MARK + 0x34, DESC['EXCL_FrameRate'])
            self.w(SLX.MARK + 0x38, DESC['EXCL_CinemaDNGQuality'])
        self.w(READER + 8, APP)
        self.w(GUIW, APP)
        for name, d in DESC.items():
            self.w(d + 8, 0)                            # stock values at boot
        self.w(NOTIFIER, VTABLE)
        self.w(NOTIFIER + 4, RAM + 0x200)               # its converter
        self.resolution, self.nbr_result = resolution, nbr_result
        self.bit, self.bit_sets = 0, []                 # eRawBitType: 0 = 12, 1 = 14
        self.vars, self.loads = {}, []
        for a in (GETSET, SETRES):
            uc.mem_write(a, struct.pack('<I', 0xE12FFF1E))
        for gui in (0xC37B7538, 0xC37B75C8):           # the two menu objects the setters use
            self.w(gui, RAM + 0xD000)
        self.w(RAM + 0xD000, RAM + 0xD100); self.w(RAM + 0xD000 + 0x34, RAM + 0xD200)
        self.w(RAM + 0xD100 + 0x44, GETSET)
        self.w(RAM + 0xD300, RAM + 0xD400); self.w(RAM + 0xD400 + 0x13C, SETRES)
        self.posted = []
        uc.hook_add(UC_HOOK_CODE, self.stub, begin=B, end=0xC2FFFFFF)
        uc.hook_add(UC_HOOK_CODE, self.stub, begin=GETSET, end=SETRES + 4)
        uc.hook_add(UC_HOOK_MEM_INVALID, lambda *a: False)

    def w(self, a, v): self.uc.mem_write(a, struct.pack('<I', v & 0xFFFFFFFF))
    def r(self, a): return struct.unpack('<I', self.uc.mem_read(a, 4))[0]

    def stub(self, uc, address, size, data):
        if address not in ARM_STUBS and address not in THUMB_STUBS and address not in (GETSET, SETRES):
            return
        a = [uc.reg_read(x) for x in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3)]
        ret = 0
        if address == 0xC06BD9E0:                       # row -> resolution value
            ret = {0: 3, 1: 2, 2: 4}[a[1]]
        elif address == GETSET:
            ret = RAM + 0xD300
        elif address == SETRES:                         # the setting, set synchronously
            assert a[0] == RAM + 0xD300
            self.resolution = a[1]
        elif address == 0xC0593F30:
            assert a[0] in (NOTIFIER, 0), hex(a[0])
            self.vars[NAMES[a[1]]] = a[2]
            if NAMES[a[1]] in DESC:
                self.w(DESC[NAMES[a[1]]] + 8, a[2])     # the variable really changes
        elif address == 0xC0057AE8:
            ret = RAM + 0x300
        elif address == 0xC005BF28:
            assert a[0] == RAM + 0x300
            ret = self.bit
        elif address == 0xC005BEF0:
            assert a[0] == RAM + 0x300 and a[2] == 0
            self.bit_sets.append(a[1])
            self.bit = a[1]
        elif address == 0xC005C058:
            assert a[0] == RAM + 0x300
            ret = self.resolution
        elif address in (0xC06CC068, 0xC06CBBE0, 0xC06BD988):
            assert a[0] == RAM + 0x200
            ret = a[1] + 100                            # 'stock conversion', recognisable
        elif address == 0xC05E84D8:
            self.loads.append(tuple(a))
            ret = self.nbr_result
        uc.reg_write(UC_ARM_REG_R0, ret)

    def value(self, name): return self.r(DESC[name] + 8)

    def page(self):
        """C05E82F0 (Thumb) up to where stock carries on, after the displaced push.w."""
        uc = self.uc
        sp = RAM + 0xF000
        regs = (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4,
                UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7, UC_ARM_REG_R11, UC_ARM_REG_LR)
        for i, reg in enumerate(regs):
            uc.reg_write(reg, 0x2222 * (i + 1))
        uc.reg_write(UC_ARM_REG_SP, sp)
        uc.emu_start(0xC05E82F0 | 1, 0xC05E82F4, count=100000)
        assert uc.reg_read(UC_ARM_REG_PC) == 0xC05E82F4
        assert uc.reg_read(UC_ARM_REG_SP) == sp - 24, 'push.w not replayed'
        assert uc.reg_read(UC_ARM_REG_CPSR) & 0x20, 'not back in Thumb'
        for i, reg in enumerate(regs):
            assert uc.reg_read(reg) == 0x2222 * (i + 1), f'register {reg} changed'
        pushed = struct.unpack('<6I', uc.mem_read(sp - 24, 24))
        assert pushed == tuple(0x2222 * (i + 1) for i in (4, 5, 6, 7, 8, 9)), pushed
        return self

    def call(self, site, arg):
        uc = self.uc
        sp = RAM + 0xF000
        for i, reg in enumerate((UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
                                 UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)):
            uc.reg_write(reg, 0x1111 * (i + 4))
        uc.reg_write(UC_ARM_REG_SP, sp)
        uc.reg_write(UC_ARM_REG_R0, NOTIFIER)
        uc.reg_write(UC_ARM_REG_R1, arg)
        uc.reg_write(UC_ARM_REG_LR, STOP)
        uc.emu_start(site, STOP, count=100000)
        assert uc.reg_read(UC_ARM_REG_SP) == sp
        for i, reg in enumerate((UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7,
                                 UC_ARM_REG_R8, UC_ARM_REG_R9, UC_ARM_REG_R10, UC_ARM_REG_R11)):
            assert uc.reg_read(reg) == 0x1111 * (i + 4), f'r{i + 4} not preserved'
        return self


RATE, BIT, RES = 0xC059B2F8, 0xC059BA10, 0xC05931D0


class Hooks(unittest.TestCase):
    def test_not_installed_is_stock(self):
        c = Cam(installed=False).call(RATE, 4).call(BIT, 1)
        self.assertEqual(c.vars, {'EXCL_FrameRate': 104, 'EXCL_CinemaDNGQuality': 101})
        self.assertEqual(c.loads, [])
        self.assertEqual((c.r(SLX.MARK + 0x20), c.r(SLX.MARK + 0x24)), (4, 1))

    def test_not_custom_is_stock(self):
        c = Cam(resolution=1).call(RATE, 4).call(BIT, 0)
        self.assertEqual(c.vars, {'EXCL_FrameRate': 104, 'EXCL_CinemaDNGQuality': 100})
        self.assertEqual(c.loads, [])

    def test_custom_registers_once_then_private_frames(self):
        c = Cam().call(RATE, 0).call(BIT, 0).call(RATE, 1)
        self.assertEqual(c.vars, {'EXCL_FrameRate': SLX.RATE_INDEX, 'EXCL_CinemaDNGQuality': SLX.BIT_INDEX})
        self.assertEqual(c.loads, [(APP, RAM + 0x8000, 596, 0)])     # ctx = [reader+8], as OG
        self.assertEqual(c.r(SLX.MARK + 0x48), APP)
        self.assertEqual(c.r(SLX.MARK + 0x1C), 1)
        self.assertEqual((c.r(SLX.MARK + 0x28), c.r(SLX.MARK + 0x2C)), (2, 1))

    def test_a_refused_pack_is_stock_and_never_retried(self):
        c = Cam(nbr_result=5).call(RATE, 0).call(BIT, 0).call(RATE, 2)
        self.assertEqual(c.vars, {'EXCL_FrameRate': 102, 'EXCL_CinemaDNGQuality': 100})
        self.assertEqual(len(c.loads), 1)
        self.assertEqual(c.r(SLX.MARK + 0x1C), 3)

    def test_no_pack_recorded_is_stock(self):
        c = Cam()
        c.w(SLX.MARK + 0x10, 0)
        c.call(RATE, 0)
        self.assertEqual((c.vars, c.loads, c.r(SLX.MARK + 0x1C)), ({'EXCL_FrameRate': 100}, [], 3))

    def test_resolution_change_reapplies_with_the_last_states(self):
        c = Cam(resolution=1).call(RATE, 4).call(BIT, 1)
        c.resolution = 4                                  # FHD -> CUSTOM, stock states unchanged
        c.vars.clear()
        c.call(RES, 2)
        self.assertEqual(c.vars, {'MV_Resolution': 102, 'EXCL_FrameRate': SLX.RATE_INDEX,
                                  'EXCL_CinemaDNGQuality': SLX.BIT_INDEX})
        c.resolution = 1                                  # and back
        c.vars.clear()
        c.call(RES, 1)
        self.assertEqual(c.vars, {'MV_Resolution': 101, 'EXCL_FrameRate': 104,
                                  'EXCL_CinemaDNGQuality': 101})

    def test_resolution_before_any_state_under_custom_writes_ours(self):
        c = Cam().call(RES, 2)
        self.assertEqual(c.vars, {'MV_Resolution': 102, 'EXCL_FrameRate': SLX.RATE_INDEX,
                                  'EXCL_CinemaDNGQuality': SLX.BIT_INDEX})

    def test_resolution_before_any_state_not_custom_does_nothing_more(self):
        c = Cam(resolution=1).call(RES, 1)
        self.assertEqual(c.vars, {'MV_Resolution': 101})

    def test_standby_resolution_notifiers(self):
        for site, name in ((0xC059C640, 'LV_Resolution'), (0xC059C9F0, 'LV_Resolution2')):
            with self.subTest(site=hex(site)):
                c = Cam(resolution=1).call(RATE, 3)
                c.resolution = 4
                c.vars.clear()
                c.call(site, 2)
                self.assertEqual(c.vars, {name: 102, 'EXCL_FrameRate': SLX.RATE_INDEX,
                                          'EXCL_CinemaDNGQuality': SLX.BIT_INDEX})

    def test_a_reader_whose_ctx_is_not_the_app_is_refused(self):
        c = Cam()
        c.w(READER + 8, RAM + 0xC000)
        c.call(RATE, 0)
        self.assertEqual((c.loads, c.r(SLX.MARK + 0x1C), c.vars), ([], 3, {'EXCL_FrameRate': 100}))

    def test_page_parse_under_custom_writes_ours_and_keeps_stock(self):
        c = Cam()
        c.w(DESC['EXCL_FrameRate'] + 8, 4)
        c.w(DESC['EXCL_CinemaDNGQuality'] + 8, 1)
        c.page()
        self.assertEqual((c.value('EXCL_FrameRate'), c.value('EXCL_CinemaDNGQuality')),
                         (SLX.RATE_INDEX, SLX.BIT_INDEX))
        self.assertEqual((c.r(SLX.MARK + 0x3C), c.r(SLX.MARK + 0x40)), (4, 1))
        self.assertEqual(len(c.loads), 1)
        c.page()                                          # again: the saved stock values stay
        self.assertEqual((c.r(SLX.MARK + 0x3C), c.r(SLX.MARK + 0x40)), (4, 1))
        c.resolution = 1                                  # left CUSTOM with no notifier: undo
        c.page()
        self.assertEqual((c.value('EXCL_FrameRate'), c.value('EXCL_CinemaDNGQuality')), (4, 1))

    def test_page_parse_not_installed_or_not_custom_changes_nothing(self):
        for kw, loads in ((dict(installed=False), 0), (dict(resolution=1), 1)):
            with self.subTest(**kw):
                c = Cam(**kw)
                c.w(DESC['EXCL_FrameRate'] + 8, 4)
                c.page()
                self.assertEqual((c.value('EXCL_FrameRate'), len(c.loads)), (4, loads))

    def test_page_parse_registers_outside_custom_but_notifiers_do_not(self):
        """MODE / SIZE name SL_MODE / SL_SIZE in every frame: the page parser
        registers the pack whatever the resolution; a notifier still waits for CUSTOM."""
        c = Cam(resolution=1).call(RATE, 4)
        self.assertEqual((c.loads, c.r(SLX.MARK + 0x1C)), ([], 0))
        c.page()
        self.assertEqual((c.loads, c.r(SLX.MARK + 0x1C)), ([(APP, RAM + 0x8000, 596, 0)], 1))
        c.page()
        self.assertEqual(len(c.loads), 1)                 # once
        c.resolution = 4
        c.page()
        self.assertEqual((len(c.loads), c.value('EXCL_FrameRate')), (1, SLX.RATE_INDEX))

    def test_a_refused_pack_gives_b25_its_stock_page_back(self):
        entry, state = RAM + 0x7000, RAM + 0x7100
        for kw in (dict(resolution=1), dict(resolution=4)):
            with self.subTest(**kw):
                c = Cam(nbr_result=5, **kw)
                c.w(SLX.MARK + 8, state)
                c.w(state + 0x0C, entry)
                c.w(entry + 8, 0x8389ABCD)                # the private page's offset
                c.page()
                self.assertEqual((c.r(SLX.MARK + 0x1C), c.r(entry + 8)), (3, 0x19C130))
                c.w(entry + 8, 0x8389ABCD)
                c.page()                                  # never retried, never touched again
                self.assertEqual((len(c.loads), c.r(entry + 8)), (1, 0x8389ABCD))

    def test_page_parse_calls_the_ui_builder_with_the_custom_flag(self):
        """ROLE 7 calls sl_menu_ui([MARK+8], CUSTOM and ready) through MARK+0x50 on
        every page parse (the private pages register whatever the resolution);
        Cam.page() still checks every register stock sees is untouched."""
        fn, state = RAM + 0x6000, RAM + 0x7100
        for res, flag in ((1, 0), (4, 1)):
            with self.subTest(resolution=res):
                c = Cam(resolution=res)
                c.uc.mem_write(fn, struct.pack('<H', 0x4770))       # Thumb bx lr
                seen = []
                c.uc.hook_add(UC_HOOK_CODE, lambda uc, a, sz, d: seen.append(
                    (uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1))), begin=fn, end=fn + 1)
                c.w(SLX.MARK + 8, state)
                c.w(SLX.MARK + 0x50, fn | 1)
                c.page()
                self.assertEqual(seen, [(state, flag)])

    def live_cam(self, with_live=True):
        """Cam plus imx410_rate_native ROLE 6/7 (with their LIVE continuation, as the
        plan assembles them on a --b25-menu card); the three stock callback bodies
        replaced by `mov r0,#0x55; pop {r4-r7,pc}` after their displaced push."""
        import imx410_plan as PL
        import imx410_rate_native as RN
        saved = (PL.WITH_SL_EXCL, PL.WITH_RATE_ROW, PL.WITH_BIT_ROW)
        PL.WITH_SL_EXCL, PL.WITH_RATE_ROW, PL.WITH_BIT_ROW = True, False, False
        try:
            d = PL.defines()
            from armasm import assemble
            src = str(pathlib.Path(RN.__file__).with_suffix('.S'))
            c = Cam()
            for role in (6, 7):
                site, target = RN.HOOKS[role - 1][0], RN.HOOKS[role - 1][1]
                c.uc.mem_write(target, assemble(src, defines=d[f'native_rate_{role}']))
                c.uc.mem_write(site, struct.pack('<I', RN._b(site, target)))
        finally:
            PL.WITH_SL_EXCL, PL.WITH_RATE_ROW, PL.WITH_BIT_ROW = saved
        body = struct.pack('<II', 0xE3A00055, 0xE8BD80F0)          # mov r0,#0x55 ; pop {r4-r7,pc}
        c.stock_hits = []
        for back in (0xC057A6FC, 0xC05821BC, 0xC057A5F4):
            c.uc.mem_write(back, body)
            c.uc.hook_add(UC_HOOK_CODE, lambda uc, a, sz, dd: c.stock_hits.append(('stock', a)), begin=back, end=back + 1)
        fn, state = RAM + 0x6000, RAM + 0x7100
        c.uc.mem_write(fn, struct.pack('<HH', 0x2077, 0x4770))      # Thumb: movs r0,#0x77 ; bx lr
        c.uc.hook_add(UC_HOOK_CODE, lambda uc, a, sz, dd: c.stock_hits.append(('live', uc.reg_read(UC_ARM_REG_R0))),
                      begin=fn, end=fn + 1)
        c.w(SLX.MARK + 8, state)
        c.w(SLX.MARK + 0x54, (fn | 1) if with_live else 0)
        c.state = state
        return c

    def run_callback(self, c, site, row=None):
        uc = c.uc
        var = RAM + 0x5000
        if row is not None:
            c.w(var + 8, row)
        sp = RAM + 0xF000
        for i, reg in enumerate((UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7)):
            uc.reg_write(reg, 0x1111 * (i + 4))
        uc.reg_write(UC_ARM_REG_SP, sp)
        uc.reg_write(UC_ARM_REG_R0, var)
        uc.reg_write(UC_ARM_REG_LR, STOP)
        uc.emu_start(site, STOP, count=100000)
        self.assertEqual(uc.reg_read(UC_ARM_REG_SP), sp)
        for i, reg in enumerate((UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7)):
            self.assertEqual(uc.reg_read(reg), 0x1111 * (i + 4))
        return uc.reg_read(UC_ARM_REG_R0)

    def test_frame_rate_callbacks_run_stock_then_the_live_mode_list(self):
        import imx410_rate_native as RN
        for site, back in ((0xC057A6F8, 0xC057A6FC), (0xC05821B8, 0xC05821BC)):
            for row, flag in ((9, 1), (3, 0)):
                with self.subTest(site=hex(site), row=row):
                    c = self.live_cam()
                    r0 = self.run_callback(c, site, row)
                    self.assertEqual(c.stock_hits, [('stock', back), ('live', c.state)])
                    self.assertEqual(r0, 0x55)                       # stock's result, not live's
                    self.assertEqual(c.r(RN.RATE240), flag)          # 240's own work still done first

    def test_bit_depth_callback_runs_stock_then_the_live_mode_list(self):
        c = self.live_cam()
        self.assertEqual(self.run_callback(c, SLX.DNG_SITE), 0x55)
        self.assertEqual(c.stock_hits, [('stock', 0xC057A5F4), ('live', c.state)])

    def test_no_live_builder_recorded_is_skipped(self):
        c = self.live_cam(with_live=False)
        self.assertEqual(self.run_callback(c, SLX.DNG_SITE), 0x55)
        self.assertEqual(c.stock_hits, [('stock', 0xC057A5F4)])

    def test_private_pages_borrow_their_parents_gui_id(self):
        """ROLE 15 at C056461C: "SL_..." -> B2_5's GUI id 36 (camera r15: without it
        NullGuiInterface swallowed every key); anything else -> stock lookup."""
        c = Cam()
        stock = 0xC0564638
        c.uc.mem_write(stock, struct.pack('<II', 0xE3000ABC, 0xE12FFF1E))   # movw r0,#0xABC ; bx lr
        site_word = struct.unpack('<I', c.uc.mem_read(SLX.GUI_SITE, 4))[0]
        self.assertEqual(site_word & 0xFF000000, 0xEB000000)
        self.assertEqual(SLX.GUI_SITE + 8 + (((site_word & 0xFFFFFF) ^ 0x800000) - 0x800000) * 4, SLX.GUI_CODE)
        names = RAM + 0x4000
        for k, (name, want) in enumerate(((b'SL_TEST', 36), (b'SL_SIZE', 36), (b'B2_5', 0xABC),
                                          (b'SLX', 0xABC), (b'SL', 0xABC), (b'S', 0xABC), (None, 0xABC))):
            with self.subTest(name=name):
                at = 0
                if name is not None:
                    at = names + 0x40 * k
                    c.uc.mem_write(at, name + b'\0')
                c.uc.reg_write(UC_ARM_REG_R0, RAM + 0x100)
                c.uc.reg_write(UC_ARM_REG_R1, at)
                c.uc.reg_write(UC_ARM_REG_SP, RAM + 0xF000)
                c.uc.reg_write(UC_ARM_REG_LR, STOP)
                c.uc.emu_start(SLX.GUI_CODE, STOP, count=1000)
                self.assertEqual(c.uc.reg_read(UC_ARM_REG_R0), want)

    def test_no_mode_builder_recorded_is_skipped(self):
        c = Cam()
        c.w(SLX.MARK + 8, RAM + 0x7100)
        c.page()                                          # MARK+0x50 = 0: no call, no fault
        self.assertEqual(c.value('EXCL_FrameRate'), SLX.RATE_INDEX)

    def test_a_refusal_without_installer_state_writes_nothing(self):
        c = Cam(nbr_result=5)
        c.page()                                          # MARK+8 = 0: no entry to restore
        self.assertEqual(c.r(SLX.MARK + 0x1C), 3)

    def test_boot_in_custom_then_fhd_restores_through_the_notifier(self):
        """r4 on camera: no notifier since boot, page shows CUSTOM, then FHD."""
        c = Cam()
        c.w(DESC['EXCL_FrameRate'] + 8, 0)
        c.page()
        self.assertEqual(c.value('EXCL_FrameRate'), SLX.RATE_INDEX)
        c.resolution = 1
        c.vars.clear()
        c.call(RES, 1)                                    # MV_Resolution, last states never seen
        self.assertEqual(c.vars.get('EXCL_FrameRate'), 0)  # the saved stock value, notified
        self.assertEqual(c.value('EXCL_FrameRate'), 0)

    def setter(self, c, site, row):
        uc = c.uc
        var = RAM + 0xC800
        c.w(var + 8, row)
        sp = RAM + 0xF000
        for i, reg in enumerate((UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7)):
            uc.reg_write(reg, 0x3333 * (i + 1))
        uc.reg_write(UC_ARM_REG_SP, sp)
        uc.reg_write(UC_ARM_REG_R0, var)
        uc.reg_write(UC_ARM_REG_LR, STOP)
        uc.emu_start(site, STOP, count=100000)
        self.assertEqual(uc.reg_read(UC_ARM_REG_SP), sp)
        self.assertEqual(uc.reg_read(UC_ARM_REG_R0), 0)            # the callback's own result
        for i, reg in enumerate((UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7)):
            self.assertEqual(uc.reg_read(reg), 0x3333 * (i + 1))

    def test_menu_resolution_change_posts_both_lists(self):
        """r5 camera: in-menu FHD <-> CUSTOM updated frame rate only."""
        for site in (0xC057A6A0, 0xC05824D0):
            with self.subTest(site=hex(site)):
                c = Cam(resolution=2)                     # FHD, stock values 4 / 0
                c.w(DESC['EXCL_FrameRate'] + 8, 4)
                self.setter(c, site, 2)                   # -> CUSTOM (row 2)
                self.assertEqual(c.resolution, 4)
                self.assertEqual(c.vars, {'EXCL_FrameRate': SLX.RATE_INDEX,
                                          'EXCL_CinemaDNGQuality': SLX.BIT_INDEX})
                self.assertEqual((c.r(SLX.MARK + 0x3C), c.r(SLX.MARK + 0x40)), (4, 0))
                c.vars.clear()
                self.setter(c, site, 1)                   # -> FHD
                self.assertEqual(c.vars, {'EXCL_FrameRate': 4, 'EXCL_CinemaDNGQuality': 0})
                c.vars.clear()
                self.setter(c, site, 0)                   # -> UHD: nothing of ours is left
                self.assertEqual(c.vars, {})

    def test_menu_resolution_change_not_installed_posts_nothing(self):
        c = Cam(installed=False, resolution=2)
        self.setter(c, 0xC057A6A0, 2)
        self.assertEqual((c.vars, c.loads), ({}, []))

    def test_custom_saves_the_current_value_and_restores_it(self):
        c = Cam(resolution=1).call(RATE, 4).call(BIT, 1)         # stock wrote 104 / 101
        c.resolution = 4
        c.call(RATE, 0).call(BIT, 1)                              # entering CUSTOM
        self.assertEqual((c.r(SLX.MARK + 0x3C), c.r(SLX.MARK + 0x40)), (104, 101))
        c.resolution = 1
        c.vars.clear()
        c.call(RES, 1)
        self.assertEqual((c.vars['EXCL_FrameRate'], c.vars['EXCL_CinemaDNGQuality']), (104, 101))

    def test_entering_custom_calls_no_converter(self):
        """r7 froze entering CUSTOM; the converter call it added is gone."""
        c = Cam(resolution=1).call(RATE, 4)
        c.resolution = 4
        seen = []
        c.uc.hook_add(UC_HOOK_CODE, lambda uc, a, sz, d: seen.append(a), begin=0xC06CBBE0, end=0xC06CC06C)
        c.call(RATE, 0).call(BIT, 0)
        self.assertNotIn(0xC06CC068, seen)
        self.assertNotIn(0xC06CBBE0, seen)

    def test_leaving_custom_puts_14_bit_back_to_12(self):
        """r6 camera: 14-bit chosen in CUSTOM, then FHD -> bit-depth row stuck."""
        for how in ('menu', 'notifier', 'standby'):
            with self.subTest(how=how):
                c = Cam(resolution=2)
                c.bit = 1
                if how == 'menu':
                    self.setter(c, 0xC057A6A0, 1)          # -> FHD
                elif how == 'notifier':
                    c.call(RES, 1)
                else:
                    c.call(0xC059C640, 1)
                self.assertEqual((c.bit_sets, c.bit), ([0], 0))
                self.assertEqual(c.r(SLX.MARK + 0x4C), 1)

    def test_14_bit_stays_under_custom_and_12_is_left_alone(self):
        c = Cam(resolution=4)
        c.bit = 1
        c.call(RES, 2)
        self.assertEqual(c.bit_sets, [])
        c = Cam(resolution=1)
        c.call(RES, 1)
        self.assertEqual(c.bit_sets, [])

    def test_all_six_vtables_route_the_two_slots_to_the_hooked_sites(self):
        for vt in (0xC2DEE900, 0xC2DEF1B0, 0xC2DF2BDC, 0xC2DF34A0, 0xC2DF3D6C, 0xC2DF4620):
            self.assertEqual(struct.unpack_from('<I', IMAGE, vt + 0x6C4 - B)[0], RATE)
            self.assertEqual(struct.unpack_from('<I', IMAGE, vt + 0x740 - B)[0], BIT)


if __name__ == '__main__':
    unittest.main(verbosity=2)
