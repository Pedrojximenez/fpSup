#!/usr/bin/env python3
"""test_rawview_build.py — 離線驗證 rawview 卡(unicorn 模擬 launcher 與 stub)。

    python3 test_rawview_build.py

1. launcher:在假記憶體裡執行(site A/B 原廠字、mode 表、配置器、cache 函式),檢查
   31 張表與 rv_tables 逐點相同、插槽、mode 副本 N、常駐參數、veneer、兩個 bl。
2. launcher 在原廠值不符時什麼都不寫。
3. stub_gs／stub_dg:模擬各種設定組合,檢查 eff、root 指標、選表、增益。
"""
import pathlib, struct, sys, unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_bcolor as B   # noqa: E402
import rv_tables            # noqa: E402
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE   # noqa: E402
from unicorn.arm_const import UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4  # noqa: E402
from unicorn.arm_const import (UC_ARM_REG_R1, UC_ARM_REG_PC, UC_ARM_REG_LR, UC_ARM_REG_SP, UC_ARM_REG_R0,  # noqa: E402
                               UC_ARM_REG_R2, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_IP)

STAGE = 0x40100000
HEAP = 0x45000000
RET = 0x4FFF0000
SITE_A, ORIG_A = 0xC0313244, 0xE595200C
SITE_B, ORIG_B = 0xC032F728, 0xE59C6000
MODE_TAB = 0xC0B3D670
CAVE_BUMP, ARENA = 0xC072E060, 0xC072E100
ROOT_P70, KEY = 0xC2F1A0D4, 0xC2F19D44
SET_SEL, BANK_A = 0xC31B954C, 0xC31B32BC
GUI_TAB = 0xC2E412BC
GUI_PAIRS = [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (15, 6), (6, 7), (7, 8), (8, 9),
             (13, 10), (9, 11), (10, 12), (14, 13), (11, 14), (12, 15)]
MENU_ORIG = {0xC06C07CC: 0xE30122BC, 0xC06C07D0: 0xE34C22E4, 0xC06C07D8: 0xE3A02010,
             0xC0568950: 0xEB055F70, 0xC056D028: 0xEB054DBA, 0xC05818B8: 0xEB04FB96,
             0xC0595734: 0xEB04AC0B, 0xC0075CF4: 0xE15A0006,
             0xC1D63010: 0x00000070, 0xC1D631AC: 0x70410000, 0xC1D66CBC: 0xF4010000,
             0xC05E5BEC: 0x60681840, 0xC059DA1C: 0xEB048B51,
             0xC1D5F200: 0x00000070, 0xC1D62A7C: 0x00007041, 0xC1D63F8C: 0x00000070, 0xC1D65B24: 0x70410200}
UI_SITES = {0xC0568A3C: 0xEB0560B7, 0xC0595908: 0xEB04AD18, 0xC056D5F8: 0xEB054E98,
            0xC056D498: 0xEB054EF0, 0xC059588C: 0xEB04AE07, 0xC05959E4: 0xEB04ADB1,
            0xC05689A8: 0xEB055F8E, 0xC05957B0: 0xEB04AD6E}   # RAW 列調整的 bl(原廠字)
MENU_ORIG.update(UI_SITES)
MENU_ORIG[0xC1D640A8] = 0x00007041                                                  # 框種類上限 15.0
MENU_ORIG[0xC1D6ED48] = 0x00004041
import rv_dngcm                                                                      # noqa: E402
MENU_ORIG.update({a: w for a, w, _ in rv_dngcm.SITES})                               # DNG writer movw/movt
MENU_ORIG.update({0xC0D119FC: 0xC05687E0, 0xC0D11A00: 0xC0568888})                  # ColorButtonMenu vtable v25/v26
Z_SITES = {0xC056D548: 0xEB054E5C, 0xC056D3E8: 0xEB054EB4, 0xC056D5A0: 0xEB054E7A, 0xC056D440: 0xEB054ED2,
           0xC059581C: 0xEB04ADBB, 0xC0595974: 0xEB04AD65, 0xC0595854: 0xEB04ADE1, 0xC05959AC: 0xEB04AD8B}
MENU_ORIG.update(Z_SITES)
MENU_ORIG[0xC02B8E64] = 0xEB00024F                                                   # 畫質管理器指令 bl FUN_c02b97a8(stub_pq)
MENU_ORIG[0xC0088C60] = 0xEBFFFE7E                                                   # 關機存檔 bl FUN_c0088660(stub_sv)
MENU_ORIG[0xC05E2200] = 0xFCDAF7F4                                                   # Thumb bl FUN_c05d6bb8(關鍵影格圖名)                                                            # 對比/清晰鎖 0                                                  # AEL 頁 Normal ≤ 12.0
CONV = (0xC06C0D20, 0xC06C0D70, 0xC06C1060, 0xC06C10B0, 0xC06C0EC0, 0xC06C0F90, 0xC06C0F10, 0xC06C0FE0)                             # 原廠換算函式(假的:回 1000 + r1)
import rv_color                                                                      # noqa: E402
ROOT_P08 = rv_color.ROOT_P08
MAT_ROM = pathlib.Path(__file__).resolve().parents[3].joinpath('out', 'MAIN_c0000000.bin').read_bytes()[
    rv_color.MAT_TAB - 0xC0000000:rv_color.MAT_TAB - 0xC0000000 + 35 * 0x18]
MA_SITES = (0xC0568950, 0xC056D028, 0xC05818B8)
COLOR_ITEM = 0xC31ACDC4


FAKE = [15]   # 假的 GUI↔enum 轉換回傳值(OFF 的 GUI)
PUBLISHED = []
SAVES = []      # 假存檔函式看到的 (r0, r1, 紀錄色彩字)
PQCALLS = []    # 假畫質指令函式看到的 (r0, r1, r2, r3, [sp])
SETS = []       # 假 setter 看到的 (item, 值, 通知)


def mode_table():
    t = []
    for m in range(0x24):
        t += [m, 5 + m]
    t[35 * 2:35 * 2 + 2] = [0x24, 82]
    return t


