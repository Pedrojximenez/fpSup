#!/usr/bin/env python3
"""RAW14 ÷3 probe —— 離線測試。

兩類:
  1. 產生器的閘門與靜態檢查(直接測 raw14_probe.py)。
  2. 探針程序的故障注入(測 ProbeModel —— 它是 raw14_probe.S 狀態機的
     Python 對照模型)。

第 2 類驗證的是**程序**會不會停、會不會清乾淨,不是 ARM 碼本身。
ARM 碼要等三個 hook 綁定之後,才能在原廠模式上做實機驗證。
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from typing import List, Optional

import raw14_probe as P


# ------------------------------------------------------------------ 對照模型
@dataclass
class ProbeModel:
    """raw14_probe.S 的狀態機對照模型。欄位名對應 PROBE_DESIGN.md §4。"""

    state: int = 0                     # 0 idle 1 armed 2 seen 3 abort 4 clean
    frames: int = 0
    gate_hits: int = 0
    abort_code: int = 0
    deadline: Optional[int] = None
    rz_lo: int = P.RZ_LO
    rz_hi: int = P.RZ_HI
    card_writes: int = 0               # 必須永遠是 0
    log: List[str] = field(default_factory=list)

    def arm(self, now: int, arm_ms: int) -> None:
        assert self.state in (0, 4), "只能從 idle/cleaned 武裝"
        self.state = 1
        self.frames = 0
        self.gate_hits = 0
        self.abort_code = 0
        self.deadline = now + arm_ms
        self.log.append(f"arm@{now}")

    def _deadline_check(self, now: int) -> None:
        if self.state == 1 and self.deadline is not None and now >= self.deadline:
            self.state = 3
            self.abort_code = 2        # A_DEADLINE
            self.log.append(f"deadline@{now}")

    # 閘門與畫格擷取狀態脫鉤:從 arm 關到 cleanup。SEEN 和 ABORT 下仍然關著,
    # 否則一次錄影的第 2..N 格會被寫到卡上。fail-closed。
    GATE_CLOSED = (1, 2, 3)            # armed / seen / abort

    def writer_enqueue(self, now: int) -> bool:
        """原廠寫檔入列點。回傳 True = 被探針消化(沒有寫到卡)。"""
        if self.state not in self.GATE_CLOSED:
            self.card_writes += 1
            return False
        if self.state == 1:
            self._deadline_check(now)  # 只會推到 abort,不開閘
        self.gate_hits += 1
        return True

    def frame_ready(self, now: int, desc=None) -> None:
        if self.state != 1:
            return
        self._deadline_check(now)
        if self.state != 1:
            return
        self.frames += 1
        if self.frames == 1:
            self.state = 2             # 看到一格就立刻解除武裝
            self.log.append(f"seen@{now}")

    def host_poll(self, now: int, host_timeout_at: int) -> bool:
        """主機端主要看門狗。回傳 True = 還要繼續等。"""
        if self.state != 1:
            return False
        if now >= host_timeout_at:
            self.state = 3
            self.abort_code = 1        # A_HOST
            self.log.append(f"host_timeout@{now}")
            return False
        return True

    def cleanup(self) -> int:
        """冪等。回傳 abort_code。"""
        if self.rz_lo != P.RZ_LO or self.rz_hi != P.RZ_HI:
            self.abort_code = 3        # A_REDZONE
            self.state = 3
            self.log.append("redzone_bad")
            return self.abort_code
        self.state = 4
        self.log.append("clean")
        return self.abort_code


# ------------------------------------------------------------------ 閘門測試
class TestGates(unittest.TestCase):
    def test_unbound_hook_refuses_payload(self):
        plan = P.Plan(stage="stock_nominal", hooks=P.Hooks(f_write=None))
        with self.assertRaises(P.GateError) as cm:
            plan.build(P.HERE / "raw14_probe.S")
        self.assertIn("hook 未綁定", str(cm.exception))
        self.assertIn("f_write", str(cm.exception))

    def test_all_gates_are_now_resolved(self):
        out = P.Plan(stage="stock_nominal", hooks=P.Hooks()).dry_run()
        self.assertEqual(out["unresolved_hooks"], [])

    def test_tick_gate_is_resolved(self):
        """TICK_US 已解:0xC002B6E0,函式,回傳 µs。
        證據是 fpSup/gyro/phase_probe.S 已經在四個地方呼叫它。"""
        self.assertEqual(P.KNOWN_TICK_US, 0xC002B6E0)
        self.assertNotIn("tick", P.Hooks().unresolved())

    def test_tick_is_emitted_as_a_call_not_an_address(self):
        """負載必須 blx 它。之前的版本是 ldr [TICK],那會讀到函式的第一道指令。"""
        src = (P.HERE / "raw14_probe.S").read_text()
        self.assertIn("TICK_US", src)
        self.assertIn("blx", src)
        self.assertNotIn("ldr     r0, [r0]", src)
        self.assertIn("TICK_US=", " ".join(
            P.Plan("stock_nominal", P.Hooks()).defines()))

    def test_single_hook_serves_both_roles(self):
        """2026-09-16 合併:每一格 CinemaDNG 都是一次 >=1 MB 的 F_WRITE,
        所以閘門和畫格偵測是同一個事件,不需要第二個掛鉤。"""
        self.assertEqual(P.KNOWN_F_WRITE, 0xC03660E8)
        self.assertEqual(P.KNOWN_F_WRITE_BODY, 0xC03660EC)
        d = " ".join(P.Plan("stock_nominal", P.Hooks()).defines())
        self.assertIn("F_WRITE=", d)
        self.assertIn("F_WRITE_BODY=", d)
        self.assertNotIn("HOOK_FRAME", d)

    def test_displaced_instruction_matches_the_firmware(self):
        P.Plan("stock_nominal", P.Hooks()).check_displaced()

    def test_displaced_check_rejects_a_wrong_site(self):
        """掛到別的位址上,位移指令就不會是 push,必須拒絕。"""
        plan = P.Plan("stock_nominal", P.Hooks(f_write=P.KNOWN_F_WRITE + 4))
        with self.assertRaises(P.GateError) as cm:
            plan.check_displaced()
        self.assertIn("不得產生負載", str(cm.exception))
        self.assertIn("0xe24dd008", str(cm.exception))

    def test_payload_hand_writes_the_displaced_instruction(self):
        src = (P.HERE / "raw14_probe.S").read_text()
        self.assertIn("stmfd   sp!, {r4, r5, r6, r7, lr}", src)

    def test_small_writes_are_never_gated(self):
        """負載必須在查狀態**之前**就放行小寫入 —— shell 的 getfile/putfile、
        記錄檔、gyro CSV 都走同一個 F_WRITE。"""
        src = (P.HERE / "raw14_probe.S").read_text()
        i_cmp = src.index("cmp     r2, #DNG_MIN")
        i_state = src.index("ldr     r3, [r4, #O_STATE]")
        self.assertLess(i_cmp, i_state, "長度過濾必須在狀態檢查之前")
        self.assertEqual(P.Plan("stock_nominal", P.Hooks()).dng_min(), 0x100000)

    def test_stock_stage_rejects_selector(self):
        plan = P.Plan(stage="stock_nominal", hooks=P.Hooks(1, 2), selector=0x2E)
        with self.assertRaises(P.GateError) as cm:
            plan.check_selector(allow_undefined=True)
        self.assertIn("不得攜帶 selector", str(cm.exception))

    def test_known_selector_rejected_even_with_flag(self):
        for value in P.SELECTOR_KNOWN:
            plan = P.Plan(stage="candidate_live", hooks=P.Hooks(1, 2),
                          selector=value)
            with self.assertRaises(P.GateError) as cm:
                plan.check_selector(allow_undefined=True)
            self.assertIn("已知", str(cm.exception))

    def test_undefined_selector_needs_explicit_flag(self):
        plan = P.Plan(stage="candidate_live", hooks=P.Hooks(1, 2),
                      selector=P.SELECTOR_CANDIDATE)
        with self.assertRaises(P.GateError):
            plan.check_selector(allow_undefined=False)
        plan.check_selector(allow_undefined=True)      # 帶旗標才過

    def test_candidate_value_is_not_in_use(self):
        self.assertNotIn(P.SELECTOR_CANDIDATE, P.SELECTOR_KNOWN)

    def test_selector_table_is_one_to_one(self):
        pairs = [(d, s) for d, s, _ in P.SELECTOR_KNOWN.values()]
        self.assertEqual(len(pairs), len(set(pairs)), "selector 與 (位深,縮減) 不是一對一")
        self.assertEqual(sum(n for _, _, n in P.SELECTOR_KNOWN.values()), 70)

    def test_ladder_note_for_candidate_stages(self):
        for stage in ("candidate_dry", "candidate_live"):
            plan = P.Plan(stage=stage, hooks=P.Hooks())
            plan.check_ladder()
            self.assertTrue(any("需要" in n for n in plan.notes))


class TestLayout(unittest.TestCase):
    def test_probe_clears_every_resident(self):
        self.assertEqual(P.Plan("stock_nominal", P.Hooks()).check_layout(), [])

    def test_collision_is_detected(self):
        saved = list(P.RESIDENTS)
        try:
            P.RESIDENTS.append((P.PROBE_CODE, P.PROBE_CODE + 4, "假常駐者"))
            problems = P.Plan("stock_nominal", P.Hooks()).check_layout()
            self.assertTrue(problems)
            self.assertIn("假常駐者", problems[0])
        finally:
            P.RESIDENTS[:] = saved

    def test_state_redzone_is_inside_the_checked_span(self):
        self.assertEqual(P.PROBE_STATE_LEN, 0x48)      # 0x44 欄位 + redzone hi


# -------------------------------------------------------- 故障注入(必要兩案)
class TestProcedure(unittest.TestCase):
    """PROBE_DESIGN.md §6 階段 1、2 的離線對照。"""

    def test_stock_nominal(self):
        m = ProbeModel()
        m.arm(now=0, arm_ms=8000)
        for t in range(100, 400, 100):          # 原廠管線照常送畫格與寫檔入列
            self.assertTrue(m.writer_enqueue(t))
            m.frame_ready(t)
        self.assertEqual(m.state, 2, "應該看到畫格")
        self.assertGreaterEqual(m.frames, 1)
        self.assertGreaterEqual(m.gate_hits, 1)
        self.assertEqual(m.card_writes, 0, "探針絕不可產生檔案")
        self.assertEqual(m.cleanup(), 0)
        self.assertEqual(m.state, 4)

    def test_stock_timeout(self):
        m = ProbeModel()
        m.arm(now=0, arm_ms=8000)
        t, deadline = 0, 3000                   # 主機時限比相機端期限早
        while m.host_poll(t, deadline):
            t += 250
        self.assertEqual(m.state, 3)
        self.assertEqual(m.abort_code, 1, "應該是主機逾時")
        self.assertEqual(m.frames, 0)
        self.assertEqual(m.card_writes, 0)
        self.assertEqual(m.cleanup(), 1)
        self.assertEqual(m.state, 4)

    def test_camera_deadline_fires_but_gate_stays_closed(self):
        """主機失聯時:相機端期限停止擷取,但閘門**不得**打開。

        期限到了就開閘的話,一次進行中的錄影會從那一刻起開始寫檔案 ——
        那正是探針最不能發生的事。fail-closed:閘門只有 cleanup 能打開。
        """
        m = ProbeModel()
        m.arm(now=0, arm_ms=1000)
        self.assertTrue(m.writer_enqueue(5000))      # 已逾期,但仍然消化
        self.assertEqual(m.state, 3)
        self.assertEqual(m.abort_code, 2)
        self.assertEqual(m.card_writes, 0, "逾期後也不得產生檔案")
        m.frame_ready(5100)
        self.assertEqual(m.frames, 0, "逾期後不再擷取")

    def test_gate_stays_closed_for_every_frame_of_a_take(self):
        """回歸:第一版把閘門綁在 ARMED 上,看到第一格就開閘,
        一次錄影的第 2..N 格會被寫到卡上。"""
        m = ProbeModel()
        m.arm(now=0, arm_ms=60_000)
        for t in range(0, 300):                      # 300 格 ≈ 12 秒 @25p
            self.assertTrue(m.writer_enqueue(t * 40))
            m.frame_ready(t * 40)
        self.assertEqual(m.card_writes, 0, "整段錄影都不得產生檔案")
        self.assertEqual(m.gate_hits, 300)
        self.assertEqual(m.frames, 1)

    def test_redzone_corruption_marks_result_untrustworthy(self):
        m = ProbeModel()
        m.arm(now=0, arm_ms=8000)
        m.frame_ready(100)
        m.rz_hi ^= 0xFF                              # 注入破壞
        self.assertEqual(m.cleanup(), 3)
        self.assertEqual(m.state, 3, "redzone 壞掉不得回報成功")

    def test_cleanup_is_idempotent(self):
        m = ProbeModel()
        m.arm(now=0, arm_ms=8000)
        m.frame_ready(100)
        first = m.cleanup()
        self.assertEqual(m.cleanup(), first)
        self.assertEqual(m.cleanup(), first)
        self.assertEqual(m.state, 4)

    def test_writer_gate_is_closed_before_and_after_arming(self):
        m = ProbeModel()
        self.assertFalse(m.writer_enqueue(0))        # 未武裝 → 原廠行為
        m.arm(now=10, arm_ms=8000)
        self.assertTrue(m.writer_enqueue(20))
        m.frame_ready(20)
        m.cleanup()
        self.assertFalse(m.writer_enqueue(30))       # 已清理 → 原廠行為
        self.assertEqual(m.card_writes, 2)           # 那兩次不是探針造成的

    def test_only_first_frame_is_recorded(self):
        m = ProbeModel()
        m.arm(now=0, arm_ms=8000)
        for t in (10, 20, 30):
            m.frame_ready(t)
        self.assertEqual(m.frames, 1, "看到一格就該解除武裝")


class TestTimingModel(unittest.TestCase):
    """整條 RAW14 ÷3 可行性論證架在 `hmax × rows / 72 MHz` 上。

    下面的「相機報告」欄是 2026-09-16 用 `imager mode_list` 實機讀到的有效讀出
    時間(µs),涵蓋三個 hmax 等級與兩種位深。模型必須逐筆對上,誤差 ≤1 µs
    (相機報整數微秒)。
    """

    CLOCK_HZ = 72_000_000

    # (名稱, hmax, rows, 相機報告 µs)
    MEASURED = [
        ("ACQ            RAW14 1×", 911, 4042, 51_142),
        ("ACQ_12BIT      RAW12 1×", 445, 4042, 24_982),
        ("MONIT1_60      RAW12 ÷3", 330, 1344,  6_160),
        ("MONIT1_60_LOWP5 RAW12 ÷3", 445, 1344,  8_306),
        ("MONIT1_100_LOWP RAW12 ÷3", 395, 1344,  7_373),
    ]

    @classmethod
    def readout_us(cls, hmax: int, rows: int) -> float:
        return hmax * rows / cls.CLOCK_HZ * 1e6

    def test_model_matches_the_camera(self):
        for name, hmax, rows, reported in self.MEASURED:
            with self.subTest(mode=name):
                self.assertAlmostEqual(
                    self.readout_us(hmax, rows), reported, delta=1.0,
                    msg=f"{name}: 模型與相機報告不符",
                )

    def test_raw14_div3_prediction(self):
        """RAW14 走 hmax 911(70 個模式零例外),÷3 的列數是 1344。"""
        us = self.readout_us(911, 1344)
        self.assertAlmostEqual(us, 17_005, delta=2.0)

    def test_frame_rate_budget(self):
        us = self.readout_us(911, 1344)
        fits = {
            "25p": 40_000,
            "29.97p": 33_366,
            "50p": 20_000,
        }
        for name, budget in fits.items():
            with self.subTest(rate=name):
                self.assertLess(us, budget, f"{name} 應該塞得進去")
        self.assertGreater(us, 16_683, "60p 應該塞不進去")

    def test_60p_shortfall_is_small_enough_to_matter(self):
        """差 322 µs —— 記錄下來,因為它小到會讓人想去動 hmax。
        70 個 RAW14 模式的 hmax 全部固定 911,所以那不是可調的。"""
        shortfall = self.readout_us(911, 1344) - 16_683
        self.assertAlmostEqual(shortfall, 322, delta=3.0)


class TestSynthesis(unittest.TestCase):
    """暫存器合成。每個結論都由多組獨立配對交叉驗證。"""

    @classmethod
    def setUpClass(cls):
        import synthesize
        cls.S = synthesize
        cls.syn = synthesize.Synthesis()

    def test_depth_block_agrees_across_four_pairs(self):
        """四組配對必須對位址**和值**都一致 —— 不一致時 depth_block() 會拋。"""
        block = self.syn.depth_block()
        self.assertEqual(len(block), 38)

    def test_reduction_core(self):
        self.assertEqual(len(self.syn.reduction_core()), 22)

    def test_the_only_overlap_is_the_selector(self):
        """整個 14-bit ÷3 計畫的生死關就是這一行。"""
        self.assertEqual(self.syn.overlap(), [self.S.SELECTOR_REG])

    def test_selector_table_is_one_to_one_and_covers_70(self):
        pairs = [(d, s) for d, s, _ in self.S.SELECTOR_KNOWN.values()]
        self.assertEqual(len(pairs), len(set(pairs)))
        self.assertEqual(sum(n for _, _, n in self.S.SELECTOR_KNOWN.values()), 70)
        self.assertNotIn(self.S.SELECTOR_CANDIDATE, self.S.SELECTOR_KNOWN)

    def test_plan_for_m139(self):
        plan = self.syn.plan(139)
        self.assertEqual(len(plan["sensor"]), 38)
        self.assertEqual(len(plan["timing"]), 1)
        gambles = [e for e in plan["sensor"] if e["gamble"]]
        self.assertEqual(len(gambles), 1)
        self.assertEqual(gambles[0]["new"], self.S.SELECTOR_CANDIDATE)
        self.assertGreater(plan["margin_ms"], 0)
        self.assertAlmostEqual(plan["readout_ms"], 17.005, delta=0.01)

    def test_plan_refuses_a_known_selector(self):
        for value in self.S.SELECTOR_KNOWN:
            with self.assertRaises(self.S.SynthesisError):
                self.syn.plan(139, selector=value)

    def test_plan_refuses_a_non_div3_base(self):
        for m in (97, 141, 98):
            with self.assertRaises(self.S.SynthesisError):
                self.syn.plan(m)

    def test_active_rows_match_the_raster(self):
        self.assertEqual(self.syn._active_rows(139), 1344)
        self.assertEqual(self.syn._active_rows(8), 1344)


if __name__ == "__main__":
    unittest.main(verbosity=2)
