#!/usr/bin/env python3
"""ogstate — 一次把「選單以為的」與「相機真的解析到的」並排印出來。

這支工具只讀,不寫。它存在的理由是三個現場回報:
  1. 突然跳回其他格式    2. 未知原因凍結    3. 開機沒等 AutoRun 就錄影必凍結

狀態由**兩個互相獨立的真相來源**決定,而沒有任何東西保證它們一致:

    FLAG   (0xC0731C08)  只有 og3ksel(解析度 setter)寫。= 「選單選了 OG」
    HITS   (0xC0730700)  只有 fmttable 的 hit 寫。       = 「picker 解析到 OG」

消費端也分成兩派,沒有一派同時看兩個:

    og3kcanvas 錄影 case          profile 相符 **且** FLAG==1
    og3kout / aspect / fps / gs   **只看 FLAG**
    fmttable 的 hit               **只比對鍵**

2026-09-21 上機之後,危險的組合已經縮到一個(見
notes/FLAG_AND_PICKER_DISAGREE.md §10):

    **FLAG==1 而錄影格式不是 CinemaDNG** —— MOV 不走 picker,所以有 profile
    守衛的兩個 hook 全部不動作,只看 FLAG 的那一組卻全開著,H.264 編碼器
    拿到給 3:2 CinemaDNG 準備的輸出描述子 -> 按錄影**硬凍結**,實測確認。

反過來的 FLAG==0 是安全的:`og3kname` 也是 FLAG 守衛的,所以鍵根本組不出來,
整條路乾淨退回 FHD(實測 file-size 3,244,544)。它不會凍,但**會安靜地錄成
別的格式**。

注意 HITS 是**累計值**,不是狀態。單看它大於零只代表這次開機曾經解析到過
OG,不代表現在是。要判斷「現在」必須看增量,或看錄影格式。

用法(相機接 USB、shell 已起來):
    OG_TARGET=og3k ./ogstate.py          印一次
    OG_TARGET=og2k ./ogstate.py --watch  每秒印一次,按 Ctrl-C 停

**凍結之後不要立刻斷電。** SD 卡上的凍結只停住寫入端,shell 有機會還活著
(見 notes/HSW_240FPS_MODE12.md §52.4)。但 §10 那條 MOV 凍結會把 shell
一起帶走,實測拿不到現場,只能斷電。
"""
from __future__ import annotations

import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent.parent / "fpSup" / "fp_usb_shell"))
from putfile import mem_get, sh                                      # noqa: E402
from og3k_plan import (BITLATCH, DONOR_TIMING_ADDR, FLAG, GS_LOG, HITS,
                       LOG, OHITS, OREJ, OG_PROFILE, PBFLAG, ROW_LOG, T,
                       TARGET)                                    # noqa: E402

BITS = {0: "12-bit", 3: "10-bit", 4: "8-bit"}


def rd(address: int, tries: int = 8) -> int | None:
    for _ in range(tries):
        words = mem_get(address)
        if words and words[0] is not None:
            return words[0]
    return None


def timing_name(w0: int | None, w1: int | None) -> str:
    """把 donor 時序記錄的兩個字解回 hmax/tail/vmax,並說它是不是原廠值。

    fmttable 命中時寫 +0x04 = hmax | tail<<16、+0x08 = vmax | x<<16。
    原廠值來自目標定義的 mode_stock,所以「不是原廠」就代表 picker 命中過。
    """
    if w0 is None or w1 is None:
        return "讀不到"
    hmax, tail = w0 & 0xFFFF, w0 >> 16
    vmax, x = w1 & 0xFFFF, w1 >> 16
    shape = f"hmax {hmax} tail {tail} vmax {vmax} x {x}"
    if (w0, w1) == tuple(T["mode_stock"]):
        return f"{shape} —— 原廠(picker 沒有改過它)"
    return f"{shape} —— **非原廠**,picker 命中後留下的"


def setting(name: str) -> str:
    """讀一個選單設定。讀不到就回 '?',不讓它擋住其他判讀。"""
    try:
        return sh(f"menu {name}").strip().splitlines()[0].strip()
    except Exception:
        return "?"


