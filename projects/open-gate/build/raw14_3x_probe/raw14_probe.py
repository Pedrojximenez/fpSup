#!/usr/bin/env python3
"""RAW14 ÷3 bounded probe —— 離線產生器與靜態驗證器。

這支程式沒有相機、USB、序列埠或活記憶體後端。它組譯負載、跑靜態檢查、
輸出 JSON 計畫。三個 hook 位址沒有全部綁定之前,它拒絕輸出任何可執行負載;
把未定義的感測器 selector 寫進計畫還需要另一道明確同意。

設計見 PROBE_DESIGN.md。
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent

# --------------------------------------------------------------- RAM 區域地圖
# 已知常駐者。探針必須完全避開。來源:
#   .claude/skills/fp-camera-control(shell 模板、gyro、rowpatch)
#   ../og3k_plan.py(OG3K/OG2K 的整個配置)
RESIDENTS: List[Tuple[int, int, str]] = [
    (0xC072E064, 0xC072EFAC, "gyro logger"),
    (0xC072F800, 0xC0730000, "USB shell template / getfile / putfile"),
    (0xC072F800, 0xC072F8E8, "open gate rowpatch"),
    (0xC0730700, 0xC0732AFF, "OG3K / OG2K payload+state 區塊"),
]

# 探針自己的區段。刻意放在 OG 區塊之上,留一整個 4K 的距離。
PROBE_BASE = 0xC0734000
PROBE_CODE = PROBE_BASE + 0x000          # 負載
PROBE_CODE_MAX = 0x400                   # 1 KB 上限
PROBE_STATE = PROBE_BASE + 0x800         # 狀態區(前面 4 bytes 是 redzone lo)
PROBE_STATE_LEN = 0x48

MAGIC = 0x52313450                       # 'R14P'
RZ_LO = 0x5A5AA5A5
RZ_HI = 0xA5A55A5A

# --------------------------------------------------------------- selector 表
# 70 個模式裡 reg 0x0001 的完整分布,與 (位深, 縮減) 完美一對一。
SELECTOR_KNOWN: Dict[int, Tuple[str, str, int]] = {
    0x29: ("RAW14", "1/1", 8),
    0x2A: ("RAW12", "1/1", 15),
    0x2F: ("RAW12", "3/3", 8),
    0x30: ("RAW12", "3/6", 3),
    0x39: ("RAW12", "2/2", 36),
}
# 候選:未被任何模式使用,且符合「RAW14 比同縮減的 RAW12 少 1」。
# 該規則只有一個觀測對(0x29/0x2A)支撐 —— 這是探測,不是計畫。
SELECTOR_CANDIDATE = 0x2E

STAGES = ("stock_nominal", "stock_timeout", "candidate_dry", "candidate_live")

# ------------------------------------------------------------------ 已解閘門
# 微秒計時器。不是位址,是**函式** —— 回傳 µs。
# 證據:fpSup/gyro/phase_probe.S 以 TICK_US 之名在四處呼叫它;
# 反編譯 FUN_c002b6e0 確認它把 64-bit 計數換算成微秒。
KNOWN_TICK_US = 0xC002B6E0

# 通用檔案寫入 FUN_c03660e8(file_object, buffer, length)。
# 掛在**第一道指令**,所以進來時 prologue 還沒跑、lr 還是呼叫端的。
# 回傳 0 = 失敗、非 0 = 成功(blk_c03.c:21560 與 85823 兩個呼叫端都這樣判斷)。
# 錄影的每一格 CinemaDNG 都是一次 >=1 MB 的寫入,所以這一個掛鉤同時是
# 閘門和畫格偵測 —— 原本的 HOOK_WRITER / HOOK_FRAME 兩個閘門合併成這個。
KNOWN_F_WRITE = 0xC03660E8
KNOWN_F_WRITE_BODY = KNOWN_F_WRITE + 4

# 被位移的那道指令。負載裡是手寫的 `stmfd sp!, {r4,r5,r6,r7,lr}`,
# 必須和韌體實際內容逐位元相符,否則 trampoline 會執行錯的東西。
DISPLACED_EXPECTED = 0xE92D40F0

FIRMWARE = Path("/Users/dido/Developer.localized/SIGMAfp_re/out/MAIN_c0000000.bin")
ROM_BASE = 0xC0000000


class GateError(RuntimeError):
    """未解的閘門。產生器絕不在閘門沒滿足時輸出負載。"""


@dataclass
class Hooks:
    """必須由主要證據綁定的位址。None = 未解。

    2026-09-16:writer 與 frame 合併成單一的 f_write 掛鉤,三個閘門全部解開。
    """

    f_write: Optional[int] = KNOWN_F_WRITE
    tick: Optional[int] = KNOWN_TICK_US

    def unresolved(self) -> List[str]:
        return [n for n in ("f_write", "tick") if getattr(self, n) is None]


@dataclass
class Plan:
    stage: str
    hooks: Hooks
    selector: Optional[int] = None
    arm_ms: int = 8000
    notes: List[str] = field(default_factory=list)

    # ------------------------------------------------------------- 靜態檢查
    def check_stage(self) -> None:
        if self.stage not in STAGES:
            raise GateError(f"未知階段 {self.stage!r};可用:{', '.join(STAGES)}")

    def check_hooks(self) -> None:
        missing = self.hooks.unresolved()
        if missing:
            raise GateError(
                "hook 未綁定:" + ", ".join(missing)
                + " —— 見 PROBE_DESIGN.md §5。產生器不輸出未綁定的負載。"
            )

    def check_selector(self, allow_undefined: bool) -> None:
        if self.stage != "candidate_live":
            if self.selector is not None:
                raise GateError(
                    f"階段 {self.stage} 不得攜帶 selector;"
                    "只有 candidate_live 會寫 reg 0x0001。"
                )
            return
        if self.selector is None:
            raise GateError("candidate_live 必須指定 selector")
        if self.selector in SELECTOR_KNOWN:
            depth, scale, _ = SELECTOR_KNOWN[self.selector]
            raise GateError(
                f"0x{self.selector:02X} 是已知的 {depth} {scale} —— "
                "拿已知索引冒充 RAW14 3/3 會讓感測器與下游配置不一致,禁止。"
            )
        if not allow_undefined:
            raise GateError(
                f"0x{self.selector:02X} 在 70 個模式裡未定義。"
                "要把它寫進計畫需要 --allow-undefined-selector,"
                "而且那是賭 sensor silicon 裡存在這個 drive mode。"
            )

    def check_layout(self) -> List[str]:
        """探針區段不得與任何已知常駐者重疊。"""
        problems = []
        spans = [
            (PROBE_CODE, PROBE_CODE + PROBE_CODE_MAX, "probe code"),
            (PROBE_STATE - 4, PROBE_STATE + PROBE_STATE_LEN, "probe state+redzone"),
        ]
        for lo, hi, what in spans:
            for rlo, rhi, who in RESIDENTS:
                if lo < rhi and rlo < hi:
                    problems.append(
                        f"{what} [{lo:#010x},{hi:#010x}) 撞到 {who} "
                        f"[{rlo:#010x},{rhi:#010x})"
                    )
        return problems

    def check_ladder(self) -> None:
        """階梯順序是硬性的:不得跳階。"""
        idx = STAGES.index(self.stage)
        if idx >= 2:
            note = (
                f"階段 {self.stage} 需要 {STAGES[idx - 1]} 已經通過的實測證據;"
                "本產生器不持有實測結果,由操作者負責。"
            )
            if note not in self.notes:       # build() 失敗後 dry_run() 會再呼叫一次
                self.notes.append(note)

    # ------------------------------------------------------------- 組譯
    def defines(self) -> List[str]:
        d = [f"STATE={PROBE_STATE:#x}"]
        if self.hooks.f_write is not None:
            d.append(f"F_WRITE={self.hooks.f_write:#x}")
            d.append(f"F_WRITE_BODY={self.hooks.f_write + 4:#x}")
        if self.hooks.tick is not None:
            d.append(f"TICK_US={self.hooks.tick:#x}")
        return d

    @staticmethod
    def dng_min() -> int:
        """負載裡的 DNG_MIN。一格 CinemaDNG 最小 1 MB;
        OG2K 12-bit 是 4.06 MB,RAW14 16-bit 容器是 5.42 MB。"""
        return 0x00100000

    def check_displaced(self) -> None:
        """負載裡手寫的位移指令必須和韌體逐位元相符。"""
        if self.hooks.f_write is None:
            return
        if not FIRMWARE.exists():
            raise GateError(f"找不到韌體映像 {FIRMWARE},無法驗證位移指令")
        with FIRMWARE.open("rb") as fh:
            fh.seek(self.hooks.f_write - ROM_BASE)
            word = int.from_bytes(fh.read(4), "little")
        if word != DISPLACED_EXPECTED:
            raise GateError(
                f"{self.hooks.f_write:#010x} 是 {word:#010x},"
                f"負載假設的是 {DISPLACED_EXPECTED:#010x}"
                "(stmfd sp!, {r4,r5,r6,r7,lr})。掛鉤點或韌體變了,不得產生負載。"
            )

    @staticmethod
    def _tool(kind: str) -> Optional[str]:
        """工具鏈可能叫 arm-none-eabi-* 或 arm-linux-gnueabihf-*,
        也可能只裝在 Homebrew 的 keg 裡。三種都找。"""
        names = [f"arm-none-eabi-{kind}", f"arm-linux-gnueabihf-{kind}"]
        for name in names:
            found = shutil.which(name)
            if found:
                return found
        for prefix in ("/opt/homebrew/bin", "/usr/local/bin"):
            for name in names:
                cand = Path(prefix) / name
                if cand.exists():
                    return str(cand)
        return None

    def assemble(self, source: Path) -> bytes:
        As = self._tool("as")
        ld = self._tool("ld")
        objcopy = self._tool("objcopy")
        if not As or not ld or not objcopy:
            raise GateError(
                "找不到 ARM 工具鏈(as/ld/objcopy)。這不影響閘門檢查 —— "
                "hook 綁定之前本來就不會走到組譯。"
            )
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            obj, elf, binf = tmp / "p.o", tmp / "p.elf", tmp / "p.bin"
            cmd = [As, "-march=armv7-a", "-o", str(obj)]
            for d in self.defines():
                cmd += ["--defsym", d]
            cmd.append(str(source))
            subprocess.run(cmd, check=True, capture_output=True)
            subprocess.run(
                [ld, "-Ttext", f"{PROBE_CODE:#x}", "-o", str(elf), str(obj)],
                check=True, capture_output=True,
            )
            subprocess.run(
                [objcopy, "-O", "binary", str(elf), str(binf)],
                check=True, capture_output=True,
            )
            return binf.read_bytes()

    # ------------------------------------------------------------- 產出
    def build(self, source: Path, allow_undefined: bool = False) -> Dict:
        self.check_stage()
        self.check_ladder()
        self.check_selector(allow_undefined)
        self.check_displaced()
        layout = self.check_layout()
        if layout:
            raise GateError("區段衝突:\n  " + "\n  ".join(layout))
        self.check_hooks()

        payload = self.assemble(source)
        if len(payload) > PROBE_CODE_MAX:
            raise GateError(
                f"負載 {len(payload)} bytes 超過區段上限 {PROBE_CODE_MAX}"
            )
        return {
            "stage": self.stage,
            "base": PROBE_CODE,
            "state": PROBE_STATE,
            "payload_len": len(payload),
            "payload_sha256": __import__("hashlib").sha256(payload).hexdigest(),
            "hooks": {
                "f_write": self.hooks.f_write,
                "f_write_body": self.hooks.f_write + 4,
                "tick_us": self.hooks.tick,
            },
            "selector": self.selector,
            "arm_ms": self.arm_ms,
            "writes_to_card": False,
            "allocates_memory": False,
            "notes": self.notes,
        }

    def dry_run(self) -> Dict:
        """不組譯,只回報閘門狀態 —— hook 沒綁定時唯一能做的事。"""
        self.check_stage()
        self.check_ladder()
        layout = self.check_layout()
        return {
            "stage": self.stage,
            "executable": False,
            "unresolved_hooks": self.hooks.unresolved(),
            "layout_problems": layout,
            "selector_known": {
                f"0x{v:02X}": f"{d} {s} (n={n})"
                for v, (d, s, n) in sorted(SELECTOR_KNOWN.items())
            },
            "selector_candidate": f"0x{SELECTOR_CANDIDATE:02X}",
            "notes": self.notes,
        }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", default="stock_nominal", choices=STAGES)
    ap.add_argument("--f-write", type=lambda s: int(s, 0), default=KNOWN_F_WRITE)
    ap.add_argument("--tick", type=lambda s: int(s, 0), default=KNOWN_TICK_US)
    ap.add_argument("--selector", type=lambda s: int(s, 0))
    ap.add_argument("--arm-ms", type=int, default=8000)
    ap.add_argument("--allow-undefined-selector", action="store_true")
    ap.add_argument("--source", type=Path, default=HERE / "raw14_probe.S")
    args = ap.parse_args(argv)

    plan = Plan(
        stage=args.stage,
        hooks=Hooks(args.f_write, args.tick),
        selector=args.selector,
        arm_ms=args.arm_ms,
    )
    try:
        out = plan.build(args.source, args.allow_undefined_selector)
    except GateError as exc:
        out = plan.dry_run()
        out["gate_error"] = str(exc)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 2
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
