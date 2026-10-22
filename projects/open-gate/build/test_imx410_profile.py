#!/usr/bin/env python3
"""我們自己宣告的 profile(imx410_profile.declare),離線。

最強的一條:只拿**一列**影片類底列(p171,原廠 UHD30 12-bit),配上公式,
要重現原廠全部 78 組影片 profile 的**整列 65 欄**(引擎 fps +0x30 除外,
它由 imx410_canvas 從 FPSLATCH 寫)。也就是說:除了公式算的欄位,其他欄位
在影片類裡全部相同,宣告一列 profile 不需要「借」任何幾何。

再加上外部專案實機錄過的 3:2 6K 讀出(formats OG3.5K、FP3K),與 r69 凍結的
M7 那一組現在算出來等於原廠 UHD30 的預覽。不碰相機。
"""
import json
import struct
import sys

import imx410_profile as P

import pathlib

HERE = pathlib.Path(__file__).resolve().parent
ROOTDIR = HERE.parent.parent.parent
D = json.loads((ROOTDIR / "research/other/external/FP3K-technical-handoff-2026-09-10"
                "/analysis/firmware/raw-profiles.json").read_text())
BYROW = {r["index"]: r["words"] for r in D["rows"]}
BYID = {r["profile_ids"][0]: r["words"] for r in D["rows"]}
ROUTES = D["movie_routes"]
IMG = (ROOTDIR / "out/MAIN_c0000000.bin").read_bytes()
META, B = 0xC0B59DC0, 0xC0000000
BITS = {10: 8, 9: 10, 7: 12}


def mode_scale():
    out = {}
    for i in range(70):
        mid = struct.unpack_from("<I", IMG, META + i * 0x64 - B)[0]
        out[mid] = tuple(float(x) for x in struct.unpack_from("<2I", IMG, META + i * 0x64 - B + 0x4C))
    return out


SCALE = mode_scale()