def snapshot() -> dict:
    words = {name: rd(address) for name, address in (
        ("FLAG", FLAG), ("HITS", HITS), ("SEL_COUNT", LOG),
        ("SEL_LAST_ENUM", LOG + 4), ("BITLATCH", BITLATCH), ("PBFLAG", PBFLAG),
        ("CANVAS_REC", ROW_LOG), ("CANVAS_PB", ROW_LOG + 4),
        ("CANVAS_LAST_PROF", ROW_LOG + 8),
        ("OUT_HITS", OHITS), ("OUT_REJ", OREJ), ("GS_HITS", GS_LOG),
        ("TIMING_W0", DONOR_TIMING_ADDR + 4), ("TIMING_W1", DONOR_TIMING_ADDR + 8),
    )}
    words["REC_SIZE"] = setting("SetMovRecSize")
    words["REC_FORMAT"] = setting("SetMovRecFormat")
    return words


def verdict(s: dict) -> list[str]:
    flag, hits = s["FLAG"], s["HITS"]
    size, fmt = s.get("REC_SIZE", "?"), s.get("REC_FORMAT", "?")
    out = []
    if flag is None or hits is None:
        return ["讀不到 FLAG/HITS —— resident 沒裝,或 shell 掛了"]

    # 2026-09-21 實測的唯一硬凍結路徑。見 notes §10。
    if flag == 1 and fmt not in ("0", "?"):
        out.append(f"★★ 危險:FLAG=1 但錄影格式是 {fmt}(不是 CinemaDNG)。"
                   "\n   MOV 不走 picker,有 profile 守衛的 hook 全部不動作,"
                   "只看 FLAG 的那一組卻全開著。"
                   "\n   **現在按錄影會硬凍結(實測)。** 先把解析度切回 FHD/UHD,"
                   "或把錄影格式切回 CinemaDNG。")
    if flag == 0 and size == "4":
        out.append("★ 選單說解析度是 4(" + T["label"] + ")但 FLAG=0 ——"
                   "連解析度名都不會發射,所以鍵組不出來。"
                   "\n  不會凍,但**錄出來會是 FHD**,而且畫面不會告訴你。"
                   "\n  進選單重選一次解析度即可修復。")
    if flag == 1 and size not in ("4", "?"):
        out.append(f"★ 反向殘留:FLAG=1 但 SetMovRecSize 是 {size} ——"
                   "FLAG 是舊的,有人繞過解析度 setter 改了設定。")
    if s["CANVAS_LAST_PROF"] not in (None, 0) and s["CANVAS_LAST_PROF"] != OG_PROFILE:
        out.append(f"· 畫布最後看到的 profile 是 p{s['CANVAS_LAST_PROF']},"
                   f"不是 p{OG_PROFILE} —— 目前解析到的不是我們的格式。")
    if flag == 1 and s["SEL_LAST_ENUM"] not in (None, 4):
        out.append(f"· FLAG=1 但 og3ksel 最後看到的 enum 是 {s['SEL_LAST_ENUM']}"
                   "(不是 4)—— FLAG 是舊的。")
    return out or ["一致:選單、FLAG 與錄影格式三者相符。"]


def show(s: dict) -> None:
    bits = BITS.get(s["BITLATCH"], f"未知({s['BITLATCH']})")
    print(f"目標 {TARGET}  label {T['label']}  donor p{OG_PROFILE} / mode {T['mode']}")
    print(f"  選單 RecSize / 錄影格式 {s.get('REC_SIZE')} / {s.get('REC_FORMAT')}"
          "   (RecSize 4 = 本目標,格式 0 = CinemaDNG)")
    print(f"  FLAG(選單狀態)        {s['FLAG']}")
    print(f"  HITS(picker 累計命中) {s['HITS']}")
    print(f"  og3ksel  次數/最後 enum {s['SEL_COUNT']} / {s['SEL_LAST_ENUM']}")
    print(f"  畫布  錄影/回放/最後 p  {s['CANVAS_REC']} / {s['CANVAS_PB']} / {s['CANVAS_LAST_PROF']}")
    print(f"  主輸出 命中/拒絕        {s['OUT_HITS']} / {s['OUT_REJ']}")
    print(f"  增益分派 介入           {s['GS_HITS']}")
    print(f"  PBFLAG / BITLATCH      {s['PBFLAG']} / {bits}")
    w0, w1 = s["TIMING_W0"], s["TIMING_W1"]
    w0s = "????????" if w0 is None else f"{w0:08X}"
    w1s = "????????" if w1 is None else f"{w1:08X}"
    print(f"  donor 時序 @0x{DONOR_TIMING_ADDR + 4:08X}  {w0s} {w1s}"
          f"  -> {timing_name(w0, w1)}")
    for line in verdict(s):
        print("  " + line)


if __name__ == "__main__":
    if "--watch" in sys.argv:
        while True:
            show(snapshot())
            print("-" * 60)
            time.sleep(1)
    else:
        show(snapshot())
