#!/usr/bin/env python3
"""og3kaspect / og3kaspect2 的 PICKOK 閘門:在 unicorn 裡跑,驗真值表。

**emulated,不是相機。** 這裡證明的只有「payload 依兩個旗標給出哪個 enum」。

長寬比表 C0B4CAB8:1=4:3  2=3:2  3=16:9  4=1:1
    FLAG=0                  -> 3(原廠 16:9)
    FLAG=1 且 PICKOK=1      -> 2(3:2)
    FLAG=1 但 PICKOK=0      -> 3  ← 2026-09-27 新增:picker 不同意就退場
                                    (OG3K + 119.88 -> 鍵 OG3K120 查不到 ->
                                     原廠退回 UHD30,顯示要跟著走 16:9)

    python3 -B test_pickok.py
"""
import pathlib, struct, sys, unittest
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent.parent / "fpSup" / "fp_usb_shell"))
from armasm import assemble
from unicorn import *
from unicorn.arm_const import *

import og3k_plan as P

CODE = 0xC0731B00           # og3kaspect 的 payload 位址(ASP_CODE)
BACKS = {"og3kaspect.S": 0xC0306EA4, "og3kaspect2.S": 0xC0306EF0}


def run(src, flag, pickok, with_match=True):
    defines = [f"TARGET_MATCH={P.MATCH:#x}"] if with_match else []
    blob = assemble(HERE / src, defines=defines)
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    mu.mem_map(0xC0730000, 0x10000)         # cave
    mu.mem_map(0xC0300000, 0x10000)         # 回跳點
    mu.mem_write(CODE, blob)
    mu.mem_write(P.FLAG, struct.pack('<I', flag))
    mu.mem_write(P.MATCH, struct.pack('<I', pickok))
    back = BACKS[src]
    mu.mem_write(back, struct.pack('<I', 0xEAFFFFFE))   # b .  停在這裡
    mu.reg_write(UC_ARM_REG_R0, 0xDEAD)
    mu.reg_write(UC_ARM_REG_SP, 0xC073F000)
    try:
        mu.emu_start(CODE, back + 4, count=60)
    except UcError:
        pass
    return mu.reg_read(UC_ARM_REG_R0)


def run_fmttable(key, table=None):
    """跑 fmttable 的查表,回傳 (PICKOK, 有沒有命中)。

    只餵**未命中**那條路時不會碰到 cpsr/dmb,所以在 unicorn 裡很乾淨;
    命中那條會寫 donor 時序記錄,所以也把那塊映進去。
    """
    blob = assemble(HERE / "fmttable.S",
                    defines=[f"TARGET_ENGFPS={P.FPSLATCH:#x}",
                             f"TARGET_MATCH={P.MATCH:#x}",
                             f"TARGET_LABEL={int.from_bytes(P.T['label'].encode(),'little'):#x}"])
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    mu.mem_map(0xC0730000, 0x10000)          # cave + 格式表
    mu.mem_map(0xC0BE0000, 0x10000)          # picker 表
    mu.mem_map(0xC0B50000, 0x20000)          # donor 時序記錄
    mu.mem_map(0xC0430000, 0x10000)          # 原廠回跳點
    mu.mem_map(0xC0740000, 0x10000)          # 鍵緩衝 + 堆疊
    mu.mem_write(P.CODE, blob)
    # 格式表:從計畫裡取真正的八筆
    pl = P.Plan()
    for a, v, note in pl.fmt_table():
        if 0xC0731000 <= a < 0xC0740000:
            mu.mem_write(a, struct.pack('<I', v))
    mu.mem_write(P.MATCH, struct.pack('<I', 0x5A5A))       # 哨兵:沒被寫就看得出來
    KEY = 0xC0741000
    mu.mem_write(KEY, key.encode() + b'\0' * (16 - len(key)))
    mu.mem_write(0xC043CCFC, struct.pack('<I', 0xEAFFFFFE))  # BACK: b .
    mu.reg_write(UC_ARM_REG_R0, 0)
    mu.reg_write(UC_ARM_REG_R1, table if table is not None else 0xC0BE5B50)
    mu.reg_write(UC_ARM_REG_R2, KEY)
    mu.reg_write(UC_ARM_REG_SP, 0xC0748000)
    mu.reg_write(UC_ARM_REG_LR, 0xC043CD00)
    mu.mem_write(0xC043CD00, struct.pack('<I', 0xEAFFFFFE))
    try:
        mu.emu_start(P.CODE, 0xC043CD04, count=4000)
    except UcError:
        pass
    pick = struct.unpack('<I', mu.mem_read(P.MATCH, 4))[0]
    hits = struct.unpack('<I', mu.mem_read(P.HITS, 4))[0]
    return pick, hits


