#!/usr/bin/env python3
"""RAW14 ÷3 候選模式的暫存器合成 —— 純離線,只讀韌體映像。

把「位深區塊」和「÷3 縮減核心」從 70 個原廠模式裡解出來,再組成候選列。
所有結論都由多組獨立配對交叉驗證;任何一組不一致就不會靜默通過。

用法:
    python3 synthesize.py                 # 摘要
    python3 synthesize.py --plan 139      # 產生某個模式的完整寫入清單
    python3 synthesize.py --plan 139 --json out.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "raw14_2x_experiment"))
import raw14_2x_plan as P                                    # noqa: E402

# 位深配對:同幾何 6064x4042,只差 RAW12 <-> RAW14。
DEPTH_PAIRS: Sequence[Tuple[int, int]] = ((142, 141), (97, 0), (3, 0), (121, 0))

# ÷3 縮減配對:同位深 RAW12,1/1 -> 3/3。
REDUCTION_PAIRS: Sequence[Tuple[int, int]] = ((97, 139), (3, 8), (121, 147), (142, 56))

# 兩塊唯一的交集。它不是參數,是 Sony drive-mode 表的索引。
SELECTOR_REG = 0x0001

# 70 個模式裡 reg 0x0001 與 (位深, 縮減) 完美一對一,零例外。
SELECTOR_KNOWN: Dict[int, Tuple[str, str, int]] = {
    0x29: ("RAW14", "1/1", 8),
    0x2A: ("RAW12", "1/1", 15),
    0x2F: ("RAW12", "3/3", 8),
    0x30: ("RAW12", "3/6", 3),
    0x39: ("RAW12", "2/2", 36),
}
# 外插候選。依「RAW14 比同縮減的 RAW12 少 1」,但那條規則只有一個觀測對
# (0x29/0x2A)支撐。這是探測,不是計畫。
SELECTOR_CANDIDATE = 0x2E

RAW14_HMAX = 911          # 70 個 RAW14 模式零例外
CLOCK_HZ = 72_000_000


class SynthesisError(RuntimeError):
    pass


class Synthesis:
    def __init__(self) -> None:
        self.fw = P.Firmware()
        self.regs = self.fw.registers

    def row(self, mode: int) -> Dict[int, int]:
        return {r: self.fw.sensor_register(mode, r) for r in self.regs}

    def _deltas(self, pairs: Sequence[Tuple[int, int]]) -> List[Dict[int, Tuple[int, int]]]:
        out = []
        for a, b in pairs:
            ra, rb = self.row(a), self.row(b)
            out.append({r: (ra[r], rb[r]) for r in self.regs if ra[r] != rb[r]})
        return out

    def depth_block(self) -> Dict[int, int]:
        """RAW12 -> RAW14 的目標值。四組配對必須對位址和值都一致。"""
        deltas = self._deltas(DEPTH_PAIRS)
        common = sorted(set.intersection(*[set(d) for d in deltas]))
        block: Dict[int, int] = {}
        for r in common:
            targets = {d[r][1] for d in deltas}
            if len(targets) != 1:
                raise SynthesisError(
                    f"reg 0x{r:04X} 的 RAW14 目標值在四組配對間不一致:"
                    + ", ".join(hex(v) for v in sorted(targets))
                )
            block[r] = targets.pop()
        return block

    def reduction_core(self) -> List[int]:
        """1/1 -> 3/3 的共同暫存器位址(只取位址,值隨來源模式)。"""
        deltas = self._deltas(REDUCTION_PAIRS)
        return sorted(set.intersection(*[set(d) for d in deltas]))

    def overlap(self) -> List[int]:
        return sorted(set(self.depth_block()) & set(self.reduction_core()))

    # ------------------------------------------------------------------ 計畫
    def plan(self, base_mode: int, selector: int = SELECTOR_CANDIDATE) -> Dict:
        """base_mode 必須是 RAW12 ÷3。回傳完整的寫入清單。"""
        block = self.depth_block()
        base = self.row(base_mode)
        if base[SELECTOR_REG] not in SELECTOR_KNOWN:
            raise SynthesisError(f"M{base_mode} 的 selector 不在已知表裡")
        depth, scale, _ = SELECTOR_KNOWN[base[SELECTOR_REG]]
        if (depth, scale) != ("RAW12", "3/3"):
            raise SynthesisError(f"M{base_mode} 是 {depth} {scale},不是 RAW12 3/3")
        if selector in SELECTOR_KNOWN:
            raise SynthesisError(
                f"0x{selector:02X} 是已知的 {SELECTOR_KNOWN[selector][0]} "
                f"{SELECTOR_KNOWN[selector][1]};拿已知索引冒充 RAW14 3/3 會讓"
                "感測器與下游配置不一致,禁止。"
            )

        sensor = []
        for r, new in sorted(block.items()):
            value = selector if r == SELECTOR_REG else new
            if base[r] != value:
                sensor.append({
                    "addr": self.fw.sensor_register_address(base_mode, r),
                    "reg": r, "old": base[r], "new": value,
                    "gamble": r == SELECTOR_REG,
                })

        ta = self.fw.timing_address(base_mode)
        w = self.fw.record_words(ta, P.TIMING_STRIDE)
        hmax, tail, vmax = w[1] & 0xFFFF, w[1] >> 16, w[2] & 0xFFFF
        rows = self._active_rows(base_mode)
        readout_us = RAW14_HMAX * rows / CLOCK_HZ * 1e6
        fps = P.exact_fps(RAW14_HMAX, tail, vmax)
        frame_us = 1e6 / fps
        if readout_us >= frame_us:
            raise SynthesisError(
                f"只改 hmax 放不下:讀出 {readout_us/1000:.3f} ms >= "
                f"一格 {frame_us/1000:.3f} ms。vmax 也得動。"
            )
        timing = [{
            "addr": ta + 4, "old": w[1], "new": RAW14_HMAX | (tail << 16),
            "note": f"hmax {hmax} -> {RAW14_HMAX}(vmax {vmax} / tail {tail} 不動)",
        }]
        return {
            "base_mode": base_mode,
            "selector": selector,
            "sensor": sensor,
            "timing": timing,
            "readout_ms": round(readout_us / 1000, 3),
            "frame_ms": round(frame_us / 1000, 3),
            "fps": round(fps, 3),
            "margin_ms": round((frame_us - readout_us) / 1000, 3),
        }

    def _active_rows(self, mode: int) -> int:
        """從時序記錄的視窗欄位取有效列數。"""
        w = self.fw.record_words(self.fw.timing_address(mode), P.TIMING_STRIDE)
        y_start = w[3] >> 16
        y_end = w[4] & 0xFFFF
        return y_end - y_start


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--plan", type=int, metavar="MODE")
    ap.add_argument("--selector", type=lambda s: int(s, 0), default=SELECTOR_CANDIDATE)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args(argv)

    s = Synthesis()
    block = s.depth_block()
    core = s.reduction_core()
    over = s.overlap()
    print(f"位深區塊 RAW12->RAW14 : {len(block)} 個暫存器,{len(DEPTH_PAIRS)} 組配對一致")
    print(f"÷3 縮減核心 1/1->3/3  : {len(core)} 個暫存器,{len(REDUCTION_PAIRS)} 組配對一致")
    print(f"交集                  : {len(over)} 個 -> "
          + ", ".join(f"reg 0x{r:04X}" for r in over))

    if args.plan is None:
        return 0
    plan = s.plan(args.plan, args.selector)
    print(f"\nM{plan['base_mode']} 候選({len(plan['sensor'])} 個感測器 + "
          f"{len(plan['timing'])} 個時序寫入)")
    for e in plan["sensor"]:
        tag = "   <- 唯一的賭" if e["gamble"] else ""
        print(f"  {e['addr']:#010x}  reg 0x{e['reg']:04X}  "
              f"{e['old']:#06x} -> {e['new']:#06x}{tag}")
    for e in plan["timing"]:
        print(f"  {e['addr']:#010x}  {e['old']:#010x} -> {e['new']:#010x}   {e['note']}")
    print(f"\n  讀出 {plan['readout_ms']} ms / 一格 {plan['frame_ms']} ms "
          f"({plan['fps']} fps),餘裕 {plan['margin_ms']} ms")
    if args.json:
        args.json.write_text(json.dumps(plan, indent=1))
        print(f"  -> {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
