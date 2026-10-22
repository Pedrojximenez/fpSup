#!/usr/bin/env python3
"""test_rawview_image.py — 在真實韌體映像(out/MAIN_c0000000.bin)上模擬 rawview(fp-unicorn-emulation)。

    python3 test_rawview_image.py

與 test_rawview_build.py(假記憶體)不同:
  * launcher 在真實映像上執行 → 原廠字檢查用的是映像裡的真實指令,常數寫錯會立刻失敗;
  * 從每個真實 patch 點開始執行一條指令:原廠 bl → veneer → stub → 回到原廠下一條;
  * GUI↔enum 走韌體自己的 C06C0718/C06C0768/FUN_c06cfe18/FUN_c06cd610 與改過的 getter C06C07C0。
韌體函式只 stub 配置器與快取(沿用 fpSup/fp_usb_shell/test_loader_hook.Camera)。
模擬不代表相機:時序、GUI 重畫、實際 ISP 都要上機才知道。
"""
import pathlib, struct, sys, unittest

HERE = pathlib.Path(__file__).resolve().parent
SHELL = HERE.parents[2] / 'fpSup' / 'fp_usb_shell'
sys.path.insert(0, str(SHELL)); sys.path.insert(0, str(HERE))
sys.argv[1:] = [a for a in sys.argv[1:] if a.startswith('-')]
import test_loader_hook as T                     # noqa: E402
from unicorn.arm_const import UC_ARM_REG_SP, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_LR  # noqa: E402


def _call(self, pc, r0=0, r1=0, lr=T.DONE, sp=T.STACK - 0x1004):
    """T.Camera.call 的 5M 指令上限不夠:launcher 產 124 張表約 7M 指令(實機約數十 ms)。其餘相同。"""
    mu = self.mu
    mu.reg_write(UC_ARM_REG_SP, sp)
    mu.reg_write(UC_ARM_REG_R0, r0)
    mu.reg_write(UC_ARM_REG_R1, r1)
    mu.reg_write(UC_ARM_REG_LR, lr)
    mu.emu_start(pc, T.DONE if lr == T.DONE else lr, count=30_000_000)
    return self.r(UC_ARM_REG_R0), self.r(UC_ARM_REG_SP)


T.Camera.call = _call
import build_bcolor as B                        # noqa: E402
import rv_tables                                 # noqa: E402
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R4,  # noqa: E402
                               UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_SL, UC_ARM_REG_IP,
                               UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_CPSR)

STAGING = T.HEAP + 0x300000
CAVE_BUMP, ARENA = 0xC072E060, 0xC072E064
SITE_A, SITE_B = 0xC0313244, 0xC032F728
MA_SITES = (0xC0568950, 0xC056D028, 0xC05818B8)
MB_SITE, MC_SITE = 0xC0595734, 0xC0075CF4
ML_SITE = 0xC059DA1C
COLOR_ITEM = 0xC31ACDC4
CONV_VT = 0xC2DEAE98 - 0x11C                    # 色彩轉換器 vtable(+0x11C = getter C06C07C0)
BANK_A, SET_SEL = 0xC31B32BC, 0xC31B954C
ROOT_P70, MODE_TAB, KEY = 0xC2F1A0D4, 0xC0B3D670, 0xC2F19D44
import rv_uidata as U                                    # noqa: E402
import rv_color                                          # noqa: E402
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'open-gate' / 'build'))
ROOT_P08 = rv_color.ROOT_P08
PUB = T.HEAP + 0x3F0400                                  # 發布 UI 變數的記錄位置(測試用)
UI_SITES = (0xC05E2200, 0xC0568A3C, 0xC0595908, 0xC056D5F8, 0xC056D498, 0xC059588C, 0xC05959E4,    # RAW 列調整的 bl
            0xC05689A8, 0xC05957B0)                                                 # 預覽 GUI→enum、v82
H1 = U.H1_SITE
PAGE_SITES = tuple(a for a, *_ in U.PAGE)
NBR_BASE = 0xC0D22400


class CardCamera(T.Camera):
    """整張卡的測試:Camera 的 H_ADDR 固定回 HEAP,而 stage2 的 journal 也在 HEAP + 0x20000 起。
    rawview 配置 0x42000(62 張表)會蓋到它;實機配置器不會。這裡讓 H_ADDR 回另一塊。"""
    RAW_HEAP = T.HEAP + 0x200000

    def _hook(self, mu, addr, size, ud):
        if addr == T.F['H_ADDR']:
            return self._ret(self.RAW_HEAP)
        return super()._hook(mu, addr, size, ud)


