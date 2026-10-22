#!/usr/bin/env python3
"""og3kcanvas 的錄影 case:在 unicorn 裡跑 payload,逐欄比對它寫進畫布的東西。

**emulated,不是相機。** 這裡能證明的只有「payload 對一塊假畫布做了什麼」;
引擎真的怎麼用 +0x030/+0x090/+0x0C0 只有上機才知道
(2026-09-27 已上機讀值確認三欄生效,見
notes/OG3K_ENGINE_CONFIG_THREE_FIELDS.md §6)。

初始畫布用**映像裡 p83 真正的 65 欄**,不是全零 —— 全零看不見
「把 1 寫成 0」這種改動,而 +0x0C0 正好就是這種。

    python3 -B test_canvas_engfps.py

五個突變都驗證會失敗(2026-09-27):拿掉 strne 的 0 守衛、+0x0C0 寫回 1、
+0x090 寫 0、拿掉 profile 守衛、fmttable 不鎖存。
"""
import os, struct, sys, pathlib, unittest
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from unicorn import *
from unicorn.arm_const import *

HOLDER = 0x45000000
CANVAS = HOLDER + 0x5C
RAM    = 0x45000000

def donor_row(profile):
    """畫布的初始內容 = 韌體裡那個 profile 的 65 欄。

    用全零的假畫布會看不見「把 1 寫成 0」這種改動 —— +0x0C0 正好就是這種。
    """
    import json, struct
    root = HERE.parents[2]
    d = json.loads((root / 'research/other/external/FP3K-technical-handoff-2026-09-10'
                    / 'analysis/firmware/raw-profiles.json').read_text())
    offs = [c['offset'] for c in d['columns']]
    for r in d['rows']:
        if profile in r['profile_ids']:
            return dict(zip(offs, r['words']))
    raise KeyError(profile)


def run(target='og3k', hirate=None, engfps=None, profile=None,
        flag=1, fpslatch=None, bitlatch=0):
    env = dict(os.environ, OG_TARGET=target)
    if hirate is not None: env['OG_HIRATE'] = hirate
    if engfps is not None: env['OG_ENGFPS'] = engfps
    for k in list(sys.modules):
        if k.startswith('og3k_plan'): del sys.modules[k]
    old = os.environ.copy(); os.environ.clear(); os.environ.update(env)
    try:
        import og3k_plan as P
        pl = P.Plan()
        blob = pl.blobs['og3kcanvas']
        consts = dict(FLAG=P.FLAG, BITLATCH=P.BITLATCH, ROW_CODE=P.ROW_CODE,
                      LOG=P.ROW_LOG, PROF=P.OG_PROFILE,
                      FPSLATCH=getattr(P, 'FPSLATCH', None),
                      REC=P.CANVAS_REC, ENGFPS=P.WITH_ENGFPS)
    finally:
        os.environ.clear(); os.environ.update(old)

    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    mu.mem_map(0xC0730000, 0x10000)          # cave
    mu.mem_map(RAM, 0x10000)                 # 假畫布
    mu.mem_write(consts['ROW_CODE'], blob)
    mu.mem_map(0x44FF0000, 0x10000)          # stack
    mu.mem_write(consts['FLAG'], struct.pack('<I', flag))
    mu.mem_write(consts['BITLATCH'], struct.pack('<I', bitlatch))
    if consts['FPSLATCH'] and fpslatch is not None:
        mu.mem_write(consts['FPSLATCH'],
                     struct.pack('<f', fpslatch) if isinstance(fpslatch, float)
                     else struct.pack('<I', fpslatch))
    row = donor_row(consts['PROF'])
    for off, val in row.items():
        mu.mem_write(CANVAS + off, struct.pack('<I', val))
    before = bytes(mu.mem_read(CANVAS, 0x140))
    mu.reg_write(UC_ARM_REG_R4, HOLDER)
    mu.reg_write(UC_ARM_REG_R5, consts['PROF'] if profile is None else profile)
    mu.reg_write(UC_ARM_REG_SP, 0x44FF8000)
    mu.reg_write(UC_ARM_REG_LR, 0xC0700000)
    mu.mem_map(0xC0700000, 0x1000)
    mu.mem_write(0xC0700000, struct.pack('<I', 0xEAFFFFFE))   # b .  (停在這裡)
    try:
        mu.emu_start(consts['ROW_CODE'], 0xC0700004, count=400)
    except UcError:
        pass
    after = bytes(mu.mem_read(CANVAS, 0x140))
    wrote = {off: struct.unpack_from('<I', after, off)[0]
             for off in range(0, 0x140, 4)
             if after[off:off+4] != before[off:off+4]}
    final = {off: struct.unpack_from('<I', after, off)[0] for off in row}
    return consts, wrote, final, row


class T(unittest.TestCase):
    def test_og3k_default_writes_exactly_the_plan(self):
        """最終畫布必須等於 p83 加上剛好這七欄 —— 多一欄少一欄都算失敗。"""
        c, wrote, final, row = run(fpslatch=25.0)
        want = dict(row)
        want.update(c['REC'])                       # 0x00/0x04/0x80/0x90/0xC0
        want[0x84] = 7                              # PFMT 12-bit 那一路
        want[0x30] = struct.unpack('<I', struct.pack('<f', 25.0))[0]
        self.assertEqual(final, want)
        # 三個「這是影片」的欄位確實從 donor 的值被改掉了
        self.assertEqual((row[0xC0], final[0xC0]), (1, 0), "+0x0C0 1 -> 0")
        self.assertEqual((row[0x90], final[0x90]), (0, 1), "+0x090 0 -> 1")
        self.assertEqual(struct.unpack('<f', struct.pack('<I', row[0x30]))[0], 18.0)

    def test_fps_latch_zero_leaves_canvas_alone(self):
        """還沒命中過 -> 不寫 +0x030,留著 donor 原廠的 18.0。寫 0.0 會更糟。"""
        c, wrote, final, row = run(fpslatch=0)
        self.assertNotIn(0x30, wrote)
        self.assertEqual(final[0x30], row[0x30])

    def test_each_rate_lands_verbatim(self):
        for fps in (24.0, 25.0, 30.0, 48.0, 50.0, 60.0):
            c, wrote, final, row = run(fpslatch=fps)
            got = struct.unpack('<f', struct.pack('<I', wrote[0x30]))[0]
            self.assertEqual(got, fps, f"{fps} 沒有原封不動寫進 +0x030")
            self.assertGreater(got, 0, "非正值會讓 plane count 歸零")

    def test_flag_zero_writes_nothing(self):
        c, wrote, final, row = run(fpslatch=25.0, flag=0)
        self.assertEqual(wrote, {}, "FLAG=0 時畫布一個位元都不能動")

    def test_other_profile_writes_nothing(self):
        c, wrote, final, row = run(fpslatch=25.0, profile=175)
        self.assertEqual(wrote, {}, "別的 profile 不能被碰到")

    def test_baseline_leaves_all_three_at_donor_values(self):
        """對照組:三欄都維持 p83 原廠值(18.0 / 0 / 1)。"""
        c, wrote, final, row = run(hirate='none', engfps='0', fpslatch=25.0)
        self.assertFalse(c['ENGFPS'])
        for off in (0x30, 0x90, 0xC0):
            self.assertEqual(final[off], row[off], f"+0x{off:03X} 不該被動")

if __name__ == '__main__':
    unittest.main(verbosity=2)