def machine(site_a=ORIG_A):
    blob, info = B.build_blob()
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    for base, size in ((STAGE, 0x10000), (HEAP, 0x100000), (RET, 0x1000), (0x4F000000, 0x10000),
                       (0xC0000000, 0x00E00000), (0xC1D00000, 0x00100000), (0xC2D00000, 0x00100000), (0xC2E00000, 0x00200000), (0xC3100000, 0x00100000), (0xC3400000, 0x00100000), (0xC3700000, 0x00100000)):
        mu.mem_map(base, size)
    mu.mem_write(STAGE, blob)
    mu.mem_write(SITE_A, struct.pack('<I', site_a))
    mu.mem_write(SITE_B, struct.pack('<I', ORIG_B))
    mu.mem_write(MODE_TAB, struct.pack(f'<{0x48}I', *mode_table()))
    mu.mem_write(CAVE_BUMP, struct.pack('<I', ARENA))
    mu.mem_write(ROOT_P70, struct.pack('<I', MODE_TAB))
    mu.mem_write(GUI_TAB, b''.join(struct.pack('<II', *p) for p in GUI_PAIRS))
    mu.mem_write(ROOT_P08, struct.pack('<II', rv_color.MAT_TAB, 35))
    mu.mem_write(rv_color.MAT_TAB, MAT_ROM)
    for a, w in MENU_ORIG.items():
        mu.mem_write(a, struct.pack('<I', w))
    calls = []

    def hook(uc, addr, size, _):
        if addr in (0xC06C0718, 0xC06C0768, 0xC06C07E8):              # 假的轉換函式:回傳 15(OFF 的 GUI)
            calls.append(addr)
            uc.reg_write(UC_ARM_REG_R0, FAKE[0])
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
            return
        if addr == 0xC0593F30:                             # 發布 UI 變數:記下 (名稱位址, 值)
            PUBLISHED.append((uc.reg_read(UC_ARM_REG_R1), uc.reg_read(UC_ARM_REG_R2)))
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
            return
        if addr in CONV:
            calls.append(addr)
            uc.reg_write(UC_ARM_REG_R0, 1000 + uc.reg_read(UC_ARM_REG_R1))
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
            return
        if addr == 0xC0088660:                             # 原廠存檔(假的):記下 (r0, r1, 呼叫者 r4 物件的色彩字)
            obj = uc.reg_read(UC_ARM_REG_R4)
            SAVES.append((uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1),
                          struct.unpack('<I', uc.mem_read(obj + 0x13C, 4))[0]))
            uc.reg_write(UC_ARM_REG_R0, 0x55)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
            return
        if addr == 0xC02B97A8:                             # 畫質管理器執行指令(假的):記下 r0–r3 與 [sp]
            PQCALLS.append(tuple(uc.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3))
                           + (struct.unpack('<I', uc.mem_read(uc.reg_read(UC_ARM_REG_SP), 4))[0],))
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
            return
        if addr == 0xC0057AE8:                             # 選單設定管理(假的)
            calls.append(addr)
            uc.reg_write(UC_ARM_REG_R0, 0x4F003000)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
            return
        if addr == 0xC005C958:                             # 色彩 setter(假的):記下 (item, 值, 通知)
            calls.append(addr)
            SETS.append((uc.reg_read(UC_ARM_REG_R0), uc.reg_read(UC_ARM_REG_R1), uc.reg_read(UC_ARM_REG_R2)))
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
            return
        if addr in (0xC05687E0, 0xC0568888):              # ColorButtonMenu v25/v26(假的:直接返回)
            calls.append(addr)
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
            return
        if addr in (0xC001D740, 0xC001D7F0, 0xC000E91C, 0xC000EABC):
            calls.append(addr)
            if addr == 0xC001D7F0:
                uc.reg_write(UC_ARM_REG_R0, HEAP + 0x123)       # 故意不對齊
            uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))
    mu.hook_add(UC_HOOK_CODE, hook, begin=0xC0000000, end=0xC00FFFFF)
    mu.hook_add(UC_HOOK_CODE, hook, begin=0xC06C0000, end=0xC06C1FFF)
    mu.hook_add(UC_HOOK_CODE, hook, begin=0xC0593F30, end=0xC0593F30)
    mu.hook_add(UC_HOOK_CODE, hook, begin=0xC02B97A8, end=0xC02B97A8)
    mu.hook_add(UC_HOOK_CODE, hook, begin=0xC05687E0, end=0xC0568888)
    PUBLISHED.clear(); SAVES.clear(); SETS.clear(); PQCALLS.clear()
    return mu, blob, info, calls


def run_launcher(mu):
    mu.reg_write(UC_ARM_REG_SP, 0x4F00F000)
    mu.reg_write(UC_ARM_REG_LR, RET)
    mu.emu_start(STAGE, RET, count=20_000_000)


def u32(mu, a, n=1):
    v = struct.unpack(f'<{n}I', mu.mem_read(a, 4 * n))
    return v if n > 1 else v[0]


