#!/usr/bin/env python3
"""imx410_full 的交叉驗證。

全功能版的引擎必須能**獨立重現**四個已出貨目標的幾何與時序 —— 不是從
og3k_plan 抄過來,而是從韌體映像重新算出來,然後跟那些寫死的數字對上。
對不上就代表引擎的規則錯了,而不是目標寫錯了。

    python3 -m pytest test_imx410_full.py -q
    ./test_imx410_full.py                      (不裝 pytest 也能跑)
"""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from imx410_full import (CANVAS_HIRATE_NAMES, CANVAS_PLANE, RECIPE_LABEL,
                         canvas_pairs, recipe_words, ALIGN, ALIGN_SAFE, CANVAS_BASE, CANVAS_HIRATE,
                         CLOCK, HBIN_TAPS, MEDIA_SD, MEDIA_SSD, POOL_INFLIGHT,
                         POOL_TOTAL, RATES, RWZM_UNITY, VBIN_TAPS, Registry,
                         burst, resolve)

REG = Registry()

# 原廠 70 筆 timing 用過的 16 種 tail,最小 330、最大 2151。解算器選的 tail
# 要落在這個範圍裡才算「有先例」。
STOCK_TAIL_LO, STOCK_TAIL_HI = 330, 2151


def _assert_same_frame(mode, rate, vmax, tail):
    """(vmax, tail) 的表示法**不唯一** —— tail 多加一個 hmax、vmax 少一,
    週期數完全相同。所以比的是週期,不是字面值;另外檢查 tail 有原廠先例。
    """
    got = Registry.solve_timing(mode, RATES[rate])
    assert got is not None, (mode.mid, rate)
    cycles = mode.hmax * (vmax - 1) + tail
    assert cycles == round(CLOCK / RATES[rate]), (rate, "參考值本身就不是 0 ppm")
    assert mode.hmax * (got[0] - 1) + got[1] == cycles, (mode.mid, rate, got)
    assert STOCK_TAIL_LO <= got[1] <= STOCK_TAIL_HI, (mode.mid, rate, got)


# ---- 感測器模式表 ----------------------------------------------------------
def test_seventy_modes():
    assert len(REG.modes) == 70
    assert len({m.mid for m in REG.modes}) == 70


def test_known_modes():
    """SENSOR_MODE_METADATA.md §4 抽查四筆,含各家族代表。"""
    for mid, name, raw, hmax, vmax, tail, fps in (
            (98, "ACQ_12BIT_MIX", (3032, 2012), 445, 2094, 445, 77.267),
            (139, "MONIT1_60_LOWP5", (2016, 1344), 445, 2700, 445, 59.925),
            (12, "MONIT1_240", (2016, 672), 330, 910, 330, 239.760),
            (0, "ACQ", (6064, 4042), 911, 4132, 911, 19.127)):
        m = REG.by_id[mid]
        assert m.name == name, (mid, m.name)
        assert m.raw == raw, (mid, m.raw)
        assert (m.hmax, m.vmax, m.tail) == (hmax, vmax, tail), (mid, m)
        assert abs(m.fps - fps) < 0.001, (mid, m.fps)


def test_fingerprints():
    """R14 八筆、hmax 911 與 RAW14 在 70 筆裡零例外地相關。"""
    r14 = [m for m in REG.modes if m.depth == 14]
    assert len(r14) == 8
    assert all(m.hmax == 911 for m in r14)
    assert all(m.hmax <= 450 for m in REG.modes if m.depth == 12)


def test_open_gate_families():
    """涵蓋 >99% 全尺寸的族 —— 這是「open gate」名副其實的那幾個。"""
    full = {(r["raw"], r["scale"]) for r in REG.rasters()
            if r["cover_x"] > 0.99 and r["cover_y"] > 0.99}
    assert ((6064, 4042), (1, 1)) in full
    assert ((3032, 2012), (2, 2)) in full        # OG3K
    assert ((2016, 1344), (3, 3)) in full        # OG2K
    assert ((2016, 672), (3, 6)) in full         # HSW,非對稱
    # 光柵更大不代表視野更大:3968x2640 的 1x1 只有中央 65%。
    crop = {r["raw"] for r in REG.rasters() if r["cover_x"] < 0.7}
    assert (3968, 2640) in crop and (4176, 2174) in crop


# ---- 時序解算 --------------------------------------------------------------
def test_timing_matches_og3k():
    """OG3K 八個格率的時序抄自原廠模式;引擎自己解要解出同樣的值。

    來源 FORMAT_REGISTRY_DESIGN.md §6 的表。OG3K25/50 那兩列原廠抄的是
    hmax 450 的模式(125 / 115),我們固定用 donor 98 的 hmax 445,所以
    只比對 hmax 445 的六個 —— 換 hmax 就換線時,也就換了類比指紋。
    """
    m98 = REG.by_id[98]
    for rate, vmax, tail in (("23_98", 6748, 585), ("24", 6740, 1145),
                             ("30", 5398, 735), ("48", 3370, 795),
                             ("60", 2698, 1035)):
        _assert_same_frame(m98, rate, vmax, tail)


