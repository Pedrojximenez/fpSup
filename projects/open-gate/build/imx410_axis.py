#!/usr/bin/env python3
"""把一組七軸推上相機,讀回 RECIPE,跟主機模型逐字比對。

    ./imx410_axis.py --check --preset B      乾跑,零寫入,印出要寫什麼
    ./imx410_axis.py --preset B              真的推上去

**差分的重點不是「錄出來看起來對」,是「相機算的 RECIPE 逐字等於主機模型」。**
27 個字全等才算過 —— 那比看檔案強得多,而且不必錄影就拿得到。

只寫 AXIS 那 9 個字(`0xC0732490`,我們自己安裝的區塊,不是原廠資料),
再用 `menu SetMovRecSize 3 -> 4` 重觸發 picker。og3krecipe 看到 snapshot 與
AXIS 不同就重算,所以不需要別的觸發路徑。

歷史前提:`imx410_load.py` 已經裝好,而且 `menu SetMovRecFormat 0` 已經鎖過。
現行固定 cave 配置已確認不安全；未完成 USER 搬遷前，實機 push 由同一套
Sensor Lab cave 檢查攔下。`--check` 仍可離線計算配方。
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]
                       / "fpSup" / "fp_usb_shell"))

from imx410_block import (AXIS_WORDS, RECIPE_WORDS, R_ACTH, R_ACTW, R_HBIN_E,
                          R_MODE, R_RECH, R_RECW, R_VALID, R_VBIN_E, R_ZH,
                          R_ZV, axis_words, expected_recipe)
from imx410_full import Registry, resolve

# imx410_plan 的位址,不另外寫死一份。
from imx410_plan import AXIS, HITS, RECIPE


# ---- 預設組 ----------------------------------------------------------------
# ★ B 與 C 是**一對**:同一個 3840x2160,兩組完全不同的旋鈕。
#   單跑一組不算證據 —— 逆向成立的證明就是「輸出一個字都不差」。
#   原廠自己的 UHD30 / UHD30CROP 就是這兩組。
PRESETS = {
    # A 是**原封不動的 INITIAL_AXIS** —— 不經過 resolve。對照組要重現的是
    # 「安裝完的樣子」,經過 resolve 會把裁切填成明確值、AXIS 就跟安裝值不同了。
    "A": dict(label="對照:正向預設 3032x2012(= INITIAL_AXIS,已驗證過)",
              axis=dict(bit=12, rate="30", raster=(3032, 2012))),
    "B": dict(label="逆向:視野 4176x2174 + 目標 3840x2160(RWZM unity)",
              kw=dict(bit=12, rate="30", raster=(4176, 2174),
                      want=(3840, 2160))),
    "C": dict(label="逆向:視野 6064x3412 + 目標 3840x2160(RWZM 1600)",
              kw=dict(bit=12, rate="30", raster=(6064, 3412),
                      want=(3840, 2160)),
              # ⚠ RWZM 非 unity -> CG_ZOOM 閘門打開 -> 畫布的四欄 RWZM
              #   **史上第一次真的寫下去**。筆記說寫錯會花屏後凍結。
              risky="RWZM 四欄第一次真的寫入"),
    # ---- CRCT 的兩階驗證梯 ----------------------------------------------
    # 目標:在**沒有 binned 感測器模式**的光柵上也能深度縮減。
    # 7/16 個光柵族沒有 binned 替代品(全開閘、全寬 16:9、2:1、Super35),
    # 而且**所有 binned 模式都是 RAW12** —— RAW14 那四個一個都沒有。
    #
    # ⚠ 一次只拆一個未知數。CRCT 在**錄影路徑**原廠 306 列全是 x1,
    #   連單獨用都沒有先例;「bin + zoom 併用」也是 0 列。兩個疊在一起試,
    #   壞了會分不出是哪一個。§7.1 的紀律就是這條。
    # ⚠ 非法 bin 值的失效模式是**相機當場鎖死、只能抽電池**(§6),
    #   不是畫面壞掉。合法值(x1/x3/x5、x1/x3)由引擎把關。
    # D 的對照組:同一個光柵、同一個 act、**只差 bin**。
    # CRCT 有效  -> D 是完整視野、D0 是極緊的中央裁切(方向相反,好分辨)
    # CRCT 無效  -> 兩張一樣緊(producer 都從 6064x3412 裡取一小塊)
    "D0": dict(label="階段① 對照:bin x1/x1,其餘與 D 相同",
               kw=dict(bit=12, rate="30", raster=(6064, 3412),
                       hbin=1, vbin=1, crop=(2000, 1126))),
    "D": dict(label="階段①:CRCT bin 單獨(x3/x3,zoom 留 unity)",
              kw=dict(bit=12, rate="30", raster=(6064, 3412),
                      hbin=3, vbin=3),
              risky="CRCT 在錄影路徑**史上第一次**被用(原廠 306 列全 x1)"),
    # 目標挑 1280x720:bin 完是 2021x1137,RWZM 1600 給 1293x727 —— 剛好夠,
    # 所以 zoom 會落在**原廠用過的值**上。驗「併用」時不要順便引進一個
    # 沒先例的 zoom 值,那又是多一個未知數。
    # ★ 2026-09-29 訂正:D 用 6064x3412 是選錯光柵 —— 6064/3 = 2021.33 除不盡,
    #   錄出來是 stride 不匹配(A001_166:垂直接縫 + 紫紅偏色)。
    #   F 換成 2016x1344:÷3 = 672x448 **完全乾淨**(672 % 16 == 0、448 偶數),
    #   把「CRCT 到底會不會動」跟「整除」這兩個問題分開。
    "F0": dict(label="階段①b 對照:2016x1344 bin x1/x1",
               kw=dict(bit=12, rate="30", raster=(2016, 1344),
                       hbin=1, vbin=1, crop=(656, 438))),
    "F": dict(label="階段①b:2016x1344 bin x3/x3 -> 672x448(整除,零餘數)",
              kw=dict(bit=12, rate="30", raster=(2016, 1344),
                      hbin=3, vbin=3),
              risky="CRCT 錄影路徑,但光柵整除 —— 排除 stride 這個變因"),
    # ---- RWZM 到底是縮放還是裁切 ----------------------------------------
    # CRCT 被證明只是個宣告之後,RWZM 是 CDNG **唯一**的縮減手段 ——
    # 但它同樣沒被驗過內容(A001_150 只比了幾何標籤)。同一個光柵、同一個
    # bin,只差 zoom:
    #   RWZM 真的縮放 -> G ≈ G0 降取樣 1.5625 倍
    #   RWZM 只是裁切 -> G ≈ G0 的一塊
    "G0": dict(label="RWZM 對照:3032x2012 zoom unity",
               kw=dict(bit=12, rate="30", raster=(3032, 2012),
                       rwzm=(1024, 1024))),
    "G": dict(label="RWZM 測試:3032x2012 zoom 1600/1600",
              kw=dict(bit=12, rate="30", raster=(3032, 2012),
                      rwzm=(1600, 1600)),
              risky="CDNG 唯一的縮減手段,但內容沒驗過"),
    # ---- 240 fps ---------------------------------------------------------
    # 唯一跑得到的光柵是 2016x672(scale 3x6,非對稱 -> 垂直要後製拉伸 2x)。
    # 格率走 AXIS 不走選單,所以不必補 CSV 第十列;但 donor 必須是 p13 + fill
    # (rec 2016x672 離 p83 太遠),而 fill 是**安裝時**的閘門 -> 要用這組軸重裝。
    # >60 fps 的七欄由 CG_OVER60 在相機端判斷,會自動寫進去(漏了會凍結)。
    # ---- 階段②:hbin/vbin **串** RWZM ----------------------------------
    # 2026-09-30。`CRCT_PATH_SELECTOR_SOLVED.md` 解開了為什麼階段 ① 失敗:
    # 路徑選擇器 `FUN_c0325228` 依 (錄影 RWZM, 預覽 RWZM) 分六支,而
    # **RWZM unity 會落在分支 B,mux = 1 Crmf —— binning 抽頭根本沒被選**。
    # 所以「bin 單獨」在設計上就不可能有作用,階段 ① 測的是不存在的組合。
    #
    # 要選到 Hbin2(mux 4)只有分支 C 與 F,而 C 的條件是
    # 「錄=預覽、非 unity」—— 我們的畫布本來就把 preview/record 的 RWZM
    # 寫成同值,所以**只要 rwzm != unity 就自動落在 C**,主管線吃
    # **錄影的 bin 與 RWZM**。
    #
    # 原廠 306 列的分支分布 B:172 C:36 D:81 E:17,而 E 的那 17 列正是
    # §6.1 說的「預覽 x3/x3」那批 —— 原廠只在**預覽**側串過,
    # 錄影欄 306/306 全是 x1。所以這一組**沒有原廠先例**。
    "I0": dict(label="階段② 對照:bin x1/x1 + rwzm 1600(同樣落在分支 C)",
               kw=dict(bit=12, rate="30", raster=(2016, 1344),
                       hbin=1, vbin=1, rwzm=(1600, 1600))),
    "I": dict(label="★ 階段②:bin x3/x3 **串** rwzm 1600 -> 400x276",
              kw=dict(bit=12, rate="30", raster=(2016, 1344),
                      hbin=3, vbin=3, rwzm=(1600, 1600)),
              risky="錄影路徑的 CRCT binning **史上第一次**真的可能被啟動 —— "
                    "原廠 306 列的錄影欄全是 x1。光柵 2016x1344 對 3 整除,"
                    "排除 A001_166 那個 stride 變因。"),
    "H": dict(label="240 fps:2016x672 mode 12",
              kw=dict(bit=12, rate="240", raster=(2016, 672)),
              risky="240 從沒上機過;七欄 hirate 漏一欄就是凍結"),
    # ★ 240 + RWZM 修正非對稱 binning。光柵 2016x672 的 scale 是 3x6,
    #   每個像素 = 3 寬 x 6 高的感測器區域(1:2 非方形)。水平壓 2x 之後
    #   每個像素變 6x6 -> **方形像素**,而且 1008x672 剛好 3:2。
    #   這是非等向 RWZM 的正當用途:修正感測器自己的非對稱,不是刻意擠壓。
    #   資料率也從 476 掉到 244 MB/s。
    #   ⚠ 非等向零原廠先例,且 2048 是**預覽**才用過的值(錄影只有 1024/1500/1600)。
    "H2": dict(label="240 fps + RWZM 2048/1024 -> 1008x672 方形像素 3:2",
               kw=dict(bit=12, rate="240", raster=(2016, 672),
                       rwzm=(2048, 1024)),
               risky="非等向 RWZM 零先例 + 2048 錄影路徑沒用過 + 240 沒上機過"),
    # ---- 同一組 H2 軸,只差釘選的 mode(2026-10-02,MODE 清單列出 M9 @ 240)----
    # 差分:M12 是 240 已錄成功的那顆(原廠時序 = 239.76,時序一字不改);
    # M9 (MONIT1_60_LOWP) 光柵 / hmax 完全相同,原廠時序 59.94,要配方改時序。
    "H2M12": dict(label="對照:H2 + 釘選 M12(240 已實錄)", base="H2", mode=12),
    "H2M9": dict(label="實驗:H2 + 釘選 M9(原廠 59.94,改時序跑 240)", base="H2", mode=9,
                 risky="M9 在 240 從沒上機:時序由配方改寫(vmax 3640 -> 910)"),
    "E": dict(label="階段②:CRCT bin + RWZM 併用(x3/x3 之後 RWZM 1600 到 1280x720)",
              kw=dict(bit=12, rate="30", raster=(6064, 3412),
                      hbin=3, vbin=3, want=(1280, 720)),
              risky="bin 與 zoom 併用 —— 原廠零先例,且要 D 過了才試"),
}


def preset_axis(reg, name):
    """預設組 -> (AXIS 九個字, resolve 的結果或 None)。

    ★ **`A_MODE` 一律留 0(自動)。** 它是個**釘選**:`expected_recipe` 的
      `if axis[A_MODE] and m.mid != axis[A_MODE]: continue`。把求解器挑的 mode
      填進去等於把相機自己的 donor 排序繞過去 —— 而「相機挑的 donor 與主機
      模型挑的是不是同一顆」正是這個差分最該驗的東西之一。釘下去就驗不到了。
    """
    spec = PRESETS[name]
    if "base" in spec:                       # 另一組的軸,只把 A_MODE 釘死(差分用)
        ax, r = preset_axis(reg, spec["base"])
        ax = list(ax)
        ax[-1] = spec["mode"]
        return ax, r
    if "axis" in spec:                       # 直接給軸,不經過求解器
        return axis_words(**spec["axis"]), None
    r = resolve(reg, **spec["kw"])
    if not r.ok:
        raise SystemExit(f"{name}: 解不出來 —— " + "; ".join(r.errors))
    ax = axis_words(bit=r.bit, rate=r.rate, raster=r.raster,
                    hbin=r.hbin, vbin=r.vbin, rwzm=r.rwzm,
                    crop=r.crop or (0, 0), mode=0)
    return ax, r


def describe(name, ax, r, reg):
    spec = PRESETS[name]
    print(f"\n=== {name}  {spec['label']}")
    if spec.get("risky"):
        print(f"  ⚠ {spec['risky']}")
    print(f"  AXIS   {ax}")
    if r is None:
        print("  (直接給軸,沒經過求解器 —— A_CROP/A_MODE 留 0 = 原廠留邊 + 自動)")
    else:
        print(f"  求解器 bin ÷{r.hbin}/÷{r.vbin}  RWZM {r.rwzm[0]}/{r.rwzm[1]}  "
              f"裁切 {r.crop[0]}x{r.crop[1]}  它會挑的 mode {r.mode}"
              f"(AXIS 裡留 0 讓相機自己挑)")
    want = expected_recipe(reg, ax)
    print(f"  主機模型 rec {want[R_RECW]}x{want[R_RECH]}  "
          f"act {want[R_ACTW]}x{want[R_ACTH]}  valid {want[R_VALID]}")
    return want


def push(reg, name, settle=1.2):
    """真的推上去,回傳 (相機的 RECIPE, 主機模型, 相同嗎)。"""
    # Even an AXIS-only update can activate the unsafe resident payload on an
    # old card.  Refuse before importing the USB transport or reading camera.
    import imx410_plan as plan
    from imx410_load import _preflight_safe_plan
    try:
        _preflight_safe_plan(plan.plan())
    except ValueError as error:
        raise SystemExit(f"Sensor Lab 現行配置不安全；零相機 I/O：{error}") from error
    from putfile import mem_get, mem_set, sh

    ax, r = preset_axis(reg, name)
    want = describe(name, ax, r, reg)

    before = mem_get(HITS, 1)[0]
    for i, w in enumerate(ax):
        mem_set(AXIS + i * 4, w)
    back = list(mem_get(AXIS, AXIS_WORDS))
    if back != list(ax):
        raise SystemExit(f"AXIS 寫不進去:讀回 {back} != {list(ax)}")

    # 重觸發 picker。切走再切回來 —— snapshot 與 AXIS 不同就重算。
    sh("menu SetMovRecSize 3")
    time.sleep(0.6)
    sh("menu SetMovRecSize 4")
    time.sleep(settle)

    got = list(mem_get(RECIPE, RECIPE_WORDS))
    hits = mem_get(HITS, 1)[0]
    same = got == list(want)
    print(f"  相機   rec {got[R_RECW]}x{got[R_RECH]}  "
          f"act {got[R_ACTW]}x{got[R_ACTH]}  valid {got[R_VALID]}  "
          f"mode {got[R_MODE]}  bin_e {got[R_HBIN_E]}/{got[R_VBIN_E]}  "
          f"rwzm {got[R_ZH]}/{got[R_ZV]}")
    print(f"  畫布命中 {before} -> {hits}"
          f"{'(沒動 —— picker 沒走到?)' if hits == before else ''}")
    print(f"  ★ RECIPE 27 字逐字比對:{'相同 ✓' if same else '*** 不同 ***'}")
    if not same:
        for i, (a, b) in enumerate(zip(got, want)):
            if a != b:
                print(f"      word[{i}]  相機 {a} (0x{a:x})   主機 {b} (0x{b:x})")
    return got, want, same


def main(argv=None):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preset", action="append", choices=sorted(PRESETS),
                    help="要推哪一組;可以給多次,依序跑")
    ap.add_argument("--check", action="store_true",
                    help="乾跑:只算出要寫什麼,**零寫入、不碰相機**")
    a = ap.parse_args(argv)

    names = a.preset or ["A"]
    reg = Registry()

    if a.check:
        print("乾跑 —— 零寫入,不碰相機")
        for n in names:
            ax, r = preset_axis(reg, n)
            describe(n, ax, r, reg)
            print(f"  會寫 {AXIS:#x}..{AXIS + AXIS_WORDS * 4:#x}"
                  f"({AXIS_WORDS} 字),然後 menu SetMovRecSize 3 -> 4")
        return 0

    bad = 0
    for n in names:
        _got, _want, same = push(reg, n)
        bad += not same
    print(f"\n{len(names) - bad}/{len(names)} 組逐字相同")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
