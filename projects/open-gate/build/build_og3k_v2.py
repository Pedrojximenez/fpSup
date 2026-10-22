#!/usr/bin/env python3
"""產生出貨版的 OG3K AutoRun —— 獨立、不含開發用的 USB shell。

寫入計畫來自 og3k_plan(載入器用的是同一份),所以 USB 開發與 AutoRun 不會分歧。
計畫已逐字比對過執行中的相機:447 筆程式碼/表格/hook 完全一致,其餘 9 筆是
開機時本來就該歸零的執行期計數器。

    ./build_og3k_v2.py            產生 og3k_v2/AutoRun.txt
    ./build_og3k_v2.py --dry      只印統計
"""
import hashlib, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from og3k_plan import Plan, PAYLOADS, HOOKS, FMT, PREV, NEW_CSV

OUT = HERE / "og3k_v2"
PAD_TO = 32_768
# AutoRun 解譯器會丟掉尾端超過某個數量的指令。實機量過:648 條全跑完,
# 697 條掉了最後十幾條。註解與空行不計。留 80 條餘裕。
CMD_LIMIT = 648
CMD_BUDGET = 560

HEAD = """\
# ============================================================================
# OG3K — SIGMA fp 3:2 open gate, 3032x2012 record / 3000x2000 DNG crop
# ============================================================================
#
# 韌體 Ver.5.02 專用,沒有執行期版本守衛。全部是冷開機的 RAM 補丁:
# 把 AutoRun.txt 移除或改名,然後完整斷電重開,就回到原廠。
#
# 選單:MENU → 紀錄設定 → 解析度,以及 QS → RES.,都會多出第三列 OG3K。
# 原廠的 UHD 與 FHD 兩列完全保留,三者可任意順序切換。
#
# 八個格率(全部用原廠自己的時序,0 ppm 誤差):
#   23.976 24 25 29.97 48 50 59.94  → 感測器 mode 98(安靜類比組)
#   100                             → 感測器 mode 117
#
# 做法不是改感測器模式表,而是一張格式表加一個 picker hook —— 要加模式只要
# 加一筆,不必再動韌體的表。
#
# 已知缺陷:錄影時 live view 右側會有一條細空隙,空隙裡是前一幀的殘影。
# 待機與半按都正常。成因是錄影開始後有一段 latch 的版面會重新以左上角對齊,
# 那段程式還沒找到;可見尺寸用 -4% 補償把空隙壓到最小。
# 錄下來的檔案不受影響。詳見 notes/LIVE_VIEW_DISPLAY_CHAIN.md。
# ============================================================================
"""


def bar(pct):
    n = round(pct / 12.5)
    return f"fpSup[{'#' * n}{'.' * (8 - n)}]{pct:03d}"


def main():
    p = Plan()
    bad = p.check()
    if bad:
        for b in bad:
            print("  " + b)
        raise SystemExit("靜態檢查失敗,不產生 AutoRun")
    if getattr(p, "trial", None):
        f = ", ".join(f"+0x{o:03X}={v}" for o, v in sorted(p.trial.items()))
        raise SystemExit(f"rowpatch 含試驗中的預覽欄位({f})。\n"
                         f"先用 ./og3k_load.py 測、錄一段並解 DNG 確認錄影無損,\n"
                         f"再把它們移進 og3k_plan.VERIFIED 才能建置 AutoRun。")
    items = list(p.all())

    L = [HEAD, "# --- 螢幕 ---------------------------------------------------------------",
         "display monitor 0 1", "display osd 1 0x00000000", "display osd 1 0x00000000"]

    def progress(pct):
        for _ in range(2):
            L.append(f"display text {bar(pct)}")
            L.append("display osd 1")

    progress(0)
    step = max(1, len(items) // 8)
    note = None
    for i, (a, v, nt) in enumerate(items):
        if nt != note:
            L.append(f"# {nt}")
            note = nt
        L.append(f"mem set 0x{a:08X} 0x{v:08X}")
        if (i + 1) % step == 0 and (i + 1) < len(items):
            progress(min(87, round((i + 1) / len(items) * 100 / 12.5) * 12))
    progress(100)
    for _ in range(3):
        L.append("display text OG3K!")
        L.append("display osd 1")

    text = "\n".join(L) + "\n"
    cmds = [l for l in text.splitlines()
            if l.strip() and not l.lstrip().startswith("#")]
    print(f"  寫入 {len(items)} 筆   指令 {len(cmds)} 條   上限 {CMD_LIMIT}")
    if len(cmds) > CMD_BUDGET:
        raise SystemExit(f"指令數 {len(cmds)} 超過預算 {CMD_BUDGET}")

    pad = "# pad: 固定大小,避免非截斷式覆寫留下舊指令\n"
    while len(text.encode()) + len(pad.encode()) <= PAD_TO - 56:
        text += pad
    text += "#" * 54 + "\n"

    if "--dry" in sys.argv:
        print("  (--dry,未寫出)")
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "AutoRun.txt").write_text(text, encoding="utf-8")
    sha = hashlib.sha256(text.encode()).hexdigest()

    man = [f"SIGMA fp OG3K — 3:2 open gate 3032x2012,選單第三列,八個格率",
           "",
           f"AutoRun.txt bytes={len(text.encode())} sha256={sha}",
           f"reference_firmware sha256={p.sha}",
           f"writes={len(items)} commands={len(cmds)} limit={CMD_LIMIT}",
           ""]
    man.append("payloads:")
    for name, _, base in PAYLOADS:
        b = p.blobs[name]
        man.append(f"  {name:<15} {len(b):>4}B @0x{base:08X} "
                   f"sha256={hashlib.sha256(b).hexdigest()[:16]}")
    man.append("")
    man.append("hooks (最後才武裝):")
    for site, code, stock, kind, nm in HOOKS:
        man.append(f"  0x{site:08X} {kind:<2} → 0x{code:08X}  原廠 0x{stock:08X}  {nm}")
    man.append("")
    man.append("格率 → 感測器模式 / 時序來源:")
    for key, donor, src, slot in FMT:
        hm, tl, vm, x = p.timing(src)
        if key == "OG3K100":          # 與 og3k_plan 裡的覆寫保持一致
            hm, tl, vm = 330, 270, 2182
        fps = 72e6 / (hm * (vm - 1) + tl)
        roll = hm * 2012 / 72e6 * 1000
        man.append(f"  {key:<10} mode {donor:<4} 時序抄自 mode {src:<4} "
                   f"hmax {hm} vmax {vm} → {fps:.3f} fps  捲簾 {roll:.2f} ms")
    man.append("")
    man.append(f"預覽 profile(跟著旗標切換 PARAM+0x28):{', '.join(hex(a) for a in PREV)}")
    man.append(f"選單 CSV:{len(NEW_CSV)} bytes")
    man.append("")
    man.append("已知缺陷:錄影時 live view 右側一條細空隙(殘影)。錄影檔案不受影響。")
    man.append("還原:移除或改名 AutoRun.txt,然後完整斷電重開。")
    (OUT / "MANIFEST.txt").write_text("\n".join(man) + "\n", encoding="utf-8")

    print(f"  → {OUT/'AutoRun.txt'}  {len(text.encode())} bytes")
    print(f"     sha256 {sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