def test_timing_matches_og2k():
    """OG2K_TIMING 的八個 (445, tail, vmax) —— 逐格對上。"""
    m139 = REG.by_id[139]
    for rate, vmax, tail in (("23_98", 6748, 585), ("24", 6741, 700),
                             ("25", 6471, 850), ("30", 5398, 735),
                             ("48", 3370, 795), ("50", 3235, 870),
                             ("60", 2699, 590), ("100", 1617, 880)):
        _assert_same_frame(m139, rate, vmax, tail)


def test_timing_zero_ppm():
    """所有廣播格率在所有 hmax 上都要解得出 0 ppm —— 週期是整數。"""
    for m in (REG.by_id[98], REG.by_id[139], REG.by_id[12], REG.by_id[3]):
        for rate, fps in RATES.items():
            got = Registry.solve_timing(m, fps)
            if got is None:
                continue
            vm, tl = got
            assert m.hmax * (vm - 1) + tl == round(CLOCK / fps), (m.mid, rate)


def test_hsw_needs_no_timing_change():
    """HSW 的全部理由:mode 12 出廠就是 239.760,一個字都不用改。"""
    m12 = REG.by_id[12]
    assert Registry.solve_timing(m12, RATES["240"]) == (m12.vmax, m12.tail)


# ---- 格率天花板 ------------------------------------------------------------
def test_no_mode_reaches_480():
    """480 / 960 fps:70 個光柵沒有一個到得了,連 blanking 歸零都不行。

    最矮的光柵是 2016x672,最短的線時是 hmax 330 →
    330 x 672 / 72 MHz = 3.08 ms = 324.7 fps 是**全機物理上限**。
    """
    ceiling = max(m.fps_ceiling for m in REG.modes)
    assert 324 < ceiling < 325, ceiling
    assert ceiling < 480
    assert not any(Registry.rate_fits(m, 480) for m in REG.modes)
    # 240 則是到得了的 —— 而且只有 2016x672 那一族到得了。
    ok = {m.raw for m in REG.modes if Registry.rate_fits(m, RATES["240"])}
    assert ok == {(2016, 672)}


def test_og3k_120_impossible():
    """3032x2012 的上限約 108 fps,所以 OG3K120 物理上不存在。"""
    m = REG.by_id[11]            # 3032x2012 裡 hmax 最小的
    assert 108 < m.fps_ceiling < 109
    assert not Registry.rate_fits(m, RATES["120"])


