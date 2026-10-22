#!/usr/bin/env python3
"""OG6K over HDMI RAW —— 離線計畫產生器。

只讀韌體映像,產生寫入清單與 JSON。沒有相機、USB、記憶體後端。

設計見 `../../notes/HDMI_RAW_PATH.md`,特別是 §5c(欄位清單)與 §5d-2(介入點)。

做三件事:
  1. 在私有 RAM 建一張 448 bytes 的 HdmiRaw 格式表(27 筆原廠 + 4 筆 OG6K,
     犧牲四個 UHD*CROP —— 正好就是我們借 profile 的那四筆)
  2. 改 `FUN_c043b988` 裡載入表位址的兩道指令,指向私有表
  3. 把四個捐贈 profile 的幾何欄位改成 6064x4042

用法:
    python3 build.py              摘要
    python3 build.py --writes     完整寫入清單
    python3 build.py --json o.json
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path
from typing import Dict, List, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
FIRMWARE = ROOT / "out" / "MAIN_c0000000.bin"
PROFILES = (ROOT / "research/other/external/FP3K-technical-handoff-2026-09-10"
            / "analysis/firmware/raw-profiles.json")
B = 0xC0000000

# ---------------------------------------------------------------- 原廠結構
HDMIRAW_TABLE = 0xC0BE5450
HDMIRAW_SPAN = 0x1C0                 # 搜尋器 FUN_c043ce18 寫死的長度
HDMIRAW_SEARCH = 0xC043CE18
ENTRIES = HDMIRAW_SPAN // 16         # 28

# 載入表位址的兩道指令(ARM)。原廠值用來驗證我們沒挑錯位址。
SITE_MOVW = 0xC043BAA0
SITE_MOVT = 0xC043BAA8
STOCK_MOVW = 0xE3051450              # movw r1, #0x5450
STOCK_MOVT = 0xE34C10BE              # movt r1, #0xC0BE

# ---------------------------------------------------------------- 私有落點
# OG3K/OG2K 佔 0xC0730700..0xC0732AFF;raw14 探針保留 0xC0734000。
PRIV_TABLE = 0xC0733000              # 448 bytes
PRIV_STR = 0xC07331C0                # 鍵字串
PRIV_END = 0xC0733400

RESIDENTS: List[Tuple[int, int, str]] = [
    (0xC072E064, 0xC072EFAC, "gyro logger"),
    (0xC072F800, 0xC0730000, "USB shell template"),
    (0xC0730700, 0xC0732B00, "OG3K / OG2K"),
    (0xC0734000, 0xC0734900, "raw14 探針"),
]

# ---------------------------------------------------------------- OG6K 定義
REC = (6064, 4042)                   # rec / active / 生產者 / 感測器輸入
PREV_GRID = (2016, 1344)             # ÷3 的全 3:2 預覽
PREV_VIS = (2000, 1334)
RWZM_UNITY = 1023                    # 原廠慣用的 unity(見筆記 §5b)
MODE = 3                             # M3 MONIT1_30
CONST = 3                            # HdmiRaw 那一族是 3,不是 CDNG 的 5

# 每個格率借對應的 UHD*CROP,連 +0x030 標稱 fps 都已經是對的。
RATES = [("OG6K23_98", 0x180, "UHD23_98CROP"),
         ("OG6K24",    0x1BE, "UHD24CROP"),
         ("OG6K25",    0x17E, "UHD25CROP"),
         ("OG6K30",    0x171, "UHD30CROP")]

# §5c 的欄位清單。值不隨格率變,四個 profile 共用。
FIELD_EDITS: Dict[int, int] = {
    0x000: REC[0], 0x004: REC[1],        # rec
    0x024: REC[0], 0x02C: REC[1],        # active(HdmiRaw 的 act == rec)
    0x0DC: REC[0], 0x0E4: REC[1],        # 生產者
    0x0F4: REC[0], 0x0F8: REC[1],        # 感測器輸入
    0x00C: PREV_GRID[0], 0x010: PREV_GRID[1],
    0x020: PREV_VIS[0], 0x028: PREV_VIS[1],
    0x0D8: PREV_GRID[0], 0x0E0: PREV_GRID[1],
    0x060: RWZM_UNITY, 0x0D0: RWZM_UNITY,   # 預覽 RWZM -> unity
    # +0x064 / +0x0D4 (RAW 平面) 原本就是 unity,不寫。
    # +0x030 (標稱 fps) 四個捐贈者原本就對,不寫。
}


class BuildError(RuntimeError):
    pass


def movw(rd: int, imm: int) -> int:
    return 0xE3000000 | ((imm >> 12) << 16) | (rd << 12) | (imm & 0xFFF)


def movt(rd: int, imm: int) -> int:
    return 0xE3400000 | ((imm >> 12) << 16) | (rd << 12) | (imm & 0xFFF)


class Plan:
    def __init__(self) -> None:
        if not FIRMWARE.exists():
            raise BuildError(f"找不到韌體映像 {FIRMWARE}")
        self.img = FIRMWARE.read_bytes()
        d = json.loads(PROFILES.read_text())
        self.col = {c["offset"]: c["table"] for c in d["columns"]}
        self.row = {}
        for r in d["rows"]:
            for p in r["profile_ids"]:
                self.row[p] = r["index"]

    # ---------------------------------------------------------- 讀韌體
    def word(self, a: int) -> int:
        return struct.unpack_from("<I", self.img, a - B)[0]

    def field_addr(self, prof: int, off: int) -> int:
        return self.col[off] + self.row[prof] * 4

    def field(self, prof: int, off: int) -> int:
        return self.word(self.field_addr(prof, off))

    def key_of(self, entry: int) -> str:
        ptr = self.word(HDMIRAW_TABLE + entry * 16 + 12)
        raw = self.img[ptr - B:ptr - B + 32]
        end = raw.find(b"\x00")
        return raw[:end if end > 0 else 32].decode("ascii", "replace")

    # ---------------------------------------------------------- 靜態檢查
    def check_sites(self) -> None:
        for addr, stock, what in ((SITE_MOVW, STOCK_MOVW, "movw"),
                                  (SITE_MOVT, STOCK_MOVT, "movt")):
            got = self.word(addr)
            if got != stock:
                raise BuildError(
                    f"{addr:#010x} 是 {got:#010x},預期原廠 {stock:#010x}"
                    f"({what} r1)。介入點或韌體變了,不產生計畫。")
        # 原廠那兩道指令必須真的組出 HdmiRaw 表的位址
        got = ((STOCK_MOVT & 0xF0000) >> 4 | (STOCK_MOVT & 0xFFF)) << 16
        got |= (STOCK_MOVW & 0xF0000) >> 4 | (STOCK_MOVW & 0xFFF)
        if got != HDMIRAW_TABLE:
            raise BuildError(f"原廠兩道指令組出 {got:#010x},不是 {HDMIRAW_TABLE:#010x}")

    def check_layout(self) -> None:
        for lo, hi, who in RESIDENTS:
            if PRIV_TABLE < hi and lo < PRIV_END:
                raise BuildError(
                    f"私有區 [{PRIV_TABLE:#010x},{PRIV_END:#010x}) 撞到 {who}")
        if PRIV_STR < PRIV_TABLE + HDMIRAW_SPAN:
            raise BuildError("字串區和表重疊")
        if PRIV_STR + 0x40 > PRIV_END:
            raise BuildError("字串區超出私有段")

    def check_donors(self) -> None:
        """四個捐贈者必須只差標稱 fps —— 否則共用一組欄位修改就不成立。"""
        base = RATES[0][1]
        offs = sorted(self.col)
        for _key, prof, name in RATES[1:]:
            diff = [o for o in offs if self.field(prof, o) != self.field(base, o)]
            if diff != [] and diff != [0x030]:
                raise BuildError(
                    f"p{prof:X} ({name}) 與 p{base:X} 差的不只 +0x030:"
                    + " ".join(f"+0x{o:03X}" for o in diff))
        # 平面格式與感測器縮減必須已經是 HdmiRaw 的樣子
        for _key, prof, name in RATES:
            if (self.field(prof, 0x080), self.field(prof, 0x084)) != (7, 11):
                raise BuildError(f"p{prof:X} 的平面格式不是 7/11")
            one = struct.unpack("<f", struct.pack("<I", self.field(prof, 0x0FC)))[0]
            if one != 1.0:
                raise BuildError(f"p{prof:X} 的感測器縮減不是 1.0")

    def check_table(self) -> None:
        donors = {p for _k, p, _n in RATES}
        found = {}
        for i in range(ENTRIES):
            prof = self.word(HDMIRAW_TABLE + i * 16 + 4)
            if prof in donors:
                found[prof] = i
        missing = donors - set(found)
        if missing:
            raise BuildError(
                "捐贈 profile 不在 HdmiRaw 表裡:"
                + " ".join(f"p{p:X}" for p in sorted(missing)))
        return found

    # ---------------------------------------------------------- 產生
    def build(self) -> Dict:
        self.check_sites()
        self.check_layout()
        self.check_donors()
        slots = self.check_table()

        # 字串區
        strings: Dict[str, int] = {}
        cur = PRIV_STR
        for key, _p, _n in RATES:
            strings[key] = cur
            cur += (len(key) + 4) & ~3
        if cur > PRIV_END:
            raise BuildError("字串放不下")

        # 私有表 = 原廠 28 筆,四筆換掉
        table = bytearray(self.img[HDMIRAW_TABLE - B:HDMIRAW_TABLE - B + HDMIRAW_SPAN])
        if len(table) != HDMIRAW_SPAN:
            raise BuildError("讀出的表長度不對")
        replaced = []
        for key, prof, name in RATES:
            i = slots[prof]
            struct.pack_into("<IIII", table, i * 16, CONST, prof, MODE, strings[key])
            replaced.append((i, name, key))

        writes: List[Tuple[int, int, str]] = []
        for i in range(0, HDMIRAW_SPAN, 4):
            writes.append((PRIV_TABLE + i,
                           struct.unpack_from("<I", table, i)[0],
                           "HdmiRaw 私有表"))
        for key, _p, _n in RATES:
            data = key.encode() + b"\x00" * (((len(key) + 4) & ~3) - len(key))
            for j in range(0, len(data), 4):
                writes.append((strings[key] + j,
                               struct.unpack_from("<I", data, j)[0],
                               f"鍵字串 {key}"))
        writes.append((SITE_MOVW, movw(1, PRIV_TABLE & 0xFFFF), "改導:movw r1"))
        writes.append((SITE_MOVT, movt(1, PRIV_TABLE >> 16), "改導:movt r1"))
        for key, prof, _n in RATES:
            for off, val in sorted(FIELD_EDITS.items()):
                a = self.field_addr(prof, off)
                if self.word(a) != val:
                    writes.append((a, val, f"p{prof:X} +0x{off:03X} ({key})"))

        return {
            "table": PRIV_TABLE, "strings": PRIV_STR,
            "replaced": replaced,
            "writes": [[a, v, w] for a, v, w in writes],
            "write_count": len(writes),
            "code_writes": 2,
        }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--writes", action="store_true")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args(argv)
    try:
        plan = Plan().build()
    except BuildError as exc:
        print(f"★ 拒絕產生:{exc}")
        return 2
    print(f"私有表 {plan['table']:#010x}  字串 {plan['strings']:#010x}")
    print("換掉的四筆:")
    for i, name, key in plan["replaced"]:
        print(f"   [{i:2d}] {name:<14} -> {key}")
    print(f"\n共 {plan['write_count']} 筆寫入(其中 {plan['code_writes']} 筆是程式碼)")
    if args.writes:
        for a, v, w in plan["writes"]:
            print(f"   {a:#010x} = {v:#010x}   {w}")
    if args.json:
        args.json.write_text(json.dumps(plan, indent=1))
        print(f"-> {args.json}")
    print("★ 靜態檢查通過")
    return 0


if __name__ == "__main__":
    sys.exit(main())