class Rig:
    def __init__(self):
        self.blob, self.info = B.build_blob()
        cam = self.cam = T.Camera({}, b'')
        cam.mu.mem_write(CAVE_BUMP, struct.pack('<I', ARENA))     # stage2 每次開機重設
        cam.mu.mem_write(STAGING, self.blob)
        cam.mu.mem_write(ROOT_P08, struct.pack('<II', rv_color.MAT_TAB, 35))   # .data 的執行期初值(seg1)
        # 發布 UI 變數 FUN_c0593f30 換成記錄器:[PUB] = 名稱、[PUB+4] = 值、[PUB+8] = 次數
        mw = lambda op, imm: op | (imm >> 12 & 0xF) << 16 | (imm & 0xFFF)
        cam.mu.mem_write(0xC0593F30, struct.pack('<9I', mw(0xE3003000, PUB & 0xFFFF), mw(0xE3403000, PUB >> 16),
                                                 0xE5831000, 0xE5832004, 0xE593C008, 0xE28CC001, 0xE583C008,
                                                 0xE12FFF1E, 0))
        self.orig = {a: cam.word(a) for a in (SITE_A, SITE_B, *MA_SITES, MB_SITE, MC_SITE, ML_SITE,
                                              0xC06C07CC, 0xC06C07D0, 0xC06C07D8, H1, *PAGE_SITES)}
        r0, sp = cam.call(STAGING, lr=T.DONE, sp=T.STACK - 0x1000)
        self.ret, self.sp = r0, sp
        self.T0 = (T.HEAP + 0xFFF) & ~0xFFF                       # Camera 的 H_ADDR 回 HEAP
        self.res = self.T0 + 0x3E200
        conv = T.HEAP + 0x3F0000
        cam.mu.mem_write(conv + 4, struct.pack('<I', CONV_VT))
        self.conv = conv

    def step(self, pc, stop, regs):
        """從 pc 執行到 stop(原廠下一條)。"""
        mu = self.cam.mu
        for k, v in regs.items():
            mu.reg_write(k, v & 0xFFFFFFFF)
        mu.reg_write(UC_ARM_REG_LR, T.DONE)
        mu.emu_start(pc, stop, count=200000)
        return mu

    def u32(self, a):
        return self.cam.word(a)


