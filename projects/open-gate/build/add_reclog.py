#!/usr/bin/env python3
"""在 AutoRun 前段插入 `rec log-on`,讓錄影 log 以檔案形式落在媒體上。

為什麼要插在前段:快載入的 store bootstrap 命中之後會**停掉腳本**,
所以加在結尾的指令在快卡上永遠不會執行。插在 store bootstrap 之前。

★ 2026-09-20 反組譯更正:先前用的是 `rec log-sim`,**那個指令不會寫檔**。
六個子指令的真正語意(0xC04073C8 起,旗標區 0xC3757F08):

    log-on    strb #1,[0xC3757F08]          結束時寫檔     ← 這個才對
    log-uart  [+0x0C] = 0xC0407368, [+4]=r0 結束時吐 UART
    log-sim   [+0x08] = 0xC0407368, [+4]=r0 錄影中逐筆吐 UART
    log-off   清掉上面三個
    log-out   當場把緩衝吐到 r0(UART),不設旗標
    log-file  當場把緩衝寫成檔案,不設旗標

結束時的處理在 FUN_c06b03A0:`if (byte 0xC38D05BC) 寫檔;if (+0x0C) 吐 UART`。
只有 `log-on` 會把那個 byte 設成 1,所以只有它會產生檔案。

而且 log-sim / log-uart / log-out 都會把**下指令當下的 shell 輸出控制代碼**
(r0)存起來,之後每一筆 log 都呼叫它。從 AutoRun 下這些指令,存的是開機
腳本的控制代碼 —— 錄影時早就失效了。`log-on` 完全不碰 r0,所以只有它
適合寫進 AutoRun。

檔名:CinemaDNG 走 FUN_c03A5858,把 WAV 路徑的副檔名換成 `.txt`
(拿不到就退回媒體根目錄的 `\\cine_log.txt`);MOV 走 FUN_c06B4D10,
預設 `\\mov_log.txt`。檔案落在**錄影當下的那個 slot**。

    ./add_reclog.py <AutoRun.txt> [模式]
        模式預設 log-on。給 log-sim / log-uart / log-out 會被擋下來
        —— 它們在 AutoRun 裡沒有意義,要強迫寫入請加 --force。
"""
import sys, pathlib

argv = [a for a in sys.argv[1:] if a != "--force"]
force = "--force" in sys.argv
path = pathlib.Path(argv[0])
mode = argv[1] if len(argv) > 1 else "log-on"

STALE_CTX = {"log-sim", "log-uart", "log-out"}
if mode in STALE_CTX and not force:
    raise SystemExit(
        f"`rec {mode}` 存的是下指令當下的 shell 輸出控制代碼,從 AutoRun 下\n"
        f"它存的是開機腳本的,錄影時已失效;而且它**不會寫檔**。\n"
        f"要檔案請用 `log-on`。確定要照舊的話加 --force。")
if mode not in STALE_CTX | {"log-on", "log-file", "log-off"}:
    raise SystemExit(f"{mode!r} 不是 rec 的子指令")

lines = path.read_text().splitlines(True)

marker = "# --- store bootstrap"
idx = next((i for i, l in enumerate(lines) if l.startswith(marker)), None)
if idx is None:
    raise SystemExit("找不到 store bootstrap 標記 —— 這張卡不是快載入版?")

block = [
    "\n",
    "# --- 錄影 log 導到檔案(診斷用)-------------------------------------------\n",
    "# 接 SSD 錄影時相機的 USB-C 被佔用,拿不到 shell,`rec log-out` 讀不到。\n",
    "# `log-on` 讓每段錄影**結束時**把 log 寫成檔案(檔名 = WAV 路徑換成 .txt),\n",
    "# 事後把媒體插回電腦就讀得到 req_cnt / fin_cnt 與媒體參數那一行。\n",
    "# 注意:是「結束時」—— 錄影凍住沒結束的話,檔案不會產生。\n",
    "# 必須插在 store bootstrap **之前** —— 快載入命中後會停掉腳本。\n",
    f"rec {mode}\n",
    "\n",
]
lines[idx:idx] = block
path.write_text("".join(lines))
print(f"已在第 {idx} 行前插入 `rec {mode}`;新長度 {len(lines)} 行")