class FmtTable(unittest.TestCase):
    def test_unsupported_rate_clears_pickok(self):
        """★ 缺陷本身:OG3K120 —— 我們的表與原廠表都查不到。"""
        pick, hits = run_fmttable("OG3K120")
        self.assertEqual(pick, 0, "查不到自家的鍵時 PICKOK 必須清 0")
        self.assertEqual(hits, 0, "不該命中")

    def test_supported_rate_sets_pickok(self):
        pick, hits = run_fmttable("OG3K30")
        self.assertEqual(pick, 1, "命中時 PICKOK 必須寫 1")
        self.assertEqual(hits, 1)

    def test_foreign_key_leaves_pickok_alone(self):
        """原廠的鍵不能碰 PICKOK —— 否則選 UHD 也會把它清掉。"""
        pick, hits = run_fmttable("UHD30")
        self.assertEqual(pick, 0x5A5A, "非自家標籤的鍵不該動 PICKOK")
        self.assertEqual(hits, 0)

    def test_other_table_leaves_pickok_alone(self):
        """r1 不是三張 picker 表之一 -> 早退,連掃都不掃。"""
        pick, _ = run_fmttable("OG3K120", table=0xC0BE0000)
        self.assertEqual(pick, 0x5A5A)


def run_out(flag, pickok, with_match=True):
    """跑 og3kout 的 idx0,回傳 TPL0 的第一個字。

    可觀測量:私有模板 TPL0 **只有走 armed 那條**才會被建起來(檔頭:第一次
    命中時整份複製到私有緩衝);走 logonly 就只記錄、不建。
    """
    defines = [f"TARGET_MATCH={P.MATCH:#x}"] if with_match else []
    blob = assemble(HERE / "og3kout.S", defines=defines)
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    mu.mem_map(0xC0730000, 0x10000)
    mu.mem_map(0xC0430000, 0x10000)
    mu.mem_map(0xC0740000, 0x10000)
    mu.mem_write(P.OUT_CODE, blob)
    mu.mem_write(P.FLAG, struct.pack('<I', flag))
    mu.mem_write(P.MATCH, struct.pack('<I', pickok))
    mu.mem_write(P.PBFLAG, struct.pack('<I', 0))
    mu.mem_write(P.TPL0, struct.pack('<I', 0))
    # 原廠描述子:1620x911(og3kout 的守衛要求確為這個尺寸)
    DESC, ARR = 0xC0745000, 0xC0746000
    mu.mem_write(DESC, struct.pack('<11I', 1620, 911, 0, 0, 1620, 911,
                                   0, 4, 0x3FC000, 1, 1))
    mu.mem_write(ARR, struct.pack('<2I', DESC, 0))
    mu.mem_write(0xC0437E9C, struct.pack('<I', 0xEAFFFFFE))   # BACK: b .
    mu.reg_write(UC_ARM_REG_R0, ARR)
    mu.reg_write(UC_ARM_REG_R1, 0)
    mu.reg_write(UC_ARM_REG_SP, 0xC0748000)
    mu.reg_write(UC_ARM_REG_LR, 0xC0437F00)
    mu.mem_write(0xC0437F00, struct.pack('<I', 0xEAFFFFFE))
    try:
        mu.emu_start(P.OUT_CODE, 0xC0437F04, count=4000)
    except UcError:
        pass
    return struct.unpack('<I', mu.mem_read(P.TPL0, 4))[0]


class Out(unittest.TestCase):
    def test_gate(self):
        self.assertNotEqual(run_out(1, 1), 0, "FLAG=1 PICKOK=1 應該建模板")
        self.assertEqual(run_out(1, 0), 0,
                         "★ FLAG=1 但 picker 不同意 -> 不能建 3:2 的模板")
        self.assertEqual(run_out(0, 0), 0, "FLAG=0 本來就不該建")

    def test_without_match(self):
        """對照組:PICKOK 不被看,FLAG 一個人決定。"""
        self.assertNotEqual(run_out(1, 0, with_match=False), 0)


class T(unittest.TestCase):
    def test_truth_table(self):
        for src in BACKS:
            for flag, pickok, want in ((0, 0, 3), (0, 1, 3), (1, 1, 2), (1, 0, 3)):
                got = run(src, flag, pickok)
                self.assertEqual(got, want,
                                 f"{src}: FLAG={flag} PICKOK={pickok} -> "
                                 f"enum {got},應該是 {want}")

    def test_picker_disagrees_gives_stock(self):
        """★ 這一條就是缺陷本身:FLAG 立著但 picker 退回 UHD30。"""
        for src in BACKS:
            self.assertEqual(run(src, 1, 0), 3, f"{src}: 應該退回 16:9")

    def test_without_match_flag_alone_decides(self):
        """對照組(OG_MATCH=0):PICKOK 完全不被看,行為與改動前相同。"""
        for src in BACKS:
            self.assertEqual(run(src, 1, 0, with_match=False), 2)
            self.assertEqual(run(src, 1, 1, with_match=False), 2)
            self.assertEqual(run(src, 0, 0, with_match=False), 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