class Launcher(unittest.TestCase):
    def test_installs(self):
        mu, blob, info, calls = machine()
        run_launcher(mu)
        T0 = (HEAP + 0x123 + 0xFFF) & ~0xFFF
        LOG = rv_tables.log_q16(); WQ, SAMP, Bc = rv_tables.coefs()
        for k in range(rv_tables.NREC):                                        # 124 張;62 起在常駐區之後
            got = struct.unpack('<2048H', mu.mem_read(T0 + rv_tables.table_addr_off(k), 4096))
            self.assertEqual(list(got), rv_tables.table(k, LOG, WQ, SAMP, Bc), f'table {k}')
        slots = T0 + 0x3E004
        self.assertEqual(slots % 8, 4)
        for j in range(11):
            self.assertEqual(u32(mu, slots + 8 * j, 2), (0, T0))
        mode = T0 + 0x3E060
        n = ((slots - 0xC0971114) >> 3) + 5 & 0xFFFFFFFF
        self.assertEqual(u32(mu, mode + 0x11C), n)
        self.assertEqual(list(u32(mu, mode, 0x46)), mode_table()[:0x46])
        for k in (-5, 0, 5):   # 韌體的位址算式落在插槽上
            a = (0xC0971114 + ((n + k) & 0xFFFFFFFF) * 8 + 4) & 0xFFFFFFFF
            self.assertEqual(a, slots + 8 * (k + 5) + 4)
        res = T0 + 0x3E200
        self.assertEqual(bytes(mu.mem_read(res, 4)), b'BCL1')
        self.assertEqual(u32(mu, res + 4, 6), (0, 0, 0, T0, slots, mode))
        self.assertEqual(list(u32(mu, res + 0x1C, 30)), rv_tables.thresholds())
        self.assertEqual(u32(mu, CAVE_BUMP), ARENA + 152)                  # 19 個 veneer
        stubs = [info[k] for k in ('stub_gs', 'stub_dg', 'stub_ma', 'stub_mb', 'stub_mc')]
        for n, off in enumerate(stubs):
            self.assertEqual(u32(mu, ARENA + 8 * n, 2), (0xE51FF004, res + off))
        for site, n in ((SITE_A, 0), (SITE_B, 1), *((s_, 2) for s_ in MA_SITES), (0xC0595734, 3), (0xC0075CF4, 4)):
            w = u32(mu, site)
            off = ((w & 0xFFFFFF) ^ 0x800000) - 0x800000
            self.assertEqual(w >> 24, 0xEB, hex(site))
            self.assertEqual(site + 8 + off * 4, ARENA + 8 * n, hex(site))
        def imm(w): return ((w >> 4) & 0xF000) | (w & 0xFFF)
        mw, mt, cnt = u32(mu, 0xC06C07CC), u32(mu, 0xC06C07D0), u32(mu, 0xC06C07D8)
        self.assertEqual((mw & 0xFFF0F000, mt & 0xFFF0F000, cnt), (0xE3002000, 0xE3402000, 0xE3A02011))
        tab = (imm(mt) << 16) | imm(mw)
        self.assertEqual(tab, res + 0x98)
        pairs = [u32(mu, tab + 8 * i, 2) for i in range(17)]
        self.assertEqual(pairs, GUI_PAIRS + [(0xC, 16)])
        self.assertEqual(u32(mu, ROOT_P70), MODE_TAB)      # 開機時不動 root
        self.assertEqual(u32(mu, ROOT_P08), rv_color.MAT_TAB)
        mat = u32(mu, res + 0x1A8)                         # 矩陣副本:只有 OFF 那筆不同
        self.assertEqual(mat, T0 + 0x40800)
        got = bytes(mu.mem_read(mat, 35 * 0x18))
        o = 34 * 0x18
        self.assertEqual(got[:o] + got[o + 24:], MAT_ROM[:o] + MAT_ROM[o + 24:])
        self.assertEqual(struct.unpack_from('<I9h', got, o), (0x24, *rv_color.bc_table(0)))   # bCOLOR:FC / Video
        for site, n in ((0xC0568A3C, 7), (0xC0595908, 8), (0xC056D5F8, 9), (0xC056D498, 9), (0xC059588C, 10), (0xC05959E4, 10), (0xC05689A8, 11), (0xC05957B0, 8)):
            w = u32(mu, site)                                # RAW 列調整的 bl → veneer n → stub
            self.assertEqual(site + 8 + ((((w & 0xFFFFFF) ^ 0x800000) - 0x800000) * 4), ARENA + 8 * n, hex(site))
        def movwt(w, t): return ((u32(mu, t) >> 4 & 0xF000 | u32(mu, t) & 0xFFF) << 16) | (u32(mu, w) >> 4 & 0xF000 | u32(mu, w) & 0xFFF)
        cm = res + info['cm_buf']
        self.assertEqual(movwt(0xC02C4BE4, 0xC02C4BE8), cm)          # DNG writer 的 OFF CM1 → cm_buf
        self.assertEqual(movwt(0xC02C4C98, 0xC02C4C9C), cm + 72)     # CM2
        self.assertEqual(u32(mu, 0xC02C4BE4) & 0xFFF0F000, 0xE3002000)
        self.assertEqual((u32(mu, 0xC0D119FC), u32(mu, 0xC0D11A00)), (res + info['stub_mo'], res + info['stub_mx']))
        for site, n in ((0xC056D548, 12), (0xC056D3E8, 12), (0xC056D5A0, 13), (0xC056D440, 13),
                        (0xC059581C, 14), (0xC0595974, 14), (0xC0595854, 15), (0xC05959AC, 15)):
            w = u32(mu, site)
            self.assertEqual(site + 8 + ((((w & 0xFFFFFF) ^ 0x800000) - 0x800000) * 4), ARENA + 8 * n, hex(site))
        self.assertEqual(bytes(mu.mem_read(cm, 144)), rv_dngcm.blob()[:144])   # 初值 = 原廠 OFF 常數
        for n, k in ((7, 'stub_ef'), (8, 'stub_en'), (9, 'stub_sa'), (10, 'stub_sn'), (11, 'stub_mj')):
            self.assertEqual(u32(mu, ARENA + 8 * n, 2), (0xE51FF004, res + info[k]))
        w = u32(mu, 0xC0088C60)                              # 關機存檔 bl → veneer 17 → stub_sv
        self.assertEqual(0xC0088C60 + 8 + ((((w & 0xFFFFFF) ^ 0x800000) - 0x800000) * 4), ARENA + 8 * 17)
        self.assertEqual(u32(mu, ARENA + 8 * 17, 2), (0xE51FF004, res + info['stub_sv']))
        w = u32(mu, 0xC02B8E64)                              # 畫質管理器指令 bl → veneer 18 → stub_pq
        self.assertEqual(0xC02B8E64 + 8 + ((((w & 0xFFFFFF) ^ 0x800000) - 0x800000) * 4), ARENA + 8 * 18)
        self.assertEqual(u32(mu, ARENA + 8 * 18, 2), (0xE51FF004, res + info['stub_pq']))
        self.assertEqual(calls, [0xC001D740, 0xC001D7F0, 0xC000E91C, 0xC000EABC, 0xC000E91C, 0xC000EABC])   # 色彩不是 0x1x:不還原

    def test_boot_restores_raw_from_saved_color(self):
        for v, want in ((0x13, (1, 1, 0)), (0x14, (0, 0, 1)), (0x10, (0, 0, 0)), (0x17, (1, 1, 1))):
            mu, blob, info, calls = machine()
            mu.mem_write(BANK_A + 0x12C, struct.pack('<I', v))           # 上次關機 stub_sv 存的 0x10 | lat | con << 1 | sat << 2
            mu.mem_write(0xC3766498 + 0x84, b'\x01')
            run_launcher(mu)
            T0 = (HEAP + 0x123 + 0xFFF) & ~0xFFF
            res = T0 + 0x3E200
            lat, con, sat = want
            self.assertEqual((u32(mu, res + 0x1A4), u32(mu, res + 0x1C4), u32(mu, res + 0x1C8),
                              u32(mu, res + 0x1B0), u32(mu, res + 0x1B4)), (lat, con, con, sat, sat), hex(v))
            self.assertEqual((u32(mu, res + 4), u32(mu, res + 0x94)), (1, 17), hex(v))   # flag、pend(setter 經 stub_mc 消化)
            self.assertEqual(SETS, [(0x4F003000, 0xC, 1)], hex(v))                      # 經 setter 改回 OFF 並通知
            self.assertEqual(calls[-2:], [0xC0057AE8, 0xC005C958], hex(v))
            self.assertEqual(mu.mem_read(0xC3766498 + 0x84, 1), b'\x00')                # COLOR 鍵選單下次開啟重建
            self.assertEqual(u32(mu, 0xC0088C60) >> 24, 0xEB)                            # hook 已先裝好
        for v in (0x0C, 0x0F, 0x18, 0x00):                                             # 其他值:不動
            mu, blob, info, calls = machine()
            mu.mem_write(BANK_A + 0x12C, struct.pack('<I', v))
            run_launcher(mu)
            T0 = (HEAP + 0x123 + 0xFFF) & ~0xFFF
            self.assertEqual((SETS, u32(mu, T0 + 0x3E200 + 4)), ([], 0), hex(v))

    def test_stands_down_on_foreign_site(self):
        mu, *_ , calls = machine(site_a=0xEB000000)
        run_launcher(mu)
        self.assertEqual(u32(mu, SITE_A), 0xEB000000)
        self.assertEqual(u32(mu, SITE_B), ORIG_B)
        self.assertEqual(u32(mu, CAVE_BUMP), ARENA)
        self.assertEqual(calls, [])
        for a, w in MENU_ORIG.items():
            self.assertEqual(u32(mu, a), w)