# ---- 對齊 ------------------------------------------------------------------
def test_align_row_bytes_are_word_multiples():
    """封裝暫存器寫的是「每列 bytes ÷ 4」,所以每列 bytes 必須是 4 的倍數。"""
    for depth, step in ALIGN.items():
        assert (step * depth // 8) % 4 == 0, depth
        # 而且 step 是**最小**的那個:再小一格就不成立。
        for smaller in range(1, step):
            if (smaller * depth) % 8 == 0 and (smaller * depth // 8) % 4 == 0:
                raise AssertionError(f"{depth}-bit 的粒度應該是 {smaller} 不是 {step}")


def test_align_safe_covers_every_depth():
    assert all(ALIGN_SAFE % s == 0 for s in ALIGN.values())


def test_record_raster_matches_og3k():
    """OG3K:感測器光柵 3032x2012 → 記錄矩陣 3024x2010 → 裁切 3008x2000。

    3032 不是 16 的倍數,3024 是(16 x 189)—— 記錄矩陣的寬度必須自己先對齊,
    這一步在 og3k_plan 的 T['rec'] 是寫死的常數,這裡是算出來的。
    """
    assert Registry.record_raster(3032, 2012, 12)[0] == 3024
    rows = {c["label"]: c for c in Registry.crops(3032, 2012, 12)}
    assert rows["MAX(原廠留邊)"]["size"] == (3008, 2002)
    assert rows["MAX(原廠留邊)"]["origin"] == (8, 5)     # 與出貨的 OG3K 相同


def test_record_raster_matches_og2k():
    """OG2K:2016x1344 本來就對齊,裁切 2000x1334 @ (8,5)。"""
    assert Registry.record_raster(2016, 1344, 12) == (2016, 1344)
    rows = {c["label"]: c for c in Registry.crops(2016, 1344, 12)}
    assert rows["MAX(原廠留邊)"]["size"] == (2000, 1334)
    assert rows["MAX(原廠留邊)"]["origin"] == (8, 5)


def test_crops_all_aligned():
    """每一列都要同時滿足寬度粒度與偶數高,而且不超出記錄矩陣。"""
    for depth in (8, 10, 12, 14):
        step = max(ALIGN_SAFE, ALIGN[depth])
        for w, h in ((3032, 2012), (2016, 1344), (6064, 4042), (2016, 672)):
            rr = Registry.record_raster(w, h, depth)
            for c in Registry.crops(w, h, depth):
                cw, ch = c["size"]
                assert cw % step == 0, (depth, c)
                assert ch % 2 == 0, (depth, c)
                assert cw <= rr[0] and ch <= rr[1], (depth, c)
                assert (cw * depth // 8) % 4 == 0, (depth, c)


# ---- 七軸解析 --------------------------------------------------------------
def test_resolve_reproduces_og3k():
    r = resolve(REG, bit=12, rate="30", raster=(3032, 2012),
                crop=(3008, 2000))
    assert r.ok, r.errors
    assert r.mode == 98                    # quiet 指紋優先,與出貨選擇相同


def test_resolve_reproduces_og2k():
    r = resolve(REG, bit=12, rate="60", raster=(2016, 1344),
                crop=(2000, 1334))
    assert r.ok, r.errors
    assert r.mode == 139                   # M139 是 2016x1344 唯一的 quiet


def test_vbin_five_is_rejected():
    """vbin ÷5 不存在 —— 寫下去是 assert 之後 while(true),相機鎖死。

    引擎這一側就要擋,不能指望韌體回錯誤。
    """
    assert 5 in HBIN_TAPS and 5 not in VBIN_TAPS
    r = resolve(REG, bit=12, rate="30", raster=(6064, 4042), hbin=5, vbin=5)
    assert not r.ok
    assert any("vbin" in e for e in r.errors)
    # hbin=5 + vbin=3 則是合法的(非方形像素,會警告但不擋)
    r = resolve(REG, bit=12, rate="30", raster=(6064, 4042), hbin=5, vbin=3)
    assert r.ok, r.errors
    assert any("非方形" in n for n in r.notes)


def test_no_matching_mode_falls_back():
    """使用者的決定:沒有 mode 對應不擋選單,錄影落到 FHD fallback。"""
    # 3032x2012 跑不到 119.88(上限 108.4)。
    r = resolve(REG, bit=12, rate="120", raster=(3032, 2012))
    assert r.ok                              # 不是錯誤
    assert any("FHD fallback" in n for n in r.notes)


def test_fourteen_bit_is_flagged_not_blocked():
    r = resolve(REG, bit=14, rate="24", raster=(6064, 4042))
    assert any("14-bit" in n for n in r.notes)
    # 全幅 RAW14 只有 19.13p,24p 塞不進去 → 沒有 mode → fallback
    assert any("FHD fallback" in n for n in r.notes)
    # 19 fps 以下才有 mode(M0 19.127 / M141 18.003)。
    ok = REG.candidates(raster=(6064, 4042), depth=14, fps=18.0)
    assert {m.mid for m in ok} == {0, 141}


def test_rwzm_unity_is_identity():
    r = resolve(REG, bit=12, rate="30", raster=(3032, 2012),
                rwzm=(RWZM_UNITY, RWZM_UNITY))
    assert "3032x2012 → 記錄矩陣" in " ".join(r.notes)
    # 1600 = 原廠 FHD 的 1.5625x 縮小:3032 → 1940,正是 FHD 光柵 1936 的來源。
    r = resolve(REG, bit=12, rate="30", raster=(3032, 2012), rwzm=(1600, 1600))
    assert "1940x1287" in " ".join(r.notes), r.notes


# ---- 消隱餘裕:「塞得進去」不等於「可以用」 --------------------------------
def test_blanking_guard_reproduces_notes():
    """SENSOR_MODE_METADATA.md §2 自己做過的兩個判斷,現在是程式碼。"""
    m139 = REG.by_id[139]
    # 119.88:445 x 1344 = 598,080 / 600,600,只剩 5.7 行,而 vblank code 是 100。
    assert 5 < Registry.blanking_lines(m139, RATES["120"]) < 6
    assert Registry.rate_possible(m139, RATES["120"])      # 物理塞得進去
    assert not Registry.rate_fits(m139, RATES["120"])      # 但不能用
    # 100:約 274 行餘裕 >= 100,離線資料沒有排除它。
    assert 273 < Registry.blanking_lines(m139, RATES["100"]) < 275
    assert Registry.rate_fits(m139, RATES["100"])


def test_blanking_guard_rejects_m140_at_240():
    """M140 是 quiet,240 fps 也「塞得進去」—— 但只剩 2.8 行消隱。

    沒有這一關,quiet 優先的排序會挑中 M140 而不是 HSW 實際用的 M12。
    """
    m140 = REG.by_id[140]
    assert m140.fingerprint == "Q12"
    assert Registry.rate_possible(m140, RATES["240"])
    assert Registry.blanking_lines(m140, RATES["240"]) < 3
    assert not Registry.rate_fits(m140, RATES["240"])


def test_donor_choice_reproduces_all_three_products():
    """排序規則要重現三個出貨選擇,而且理由各不相同。"""
    for rate, raster, mid in (("30", (3032, 2012), 98),      # quiet + 線時長
                              ("60", (2016, 1344), 139),     # 唯一的 quiet
                              ("240", (2016, 672), 12)):     # 兩個 F12,原廠時序勝出
        r = resolve(REG, bit=12, rate=rate, raster=raster)
        assert r.mode == mid, (rate, raster, r.mode, mid)


# ---- 描述子池:寫不完是乾淨停,不是凍結 ------------------------------------
def test_pool_matches_firmware_constants():
    """FUN_c0374268 的門檻 `1 < 剩餘`,池子 0x60 = 96 ⇒ 在途上限 94。"""
    assert POOL_TOTAL == 0x60
    assert POOL_INFLIGHT == POOL_TOTAL - 2


def test_descriptor_count_is_not_a_general_burst_lower_bound():
    """A001_020 的 94 格不能推廣為 A001_150 等大格子的下界。"""
    b = burst((2016, 672), 12, RATES["240"], MEDIA_SD)
    assert not b["sustained"]
    assert b["frames"] is None and b["seconds"] is None
    assert "乾淨停止" in b["why"] and "凍結" in b["why"]


def test_burst_capacity_is_explicit_and_bytes_can_limit_before_descriptors():
    geometry = (6016, 1416)
    per = geometry[0] * geometry[1] * 12 // 8
    b = burst(geometry, 12, 30, 0, buffer_bytes=per * 37)
    assert b["frames"] == (37, 37) and b["frame_bytes"] == per
    assert burst(geometry, 12, 30, 0)["frames"] is None


def test_burst_uses_recording_matrix_not_visible_crop():
    r = resolve(REG, bit=12, rate="30", raster=(3032, 2012))
    assert r.burst["need_mbps"] == 3024 * 2012 * 1.5 * RATES["30"] / 1e6


def test_burst_sustained_when_writer_keeps_up():
    """A001_120:120 fps 在 SSD 上寫了 1177 格 —— 池子不見底。"""
    b = burst((2016, 672), 12, RATES["120"], MEDIA_SSD)
    assert b["sustained"] and b["frames"] is None


def test_data_rate_is_not_a_gate():
    """吞吐不足**不是錯誤**。它只改變錄得到多久,配方照樣成立。"""
    r = resolve(REG, bit=12, rate="240", raster=(2016, 672), media_mbps=MEDIA_SD)
    assert r.ok, r.errors
    assert not r.burst["sustained"]
    assert not any("吞吐" in e or "MB/s" in e for e in r.errors)


# ---- 畫布:凍結的唯一已知預測器 --------------------------------------------
def test_canvas_window_required_when_donor_raster_differs():
    """p13 宣告 2016x1344、mode 12 只讀 672 行 —— 漏了 +0xF4/+0xF8 就結束不了。"""
    r = resolve(REG, bit=12, rate="30", raster=(3032, 2012))
    # 記錄矩陣 3024 != donor 光柵 3032,所以視窗必寫。
    assert 0xF4 in r.canvas and 0xF8 in r.canvas
    assert all(off in r.canvas for off in CANVAS_BASE)


def test_canvas_hirate_required_above_60():
    r60 = resolve(REG, bit=12, rate="60", raster=(2016, 1344))
    r120 = resolve(REG, bit=12, rate="120", raster=(2016, 672))
    assert not any(off in r60.canvas for off in CANVAS_HIRATE)
    assert all(off in r120.canvas for off in CANVAS_HIRATE), r120.canvas


# ---- 動態配方:必須逐格重現三個出貨目標的靜態畫布集合 ----------------------
# 參考值**現場**從 og3k_plan 取(它會依 OG_TARGET 在 import 時決定目標,
# 所以要各開一個行程),這樣參考值不會隨時間漂掉。
def _shipped_canvas(target):
    import json
    import subprocess
    src = ("import og3k_plan as P, json;"
           "print(json.dumps({'rec': list(P.T['rec']), 'act': list(P.T['act']),"
           "'canvas': {str(k): v for k, v in P.CANVAS_REC.items()},"
           "'hirate': list(P.HIRATE_FIELDS) if P.T.get('write_hirate') else [],"
           "'preview': bool(P.T.get('write_preview')),"
           "'active': bool(P.T['write_active']),"
           "'producer': bool(P.T['write_producer']),"
           "'window': bool(P.T.get('write_window'))}))")
    out = subprocess.run([sys.executable, "-c", src],
                         cwd=str(pathlib.Path(__file__).resolve().parent),
                         env={**os.environ, "OG_TARGET": target},
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout)


def test_canvas_pairs_reproduce_shipped_targets():
    for target in ("og3k", "og2k", "hsw"):
        t = _shipped_canvas(target)
        got = canvas_pairs(rec=tuple(t["rec"]), act=tuple(t["act"]), depth=12,
                           preview=t["preview"], active=t["active"],
                           producer=t["producer"], window=t["window"],
                           hirate=tuple(t["hirate"]))
        want = {int(k, 0): v for k, v in t["canvas"].items()}
        assert got == want, (target, got, want)


def test_canvas_plane_codes():
    """+0x080/+0x084 是原廠三胞胎 65 欄裡唯一不同的兩欄。

    14-bit **不是**三胞胎的一員(picker 只有三張表),它的 RAW 平面取自
    原廠的 14-bit 照片 profile:碼 8 = 16 bpp 容器。見 §4.3。
    """
    assert CANVAS_PLANE == {12: (7, 7), 10: (10, 9), 8: (10, 10), 14: (7, 8)}
    assert CANVAS_PLANE[14] != CANVAS_PLANE[12], "14-bit 不該再是 12-bit 的佔位"
    for depth, (prev, raw) in CANVAS_PLANE.items():
        got = canvas_pairs(rec=(100, 100), act=(80, 80), depth=depth)
        assert got[0x80] == prev, depth


def test_recipe_key_fits_the_label_word():
    """MATCH 的比對是一個 32-bit 字,所以內部標籤只能四個字元。"""
    assert len(RECIPE_LABEL) == 4
    for rate in RATES:
        key = RECIPE_LABEL + rate
        assert len(key) < 15, key          # strncmp(key, entry, 15)


def test_recipe_words_timing_matches_solver():
    r = resolve(REG, bit=12, rate="30", raster=(3032, 2012))
    w = recipe_words(REG, r)
    m = REG.by_id[r.mode]
    vmax, tail = Registry.solve_timing(m, RATES["30"])
    assert w["timing_w0"] == m.hmax | (tail << 16)
    assert w["timing_w1"] == vmax | (m.x_start << 16)
    assert w["key"].rstrip(b"\x00") == b"CUST30"
    assert len(w["key"]) == 16


def test_recipe_words_window_flag_tracks_donor_raster():
    """donor 光柵 == 記錄矩陣時不寫視窗;不等時必寫。"""
    r = resolve(REG, bit=12, rate="60", raster=(2016, 1344))      # M139 2016x1344
    w = recipe_words(REG, r)
    assert w["rec"] == (2016, 1344) and not w["window"]
    r = resolve(REG, bit=12, rate="30", raster=(3032, 2012))      # M98,rec 3024
    w = recipe_words(REG, r)
    assert w["rec"][0] == 3024 and w["window"]
    assert 0xF4 in w["canvas"] and 0xF8 in w["canvas"]


# ---- 逆向幾何求解器 --------------------------------------------------------
# 原廠 profile 是逆向解出來的:先選輸出,再回推窗口/bin/RWZM。
# 規則是「產出 >= 目標,多的裁掉」——FHD60 產出 1940x1093 而 rec 是 1936x1090。
#
# ★ 2026-09-28:四個定點**全部**逐格重現。先前兩個 UHD 解不開,原因是
#   RWZM 四欄的配對讀錯一個槽(見 imx410_full 的 RWZM 段與 §12.25)。
FIXED_POINTS = (
    # (key, 窗口, 目標 rec, 原廠 (hbin,vbin,rwzmH,rwzmV))
    # rwzm 取**錄影**那一對(+0x64 / +0xD4);原廠寫 1023,韌體下夾成 1024。
    ("FHD60",     (3032, 1708), (1936, 1090), (1, 1, 1600, 1600)),
    ("FHD60CROP", (2088, 1174), (1936, 1090), (1, 1, 1024, 1024)),
    ("UHD30",     (6064, 3412), (3856, 2170), (1, 1, 1600, 1600)),
    ("UHD30CROP", (4176, 2174), (3856, 2170), (1, 1, 1024, 1024)),
)


def test_solver_reproduces_every_fixed_point():
    """四個定點必須**逐格**重現,不接受近似。

    ★ Super35 的兩列是同一個輸出的另一組解:換一個較小的窗口、RWZM 收成
      unity、多的裁掉。UHD30 與 UHD30CROP 的 rec 完全相同就是這個意思。
    """
    from imx410_block import solve_geometry
    for key, win, want, exp in FIXED_POINTS:
        s = solve_geometry(win, want)
        assert s is not None, key
        assert (s[0], s[1], s[2], s[3]) == exp, (key, s[:4], exp)
        assert s[4][0] >= want[0] and s[4][1] >= want[1], (key, s[4], want)


def test_record_and_preview_rwzm_are_separate_columns():
    """★ 這條是 UHD 解不開的根因,釘死它。

    +0x60/+0x64 不是「預覽的 H/V」,而是「H 的預覽/錄影」;+0xD0/+0xD4 同理
    是 V 的。證據在韌體兩個方向的計算裡:+0x60 除的是寬、+0xD0 除的是高,
    而且是同一條路徑(blk_c03.c 13772)。所以求解器只能取**錄影**那一欄
    用過的值 —— 2048/3072 是預覽才有的,拿來解錄影幾何就會解出原廠沒有的組合。
    """
    from imx410_block import RWZM_SET, RWZM_SET_PREVIEW, RWZM_ANISOTROPIC_PROVEN
    assert RWZM_SET == (1024, 1500, 1600)
    assert RWZM_SET_PREVIEW == (1024, 1280, 1536, 1600, 2048, 3072)
    # 兩條路徑**互不包含**:1500 只有錄影用,2048/3072/1536/1280 只有預覽用。
    # 舊的 RWZM_SET (1023,1500,1536,1600,2048,3072) 是把兩欄混起來數的 ——
    # 而且連混的都漏了 1280,所以它既不是錄影的集合也不是真正的聯集。
    assert set(RWZM_SET) - set(RWZM_SET_PREVIEW) == {1500}
    assert set(RWZM_SET_PREVIEW) - set(RWZM_SET) == {1280, 1536, 2048, 3072}
    assert set(RWZM_SET) | set(RWZM_SET_PREVIEW) != \
        {1023, 1500, 1536, 1600, 2048, 3072}
    # 能算不等於驗過:原廠 306 列沒有一列非等向。
    assert RWZM_ANISOTROPIC_PROVEN is False


def test_canvas_writes_rwzm_h_and_v_into_the_right_slots():
    """畫布只寫**錄影**的 RWZM:H 進 +0x64、V 進 +0xD4(槽位見 §12.25)。

    舊排法把 ZV 寫進 +0x64(錄影的 H)、ZH 寫進 +0xD0(預覽的 V)。2026-10-04 起
    預覽那一對(+0x60 / +0xD0)由宣告列給(sl_modes.c declare_post),畫布不碰 ——
    以前預覽跟著錄影縮放,6064 寬讀出的預覽撐爆了 p83 的緩衝(r69)。
    """
    from imx410_block import CANVAS_TEMPLATE, CS_HBIN, CS_VBIN, CS_ZH, CS_ZV
    src = {off: s for off, s, _ in CANVAS_TEMPLATE if s in (CS_ZH, CS_ZV)}
    assert src == {0x064: CS_ZH, 0x0D4: CS_ZV}
    bins = {off: s for off, s, _ in CANVAS_TEMPLATE if s in (CS_HBIN, CS_VBIN)}
    assert bins == {0x05C: CS_HBIN, 0x0C8: CS_VBIN}


def test_firmware_clamps_rwzm_at_unity():
    """原廠表裡的 1023 不是「比 unity 再大一點」—— 韌體下夾在 1024。

    所以我們寫 1024 與原廠等價,不是沒有先例的值。
    DAT_c0b56538 直接從映像讀,不寫死。
    """
    from imx410_full import RWZM_CLAMP, RWZM_UNITY
    assert REG._w(0xC0B56538) == RWZM_CLAMP == RWZM_UNITY == 1024


def test_record_path_reproduces_every_stock_profile():
    """★ 最強的那條證據:全部 134 列**沒有一列**違反「產出 >= 目標」。

    用錄影那一組欄位(hbin +0x5C、vbin +0xC8、RWZM +0x64/+0xD4)正向算,
    跟該列自己的記錄矩陣比。這一條過了,就表示幾何鏈的公式是對的 ——
    先前 UHD 對不上是欄位讀錯,不是公式錯。
    """
    import struct
    from imx410_block import (param_words, HBIN_ENUM, VBIN_ENUM, P_RECW,
                              P_RECH, P_HBIN_R, P_VBIN_R, P_ZH_R, P_ZV_R,
                              P_WINW, P_WINH)
    from imx410_full import RWZM_CLAMP
    n = 0
    for pid, w in param_words().items():
        if not (w[P_RECW] and w[P_RECH]):
            continue                      # 空殼列(p13 那種)沒有記錄矩陣
        n += 1
        gw = (w[P_WINW] // HBIN_ENUM[w[P_HBIN_R]]) * 1024 // max(w[P_ZH_R],
                                                                RWZM_CLAMP)
        gh = (w[P_WINH] // VBIN_ENUM[w[P_VBIN_R]]) * 1024 // max(w[P_ZV_R],
                                                                RWZM_CLAMP)
        assert gw >= w[P_RECW] and gh >= w[P_RECH], \
            f"p{pid}: 窗口 {w[P_WINW]}x{w[P_WINH]} 產出 {gw}x{gh} " \
            f"< rec {w[P_RECW]}x{w[P_RECH]}"
    assert n == 134, n


def test_profile_scale_column_is_just_the_sensor_mode_scale():
    """★ +0xFC 不是「哪條縮減路徑」的開關,只是感測器模式的 scale 換成 float。

    先前把 UHD(1.0)與 FHD(2.0)的差別當成分界追了一輪。306 列逐列比對
    證明它是衍生值:+0xF4/+0xF8 就是某個感測器模式的光柵,+0xFC/+0x100 就是
    那個光柵的 geometry scale。UHD 是 1.0 只因為它 1x1 讀出,FHD 是 2.0 只因為
    它 2x2 —— 相關,不是機制。把這條釘住,免得有人再追一次。
    """
    import struct
    from imx410_block import param_words, P_WINW, P_WINH, P_SCALEX, P_SCALEY
    byraster = {}
    for m in REG.modes:
        byraster.setdefault(m.raw, set()).add(m.scale)
    for pid, w in param_words().items():
        raster = (w[P_WINW], w[P_WINH])
        cands = byraster.get(raster)
        assert cands, f"p{pid}: 窗口 {raster} 不是任何感測器模式的光柵"
        assert len(cands) == 1, f"p{pid}: 光柵 {raster} 的 scale 不唯一 {cands}"
        sx, sy = struct.unpack("<ff", struct.pack("<II", w[P_SCALEX],
                                                  w[P_SCALEY]))
        assert (sx, sy) == tuple(float(v) for v in next(iter(cands))), \
            f"p{pid}: +0xFC {(sx, sy)} != mode scale {cands}"


def test_reverse_direction_reproduces_the_stock_pairs():
    """★ 第七軸:最終裁切是**輸入**。

    同一個 3840x2160,從兩個不同的視野各解出一組旋鈕 —— 原廠 UHD30 與
    UHD30CROP 就是這兩組。輸出一個字都不差,差的是窗口與達成它的旋鈕,
    這正是 §12.23 描述的那件事,現在算得出來了。
    """
    r = resolve(REG, bit=12, rate="30", raster=(6064, 3412), want=(3840, 2160))
    assert r.ok, r.errors
    assert (r.hbin, r.vbin, r.rwzm) == (1, 1, (1600, 1600))
    assert r.crop == (3840, 2160)

    c = resolve(REG, bit=12, rate="30", raster=(4176, 2174), want=(3840, 2160))
    assert c.ok, c.errors
    assert (c.hbin, c.vbin, c.rwzm) == (1, 1, (1024, 1024))   # Super35:不縮,直接裁
    assert c.crop == r.crop == (3840, 2160)
    # 同一個輸出、不同的窗口 —— mode 也必須是原廠那兩個。
    assert r.mode == 7 and c.mode == 102, (r.mode, c.mode)


def test_reverse_direction_reproduces_og3k():
    """已出貨的 OG3K(3008x2000,全開閘)也必須從逆向解得出來。"""
    r = resolve(REG, bit=12, rate="30", raster=(3032, 2012), want=(3008, 2000))
    assert r.ok, r.errors
    assert (r.hbin, r.vbin, r.rwzm) == (1, 1, (1024, 1024))
    assert r.crop == (3008, 2000)


def test_reverse_direction_aligns_the_target_first():
    """目標先對齊再解 —— 對齊之後的截斷才不會把記錄矩陣掉到目標以下。

    寬對齊到 step、高取偶時 `floor(產出/step)*step >= want` 等價於
    `產出 >= want`,所以求解器只要保證後者。
    """
    r = resolve(REG, bit=12, rate="30", raster=(3032, 2012), want=(3007, 1999))
    assert r.ok, r.errors
    assert r.crop == (2992, 1998), r.crop        # 3007->2992(16 的倍數)、1999->1998
    assert any("先對齊成" in n for n in r.notes)


def test_reverse_direction_refuses_targets_the_window_cannot_give():
    """目標比視野還大就講清楚,不要硬湊出一個做不到的配方。"""
    r = resolve(REG, bit=12, rate="30", raster=(2016, 1344), want=(4096, 2160))
    assert not r.ok
    assert any("解不出" in e for e in r.errors), r.errors


def test_reverse_direction_pins_explicit_bins():
    """使用者指定了 bin 就尊重它 —— 求解器只挑 RWZM。"""
    r = resolve(REG, bit=12, rate="30", raster=(6064, 4024), hbin=3, vbin=3,
                want=(2000, 1334))
    assert r.ok, r.errors
    assert (r.hbin, r.vbin) == (3, 3)


def test_forward_direction_is_unchanged_without_want():
    """沒給 want 就還是正向 —— 已出貨的用法一個字都不能動。"""
    a = resolve(REG, bit=12, rate="30", raster=(3032, 2012))
    assert a.ok and a.hbin == 1 and a.vbin == 1
    assert a.rwzm == (RWZM_UNITY, RWZM_UNITY)
    # 上機驗過的 DefaultCropSize(A001_125)就是這一對。
    assert a.crop == (3008, 2002), a.crop


def test_host_and_camera_agree_on_the_default_crop():
    """★ 主機的預設裁切必須逐格等於相機側 A_CROP=0 的預設。

    `crops()` 的排序是**選單**的排序(MAX/FULL 置頂再依面積),FULL 面積較大
    所以排第一 —— 拿「第一列」當預設會選到 FULL,而相機那側走的是原廠留邊
    慣例(= MAX)。同一組選項在兩邊解出不同的東西,是 §12.21 那條規則要擋的
    情形。這裡拿四個光柵逐一比,兩邊都是自己算的,不是抄來的。
    """
    from imx410_block import axis_words, expected_recipe, R_ACTW, R_ACTH
    for raster in ((3032, 2012), (2016, 1344), (6064, 4024), (4176, 2174)):
        host = resolve(REG, bit=12, rate="30", raster=raster)
        assert host.ok, (raster, host.errors)
        cam = expected_recipe(REG, axis_words(bit=12, rate="30",
                                              raster=raster))
        assert host.crop == (cam[R_ACTW], cam[R_ACTH]), \
            f"{raster}: 主機 {host.crop} != 相機 {(cam[R_ACTW], cam[R_ACTH])}"


# ---- 合法輸出的解析度規則(§3.1b)----------------------------------------
# 只留「真正的影像輸出」——縮圖路徑(act 寬 < 1280)走的是別條路,混進來會
# 把統計弄髒:那 8 列的寬 750/600/376/300 本來就不是 16 的倍數。
VIDEO_ACT_MIN_W = 1280


def _video_rows():
    from imx410_block import param_words, P_ACTW
    return {pid: w for pid, w in param_words().items()
            if w[P_ACTW] >= VIDEO_ACT_MIN_W}


def test_stock_act_width_is_always_16_aligned():
    """★ 硬的那一條:可見寬一律 16 的倍數,原廠 118 列零例外。

    根據在韌體:`FUN_c0630e90` 依深度把「每列 bytes」寫進 0x30182214,
    沒對齊就是每列少搬幾個 byte、列與列累積位移(§3)。16 同時滿足四個深度。
    """
    from imx410_block import P_ACTW
    rows = _video_rows()
    assert len(rows) == 118, len(rows)
    bad = {pid: w[P_ACTW] for pid, w in rows.items() if w[P_ACTW] % 16}
    assert not bad, bad


def test_act_height_multiple_of_eight_is_a_coincidence_not_a_rule():
    """★ 軟的那一條 —— 而且是**假規則**。釘住反例,免得有人來「修正」引擎。

    原廠 118 列的可見高全部是 8 的倍數,看起來像鐵律。但我們自己出貨、
    上機驗證過的 OG2K 是 2000x1334,`1334 % 8 == 6`;而且 1334 正是分組表
    「3:2 -> 1334」那個上機驗過的值(§12.18)。

    照「原廠零例外」去收緊,等於把一個驗證過的幾何改壞。
    **「原廠 118/118」不等於「規則」——還要問有沒有反例在我們自己手上。**
    """
    from imx410_block import P_ACTH
    rows = _video_rows()
    assert all(w[P_ACTH] % 8 == 0 for w in rows.values()), "原廠應該是零例外"
    # 我們自己的反例,從 og3k_plan 的**出貨定義**讀,不寫死 ——
    # 這樣 og3k_plan 改了幾何,這個測試會跟著動而不是繼續守一個過期的數字。
    import og3k_plan
    shipped = {t["label"]: t["act"] for t in og3k_plan.TARGETS.values()}
    assert {"OG3K", "OG2K"} <= set(shipped), sorted(shipped)
    assert shipped["OG3K"][1] % 8 == 0, shipped["OG3K"]
    og2k_h = shipped["OG2K"][1]
    assert og2k_h % 8 != 0, f"OG2K 的可見高 {og2k_h} 應該正是那個反例"
    assert og2k_h % 2 == 0, og2k_h


def test_crops_never_emits_a_width_the_hardware_cannot_pack():
    """選單生出來的每一列都要通過寬度那條硬約束 —— 全部光柵 x 全部深度。"""
    from imx410_full import ALIGN, ALIGN_SAFE
    for raster in sorted({m.raw for m in REG.modes}):
        for depth in (8, 10, 12, 14):
            step = max(ALIGN_SAFE, ALIGN[depth])
            for row in Registry.crops(raster[0], raster[1], depth):
                w, h = row["size"]
                assert w % step == 0, (raster, depth, row["label"], w)
                assert h % 2 == 0, (raster, depth, row["label"], h)
                assert (w, h) <= row["raster"], (raster, depth, row["label"])


def test_rec_width_only_needs_the_depth_granularity():
    """`rec` 寬 16 對齊是**設計選擇**,不是硬體規則 —— 原廠自己就有例外。

    p43 / p83 的 rec 是 3032x2012,`3032 % 16 == 8`,而 12-bit 的粒度就是 8。
    """
    from imx410_block import P_RECW
    from imx410_full import ALIGN
    rows = _video_rows()
    assert all(w[P_RECW] % ALIGN[12] == 0 for w in rows.values())
    exceptions = {pid for pid, w in rows.items() if w[P_RECW] % 16}
    assert exceptions, "原廠應該有非 16 對齊的 rec 寬"
    assert all(rows[pid][P_RECW] == 3032 for pid in exceptions), exceptions


def test_solver_refuses_impossible_targets():
    """目標比窗口大就無解,不要硬湊。"""
    from imx410_block import solve_geometry
    assert solve_geometry((2016, 1344), (4096, 2160)) is None


def _plane_tab_from_payload():
    """og3krecipe.S 的 plane_tab,直接從原始碼解出來。"""
    import re
    src = pathlib.Path(__file__).resolve().parent / "og3krecipe.S"
    body = src.read_text().split("plane_tab:", 1)[1]
    out = {}
    for line in body.splitlines():
        line = line.split("/*")[0].strip()
        if not line:
            continue
        if not line.startswith(".short"):
            break
        d, p, r = (int(x) for x in line[len(".short"):].split(","))
        if d == 0:
            break
        out[d] = (p, r)
    return out


def test_host_and_camera_agree_on_every_plane_format_code():
    """平面碼有兩張表 —— 主機的 CANVAS_PLANE 與 og3krecipe.S 的 plane_tab。

    兩邊都是依**位深**查,分頭改就會靜默不一致:資料照一邊打包、
    BitsPerSample 照另一邊寫,結果是毀檔而不是報錯。見 §4.3。
    """
    from imx410_full import CANVAS_PLANE
    cam = _plane_tab_from_payload()
    assert set(cam) == set(CANVAS_PLANE), (sorted(cam), sorted(CANVAS_PLANE))
    for depth in sorted(cam):
        assert cam[depth] == CANVAS_PLANE[depth], (depth, cam[depth],
                                                   CANVAS_PLANE[depth])


def test_fourteen_bit_raw_plane_is_a_sixteen_bpp_container():
    """RAW14 沒有 14 bpp 的平面碼;原廠 14-bit profile 用碼 8 = 16 bpp。

    p41/p44/p81/p84 的光柵正好是 RAW14 感測器模式的光柵,它們的 +0x84 是 8。
    把這個出處釘住 —— 不然「(7,8) 是哪來的」半年後就沒人知道了。見 §4.3。
    """
    from imx410_block import param_words, P_RECW, P_RECH
    from imx410_full import CANVAS_PLANE, Registry
    rows = param_words()
    raw14 = {m.raw for m in Registry().modes if m.depth == 14}
    donors = {pid: w for pid, w in rows.items()
              if w[0x84 // 4] == 8 and (w[P_RECW], w[P_RECH]) in raw14}
    assert set(donors) == {41, 44, 81, 84}, sorted(donors)
    assert CANVAS_PLANE[14][1] == 8


def test_fourteen_bit_only_ever_picks_a_raw14_donor_mode():
    """位深 14 就只能借 RAW14 的感測器模式,不能退回 12-bit 的。"""
    from imx410_full import Registry, resolve
    reg = Registry()
    raw14 = {m.mid for m in reg.modes if m.depth == 14}
    seen = 0
    for rate, raster in (("24", (5712, 3216)), ("25", (3968, 2640)),
                         ("30", (4176, 2174))):
        r = resolve(reg, bit=14, rate=rate, raster=raster)
        assert not r.errors, (rate, raster, r.errors)
        if r.mode is not None:
            assert r.mode in raw14, (rate, raster, r.mode)
            seen += 1
    assert seen == 3, seen


def _run():
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    bad = 0
    for n, f in fns:
        try:
            f()
            print(f"  ok   {n}")
        except AssertionError as e:
            bad += 1
            print(f"  FAIL {n}: {e}")
    print(f"\n{len(fns) - bad}/{len(fns)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(_run())