class Install(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rig()

    def test_image_holds_the_expected_stock_words(self):
        # launcher 的 GUARD 常數必須就是映像裡的指令
        self.assertEqual(self.r.orig[SITE_A], 0xE595200C)
        self.assertEqual(self.r.orig[SITE_B], 0xE59C6000)
        self.assertEqual(self.r.orig[MC_SITE], 0xE15A0006)

    def test_returns_clean(self):
        self.assertEqual(self.r.ret, 0)
        self.assertEqual(self.r.sp, T.STACK - 0x1000)

    def test_tables_from_real_launcher(self):
        LOG = rv_tables.log_q16(); WQ, SAMP, Bc = rv_tables.coefs()
        for k in (0, 9, 30, 31, 40, 61, 62, 71, 93, 102, 123):
            got = struct.unpack('<2048H', self.r.cam.mu.mem_read(self.r.T0 + rv_tables.table_addr_off(k), 4096))
            self.assertEqual(list(got), rv_tables.table(k, LOG, WQ, SAMP, Bc))

    def test_every_site_is_a_bl_to_a_veneer_to_our_stub(self):
        want = {SITE_A: 'stub_gs', SITE_B: 'stub_dg', MB_SITE: 'stub_mb', MC_SITE: 'stub_mc', ML_SITE: 'stub_ml',
                **{s: 'stub_ma' for s in MA_SITES}}
        for site, stub in want.items():
            w = self.r.u32(site)
            self.assertEqual(w >> 24, 0xEB, hex(site))
            ven = site + 8 + ((((w & 0xFFFFFF) ^ 0x800000) - 0x800000) * 4)
            self.assertTrue(ARENA <= ven < ARENA + 56, hex(ven))
            self.assertEqual(self.r.u32(ven), 0xE51FF004)
            self.assertEqual(self.r.u32(ven + 4), self.r.res + self.r.info[stub], stub)

    def test_real_getter_returns_17_row_table(self):
        mu = self.r.step(0xC06C07C0, 0xC06C07E4, {UC_ARM_REG_R0: self.r.conv,
                                                    UC_ARM_REG_R1: T.HEAP + 0x3F0100,
                                                    UC_ARM_REG_SP: T.STACK - 0x1000})
        self.assertEqual(mu.reg_read(UC_ARM_REG_R0), 17)
        tab = self.r.u32(T.HEAP + 0x3F0100)
        self.assertEqual(tab, self.r.res + 0x98)
        self.assertEqual(struct.unpack('<2I', mu.mem_read(tab + 16 * 8, 8)), (0xC, 16))


class UiInstall(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Rig()

    def test_image_stock_words(self):
        self.assertEqual(self.r.orig[H1], U.H1_ORIG)
        for a, old, new in U.PAGE:
            self.assertEqual(self.r.orig[a], old, hex(a))

    def test_page_words_patched(self):
        for a, old, new in U.PAGE:
            self.assertEqual(self.r.u32(a), new, hex(a))

    def test_h1_is_thumb_bw_to_thumb_veneer(self):
        w = self.r.u32(H1)
        hw1, hw2 = w & 0xFFFF, w >> 16
        self.assertEqual((hw1 >> 11, hw2 & 0xD000), (0x1E, 0x9000))           # B.W T4
        S = (hw1 >> 10) & 1
        I1, I2 = 1 - (((hw2 >> 13) & 1) ^ S), 1 - (((hw2 >> 11) & 1) ^ S)
        off = (S << 24) | (I1 << 23) | (I2 << 22) | ((hw1 & 0x3FF) << 12) | ((hw2 & 0x7FF) << 1)
        off -= (S << 25)
        ven = H1 + 4 + off
        self.assertEqual(ven, ARENA + 40)
        self.assertEqual(self.r.u32(ven), 0xF000F8DF)
        self.assertEqual(self.r.u32(ven + 4), self.r.res + self.r.info['stub_fv'])

    def fv(self, addr, size):
        mu = self.r.cam.mu
        view, sp = T.HEAP + 0x3F0400, T.STACK - 0x1010
        mu.mem_write(view, b'\0' * 16)
        mu.mem_write(sp, struct.pack('<I', size))
        self.r.step(H1 | 1, 0xC05E5BF0, {UC_ARM_REG_R0: addr - NBR_BASE, UC_ARM_REG_R1: NBR_BASE,
                                         UC_ARM_REG_R5: view, UC_ARM_REG_SP: sp})
        return self.r.u32(view + 4), self.r.u32(sp)

    def test_h1_swaps_the_three_csvs(self):
        for name, at, data in U.blobs():
            got, size = self.fv(at, 999)
            self.assertEqual(size, len(data), name)
            self.assertEqual(bytes(self.r.cam.mu.mem_read(got, len(data))), data, name)

    def test_h1_swaps_raw_icon(self):
        import xci
        for name, at, data in U.icon_blobs():
            got, size = self.fv(at, 533)
            self.assertEqual(size, len(data), name)
            blob = bytes(self.r.cam.mu.mem_read(got, len(data)))
            self.assertEqual(blob, data, name)
            self.assertEqual(xci.decode(blob)[:2], (86, 74))                 # 與原廠 set_* 圖示同尺寸
        self.assertIn(b'17,set_flash_1,', U.blobs()[0][2])                  # 第 17 列用借來的名稱

    def test_h1_never_swaps_glyphs(self):
        # fs2-11 上機:依條件換字形檔會因圖片快取而錯亂、外溢 → 任何條件下都不換 font_menu_LB
        res = self.r.res
        mw = lambda off, v: self.r.cam.mu.mem_write(res + off, struct.pack('<I', v))
        mw(4, 1); mw(0x1B8, 1); mw(0x1BC, 16)
        for _, at, _, _ in U.GLYPHS_H1:
            self.assertEqual(self.fv(at, 111), (at, 111))

    def test_h1_leaves_other_files(self):
        for at in (0xC0F8E2EC, 0xC0D566E8, 0xC0D22400, 0xC14E4F98, 0xC14EBCC4):
            self.assertEqual(self.fv(at, 123), (at, 123))


class CardBoot(unittest.TestCase):
    """整張 FS2 卡:真實 loader → stage2 宣告區段記 journal → rawview → 關機回呼寫回。"""
    @classmethod
    def setUpClass(cls):
        import re, subprocess, tempfile
        out = pathlib.Path(tempfile.mkdtemp())
        r = subprocess.run([sys.executable, '-B', str(HERE / 'build_bcolor.py'), '--fs2', '--out', str(out)],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        text = (out / 'AutoRun.txt').read_text()
        sets = re.findall(r'^mem set (0x\w+) (0x\w+)', text, re.M)
        cls.loader = {int(a, 16): int(v, 16) for a, v in sets if T.CAVE_LO <= int(a, 16) < T.CAVE_LOW + 0x200}
        cls.bin = (out / 'fpSup.BIN').read_bytes()
        cls.sites = [(a, w) for a, w, _ in B.hook_sites()]

    def boot(self, leftover=None):
        cam = CardCamera(self.loader, self.bin)
        mu = cam.mu
        mu.mem_write(ROOT_P70, struct.pack('<I', 0xC0B3D670))           # .data 的執行期初值
        mu.mem_write(ROOT_P08, struct.pack('<II', rv_color.MAT_TAB, 35))
        mu.mem_write(T.SITE, struct.pack('<I', 0xEB000000 | ((((T.CAVE_LOW + 4) - T.SITE - 8) >> 2) & 0xFFFFFF)))
        for a, w in (leftover or {}).items():
            mu.mem_write(a, struct.pack('<I', w))
        before = {a: cam.word(a) for a, _ in self.sites}
        r0, sp = cam.call(T.CAVE_LOW + 4, r0=0xC0BABDD8, r1=1, lr=T.AR_RET, sp=T.STACK - 0x1004)
        return cam, before

    def journal(self, cam):
        x = cam.word(T.MARK + 8)
        j, got = cam.word(x + 8), {}
        while cam.word(j):
            a, n = cam.word(j), cam.word(j + 4)
            got[a] = bytes(cam.mu.mem_read(j + 8, n))
            j += 8 + n
        return x, got

    def run_rawview(self, cam):
        blob, info = B.build_blob()
        cam.mu.mem_write(CAVE_BUMP, struct.pack('<I', ARENA))
        cam.mu.mem_write(STAGING, blob)
        cam.call(STAGING, lr=T.DONE, sp=T.STACK - 0x1000)

    def test_sites_declared_and_journaled_as_stock(self):
        cam, before = self.boot()
        self.assertIsNone(cam.ar_started)
        _, j = self.journal(cam)
        for a, w in self.sites:
            self.assertIn(a, j, hex(a))
            self.assertEqual(j[a][:4], w, hex(a))                   # 冷開機:記到的就是原廠字
            self.assertEqual(cam.word(a), struct.unpack('<I', w)[0], hex(a))

    def test_power_off_restores_every_site(self):
        cam, before = self.boot()
        self.run_rawview(cam)
        patched = [a for a, w in self.sites if cam.word(a) != struct.unpack('<I', w)[0]]
        self.assertEqual(len(patched), len(self.sites) - 2)          # root+0x70/+0x08 只在 RAW 生效時才改
        cam.mu.mem_write(ROOT_P70, struct.pack('<I', 0x45123456))    # 模擬 RAW 開著時關機
        cam.mu.mem_write(ROOT_P08, struct.pack('<I', 0x45123000))
        x, _ = self.journal(cam)
        for _ in range(2):
            cam.call(cam.word(x + 4), r0=x, r1=4)
        for a, w in self.sites:
            self.assertEqual(cam.word(a), struct.unpack('<I', w)[0], hex(a))

    def test_leftover_patches_are_repaired_before_rawview(self):
        stale = {a: 0xEB000000 | (i + 1) for i, (a, w) in enumerate(self.sites)}
        cam, before = self.boot(leftover=stale)
        for a, w in self.sites:
            self.assertEqual(cam.word(a), struct.unpack('<I', w)[0], hex(a))   # stage2 寫回原廠字
        self.run_rawview(cam)
        self.assertEqual(cam.word(SITE_A) >> 24, 0xEB)
        self.assertNotEqual(cam.word(SITE_A), stale[SITE_A])                    # 我們的 bl,不是殘留


class StandDown(unittest.TestCase):
    """任何一個 patch 點不是原廠字(別的 sup、別版韌體、上次沒還原)→ 什麼都不裝。"""
    SITES = (SITE_A, SITE_B, *MA_SITES, MB_SITE, MC_SITE, ML_SITE, 0xC06C07CC, 0xC06C07D0, 0xC06C07D8,
             H1, *PAGE_SITES, *UI_SITES, 0xC02C4BE4, 0xC02C4BE8, 0xC02C4C98, 0xC02C4C9C,
             0xC0D119FC, 0xC0D11A00, 0xC056D548, 0xC056D3E8, 0xC056D5A0, 0xC056D440,
             0xC059581C, 0xC0595974, 0xC0595854, 0xC05959AC)
    DATA = (ROOT_P08, ROOT_P08 + 4, rv_color.OFF_REC, rv_color.OFF_REC + 4, rv_color.OFF_REC + 16)   # 矩陣表與 OFF 筆

    def run_with(self, bad=None):
        blob, _ = B.build_blob()
        cam = T.Camera({}, b'')
        cam.mu.mem_write(CAVE_BUMP, struct.pack('<I', ARENA))
        cam.mu.mem_write(STAGING, blob)
        cam.mu.mem_write(ROOT_P08, struct.pack('<II', rv_color.MAT_TAB, 35))   # .data 的執行期初值
        if bad is not None:
            cam.mu.mem_write(bad, struct.pack('<I', 0xE1A00000))           # nop:外來的字
        before = {s: cam.word(s) for s in self.SITES + self.DATA}
        r0, sp = cam.call(STAGING, lr=T.DONE, sp=T.STACK - 0x1000)
        self.assertEqual((r0, sp), (0, T.STACK - 0x1000))
        return cam, before

    def test_installs_when_all_stock(self):                                  # 正向對照:否則下面的測試不證明什麼
        cam, before = self.run_with()
        self.assertIn('H_GET', cam.calls)
        self.assertNotEqual(cam.word(SITE_A), before[SITE_A])

    def test_each_guard(self):
        for site in self.SITES + self.DATA:
            with self.subTest(site=hex(site)):
                cam, before = self.run_with(site)
                self.assertEqual({s: cam.word(s) for s in self.SITES + self.DATA}, before)
                self.assertEqual(cam.word(CAVE_BUMP), ARENA)
                self.assertNotIn('H_GET', cam.calls)


class Menu(unittest.TestCase):
    def setUp(self):
        self.r = Rig()
        self.flag = lambda: self.r.u32(self.r.res + 4)
        self.pend = lambda: self.r.u32(self.r.res + 0x94)
        self.var = lambda: self.r.u32(self.r.res + 0x1BC)

    def gui_to_enum(self, site, gui):
        mu = self.r.step(site, site + 4, {UC_ARM_REG_R0: self.r.conv, UC_ARM_REG_R1: gui,
                                           UC_ARM_REG_SP: T.STACK - 0x1000})
        return mu.reg_read(UC_ARM_REG_R0)

    def enum_to_gui(self, e):
        mu = self.r.step(MB_SITE, MB_SITE + 4, {UC_ARM_REG_R0: self.r.conv, UC_ARM_REG_R1: e,
                                                 UC_ARM_REG_SP: T.STACK - 0x1000})
        return mu.reg_read(UC_ARM_REG_R0)

    def setter(self, item, old, new):
        mu = self.r.step(MC_SITE, MC_SITE + 4, {UC_ARM_REG_R4: item, UC_ARM_REG_SL: old,
                                                 UC_ARM_REG_R6: new, UC_ARM_REG_SP: T.STACK - 0x1004})
        return bool(mu.reg_read(UC_ARM_REG_CPSR) & (1 << 30))

    def test_real_converters_with_17_rows(self):
        for site in MA_SITES:
            qs = site == 0xC05818B8                                    # QS:重新同步,不算選擇
            self.assertEqual(self.gui_to_enum(site, 16), 0xC)          # RAW 列 → OFF enum
            self.assertEqual(self.pend(), 0 if qs else 17)
            self.assertEqual(self.gui_to_enum(site, 15), 0xC)
            self.assertEqual(self.pend(), 0 if qs else 16)
            self.assertEqual(self.gui_to_enum(site, 6), 15)            # 原廠列不變(WarmGold)
            self.assertEqual(self.pend(), 0)
        self.assertEqual(self.enum_to_gui(0xC), 15)                    # flag 0:OFF
        self.assertEqual(self.enum_to_gui(0), 0)

    def select(self, gui, site=MA_SITES[0]):
        self.gui_to_enum(site, gui)
        return self.setter(COLOR_ITEM, 0xC, 0xC)

    def test_preview_path_through_real_site(self):
        # 游標移動(預覽)走 C05689A8 → 原廠 C06C07E8(同一張 17 筆表)
        self.assertEqual(self.gui_to_enum(0xC05689A8, 16), 0xC)
        self.assertEqual(self.pend(), 17)
        self.assertFalse(self.setter(COLOR_ITEM, 0xC, 0xC))
        self.assertEqual(self.flag(), 1)
        self.assertEqual(self.gui_to_enum(0xC05689A8, 14), 11)        # 原廠列:GUI 14 → enum 11
        self.assertEqual(self.pend(), 0)

    def test_effect_glyph_names_through_real_site(self):
        from unicorn.arm_const import UC_ARM_REG_R2, UC_ARM_REG_R11
        r = self.r; mu = r.cam.mu
        w = r.u32(0xC05E2200)                                    # Thumb BL → veneer 16 → stub_ai
        h1, h2 = w & 0xFFFF, w >> 16
        self.assertEqual((h1 & 0xF800, h2 & 0xD000), (0xF000, 0xD000))
        S = h1 >> 10 & 1; I1 = ~(h2 >> 13 ^ S) & 1; I2 = ~(h2 >> 11 ^ S) & 1
        off = (S << 24 | I1 << 23 | I2 << 22 | (h1 & 0x3FF) << 12 | (h2 & 0x7FF) << 1) - ((1 << 25) if S else 0)
        ven = 0xC05E2200 + 4 + off
        self.assertEqual((ven, r.u32(ven), r.u32(ven + 4)), (ARENA + 128, 0xF000F8DF, r.res + r.info['stub_ai']))
        cont = 0xC3000600
        K06, K07, LB5, LB0 = 0xC18E6BA0, 0xC18E6BB8, 0xC18E67B0, 0xC18E6760
        S_, G_, A_ = 0xC18E697C, 0xC18E692C, 0xC18E6940   # bCOLOR:font_menu_LB_id_F / B / C(FC、BC)
        def apply(name, cid=0x177):
            mu.mem_write(cont + 0x18, struct.pack('<I', cid))
            m = r.step(0xC05E2200 | 1, 0xC05D6BB8, {UC_ARM_REG_R2: name, UC_ARM_REG_R11: cont, UC_ARM_REG_SP: T.STACK - 0x1000})
            return m.reg_read(UC_ARM_REG_R2)
        self.assertEqual(apply(K06), K06)                        # RAW 未生效:原名
        self.select(16)
        self.assertEqual([apply(K06), apply(K07), apply(LB5, 0x178), apply(LB0, 0x178)], [S_, G_, A_, LB0])
        self.assertEqual(apply(K06, 0x200), K06)                 # 別的容器:不換
        r.cam.mu.mem_write(r.res + 0x1BC, struct.pack('<I', 14)) # 游標不在 RAW 列:不換
        self.assertEqual(apply(K06), K06)
        self.select(15)
        self.assertEqual(apply(LB5, 0x178), LB5)

    def test_select_raw_then_off_through_real_sites(self):
        self.assertFalse(self.select(16))                              # 強制「不相等」
        self.assertEqual((self.flag(), self.pend()), (1, 0))
        self.assertEqual(self.enum_to_gui(0xC), 16)
        self.assertFalse(self.select(15, MA_SITES[1]))
        self.assertEqual(self.flag(), 0)
        self.assertEqual(self.enum_to_gui(0xC), 15)
        self.assertTrue(self.setter(0xC3000040, 3, 3))                # 別的 item:原比較

    def test_repeat_off_write_keeps_raw(self):
        # 2026-09-25 上機:COLOR 鍵選單選第 17 列後按 OK,韌體再寫一次 OFF(不經 GUI 轉換)→ 舊規則把 RAW 清掉
        self.select(16)
        self.assertTrue(self.setter(COLOR_ITEM, 0xC, 0xC))           # 無 pend、值仍 OFF:不變 → 原比較(相等)
        self.assertEqual(self.flag(), 1)
        self.assertEqual(self.enum_to_gui(0xC), 16)
        self.select(15)                                                # 明確選 OFF
        self.assertEqual(self.flag(), 0)
        self.select(16)
        self.assertFalse(self.setter(COLOR_ITEM, 0xC, 5))              # 改成別的色彩模式
        self.assertEqual(self.flag(), 0)

    def real_enum_to_gui(self, e):
        mu = self.r.step(0xC06C0768, T.DONE, {UC_ARM_REG_R0: self.r.conv, UC_ARM_REG_R1: e,
                                              UC_ARM_REG_SP: T.STACK - 0x1000})
        return mu.reg_read(UC_ARM_REG_R0)

    def lv(self, e):
        mu = self.r.step(ML_SITE, ML_SITE + 4, {UC_ARM_REG_R0: self.r.conv, UC_ARM_REG_R1: e,
                                               UC_ARM_REG_SP: T.STACK - 0x1000})
        return mu.reg_read(UC_ARM_REG_R0)

    def test_any_enum_to_gui_path_gives_16_when_raw(self):
        # 2026-09-25 上機:RAW 開後韌體經未 patch 的 enum→GUI 路徑以 15 重新同步 → 改表讓所有路徑都得 16
        self.assertEqual((self.real_enum_to_gui(0xC), self.lv(0xC)), (15, 15))
        self.select(16)
        self.assertEqual(self.real_enum_to_gui(0xC), 16)            # 原廠函式,未經任何 stub
        self.assertEqual(self.lv(0xC), 15)                          # LV_ColorMode 不給 16
        self.assertEqual(self.real_enum_to_gui(0), 0)
        for gui in (15, 16):                                         # 兩列都還是 OFF
            self.assertEqual(self.gui_to_enum(MA_SITES[1], gui), 0xC)
        self.assertTrue(self.setter(COLOR_ITEM, 0xC, 0xC))          # 重新同步後再寫 OFF(pend 17 → 仍 RAW)
        self.assertEqual(self.flag(), 1)
        self.select(15)
        self.assertEqual((self.flag(), self.real_enum_to_gui(0xC)), (0, 15))

    def test_debug_ring_records_events(self):
        self.select(16)
        n = self.r.u32(self.r.res + 0x120)
        self.assertEqual(n, 2)
        e0 = struct.unpack('<4I', self.r.cam.mu.mem_read(self.r.res + 0x124, 16))
        e1 = struct.unpack('<4I', self.r.cam.mu.mem_read(self.r.res + 0x134, 16))
        self.assertEqual(e0, (0x4D | (MA_SITES[0] + 4 - 0xC0000000) << 8, 16, 17, 0))   # 記下呼叫點
        self.assertEqual(e1, (0x43 | (0xC << 8), 0xC, 15, 16))

    def test_pend_but_value_not_off(self):
        self.gui_to_enum(MA_SITES[0], 16)
        self.setter(COLOR_ITEM, 0xC, 3)                                # 選了 RAW 列,但寫入的值不是 OFF
        self.assertEqual((self.flag(), self.pend()), (0, 0))
        self.assertEqual(self.enum_to_gui(0xC), 15)

    def s32(self, a):
        return struct.unpack('<i', self.r.cam.mu.mem_read(a, 4))[0]

    def through(self, site, regs):
        """執行 RAW 列調整的 bl 點(真實映像的指令,經 veneer 到 stub),回 r0(有號)。"""
        mu = self.r.step(site, site + 4, {UC_ARM_REG_SP: T.STACK - 0x1000, **regs})
        v = mu.reg_read(UC_ARM_REG_R0)
        return v - (1 << 32) if v & 0x80000000 else v

    def test_updown_and_saturation_through_real_sites(self):
        from unicorn.arm_const import UC_ARM_REG_R7
        self.select(16)
        res = self.r.res
        for site in (0xC0595908, 0xC05957B0):                                                                 # v87 AJ、v82 FIX
            self.assertEqual(self.through(site, {UC_ARM_REG_R0: 0, UC_ARM_REG_R1: 5, UC_ARM_REG_R7: 0xC}), -5)  # SA
        self.assertEqual(self.through(0xC0568A3C, {UC_ARM_REG_R0: 0, UC_ARM_REG_R1: 3}), 0)                     # 往上 3 格
        self.assertEqual(self.r.u32(res + 0x1A4), 1)                                                          # GA
        self.assertEqual((self.r.u32(PUB), self.r.u32(PUB + 4), self.r.u32(PUB + 8)), (0xC2DF01A8, 5, 2))    # 框設為 +5
        for site in (0xC0595908, 0xC05957B0):
            self.assertEqual(self.through(site, {UC_ARM_REG_R0: 0, UC_ARM_REG_R1: 0, UC_ARM_REG_R7: 0xC}), 5)
        self.through(0xC0568A3C, {UC_ARM_REG_R0: 0, UC_ARM_REG_R1: 5})                                         # 開選單時複製 FIX(+5)→ 不切換
        self.assertEqual((self.r.u32(res + 0x1A4), self.r.u32(PUB + 8)), (1, 2))
        self.through(0xC056D5F8, {UC_ARM_REG_R0: 0, UC_ARM_REG_R1: 1})                                         # AJ 捲動:bCOLOR 鎖 0
        self.assertEqual((self.s32(res + 0x1B0), self.s32(res + 0x1B4)), (0, 0))
        self.through(0xC056D498, {UC_ARM_REG_R0: 0, UC_ARM_REG_R1: 1})                                         # FIX 確認:存 0
        self.assertEqual(self.s32(res + 0x1B4), 0)
        self.assertEqual(self.through(0xC059588C, {UC_ARM_REG_R0: 0, UC_ARM_REG_R1: 0}), 0)                    # v85 COLFIX
        self.assertEqual(self.through(0xC05959E4, {UC_ARM_REG_R0: 0, UC_ARM_REG_R1: 0}), 0)                    # v90 COLAJ
        self.through(0xC056D548, {UC_ARM_REG_R0: 0, UC_ARM_REG_R1: 1})                                         # 對比 AJ +1
        self.through(0xC056D3E8, {UC_ARM_REG_R0: 0, UC_ARM_REG_R1: 1})                                         # 對比 FIX
        self.assertEqual((self.s32(res + 0x1C4), self.s32(res + 0x1C8)), (1, 1))
        self.assertEqual(self.through(0xC059581C, {UC_ARM_REG_R0: 0, UC_ARM_REG_R1: 0}), 1)                    # v83 COLFIX 對比
        self.assertEqual(self.through(0xC0595974, {UC_ARM_REG_R0: 0, UC_ARM_REG_R1: 0}), 1)                    # v88 COLAJ 對比
        n = self.r.u32(PUB + 8)
        self.through(0xC056D548, {UC_ARM_REG_R0: 0, UC_ARM_REG_R1: 2})                                         # 捲過 +1
        self.assertEqual((self.s32(res + 0x1C4), self.r.u32(PUB), self.r.u32(PUB + 4), self.r.u32(PUB + 8)),
                         (1, 0xC2DF0238, 1, n + 1))                                                            # 夾 1、刻度拉回
        n = self.r.u32(PUB + 8)
        self.through(0xC056D5F8, {UC_ARM_REG_R0: 0, UC_ARM_REG_R1: (-1) & 0xFFFFFFFF})                         # 捲到 0 以下
        self.assertEqual((self.s32(res + 0x1B0), self.r.u32(PUB), self.r.u32(PUB + 4), self.r.u32(PUB + 8)),
                         (0, 0xC2DF0260, 0, n + 1))                                                            # 夾 0、刻度拉回

    def test_gain_and_table_through_real_sites(self):
        mu = self.r.cam.mu
        mu.mem_write(SET_SEL, b'\0')
        mu.mem_write(BANK_A + 0x12C, struct.pack('<3I', 0xC, 0, 0)[:4])
        mu.mem_write(BANK_A + 0x784, struct.pack('<2I', 0, 0))
        helper = 0xC3000200
        mu.mem_write(helper + 0xC, struct.pack('<I', 0))
        self.gui_to_enum(MA_SITES[0], 16); self.setter(COLOR_ITEM, 0xC, 0xC)
        self.assertEqual(self.r.u32(ROOT_P08), rv_color.MAT_TAB)
        m = self.r.step(SITE_A, SITE_A + 4, {UC_ARM_REG_R5: helper, UC_ARM_REG_R6: 936,
                                               UC_ARM_REG_SP: T.STACK - 0x1000})
        self.assertEqual(m.reg_read(UC_ARM_REG_R2), 7)
        self.assertEqual(self.r.u32(ROOT_P70), self.r.T0 + 0x3E060)
        self.assertEqual(self.r.u32(KEY), 0xFFFFFFFF)
        self.assertEqual(self.r.u32(self.r.T0 + 0x3E004 + 4), self.r.T0 + 9 * 0x1000)
        mu.mem_write(T.HEAP + 0x3F0200, struct.pack('<I', 0x2000))
        m = self.r.step(SITE_B, SITE_B + 4, {UC_ARM_REG_IP: T.HEAP + 0x3F0200, UC_ARM_REG_R5: 0,
                                               UC_ARM_REG_SP: T.STACK - 0x1004})
        self.assertEqual(m.reg_read(UC_ARM_REG_R6), 0x400)
        # 韌體實際的 mode→tone 查找:OFF(0x24)經副本落在插槽 → 表
        mode = self.r.u32(ROOT_P70)
        n = self.r.u32(mode + 0x11C)
        a = (0xC0971114 + n * 8 + 4) & 0xFFFFFFFF
        self.assertEqual(self.r.u32(a), self.r.T0 + 9 * 0x1000)


if __name__ == '__main__':
    unittest.main(verbosity=2)


class Matrix(unittest.TestCase):
    """bCOLOR 生效時 root+0x08 → 副本,OFF 筆 = sat_tab[lat | con << 1];韌體自己的查表(root+0x08)拿到它。"""
    def test_sat_levels_through_real_sites(self):
        r = Rig()
        mu = r.cam.mu
        mu.mem_write(SET_SEL, b'\0')
        mu.mem_write(BANK_A + 0x12C, struct.pack('<I', 0xC))
        mu.mem_write(BANK_A + 0x784, struct.pack('<2I', 0, 0))
        helper = 0xC3000200
        mu.mem_write(helper + 0xC, struct.pack('<I', 0))
        def gs():
            r.step(SITE_A, SITE_A + 4, {UC_ARM_REG_R5: helper, UC_ARM_REG_R6: 936, UC_ARM_REG_SP: T.STACK - 0x1000})
        r.step(MA_SITES[0], MA_SITES[0] + 4, {UC_ARM_REG_R0: r.conv, UC_ARM_REG_R1: 16, UC_ARM_REG_SP: T.STACK - 0x1000})
        r.step(MC_SITE, MC_SITE + 4, {UC_ARM_REG_R4: COLOR_ITEM, UC_ARM_REG_SL: 0xC, UC_ARM_REG_R6: 0xC, UC_ARM_REG_SP: T.STACK - 0x1004})
        import rv_dngcm
        box = lambda v: r.step(0xC0568A3C, 0xC0568A40, {UC_ARM_REG_R0: 0, UC_ARM_REG_R1: v & 0xFFFFFFFF, UC_ARM_REG_SP: T.STACK - 0x1000})
        con = lambda v: r.step(0xC056D548, 0xC056D54C, {UC_ARM_REG_R0: 0, UC_ARM_REG_R1: v, UC_ARM_REG_SP: T.STACK - 0x1000})
        sat = lambda v: r.step(0xC056D5F8, 0xC056D5FC, {UC_ARM_REG_R0: 0, UC_ARM_REG_R1: v, UC_ARM_REG_SP: T.STACK - 0x1000})
        # (動作, lat, con):框往上 → BC、往下 → FC;對比 0/1 → Video / Extended;飽和度不影響矩陣
        for act, lat, cn in ((None, 0, 0), (lambda: sat(1), 0, 0), (lambda: box(1), 1, 0), (lambda: con(1), 1, 1),
                             (lambda: box(0), 0, 1), (lambda: con(0), 0, 0), (lambda: box(1), 1, 0)):
            if act:
                act()
            gs()
            p = r.u32(ROOT_P08)
            self.assertNotEqual(p, rv_color.MAT_TAB)
            self.assertEqual(struct.unpack('<I9h', mu.mem_read(p + 34 * 0x18, 22)), (0x24, *rv_color.bc_table(lat | cn << 1)), (lat, cn))
            self.assertEqual(r.u32(r.T0 + 0x3E004 + 4), r.T0 + rv_tables.table_addr_off(lat * 31 + cn * 62 + 9), (lat, cn))
            # DNG writer 的真實指令(OFF 分支)載入的 CM 常數位址 → cm_buf:FC = fp 校準、BC = BMCC
            for site, off in ((0xC02C4BE4, 0), (0xC02C4C98, 72)):
                m = r.step(site, site + 8, {UC_ARM_REG_SP: T.STACK - 0x1000})
                a = m.reg_read(UC_ARM_REG_R2)
                self.assertEqual(a, r.res + r.info['cm_buf'] + off)
                lv = lat + 1
                self.assertEqual(bytes(mu.mem_read(a, 72)), rv_dngcm.blob()[lv * 144 + off:lv * 144 + off + 72], (lat, cn))
        r.step(MA_SITES[0], MA_SITES[0] + 4, {UC_ARM_REG_R0: r.conv, UC_ARM_REG_R1: 15, UC_ARM_REG_SP: T.STACK - 0x1000})
        r.step(MC_SITE, MC_SITE + 4, {UC_ARM_REG_R4: COLOR_ITEM, UC_ARM_REG_SL: 0xC, UC_ARM_REG_R6: 0xC, UC_ARM_REG_SP: T.STACK - 0x1004})
        gs()                                                             # 選回 OFF:全部原廠
        self.assertEqual((r.u32(ROOT_P08), r.u32(ROOT_P70)), (rv_color.MAT_TAB, MODE_TAB))
        import rv_dngcm
        self.assertEqual(bytes(mu.mem_read(r.res + r.info['cm_buf'], 144)), rv_dngcm.blob()[:144])   # 回原廠 OFF 常數