def want_of(route):
    st = BYROW[route["profile_row"]]
    return P.Want(window=tuple(route["sensor_raster"]), rec=tuple(route["raw_dimensions"]),
                  act=tuple(route["crop"]),
                  zoom=tuple(z if z > 1024 else P.RWZM_UNITY_STOCK for z in route["zoom"]),
                  bits=BITS[st[0x84 // 4]], hirate=bool(st[0xB0 // 4]),
                  scale=SCALE[route["sensor_mode"]])


def test_reproduces_every_stock_movie_row():
    """p171 底 + 公式 = 原廠 78 組影片列,整列逐字(+0x30 除外)。"""
    base = BYID[171]
    assert len(ROUTES) == 78
    for r in ROUTES:
        st = BYROW[r["profile_row"]]
        got = P.declare(want_of(r), base)
        diff = [hex(i * 4) for i in range(65) if i * 4 != P.ENGINE_FPS and got[i] != st[i]]
        assert diff == [], (r["name"], r["profile_id"], diff)


def test_any_video_base_gives_the_same_row():
    """底列是哪一列影片 profile 都一樣 —— 公式以外的欄位在影片類全部相同。"""
    r = ROUTES[0]
    rows = {tuple(P.declare(want_of(r), BYROW[x["profile_row"]])[i] for i in range(65) if i * 4 != P.ENGINE_FPS)
            for x in ROUTES}
    assert len(rows) == 1


def test_stills_and_shell_bases_are_not_video():
    """p83(拍照類)與 p13(空殼)當底列也宣告出同一列:它們跟影片類不同的
    類別欄位(0x1C / 0x88 / 0x90 / 0xC0)都在公式裡,被改回影片類的值。"""
    video = BYID[171]
    for pid in (83, 13):
        got = P.declare(want_of(ROUTES[0]), BYID[pid])
        rest = [hex(i * 4) for i in range(65) if i * 4 != P.ENGINE_FPS and got[i] != P.declare(want_of(ROUTES[0]), video)[i]]
        assert rest == [], (pid, rest)      # 公式把它們的類別欄位改回影片類


def test_external_6k_32_readouts():
    """外部專案實機錄過的 3:2 6K 讀出:預覽 ÷3、不縮放,可見 2000x1334,
    光柵 2016x1344(FP3K 逐字;formats 寫 1345,差一行),producer = 預覽,
    錄影 RWZM 只改錄影那一對,視窗 = 讀出。"""
    for name, w, prev_h in (
            ("formats OG3.5K", P.Want(window=(6062, 4040), rec=(3464, 2308), act=(3456, 2308), zoom=(1792, 1792)), 1345),
            ("FP3K", P.Want(window=(6064, 4042), rec=(3032, 2020), act=(3000, 2000), zoom=(2048, 2048)), 1344)):
        row = P.declare(w, BYID[171])
        g = lambda o: row[o // 4]
        assert (g(0x20), g(0x28)) == (2000, 1334), name
        assert g(0x0C) == 2016 and abs(g(0x10) - prev_h) <= 1, name
        assert (g(0xD8), g(0xE0)) == (g(0x0C), g(0x10)), name
        assert (g(0x58), g(0xC4), g(0x60), g(0xD0)) == (1, 1, 1023, 1023), name
        assert (g(0x64), g(0xD4)) == w.zoom, name
        assert (g(0xF4), g(0xF8)) == w.window, name
        assert (g(0xDC), g(0xE4)) == w.rec, name


def test_r69_m7_previews_like_stock_uhd30():
    """r69 凍結的那一組(M7、rec 3872x2182、RWZM 1603/1601):宣告出來的預覽
    與原廠 UHD30(p171)相同 —— 預覽不再跟著錄影的 RWZM 撐大。"""
    row = P.declare(P.Want(window=(6064, 3412), rec=(3872, 2182), act=(3856, 2172), zoom=(1603, 1601)), BYID[171])
    st = BYID[171]
    for o in (0x0C, 0x10, 0x20, 0x28, 0x58, 0xC4, 0x60, 0xD0, 0xD8, 0xE0, 0xF4, 0xF8):
        assert row[o // 4] == st[o // 4], hex(o)


def test_preview_never_past_its_source():
    """預覽光柵(可見 + 邊距)不可以超過預覽來源 —— 原廠 78 組全部成立;
    r71 的 M98 RAW 違反了(1344 > 1341):LV 花屏、錄一格就停。
    掃全部 70 個 mode 的光柵、從最大輸出到一半,16:9 / 3:2 / 原生比例。"""
    for r in ROUTES:
        w = want_of(r)
        *_, src = P.preview_path(w)
        row = P.declare(w, BYID[171])
        assert row[0x10 // 4] <= src[1] and row[0x0C // 4] <= src[0], r["name"]
    seen = 0
    for i in range(70):
        rw, rh = struct.unpack_from("<2I", IMG, META + i * 0x64 - B + 4)
        if not rw or not rh:
            continue
        for frac in (1.0, 0.75, 0.5):
            for aw, ah in ((rw, rh), (16, 9), (3, 2)):
                ow = int((rw - 16) * frac) // 16 * 16
                oh = (ow * ah // aw) // 2 * 2
                if oh + 10 > rh or ow < 64 or oh < 64:
                    continue
                zh = max(1023, (rw * 1024) // (ow + 16))
                w = P.Want(window=(rw, rh), rec=(ow + 16, oh + 10), act=(ow, oh), zoom=(zh, zh))
                try:
                    *_, src = P.preview_path(w)
                except ValueError:
                    continue
                row = P.declare(w, BYID[171])
                assert row[0x10 // 4] <= src[1], (rw, rh, ow, oh, row[0x10 // 4], src)
                assert row[0x0C // 4] <= src[0], (rw, rh, ow, oh, row[0x0C // 4], src)
                seen += 1
    assert seen > 200, seen


def test_binned_record_lands_on_branch_c():
    """分支 C:錄影 bin 3x3 + 非 unity RWZM -> 預覽的 bin 與 RWZM 逐軸等於錄影的
    (FUN_c0325228 才會選 Hbin2 抽頭);來源仍在原廠預覽上限內。"""
    for window, z in (((6048, 4032), 1600), ((2016, 1344), 1600), ((6064, 3412), 2048)):
        rec = ((window[0] // 3 * 1024 // z) & ~15, (window[1] // 3 * 1024 // z) & ~1)
        row = P.declare(P.Want(window=window, rec=rec, act=(rec[0] - 16, rec[1] - 10), zoom=(z, z),
                               bin=(3, 3)), BYID[171])
        g = lambda o: row[o // 4]
        assert (g(0x58), g(0xC4)) == (g(0x5C), g(0xC8)) == (P.HBIN_E[3], P.HBIN_E[3]), window
        assert (g(0x60), g(0xD0)) == (g(0x64), g(0xD4)) == (z, z), window
        assert g(0x0C) <= P.PREVIEW_SRC_MAX + 16
    # 沒有 bin 時照舊:全寬讀出預覽 ÷3(分支 E),錄影 bin x1
    row = P.declare(P.Want(window=(6048, 4032), rec=(3864, 2580), act=(3848, 2570), zoom=(1600, 1600)), BYID[171])
    assert (row[0x58 // 4], row[0x5C // 4]) == (P.HBIN_E[3], P.HBIN_E[1])


def test_m98_raw_previews_inside_its_source():
    """r71 實機那一組:M98 RAW(3032x2012、預覽 1536)— 光柵 2016x1341,剛好等於來源。"""
    row = P.declare(P.Want(window=(3032, 2012), rec=(3024, 2012), act=(3008, 2002), zoom=(1023, 1023),
                           scale=(2.0, 2.0)), BYID[171])
    g = lambda o: row[o // 4]
    assert (g(0x60), g(0x0C), g(0x10), g(0x20), g(0x28)) == (1536, 2016, 1341, 2000, 1331)


def test_m98_half_size_preview_alignment_stays_inside_source():
    # Old ceil16 made a 1536-wide raster from a 1531-wide source.
    w = P.Want(window=(3032, 2012), rec=(1520, 1016), act=(1504, 1006),
               zoom=(2042, 2027), scale=(2.0, 2.0))
    *_, src = P.preview_path(w)
    row = P.declare(w, BYID[171])
    assert row[0x0C // 4] == 1520
    assert row[0x0C // 4] <= src[0] and row[0x10 // 4] <= src[1]


def test_m12_auto_previews_the_record_shape():
    """Frozen r78's user-verified isotropic preview, without changing RAW."""
    row = P.declare(P.Want(window=(2016, 672), rec=(1008, 672), act=(992, 662), zoom=(2048, 1023),
                           scale=(3.0, 6.0)), BYID[171])
    g = lambda o: row[o // 4]
    assert (g(0x58), g(0xC4), g(0x60), g(0xD0)) == (0, 0, 1023, 1023)
    assert (g(0x0C), g(0x10), g(0x20), g(0x28)) == (2000, 672, 1984, 662)
    assert (g(0x64),g(0xD4)) == (2048,1023)  # RAW output zoom is preserved


def test_standby_shows_what_recording_shows():
    """待機 LV 的可見範圍 = 錄影中 LV 顯示的那塊感測器區域(實機:M12 AUTO 按下錄影
    畫面放大 ~10 px —— 待機 2000x1334 保留 99.2%、錄影 992/1008 保留 98.4%)。
    方像素的組合換算成待機視窗的像素;扁像素回傳 None。"""
    cases = (
        (P.Want(window=(2016, 672), rec=(1008, 672), act=(992, 662), zoom=(2048, 1023), scale=(3.0, 6.0)), (1984, 1324)),
        (P.Want(window=(6064, 3412), rec=(6064, 3412), act=(6048, 3402), zoom=(1023, 1023)), (2000, 1125)),
        (P.Want(window=(3032, 2012), rec=(3024, 2012), act=(3008, 2002), zoom=(1023, 1023), scale=(2.0, 2.0)), (2000, 1331)),
        (P.Want(window=(4176, 2174), rec=(4176, 2174), act=(4160, 2164), zoom=(1023, 1023)), (1333, 693)),
        (P.Want(window=(2016, 672), rec=(2016, 672), act=(2000, 662), zoom=(1023, 1023), scale=(3.0, 6.0)), (2000, 1324)))
    for w, want in cases:
        assert P.standby_visible(w) == want, (w, P.standby_visible(w), want)
    # M12 AUTO: the standby region is the recorded one -- same share of the sensor
    w = cases[0][0]
    sw, sh = P.standby_visible(w)
    vw,vh=P.preview_visible(w,P.preview_path(w)[-1]);ph,pv=P.preview_factors(w)
    assert (sw,sh)==(vw*ph*3//3072,vh*pv*6//3072)


def test_partial_anisotropic_preview_preserves_record_factors():
    # A centre crop that does not hit source margins must still convert each
    # axis independently; full-height M12 hits the cap and could mask this bug.
    w=P.Want(window=(6064,3412),rec=(3872,2182),act=(1800,700),zoom=(1603,1601))
    assert P.preview_visible(w,P.preview_path(w)[-1])==(944,364)


def test_record_tap_keeps_zoom_and_bin_distinct():
    w=P.Want(window=(2016,2016),rec=(496,336),act=(480,326),zoom=(4096,2048),bin=(1,3))
    row=P.declare(w,BYID[171]);g=lambda o:row[o//4]
    assert (g(0x58),g(0xc4),g(0x60),g(0xd0))==(0,1,4096,2048)
    assert (g(0x0c),g(0x10),g(0x20),g(0x28))==(496,336,480,326)


def test_large_anisotropic_record_uses_a_bounded_stock_preview():
    w=P.Want(window=(4160,2174),rec=(2656,926),act=(2640,916),zoom=(1600,2400))
    assert not P.record_preview(w)
    assert P.preview_factors(w)==(2048,2048)


def test_independent_preview_alignment_stays_inside_source():
    w=P.Want(window=(3700,2600),rec=(2464,1330),act=(2448,1320),zoom=(1536,2000))
    row=P.declare(w,BYID[171]);source=P.preview_path(w)[-1]
    assert row[0x0c//4]<=source[0] and row[0x10//4]<=source[1]


def test_binned_preview_cap_preserves_the_transformed_aspect():
    # Only vertical binning, unequal factors. A 2000-wide preview cap must
    # shrink both PREVIEW axes by the same amount; record factors cancel.
    w=P.Want(window=(4176,2174),rec=(2080,724),act=(2064,714),
             zoom=(2048,1023),bin=(1,3))
    row=P.declare(w,BYID[171])
    assert P.preview_factors(w)==(2048,3072)
    assert (row[0x20//4],row[0x28//4])==(2000,691)
    assert abs(row[0x28//4]/714 - row[0x20//4]/2064) < 1/714


MUTATIONS = {
    "unequal no-bin preview regresses to r77": ("return w.bin != (1, 1) and", "return (w.bin != (1, 1) or rh != rv) and"),
    "record preview decomposes zoom as binning": ("    if record_preview(w):\n        # Preserve", "    if False:\n        # Preserve"),
    "cap ignores preview axis ratio": ("cap * ah // aw", "(cap * w.act[1] // w.act[0]) * fv // fh"),
    "no snap": ("            if abs(vh - known) <= 4 and known <= sh:", "            if False:"),
    "snap past the source": ("            if abs(vh - known) <= 4 and known <= sh:", "            if abs(vh - known) <= 4:"),
    "margin 16x8": ("PREVIEW_MARGIN = (16, 10)", "PREVIEW_MARGIN = (16, 8)"),
    "preview from the larger record factor": ("    f = min(rh, rv)", "    f = max(rh, rv)"),
    "no branch C": ("    return w.bin != (1, 1) and w.window[0] * 1024 // rh <= PREVIEW_SRC_MAX", "    return False"),
    "visible ignores the record factors": ("    aw, ah = w.act[0] * fh // ph, w.act[1] * fv // pv", "    aw, ah = w.act[0], w.act[1]"),
    "dc/e4 only rec at hirate": ("    put(0xDC, w.rec[0]); put(0xE4, w.rec[1])", "    pass"),
    "0x38 always 1": ("    put(0x38, 16 if binh == HBIN_E[3] else 1)", "    put(0x38, 1)"),
    "preview ceil16 past source": ("    if vw > sw // 16 * 16:", "    if False:"),
}


def test_every_mutation_is_caught():
    import importlib.util
    src = (HERE / "imx410_profile.py").read_text()
    global P
    keep = P
    try:
        for name, (old, new) in MUTATIONS.items():
            assert src.count(old) == 1, name
            spec = importlib.util.spec_from_loader("imx410_profile_mut", loader=None)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod            # dataclass 要找得到自己的模組
            exec(src.replace(old, new), mod.__dict__)
            P = mod
            caught = False
            for t in (test_reproduces_every_stock_movie_row, test_external_6k_32_readouts,
                      test_r69_m7_previews_like_stock_uhd30, test_preview_never_past_its_source,
                      test_m98_raw_previews_inside_its_source, test_m12_auto_previews_the_record_shape,
                      test_partial_anisotropic_preview_preserves_record_factors,
                      test_record_tap_keeps_zoom_and_bin_distinct,
                      test_large_anisotropic_record_uses_a_bounded_stock_preview,
                      test_independent_preview_alignment_stays_inside_source,
                      test_binned_record_lands_on_branch_c,
                      test_binned_preview_cap_preserves_the_transformed_aspect,
                      test_m98_half_size_preview_alignment_stays_inside_source):
                try:
                    t()
                except (AssertionError, ValueError, ZeroDivisionError):
                    caught = True
            assert caught, f"mutation not caught: {name}"
    finally:
        P = keep


def _run():
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
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
