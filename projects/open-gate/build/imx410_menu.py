#!/usr/bin/env python3
"""§8.0 的六步選單,寫成薄薄一層函式蓋在引擎上。

    ./imx410_menu.py                     走一輪預設的選擇,印出每一步
    ./imx410_menu.py --bit 12 --fps 30 --want 3840x2160
    ./imx410_menu.py --sweep             掃一整片組合,檢查每一步都答得出來

**這一層不做決策,只把引擎已有的東西排成選單的形狀。** 寫得出來就表示引擎
支援那一步;寫不出來的地方就是缺口,要補在引擎裡而不是補在這裡。

★ 補了兩個引擎缺的:
    · `mode_options()` —— `Registry.candidates()` 不能用「目標解析度」篩
    · `rwzm_auto()`   —— 沒有算「精確除數」的函式;`solve_geometry` 只在
      原廠用過的三個值裡找,那是**逆向求解器**要的,不是第 ⑥ 步要的

⚠ CG_BIN/FILL/WINDOW 仍是安裝時閘門；RWZM 已由相機端執行期判斷。
主機選單可求解不表示機上選單／條件反灰已完成；最新缺口見設計 §15。
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from imx410_block import HBIN_SET, RWZM_SET, VBIN_SET
from imx410_full import (ALIGN, ALIGN_H, ALIGN_SAFE, CLOCK, FULL_H, FULL_W,
                         RATES, RWZM_UNITY, Registry)

# 尚有安裝時閘門(CG_BIN/FILL/WINDOW)；不表示 RWZM 仍被固定。
GATES_ARE_INSTALL_TIME = True


# ---- ⓪ mode 是主軸:選了它,其他軸就跟著反灰 --------------------------------
# 2026-09-29 使用者定的模型。原本 §8.0 是精靈式的四步(bit -> fps -> mode ->
# size),現在改成**原生選單的形狀**:四個清單各自獨立,靠反灰互相約束。
#
#   mode == MODE_AUTO   哨兵「自動 / 未選」—— bit 與 fps **全開**
#   mode == 實體模式     只留該模式做得到的 bit 與 fps,其餘反灰
#
# ★ 「全開」不是近似:70 個感測器模式的合法集合**聯集起來正好等於選單全部**
#   (bit 8/10/12/14、fps 23.98..240),每一個選項都有某個模式做得到。
#   有測試釘住,哪天模式表變了會先叫。
#
# ⚠ **哨兵是 0,不是某個實體模式。** 使用者原本想用待機的 mid 8(MONIT1_60)
#   當預設,但那會自相矛盾:mid 8 是 2016x1344 3x3 **RAW12**、上限 162p 但
#   光柵限制下只到 120 —— 拿它當預設的話 14-bit 與 240 一定得反灰,
#   就不是「全開」了。`AXIS` 的 `A_MODE` 本來就是 0 = 相機自己挑 donor,
#   語意剛好,直接沿用。
#
# ⚠ **0 同時是一個實體模式的 id(mid 0 = ACQ,6064x4042 RAW14)。**
#   主機(`imx410_block.py` 的 `if axis[A_MODE] and ...`)與相機
#   (`og3krecipe.S` 的 `cmp r0,#0 / beq nomforce`)都把 0 讀成「不指定」,
#   所以 **ACQ 指定不了**。這是既有的碰撞,不是這一層引入的。
#   今天不痛 —— ACQ 的上限 19.55p 低於選單最低的 23.98,本來就選不到
#   (§4.4);但只要哪天補了更低的格率列舉,這個洞就會咬人。
#   要修的話得動 AXIS 的語意與 payload,不是改這裡。有測試釘住。
MODE_AUTO = 0

# ★ **媒體不反灰 —— 使用者 2026-09-29 決定的。**
#
# 原廠會依媒體反灰:NBU 介面腳本依媒體挑六個 `B2_5_5` 變體之一,所以 SD 卡下
# 100 / 119.88 是灰的。⚠ 2026-09-30 實機訂正:挑變體的**不是** `FUN_c04a1120`
# —— 把它 hook 成 0 反灰照舊(A/B 卡相同)。打開反灰要改變體 CSV 的 `0,0` -> `1,2`,
# 值要留得住還要正規化器 hook(skill fp-native-ui §3)。決定是**不接管這個判斷,全開**:
#
#   「有些 SD 卡很厲害啊」
#
# 撐得住這個決定的是實機證據,不是樂觀:§10 證明資料率不夠時的行為是
# **錄一下下然後乾淨停止**,不是毀檔也不是凍結。所以把它當成「使用者要不要
# 冒這個險」而不是「系統不准」是誠實的 —— 原廠那條線畫在最慢的卡上。
#
# 於是反灰的判準只剩一條原則:
#
#   反灰 = **物理上做不到**(消隱餘裕、感測器位深)
#   不灰 = 只是**風險高**(資料率、卡速)
#
# ⚠ 代價要講清楚:拿掉硬閘門之後,`burst()`「錄得到多久」從參考值變成
#   使用者事前資訊。2026-09-30 已移除 94 格保證；容量未量時不報秒數。
#   相機端的落點是 `imx410_plan.WITH_RATE_ALL_OPEN`(六個變體 CSV 全開)
#   加上 `C00A87E4` 正規化 hook(CUSTOM 下值不被壓回);兩者缺一都不算全開。
MEDIA_GATING = False

# 選單實際列出來的格率(第十列 240 已加,400 沒有列)。
MENU_RATES = ("23_98", "24", "25", "30", "48", "50", "60", "100", "120", "240")
MENU_BITS = (8, 10, 12, 14)


def mode_legal(reg: Registry, mode: int = MODE_AUTO):
    """某個 mode 底下,哪些位元深度與格率還能選。

    回傳 `(bits, rates)`,都是 `MENU_BITS` / `MENU_RATES` 的子序列。

    · 位元深度:RAW14 的感測器模式只出 14;RAW12 的走三張 picker 表,
      8 / 10 / 12 都做得到(§4.2)。
    · 格率:受**消隱餘裕**限制 —— 一行的時間是 `hmax / CLOCK`,
      光柵有 `raw[1]` 行,所以 `hmax * raw[1] < CLOCK / fps` 才塞得下(§5.1)。
    """
    if mode == MODE_AUTO:
        ms = reg.modes
    else:
        m = reg.by_id.get(mode)
        if m is None:
            raise KeyError(f"mode {mode} 不存在")
        ms = (m,)
    bits, rates = set(), set()
    for m in ms:
        bits |= {14} if m.depth == 14 else {8, 10, 12}
        rates |= {k for k in MENU_RATES
                  if m.hmax * m.raw[1] < CLOCK / RATES[k]}
    return (tuple(b for b in MENU_BITS if b in bits),
            tuple(k for k in MENU_RATES if k in rates))


def menu_enabled(reg: Registry, mode: int = MODE_AUTO):
    """反灰要寫進 CSV 的東西:每個清單的「哪幾列還能選」。

    回傳 `{"B2_5_2": (bool, ...), "B2_5_5": (bool, ...)}`,
    依 CSV 的列序(位元深度 8/10/12/14、格率 23.98..240)。
    """
    bits, rates = mode_legal(reg, mode)
    return {"B2_5_2": tuple(b in bits for b in MENU_BITS),
            "B2_5_5": tuple(k in rates for k in MENU_RATES)}


# ---- ① 位元深度 ------------------------------------------------------------
def bit_options(reg: Registry):
    """可求解的位深;usable 表示模式表可解,不表示已完成實機驗收。"""
    out = []
    for depth in (8, 10, 12, 14):
        has_mode = any(m.depth == (14 if depth == 14 else 12) for m in reg.modes)
        out.append(dict(bit=depth, usable=has_mode,
                        note="RAW14 donor 可解;增益政策與 CDNG 封裝仍待實機驗證(§4)"
                             if depth == 14 else ""))
    return out


# ---- ② 格率 ----------------------------------------------------------------
def fps_options(reg: Registry, bit: int):
    """十個選單格率,包含 240;至少有一個 mode 留有正的消隱預算。"""
    depth = 14 if bit == 14 else 12
    out = []
    for key in MENU_RATES:
        fps = RATES[key]
        n = sum(1 for m in reg.modes
                if m.depth == depth and m.hmax * m.raw[1] < CLOCK / fps)
        out.append(dict(rate=key, fps=fps, modes=n, usable=n > 0))
    return out


# ---- ④ 最終解析度 ----------------------------------------------------------
def snap_resolution(want, bit: int, raster=None):
    """把使用者打的數字吸附到合法值,並說明為什麼。

    寬是**唯一會默默弄壞**的約束(§3.1b):`FUN_c0630e90` 的每列 bytes 算術
    是整數截斷,沒對齊就是每列少搬 byte、列與列累積位移,而且沒有任何地方
    會攔。高只要偶數 —— 韌體自己遮(`& 0xfffe`,12 處),給奇數只是被改掉。
    """
    step = max(ALIGN_SAFE, ALIGN[bit])
    w, h = want
    notes = []
    if raster:
        # ★ 上界就是光柵本身 —— RWZM 只能縮不能放,所以「只能往下砍」。
        if w > raster[0] or h > raster[1]:
            notes.append(f"超出光柵 {raster[0]}x{raster[1]},夾回去"
                         f"(RWZM 只能縮不能放)")
        w, h = min(w, raster[0]), min(h, raster[1])
    w = (w // step) * step
    h = (h // ALIGN_H) * ALIGN_H
    if w != want[0]:
        notes.append(f"寬 {want[0]} -> {w}({step} 的倍數;沒對齊會默默壞掉 stride)")
    if h != want[1]:
        notes.append(f"高 {want[1]} -> {h}(偶數;韌體自己也會遮成偶數)")
    return (w, h), notes


# ---- ③ mode(光柵族)-------------------------------------------------------
def raster_options(reg: Registry, bit: int, rate: str, want=None):
    """依 ①② 列出可用的**光柵族**,不是 62 顆個別 mode。

    ★ 使用者挑的是「族」= 視野 + 捲簾 + 畫質指紋。同一族內的 mode 幾乎沒差
      (6064x3412 那四顆捲簾差 1%、指紋全同),而且**具體哪一顆交給相機自己的
      donor 排序** —— `A_MODE` 留 0,2026-09-29 上機驗過相機會自己挑出
      mode 102 / mode 7(§12.29)。

    `max_size` 就是光柵本身:RWZM 只能縮不能放(下夾 1024),所以第 ④ 步的
    上界是**一個單純的矩形**。`want` 給了就順便篩掉放不下的(給驗證用)。
    """
    depth = 14 if bit == 14 else 12
    fps = RATES[rate]
    fam = {}
    for m in reg.modes:
        if m.depth != depth or m.hmax * m.raw[1] >= CLOCK / fps:
            continue
        if want and (m.raw[0] < want[0] or m.raw[1] < want[1]):
            continue                      # 放大做不到
        fam.setdefault((m.raw, m.scale), []).append(m)
    out = []
    for (raw, scale), ms in fam.items():
        cov = (raw[0] * scale[0], raw[1] * scale[1])
        roll = [m.rolling_us for m in ms]
        row = dict(raw=raw, scale=scale, coverage=cov, max_size=raw,
                   cover_x=cov[0] / FULL_W, cover_y=cov[1] / FULL_H,
                   rolling_us=(min(roll), max(roll)),
                   fingerprint=sorted({m.fingerprint for m in ms}),
                   modes=sorted(m.mid for m in ms))
        row["cut"] = Registry.cut_label(row)
        out.append(row)
    out.sort(key=lambda r: (-r["cover_x"] * r["cover_y"], -r["raw"][0]))
    return out


# 舊名字留著:「哪些族壓得出這個尺寸」仍然有用(驗證、sweep)。
def mode_options(reg: Registry, bit: int, rate: str, want):
    return raster_options(reg, bit, rate, want)


# ---- ⑤ hbin / vbin ---------------------------------------------------------
def bin_options(raster, want):
    """除完 **小於目標就不列**(使用者的規則)。

    ⚠ bin 在 CRCT、讀出**之後**(§2):它**不會**讓相機讀得更快,也**不會**
      改善捲簾。選它的理由是雜訊/疊頻 —— binning 是平均,RWZM 是縮放。
    """
    out = []
    for hb in HBIN_SET:
        for vb in VBIN_SET:
            got = (raster[0] // hb, raster[1] // vb)
            usable = got[0] >= want[0] and got[1] >= want[1]
            out.append(dict(hbin=hb, vbin=vb, after=got, usable=usable,
                            square=hb == vb,
                            note="" if hb == vb else
                                 f"非方形像素,後製要按 {hb}:{vb} 拉伸"))
    return [r for r in out if r["usable"]]


# ---- ⑥ RWZM ----------------------------------------------------------------
def rwzm_auto(raster, want, hbin=1, vbin=1, fit="squeeze"):
    """長寬**各自**的精確除數。引擎原本沒有這條。

    值是除數 x1024,韌體下夾在 1024(`DAT_c0b56538`)——所以只能縮不能放。
    `z = in * 1024 // want` 是滿足 `out >= want` 的**最大**除數,也就是縮最多、
    最接近目標的那一個。

    ★ 長寬可以不同(`blk_c03.c` 13772:`+0x64` 除寬、`+0xD4` 除高,兩個獨立
      的除數)。目標比例與光柵比例不符時它們就會不同 —— 那是**非等向壓縮**,
      使用者要的話就給,但要知道原廠 306 列零先例(`RWZM_ANISOTROPIC_PROVEN`)。

    `fit` 決定比例不符時怎麼辦,兩條都合法:

        "squeeze"  長寬各自算(使用者定的規格)。**保住視野**,代價是
                   非方形像素 —— 目標 2880x2880 配 3:2 光柵會橫向擠 50%。
        "crop"     兩軸共用同一個除數,多的裁掉。**方形像素**,代價是視野變窄。
                   原廠 306 列走的是這條(零例外 ZH == ZV)。

    回傳的 `squeeze_pct` 是 ZH/ZV 偏離 1 的百分比。比例本來就相符時它是
    0.06% 這種取整差,UI 不該為那個出聲;50% 才是真的擠。
    """
    src = (raster[0] // hbin, raster[1] // vbin)
    if src[0] < want[0] or src[1] < want[1]:
        return None
    zh = max(src[0] * 1024 // want[0], RWZM_UNITY)
    zv = max(src[1] * 1024 // want[1], RWZM_UNITY)
    if fit == "crop":
        # 兩軸共用最小的那個除數(縮最少的那一軸說了算),多的用裁切吸收。
        # 方形像素,代價是視野變窄 —— 原廠 306 列走的就是這條。
        zh = zv = min(zh, zv)
    got = (src[0] * 1024 // zh, src[1] * 1024 // zv)
    # 壓縮幅度:ZH/ZV 偏離 1 多少。0.06% 是取整差(比例本來就相符),
    # 50% 是真的把 3:2 擠成 1:1。UI 只該在後者出聲。
    squeeze = abs(zh / zv - 1) * 100
    return dict(zh=zh, zv=zv, after=src, got=got, fit=fit,
                exact=got == tuple(want),
                isotropic=zh == zv,
                squeeze_pct=squeeze,
                crops=(got[0] - want[0], got[1] - want[1]),
                stock_precedent=zh in RWZM_SET and zv in RWZM_SET)


# ---- 走完一輪 --------------------------------------------------------------
def walk(reg: Registry, bit, rate, want, raster=None, hbin=1, vbin=1,
         fit="squeeze"):
    """六步走完,回傳每一步的內容。任何一步空掉就在那裡停下來說明。

    順序(使用者 2026-09-29 定的第二版):
        ① bit  ② fps  ③ mode(光柵族)  ④ size  ⑤ hbin/vbin  ⑥ RWZM

    ★ 把 mode 放在 size 前面的理由:size 的上界因此是**一個矩形**(該族的
      光柵),而不是所有可用光柵的聯集。第一版 ③size→④mode 在高格率會讓
      使用者打完數字才發現列表是空的(120 fps 連 3008x2000 都沒有)。
    """
    out = {"bit": bit, "rate": rate}
    out["rasters"] = raster_options(reg, bit, rate)
    if not out["rasters"]:
        out["stop"] = f"③ {rate} 沒有任何可用的光柵族"
        return out
    out["raster"] = tuple(raster) if raster else out["rasters"][0]["raw"]
    if not any(r["raw"] == out["raster"] for r in out["rasters"]):
        out["stop"] = f"③ 光柵 {out['raster']} 在 {rate} 跑不到"
        return out
    snapped, notes = snap_resolution(want, bit, out["raster"])
    out["want"], out["want_notes"] = snapped, notes
    if snapped[0] <= 0 or snapped[1] <= 0:
        out["stop"] = "④ 尺寸夾完之後是 0"
        return out
    out["bins"] = bin_options(out["raster"], snapped)
    if not out["bins"]:
        out["stop"] = "⑤ 沒有可用的 bin 組合(連 1/1 都小於目標?)"
        return out
    out["rwzm"] = rwzm_auto(out["raster"], snapped, hbin, vbin, fit)
    if out["rwzm"] is None:
        out["stop"] = f"⑥ bin {hbin}/{vbin} 之後小於目標"
    return out


# ---- CLI -------------------------------------------------------------------
def _size(s):
    w, h = s.lower().split("x")
    return int(w), int(h)


def _show(reg, bit, rate, want, raster, hbin, vbin):
    r = walk(reg, bit, rate, want, raster, hbin, vbin)
    print(f"① 位元深度 {bit}")
    for o in bit_options(reg):
        if o["bit"] == bit and o["note"]:
            print(f"   ⚠ {o['note']}")
    print(f"② 格率 {rate}  ({RATES[rate]:.2f} fps)")
    print(f"③ mode(光柵族,{len(r.get('rasters', []))} 族)"
          f" —— 挑的是視野 + 捲簾,具體那顆交給相機")
    for row in r.get("rasters", []):
        mark = " <-" if row["raw"] == r.get("raster") else ""
        ru = row["rolling_us"]
        print(f"   {row['raw'][0]:5d}x{row['raw'][1]:<5d} {row['cut']:<30}"
              f" 捲簾 {ru[0]:6.0f} us  {'/'.join(row['fingerprint'])}"
              f"  最大 {row['max_size'][0]}x{row['max_size'][1]}{mark}")
    if r.get("stop") and not r.get("want"):
        print("  ", r["stop"]); return r
    print(f"④ 最終解析度 {r['want'][0]}x{r['want'][1]}"
          f"(上界 = 光柵 {r['raster'][0]}x{r['raster'][1]},只能往下砍)")
    for n in r["want_notes"]:
        print(f"   吸附:{n}")
    if r.get("stop") and not r.get("bins"):
        print("  ", r["stop"]); return r
    print(f"⑤ hbin / vbin(除完 >= 目標才列)")
    for b in r["bins"]:
        print(f"   x{b['hbin']} / x{b['vbin']}  -> {b['after'][0]}x{b['after'][1]}"
              f"   {b['note']}")
    z = r.get("rwzm")
    if z is None:
        print("  ", r.get("stop", "⑥ 無解")); return r
    print(f"⑥ RWZM  ZH {z['zh']}  ZV {z['zv']}"
          f"  -> {z['got'][0]}x{z['got'][1]}"
          f"  {'剛好命中' if z['exact'] else '需要裁掉多的'}")
    if not z["isotropic"]:
        print(f"   ⚠ 長寬不同 = 非等向壓縮(非方形像素)。原廠 306 列零先例")
    if not z["stock_precedent"]:
        print(f"   ⚠ 這組值原廠錄影路徑沒用過(只用過 {RWZM_SET})")
    if GATES_ARE_INSTALL_TIME:
        print("\n⚠ bin 模板仍由安裝時決定;RWZM 已可在執行期改變(§12.31)。"
              "\n  CRCT 錄影側串接仍待 I0/I 實機驗證(§6.2)。")
    return r


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bit", type=int, default=12)
    ap.add_argument("--fps", default="30")
    ap.add_argument("--want", type=_size, default=(3840, 2160))
    ap.add_argument("--raster", type=_size)
    ap.add_argument("--hbin", type=int, default=1)
    ap.add_argument("--vbin", type=int, default=1)
    ap.add_argument("--sweep", action="store_true",
                    help="掃一整片組合,檢查每一步都答得出來")
    a = ap.parse_args(argv)
    reg = Registry()
    if not a.sweep:
        _show(reg, a.bit, a.fps, a.want, a.raster, a.hbin, a.vbin)
        return 0

    targets = ((3840, 2160), (4096, 2160), (3840, 2560), (2880, 2880),
               (2048, 1080), (1920, 1080), (3008, 2000), (2000, 1334))
    tot = clamped = aniso = nostock = inexact = 0
    bad = []
    for o in bit_options(reg):
        if not o["usable"]:
            continue
        for f in fps_options(reg, o["bit"]):
            if not f["usable"]:
                continue
            for fam in raster_options(reg, o["bit"], f["rate"]):
                for want in targets:
                    r = walk(reg, o["bit"], f["rate"], want, fam["raw"])
                    tot += 1
                    if r.get("stop"):
                        bad.append(("停在", r["stop"], o["bit"], f["rate"],
                                    fam["raw"], want))
                        continue
                    clamped += r["want"] != want
                    z = r["rwzm"]
                    aniso += z["squeeze_pct"] > 2
                    nostock += not z["stock_precedent"]
                    inexact += not z["exact"]
                    # ★ 核心正確性:產出不可以小於(夾過的)目標
                    if z["got"][0] < r["want"][0] or z["got"][1] < r["want"][1]:
                        bad.append(("產出<目標", o["bit"], f["rate"],
                                    fam["raw"], r["want"], z))
    print(f"組合 {tot}(bit x fps x 光柵族 x 目標)")
    print(f"  ④ 目標被夾回光柵   {clamped}")
    print(f"  ⑥ 剛好命中        {tot - len(bad) - inexact}")
    print(f"  ⑥ 壓縮 >2%        {aniso}")
    print(f"  ⑥ 原廠沒用過的值   {nostock}")
    print(f"  ★ 壞掉的          {len(bad)}  <- 必須是 0")
    for b in bad[:5]:
        print("    ", b)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