class Stubs(unittest.TestCase):
    def setUp(self):
        self.mu, blob, self.info, _ = machine()
        run_launcher(self.mu)
        self.T0 = (HEAP + 0x123 + 0xFFF) & ~0xFFF
        self.res = self.T0 + 0x3E200
        self.helper = 0xC3100000
        self.mu.mem_write(SET_SEL, b'\0')

    def settings(self, color, fmt, qual):
        self.mu.mem_write(BANK_A + 0x12C, struct.pack('<I', color))
        self.mu.mem_write(BANK_A + 0x784, struct.pack('<I', fmt))
        self.mu.mem_write(BANK_A + 0x788, struct.pack('<I', qual))

    def gs(self, state, rel):
        mu = self.mu
        mu.mem_write(self.helper + 0xC, struct.pack('<I', state))
        mu.reg_write(UC_ARM_REG_R5, self.helper)
        mu.reg_write(UC_ARM_REG_R6, rel)
        mu.reg_write(UC_ARM_REG_SP, 0x4F00F000)
        mu.reg_write(UC_ARM_REG_LR, RET)
        mu.emu_start(self.res + self.info['stub_gs'], RET, count=10000)
        return mu.reg_read(UC_ARM_REG_R2)

    def dg(self, bank, gain=0x2000):
        mu = self.mu
        mu.mem_write(0x4F001000, struct.pack('<I', gain))
        mu.reg_write(UC_ARM_REG_IP, 0x4F001000)
        mu.reg_write(UC_ARM_REG_R5, bank)
        mu.reg_write(UC_ARM_REG_LR, RET)
        mu.emu_start(self.res + self.info['stub_dg'], RET, count=100)
        return mu.reg_read(UC_ARM_REG_R6)

    def test_off_by_default(self):
        self.settings(0xC, 0, 0)
        self.assertEqual(self.gs(0, 936), 0)
        self.assertEqual(self.dg(0), 0x2000)
        self.assertEqual(u32(self.mu, ROOT_P70), MODE_TAB)

    def test_on_selects_table_and_gain(self):
        self.settings(0xC, 0, 0)
        self.mu.mem_write(self.res + 4, struct.pack('<I', 1))
        self.assertEqual(self.gs(0, 936), 7)
        self.assertEqual(u32(self.mu, ROOT_P70), self.T0 + 0x3E060)
        self.assertEqual(u32(self.mu, KEY), 0xFFFFFFFF)
        self.assertEqual(u32(self.mu, self.T0 + 0x3E004 + 4), self.T0 + 9 * 0x1000)   # ISO 800
        self.assertEqual(self.dg(0), 0x400)
        self.assertEqual(self.dg(1), 0x2000)
        self.assertEqual(self.gs(7, 936), 7)            # 錄影中:原指令值原樣返回
        self.mu.mem_write(KEY, struct.pack('<I', 0x24))
        self.gs(0, 7488)
        self.assertEqual(u32(self.mu, self.T0 + 0x3E004 + 4), self.T0 + 18 * 0x1000)  # ISO 6400
        self.assertEqual(u32(self.mu, KEY), 0xFFFFFFFF)

    def test_lat_con_sat_select_tables_and_matrix(self):
        self.settings(0xC, 0, 0)
        self.mu.mem_write(self.res + 4, struct.pack('<I', 1))
        mat = u32(self.mu, self.res + 0x1A8)
        # ISO 800 = 第 9 張;lat +31;對比 1 +62,62 起的表在常駐區之後(+4)。bCOLOR:sat 不影響矩陣(鎖 0,寫入非 0 也不管)
        for lat, con, sat, k in ((0, 0, 0, 9), (0, 1, 0, 71), (1, 1, 0, 102), (1, 0, 0, 40), (1, 0, 1, 40), (1, 1, 1, 102), (0, 0, 1, 9)):   # 含只改對比的步驟
            self.mu.mem_write(self.res + 0x1A4, struct.pack('<I', lat))        # 上下框(stub_ef 寫)
            self.mu.mem_write(self.res + 0x1C4, struct.pack('<i', con))        # AEL 對比度(stub_zc 寫)
            self.mu.mem_write(self.res + 0x1B0, struct.pack('<i', sat))        # AEL 飽和度(stub_sa 寫)
            self.mu.mem_write(KEY, struct.pack('<I', 0x24))
            self.assertEqual(self.gs(0, 936), 7)                               # 同一增益:改變也要重選
            tab = u32(self.mu, self.T0 + 0x3E004 + 4)
            self.assertEqual(tab, self.T0 + rv_tables.table_addr_off(k), (lat, con, sat))
            self.assertEqual(rv_tables.SETS[k // 31], (('video', 'extended')[con], con))
            self.assertEqual(u32(self.mu, ROOT_P08), mat)
            rec = struct.unpack('<I9h', self.mu.mem_read(mat + 34 * 24, 22))
            self.assertEqual(rec, (0x24, *rv_color.bc_table(lat | con << 1)), (lat, con, sat))
            self.assertEqual(u32(self.mu, KEY), 0xFFFFFFFF)
            cm = bytes(self.mu.mem_read(self.res + self.info['cm_buf'], 144))
            self.assertEqual(cm, rv_dngcm.blob()[(lat + 1) * 144:(lat + 2) * 144], (lat, sat))   # DNG CM:FC / BC
        self.mu.mem_write(self.res + 0x1A4, struct.pack('<I', 3))              # 範圍外(不該發生):只看低位
        self.mu.mem_write(self.res + 0x1C4, struct.pack('<i', 2))
        self.gs(0, 936)
        self.assertEqual(struct.unpack('<I9h', self.mu.mem_read(mat + 34 * 24, 22)), (0x24, *rv_color.bc_table(1)))
        self.assertEqual(bytes(self.mu.mem_read(self.res + self.info['cm_buf'], 144)), rv_dngcm.blob()[288:432])
        self.settings(0, 0, 0)                                                 # 改成 Standard:不生效 → 全部還原
        self.assertEqual(self.gs(0, 936), 0)
        self.assertEqual(u32(self.mu, ROOT_P08), rv_color.MAT_TAB)
        self.assertEqual(u32(self.mu, ROOT_P70), MODE_TAB)
        self.assertEqual(bytes(self.mu.mem_read(self.res + self.info['cm_buf'], 144)), rv_dngcm.blob()[:144])

    def test_save_stub_stores_raw_as_0x1x(self):
        from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4
        obj = 0x4F004000
        def save(flag, group, color, lat=0, con=0, sat=0):
            mu = self.mu
            SAVES.clear()
            mu.mem_write(obj + 0x58CC, struct.pack('<I', group))
            mu.mem_write(obj + 0x13C, struct.pack('<I', color))
            for off, v in ((4, flag), (0x1A4, lat), (0x1C4, con), (0x1B0, sat)):
                mu.mem_write(self.res + off, struct.pack('<I', v))
            regs = {UC_ARM_REG_R0: 0x111, UC_ARM_REG_R1: obj + 0xC, UC_ARM_REG_R2: 0x333, UC_ARM_REG_R3: 0x444, UC_ARM_REG_R4: obj}
            for k, v in regs.items():
                mu.reg_write(k, v)
            mu.reg_write(UC_ARM_REG_LR, RET)
            mu.reg_write(UC_ARM_REG_SP, 0x4F00F000)
            mu.emu_start(self.res + self.info['stub_sv'], RET, count=1000)
            self.assertEqual(mu.reg_read(UC_ARM_REG_SP), 0x4F00F000)
            self.assertEqual(mu.reg_read(UC_ARM_REG_R0), 0x55)                         # 原函式的回傳值
            self.assertEqual(mu.reg_read(UC_ARM_REG_R4), obj)
            self.assertEqual(len(SAVES), 1)
            r0, r1, seen = SAVES[0]
            self.assertEqual((r0, r1), (0x111, obj + 0xC))                             # 參數原樣傳過去
            return seen, u32(mu, obj + 0x13C)
        self.assertEqual(save(1, 0, 0xC, lat=1, con=0, sat=1), (0x15, 0xC))            # 存檔當下是 0x1x,之後改回 OFF
        self.assertEqual(save(1, 0, 0xC, lat=0, con=1, sat=0), (0x12, 0xC))
        self.assertEqual(save(1, 0, 0xC, lat=1, con=1, sat=1), (0x17, 0xC))
        self.assertEqual(save(0, 0, 0xC, lat=1), (0xC, 0xC))                          # RAW 沒開:照原廠
        self.assertEqual(save(1, 2, 0xC, lat=1), (0xC, 0xC))                          # 自訂模式(第 2 組):不動
        self.assertEqual(save(1, 0, 0x3, lat=1), (0x3, 0x3))                          # 紀錄不是 OFF:不動

    def pq(self, cmd):
        from unicorn.arm_const import UC_ARM_REG_R3
        mu = self.mu
        PQCALLS.clear()
        mu.mem_write(0x4F00EFF8, struct.pack('<I', 0xABCD))                 # 呼叫者放在 [sp] 的第 5 個參數
        for r, v in ((UC_ARM_REG_R0, 0xC341399C), (UC_ARM_REG_R1, cmd), (UC_ARM_REG_R2, 0x222), (UC_ARM_REG_R3, 0x333)):
            mu.reg_write(r, v)
        mu.reg_write(UC_ARM_REG_LR, RET)
        mu.reg_write(UC_ARM_REG_SP, 0x4F00EFF8)
        mu.emu_start(self.res + self.info['stub_pq'], RET, count=1000)
        self.assertEqual(mu.reg_read(UC_ARM_REG_SP), 0x4F00EFF8)
        self.assertEqual(PQCALLS, [(0xC341399C, cmd, 0x222, 0x333, 0xABCD)])      # 原函式拿到原樣的參數

    def test_playback_renders_stock(self):
        LAST = 0xC3413CF4
        self.settings(0xC, 0, 0)
        self.mu.mem_write(self.res + 4, struct.pack('<I', 1))
        self.mu.mem_write(LAST, struct.pack('<I', 3))                          # 即時畫面
        self.assertEqual(self.gs(0, 936), 7)
        ours70, ours08 = u32(self.mu, ROOT_P70), u32(self.mu, ROOT_P08)
        self.assertNotEqual((ours70, ours08), (MODE_TAB, rv_color.MAT_TAB))
        self.assertEqual(self.dg(0), 0x400)
        self.mu.mem_write(LAST, struct.pack('<I', 0xC))                        # 回放的增益早於回放指令寫入:仍保留片段增益
        self.assertEqual(self.dg(0), 0x2000)
        self.mu.mem_write(LAST, struct.pack('<I', 3))
        self.pq(3)                                                             # 即時指令:不動
        self.assertEqual((u32(self.mu, ROOT_P70), u32(self.mu, ROOT_P08), u32(self.mu, self.res + 8)), (ours70, ours08, 1))
        self.mu.mem_write(KEY, struct.pack('<2I', 0x24, 0x24))
        self.pq(0xC)                                                           # CinemaDNG 回放
        self.assertEqual((u32(self.mu, ROOT_P70), u32(self.mu, ROOT_P08)), (MODE_TAB, rv_color.MAT_TAB))
        self.assertEqual(u32(self.mu, KEY, 2), (0xFFFFFFFF, 0xFFFFFFFF))       # 兩個通道的 tone 快取都清掉
        self.assertEqual(u32(self.mu, self.res + 8), 2)
        self.mu.mem_write(LAST, struct.pack('<I', 0xC))
        self.assertEqual(self.dg(0), 0x2000)                                   # 回放:保留片段自己的增益
        self.assertEqual(self.gs(0, 936), 0)                                   # 回放中增益計算也不套回
        self.assertEqual(u32(self.mu, ROOT_P70), MODE_TAB)
        self.mu.mem_write(LAST, struct.pack('<I', 2))                          # 回到即時畫面
        self.assertEqual(self.gs(0, 936), 7)
        self.assertEqual((u32(self.mu, ROOT_P70), u32(self.mu, ROOT_P08)), (ours70, ours08))
        self.assertEqual(self.dg(0), 0x400)
        for cmd in (0xB, 0xD):                                                 # DNG 顯影
            self.gs(0, 936)
            self.pq(cmd)
            self.assertEqual(u32(self.mu, ROOT_P70), MODE_TAB, cmd)
            self.mu.mem_write(LAST, struct.pack('<I', 2))
        self.settings(0, 0, 0)                                                 # RAW 沒生效:回放指令什麼都不動
        self.gs(0, 936)
        self.mu.mem_write(ROOT_P70, struct.pack('<I', 0x12345678))
        self.pq(0xC)
        self.assertEqual(u32(self.mu, ROOT_P70), 0x12345678)

    def test_gating(self):
        self.mu.mem_write(self.res + 4, struct.pack('<I', 1))
        for color, fmt, qual in ((0, 0, 0), (0xC, 1, 0), (0xC, 0, 4)):
            self.settings(color, fmt, qual)
            self.assertEqual(self.gs(0, 936), 0, (color, fmt, qual))
            self.assertEqual(self.dg(0), 0x2000)
            self.assertEqual(u32(self.mu, ROOT_P70), MODE_TAB)
        self.settings(0xC, 0, 0)
        self.assertEqual(self.gs(0, 936), 7)
        self.settings(0xC, 1, 0)                         # 切到 MOV:root 還原
        self.assertEqual(self.gs(0, 936), 0)
        self.assertEqual(u32(self.mu, ROOT_P70), MODE_TAB)


class Menu(unittest.TestCase):
    def setUp(self):
        self.mu, blob, self.info, self.calls = machine()
        run_launcher(self.mu)
        T0 = (HEAP + 0x123 + 0xFFF) & ~0xFFF
        self.res = T0 + 0x3E200

    def flag(self): return u32(self.mu, self.res + 4)
    def pend(self): return u32(self.mu, self.res + 0x94)
    def lat(self): return u32(self.mu, self.res + 0x1A4)
    def sat(self): return struct.unpack('<i', self.mu.mem_read(self.res + 0x1B0, 4))[0]
    def satf(self): return struct.unpack('<i', self.mu.mem_read(self.res + 0x1B4, 4))[0]
    def guis(self): return [u32(self.mu, self.res + 0x98 + 8 * i + 4) for i in (15, 16)]

    def call(self, stub, regs, lr=RET):
        mu = self.mu
        for k, v in regs.items():
            mu.reg_write(k, v & 0xFFFFFFFF)
        mu.reg_write(UC_ARM_REG_LR, lr)
        mu.reg_write(UC_ARM_REG_SP, 0x4F00F000)
        mu.emu_start(self.res + self.info[stub], lr, count=1000)
        v = mu.reg_read(UC_ARM_REG_R0)
        return v - (1 << 32) if v & 0x80000000 else v

    def ma(self, gui):
        from unicorn.arm_const import UC_ARM_REG_R1
        self.call('stub_ma', {UC_ARM_REG_R0: 0x1234, UC_ARM_REG_R1: gui})

    def mb(self):
        return self.call('stub_mb', {})

    def ml(self, ret):
        FAKE[0] = ret
        self.addCleanup(FAKE.__setitem__, 0, 15)
        return self.call('stub_ml', {})

    def mc(self, item, old, new):
        from unicorn.arm_const import UC_ARM_REG_R4, UC_ARM_REG_SL, UC_ARM_REG_CPSR
        mu = self.mu
        mu.reg_write(UC_ARM_REG_R4, item)
        mu.reg_write(UC_ARM_REG_SL, old)
        mu.reg_write(UC_ARM_REG_R6, new)
        mu.reg_write(UC_ARM_REG_LR, RET)
        mu.reg_write(UC_ARM_REG_SP, 0x4F00F004)          # 未對齊,與實際相同
        mu.emu_start(self.res + self.info['stub_mc'], RET, count=1000)
        return bool(mu.reg_read(UC_ARM_REG_CPSR) & (1 << 30))   # Z

    def select(self, gui):
        self.ma(gui)
        return self.mc(COLOR_ITEM, 0xC, 0xC)

    def ef(self, ui):
        from unicorn.arm_const import UC_ARM_REG_R1
        return self.call('stub_ef', {UC_ARM_REG_R0: 0x1234, UC_ARM_REG_R1: ui}, lr=0xC0568A40)

    def en(self, stored, mode=0xC):
        from unicorn.arm_const import UC_ARM_REG_R1, UC_ARM_REG_R7
        return self.call('stub_en', {UC_ARM_REG_R0: 0x1234, UC_ARM_REG_R1: stored, UC_ARM_REG_R7: mode}, lr=0xC059590C)

    def sa(self, ui, fix=False):
        from unicorn.arm_const import UC_ARM_REG_R1
        return self.call('stub_sa', {UC_ARM_REG_R0: 0x1234, UC_ARM_REG_R1: ui}, lr=0xC056D49C if fix else 0xC056D5FC)

    def sn(self, stored, fix=False):
        from unicorn.arm_const import UC_ARM_REG_R1
        return self.call('stub_sn', {UC_ARM_REG_R0: 0x1234, UC_ARM_REG_R1: stored}, lr=0xC0595890 if fix else 0xC05959E8)

    def test_select_raw_then_off(self):
        self.ma(16)
        self.assertEqual(self.pend(), 17)
        self.assertEqual(self.calls[-1], 0xC06C0718)              # 尾跳到原函式
        self.assertFalse(self.mc(COLOR_ITEM, 0xC, 0xC))           # enum 不變,強制「不相等」
        self.assertEqual((self.flag(), self.pend()), (1, 0))
        self.assertEqual(self.mb(), 16)
        self.assertEqual(self.guis(), [16, 15])                   # enum→GUI 第一個符合 = RAW,15 還在
        self.ma(15)
        self.assertEqual(self.pend(), 16)
        self.assertFalse(self.mc(COLOR_ITEM, 0xC, 0xC))
        self.assertEqual(self.flag(), 0)
        self.assertEqual(self.mb(), 15)
        self.assertEqual(self.guis(), [15, 16])

    def test_preview_path_selects_raw(self):
        # 2026-09-25 上機:游標移動(預覽,C06C07E8)也要選定 RAW;退出不按 OK 仍保留
        from unicorn.arm_const import UC_ARM_REG_R1
        self.call('stub_mj', {UC_ARM_REG_R0: 0x1234, UC_ARM_REG_R1: 16})
        self.assertEqual(self.pend(), 17)
        self.assertEqual(self.calls[-1], 0xC06C07E8)              # 尾跳到預覽用的原函式
        self.assertFalse(self.mc(COLOR_ITEM, 0xC, 0xC))
        self.assertEqual(self.flag(), 1)
        self.call('stub_mj', {UC_ARM_REG_R0: 0x1234, UC_ARM_REG_R1: 14})
        self.assertEqual(self.pend(), 0)
        self.assertFalse(self.mc(COLOR_ITEM, 0xC, 11))            # 游標移到別的色彩
        self.assertEqual(self.flag(), 0)

    def test_same_row_again_is_plain_compare(self):
        self.select(16)
        self.assertTrue(self.select(16))
        self.assertTrue(self.mc(COLOR_ITEM, 0xC, 0xC))            # 按 OK／離開時韌體再寫 OFF(無 pend)
        self.assertEqual(self.flag(), 1)

    def test_other_writes_clear_flag(self):
        self.select(16)
        self.assertFalse(self.mc(COLOR_ITEM, 0xC, 0))             # 改成 Standard(無 pend)
        self.assertEqual(self.flag(), 0)
        self.assertEqual(self.guis(), [15, 16])
        self.assertTrue(self.mc(COLOR_ITEM, 0, 0))

    def test_raw_selected_but_value_not_off(self):
        self.ma(16)
        self.mc(COLOR_ITEM, 0, 3)
        self.assertEqual((self.flag(), self.pend()), (0, 0))

    def test_other_items_untouched(self):
        self.ma(16)
        self.assertTrue(self.mc(0xC3000000, 5, 5))
        self.assertFalse(self.mc(0xC3000000, 5, 6))
        self.assertEqual((self.flag(), self.pend()), (0, 17))

    def test_qs_resync_does_not_select_off(self):
        # 2026-09-26 上機:切解析度時 QS 以 GUI 15 重新同步 → 不可關掉 RAW
        from unicorn.arm_const import UC_ARM_REG_R1
        self.select(16)
        self.assertEqual(self.flag(), 1)
        self.call('stub_ma', {UC_ARM_REG_R0: 0x1234, UC_ARM_REG_R1: 15}, lr=0xC05818BC)   # QS
        self.assertEqual(self.pend(), 0)
        self.assertTrue(self.mc(COLOR_ITEM, 0xC, 0xC))           # 值仍 OFF、無 pend → 不變
        self.assertEqual(self.flag(), 1)
        self.call('stub_ma', {UC_ARM_REG_R0: 0x1234, UC_ARM_REG_R1: 3}, lr=0xC05818BC)
        self.assertFalse(self.mc(COLOR_ITEM, 0xC, 3))             # QS 選別的模式:關掉 RAW
        self.assertEqual(self.flag(), 0)

    def test_other_guis_no_pend(self):
        for g in (0, 14, 17, 25):
            self.ma(g)
            self.assertEqual(self.pend(), 0, g)

    def test_lv_colormode(self):
        for r, want in ((15, 15), (16, 15), (17, 17), (25, 25), (3, 3)):
            self.assertEqual(self.ml(r), want, r)

    def test_updown_box_toggles_sa_ga(self):
        W = lambda v: v & 0xFFFFFFFF
        self.assertEqual(self.ef(1), 1001)                        # flag 關:原換算函式(假的回 1000 + r1)
        self.assertEqual(self.calls[-1], 0xC06C0D20)
        self.assertEqual(self.en(3), 1003)
        self.select(16)
        self.assertEqual(self.en(0), -5)                          # 預設 SA:框值 −5(stub_dt 畫成「SA」)
        self.assertEqual(self.en(0, mode=0xE), 1000)              # 別的模式(DUO):原換算
        self.assertEqual(self.ef(-4), 0)                          # −5 → −4(往上)→ GA
        self.assertEqual(self.lat(), 1)
        self.assertEqual(PUBLISHED, [(0xC2DF0210, 5), (0xC2DF01A8, 5)])   # 框設為 +5(AJ 與 FIX)
        self.assertEqual(self.en(0), 5)
        self.ef(6); self.assertEqual(self.lat(), 1)               # 再往上:仍 GA,框拉回 +5
        self.assertEqual(PUBLISHED[-1], (0xC2DF01A8, 5))
        n = len(PUBLISHED)
        self.ef(5); self.assertEqual(self.lat(), 1)               # 等於顯示值(自己發布的回呼):不動、不再發布
        self.assertEqual(len(PUBLISHED), n)
        self.ef(4); self.assertEqual(self.lat(), 0)               # 往下 → SA
        self.assertEqual(PUBLISHED[-2:], [(0xC2DF0210, W(-5)), (0xC2DF01A8, W(-5))])
        self.ef(-6); self.assertEqual(self.lat(), 0)              # 再往下:仍 SA,框拉回 −5
        self.assertEqual(PUBLISHED[-1], (0xC2DF01A8, W(-5)))
        self.assertEqual(self.en(0), -5)

    def test_contrast_two_levels_sharpness_locked(self):
        from unicorn.arm_const import UC_ARM_REG_R1
        con = lambda: struct.unpack('<i', self.mu.mem_read(self.res + 0x1C4, 4))[0]
        conf = lambda: struct.unpack('<i', self.mu.mem_read(self.res + 0x1C8, 4))[0]
        self.assertEqual(self.call('stub_zc', {UC_ARM_REG_R1: 2}, lr=0xC056D54C), 1002)   # flag 關:原換算
        self.assertEqual(self.call('stub_znc', {UC_ARM_REG_R1: 3}), 1003)
        self.select(16)
        self.assertEqual(self.call('stub_zc', {UC_ARM_REG_R1: 1}, lr=0xC056D54C), 0)      # 對比 AJ +1:即時,範圍內不發布
        self.assertEqual((con(), conf(), PUBLISHED), (1, 0, []))
        self.assertEqual(self.call('stub_znc', {}, lr=0xC0595978), 1)                     # COLAJ 顯示即時值
        self.assertEqual(self.call('stub_znc', {}, lr=0xC0595820), 0)                     # COLFIX 顯示確認值
        self.call('stub_zc', {UC_ARM_REG_R1: 1}, lr=0xC056D3EC)                           # FIX(按 OK)
        self.assertEqual((con(), conf()), (1, 1))
        self.call('stub_zc', {UC_ARM_REG_R1: 2}, lr=0xC056D54C)                           # 捲過 +1:夾 1,刻度拉回
        self.assertEqual((con(), PUBLISHED), (1, [(0xC2DF0238, 1)]))
        self.call('stub_zc', {UC_ARM_REG_R1: 0xFFFFFFFF}, lr=0xC056D54C)                  # 捲到 −1:夾 0
        self.assertEqual((con(), PUBLISHED[-1]), (0, (0xC2DF0238, 0)))
        self.assertEqual(self.call('stub_zs', {UC_ARM_REG_R1: 0xFFFFFFFF}, lr=0xC056D5A4), 0)   # 清晰仍鎖 0
        self.assertEqual(PUBLISHED[-1], (0xC2DF024C, 0))
        self.call('stub_zs', {UC_ARM_REG_R1: 0}, lr=0xC056D5A4)                           # 已是 0:不發布
        self.assertEqual(len(PUBLISHED), 3)
        self.assertEqual(self.call('stub_zns', {UC_ARM_REG_R1: 5}), 0)                   # 清晰顯示 0

    def test_image_log_diagnostic(self):
        from unicorn.arm_const import UC_ARM_REG_R1, UC_ARM_REG_R2
        log = self.res + 0x2A00
        for name, hit in ((b'font_menu_LB_0.xci', 1), (b'set_color_01.xci', 0), (b'font_menu_LB_kigou_07', 1)):
            self.mu.mem_write(0x4F001000, name + b'\0')
            self.call('stub_il', {UC_ARM_REG_R0: 0x4F001000, UC_ARM_REG_R1: 34, UC_ARM_REG_R2: 51}, lr=0xC0601234)
        self.assertEqual(u32(self.mu, log), 2)                                           # 只記 font_menu_LB*
        e = bytes(self.mu.mem_read(log + 4, 20))
        self.assertEqual((struct.unpack_from('<I', e)[0], e[4:18]), (0xC0601234, b'font_menu_LB_0'))

    def test_menu_open_close_and_cursor(self):
        self.call('stub_mo', {})
        self.assertEqual((u32(self.mu, self.res + 0x1B8), self.calls[-1]), (1, 0xC05687E0))
        self.ma(16)
        self.assertEqual(u32(self.mu, self.res + 0x1BC), 16)                             # 游標列
        self.call('stub_mx', {})
        self.assertEqual((u32(self.mu, self.res + 0x1B8), self.calls[-1]), (0, 0xC0568888))

    def test_saturation_locked_at_zero(self):
        """bCOLOR:飽和度鎖 0(矩陣由右側框 FC/BC 決定)。"""
        self.assertEqual(self.sa(2), 1002)                        # flag 關:原換算
        self.assertEqual(self.sn(4, fix=True), 1004)
        self.select(16)
        self.assertEqual(self.sa(0), 0)                           # 0:不動、不發布
        self.assertEqual((self.sat(), self.satf(), PUBLISHED), (0, 0, []))
        self.sa(1)                                                # 捲動到 +1:夾回 0,刻度拉回 0(只發布 AJ)
        self.assertEqual(self.sat(), 0)
        self.assertEqual(PUBLISHED, [(0xC2DF0260, 0)])
        self.sa(-1); self.assertEqual(self.sat(), 0)
        self.assertEqual(PUBLISHED[-1], (0xC2DF0260, 0))
        self.sa(1, fix=True)                                      # 確認路徑被夾:存 0,不發布
        self.assertEqual((self.sat(), self.satf(), len(PUBLISHED)), (0, 0, 2))
        self.assertEqual((self.sn(0), self.sn(0, fix=True)), (0, 0))


class BMCC(unittest.TestCase):
    """bc_bmcc:LUT 內插、tone、校準與 LCD 矩陣(資料來自 bmcc6k/ 研究歸檔)。"""

    def test_tone_matches_archived_tetrahedral_samples(self):
        import csv, bc_bmcc, numpy as np
        f = bc_bmcc.AN / 'bmcc6k-liveview-rec709-20260924/luts/scene_linear_neutral_samples.csv'
        names = {v: k for k, v in bc_bmcc.CUBES.items()}
        n = 0
        for r in csv.DictReader(f.open()):
            if r['lut'] not in names or float(r['scene_linear_rgb']) <= 0:
                continue
            s = np.log2(float(r['scene_linear_rgb']) / 0.18)
            self.assertAlmostEqual(float(bc_bmcc.tone(names[r['lut']], s)), float(r['tetrahedral_output_r']), 6, r['sample'])
            n += 1
        self.assertGreater(n, 20)

    def test_tetrahedral_is_cross_channel(self):
        """README:R 固定 0.375、G/B 0.5625 時 Video 的 R 輸出是 0(格點,不經內插)。"""
        import bc_bmcc
        self.assertAlmostEqual(float(bc_bmcc.apply('video', [0.375, 0.5625, 0.5625])[0]), 0.0, 6)
        self.assertAlmostEqual(float(bc_bmcc.apply('video', [0.375, 0.375, 0.375])[0]), 0.385742188, 6)

    def test_calibration_and_matrices(self):
        import bc_bmcc, numpy as np
        CM1, CM2, FM1, FM2 = bc_bmcc.calibration()
        d = CM2 @ FM2
        self.assertTrue(np.allclose(d, np.diag(np.diag(d)), atol=1e-6))
        self.assertTrue(np.allclose(np.diag(d), (0.41933, 1, 0.77672), atol=1e-4))   # BMCC 中性值(D65)
        for k in range(rv_color.NMAT):
            m = rv_color.bc_matrix(k)
            self.assertTrue(np.allclose(m.sum(1), 1))                                  # 灰不偏
            self.assertEqual(sum(rv_color.bc_table(k)[0:3]), 512)
        # Video 的 LUT 矩陣 ≈ 色度上的 BMWG → 709(LUT 在中低飽和就是 3×3 + tone)
        col = np.linalg.inv(bc_bmcc.M709) @ bc_bmcc.bmwg_to_xyz()
        self.assertLess(np.abs(bc_bmcc.lut_matrix('video') - col).max(), 0.02)

    def test_dng_levels(self):
        import bc_bmcc, numpy as np
        b = rv_dngcm.blob()
        self.assertEqual(len(b), 3 * 144)
        rom = rv_dngcm.ROM.read_bytes()
        raw = lambda a: rom[a - 0xC0000000:a - 0xC0000000 + 72]
        self.assertEqual(b[:144], raw(rv_dngcm.OFF_CM1) + raw(rv_dngcm.OFF_CM2))
        self.assertEqual(b[144:288], raw(rv_dngcm.NON_CM1) + raw(rv_dngcm.NON_CM2))
        CM1, CM2 = bc_bmcc.calibration()[:2]
        self.assertTrue(np.allclose(np.array(struct.unpack('<18d', b[288:])), np.concatenate([CM1.ravel(), CM2.ravel()])))


if __name__ == '__main__':
    unittest.main(verbosity=2)
