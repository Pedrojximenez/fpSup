#!/usr/bin/env python3
"""§8.6 的「mode 決定其他軸」模型。

反灰是這一層的**唯一**輸出,所以每條規則都要有測試擋著 ——
尤其是「自動 = 全開」那一條:它不是設計上的選擇,是**算出來剛好成立**的
(70 個模式的合法集合聯集正好等於選單全部)。模式表哪天變了,
這個測試要先叫,而不是使用者在相機上看到一個永遠選不到的選項。

    python3 test_imx410_menu.py
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import imx410_menu as M
import imx410_plan as PL
from imx410_full import CLOCK, RATES, Registry

REG = Registry()
IMG = PL.FIRMWARE.read_bytes()


def test_solver_menu_includes_raw14_and_tenth_rate():
    options = M.bit_options(REG)
    assert [o["bit"] for o in options if o["usable"]] == [8, 10, 12, 14]
    rows = M.fps_options(REG, 12)
    assert tuple(row["rate"] for row in rows) == M.MENU_RATES
    assert rows[-1]["rate"] == "240" and rows[-1]["usable"]
    raw14 = M.fps_options(REG, 14)
    assert next(row for row in raw14 if row["rate"] == "24")["usable"]
    assert not next(row for row in raw14 if row["rate"] == "240")["usable"]


def test_mode_axis_zero_means_auto_so_acq_cannot_be_forced():
    """哨兵是 0,而 **mid 0 = ACQ 也是實體模式** —— 既有的碰撞,釘住它。

    主機 `imx410_block` 與相機 `og3krecipe.S` 都把 `A_MODE == 0` 讀成
    「不指定」,所以 ACQ 指定不了。今天不痛(ACQ 上限 19.55p,低於選單
    最低的 23.98),但補了更低的格率列舉之後就會咬人。要修得動 AXIS 語意。
    """
    assert M.MODE_AUTO == 0
    assert 0 in REG.by_id and REG.by_id[0].name == "ACQ"
    # 主機端的「不指定」判斷就是一個真值測試,所以 0 永遠走 auto
    from imx410_block import A_MODE, axis_words
    w = axis_words(bit=12, rate="30", raster=(3032, 2012), mode=0)
    assert w[A_MODE] == 0


def test_auto_greys_nothing_and_that_is_not_an_approximation():
    """70 個模式的聯集**正好**等於選單全部,所以「自動」下一個都不用灰。

    這是算出來的巧合,不是設計。模式表變了就可能不再成立 —— 那時候
    「自動」就得開始反灰,這個測試會先告訴我們。
    """
    bits, rates = M.mode_legal(REG, M.MODE_AUTO)
    assert bits == M.MENU_BITS, bits
    assert rates == M.MENU_RATES, rates
    en = M.menu_enabled(REG, M.MODE_AUTO)
    assert all(en["B2_5_2"]) and all(en["B2_5_5"])


def test_standby_mode_eight_would_contradict_fully_open():
    """使用者原本想拿待機的 mid 8 當預設 —— 那會自相矛盾,把理由釘住。

    mid 8 = MONIT1_60,2016x1344 3x3 **RAW12**。拿它當預設的話
    14-bit 與 240 fps 都得反灰,就不是「全開」了。
    """
    m = REG.by_id[8]
    assert m.depth == 12 and m.scale == (3, 3)
    bits, rates = M.mode_legal(REG, 8)
    assert 14 not in bits
    assert "240" not in rates


def test_rate_ceiling_is_the_blanking_budget_not_a_table():
    """格率的可用性是算出來的:hmax * 行數 要塞得進一格的時間。"""
    for mid in (8, 95, 117):
        m = REG.by_id[mid]
        _, rates = M.mode_legal(REG, mid)
        for k in M.MENU_RATES:
            fits = m.hmax * m.raw[1] < CLOCK / RATES[k]
            assert (k in rates) == fits, (mid, k, fits)


def test_fourteen_bit_modes_offer_only_fourteen():
    for m in REG.modes:
        if m.mid == M.MODE_AUTO:
            continue          # 0 是哨兵,問不到 ACQ —— 見上面那個測試
        bits, _ = M.mode_legal(REG, m.mid)
        assert bits == ((14,) if m.depth == 14 else (8, 10, 12)), (m.mid, bits)


def test_open_gate_fourteen_bit_has_no_legal_menu_rate():
    """ACQ 6064x4042 RAW14 的上限是 19.55p,而選單最低 23.98 —— 一個都選不到。

    這不是 bug,是行時間(hmax 911)的物理限制,§4.4 記著。
    ACQ 的 mid 撞上哨兵,所以直接用它的消隱預算算,不經 mode_legal。
    """
    m = REG.by_id[0]
    assert m.name == "ACQ"
    fits = [k for k in M.MENU_RATES if m.hmax * m.raw[1] < CLOCK / RATES[k]]
    assert fits == [], fits


def test_csv_set_enabled_keeps_the_length_and_flips_both_columns():
    base = PL.bit_row_csv(IMG, PL.BIT_ROW_CSV[0][0])
    out = PL.csv_set_enabled(base, (True, False, True, False))
    assert len(out) == len(base)
    lines = [l for l in out[3:].split(b"\r\n") if l]
    hdr = lines[0].split(b",")
    c1, c2 = hdr.index(b"Enabled"), hdr.index(b"Enabled2")
    got = [(r.split(b",")[c1], r.split(b",")[c2]) for r in lines[1:]]
    assert got == [(b"1", b"2"), (b"0", b"0"), (b"1", b"2"), (b"0", b"0")], got


def test_csv_set_enabled_refuses_a_wrong_row_count():
    base = PL.bit_row_csv(IMG, PL.BIT_ROW_CSV[0][0])
    try:
        PL.csv_set_enabled(base, (True, True))
    except SystemExit:
        return
    raise AssertionError("列數不符竟然沒有被擋下來")


def test_a_chosen_mode_greys_everything_it_cannot_do():
    """端到端:選了 MONIT1_24_HD(5712x3216 RAW14 @24)之後只剩 14-bit 與 23.98/24。"""
    en = M.menu_enabled(REG, 95)
    assert en["B2_5_2"] == (False, False, False, True)
    assert en["B2_5_5"] == (True, True) + (False,) * 8
    for name, res in (("B2_5_2", PL.BIT_ROW_CSV[0][0]),
                      ("B2_5_5", PL.RATE_ROW_CSV[0][0])):
        base = (PL.bit_row_csv if name == "B2_5_2" else PL.rate_row_csv)(IMG, res)
        out = PL.csv_set_enabled(base, en[name])
        assert len(out) == len(base), name


def test_media_never_gates_the_menu():
    """使用者 2026-09-29 決定:反灰只擋物理做不到的,不擋卡速。

    原廠依媒體把 100 / 119.88 在 SD 上反灰;我們壓住那顆之後**不接管這個
    判斷**。撐住這個決定的是 §10 的實機證據:資料率不夠時是乾淨停止,
    不是毀檔。所以它是「要不要冒險」而不是「不准」。
    """
    assert M.MEDIA_GATING is False
    # API 裡根本沒有媒體這個輸入 —— 不是忘了接,是刻意不接
    import inspect
    assert set(inspect.signature(M.mode_legal).parameters) == {"reg", "mode"}
    assert set(inspect.signature(M.menu_enabled).parameters) == {"reg", "mode"}
    # 若有媒體閘門,SD 下這三個會被拿掉
    _, rates = M.mode_legal(REG, M.MODE_AUTO)
    for k in ("100", "120", "240"):
        assert k in rates, k


def test_the_frame_rate_class_hook_is_installed_and_stock_is_pinned():
    """Native execution/guard tests live in test_imx410_rate_native.py."""
    import struct
    assert PL.WITH_FRCLASS and PL.WITH_RATE_NATIVE
    installed = {a: v for a, v, _ in PL.plan()}
    spec = next(h for h in PL.RATE_NATIVE.HOOKS if h[0] == PL.FRCLASS_HOOK)
    assert installed[PL.FRCLASS_HOOK] == PL._b(spec[0], spec[1])
    got = struct.unpack_from("<I", IMG, PL.FRCLASS_HOOK - 0xC0000000)[0]
    assert got == PL.FRCLASS_STOCK, hex(got)


def test_the_tenth_rate_row_is_open_in_the_full_variant():
    """全開變體裡第十列(240)必須是可選的 —— 那是我們唯一要維護的那一份。"""
    csv = PL.rate_row_csv(IMG, PL.RATE_ROW_CSV[0][0])
    lines = [l for l in csv[3:].split(b"\r\n") if l]
    hdr = lines[0].split(b",")
    c1, c2 = hdr.index(b"Enabled"), hdr.index(b"Enabled2")
    rows = lines[1:]
    assert len(rows) == 10
    f = rows[9].split(b",")
    assert (f[c1], f[c2]) == (b"1", b"2"), rows[9]



def _rate_flags(csv):
    lines = [l for l in csv[3:].split(b"\r\n") if l]
    hdr = lines[0].split(b",")
    c1, c2 = hdr.index(b"Enabled"), hdr.index(b"Enabled2")
    return [(r.split(b",")[c1], r.split(b",")[c2]) for r in lines[1:]]


def test_all_rate_variants_are_fully_open():
    """使用者 2026-09-30「先全開」:六個變體每一列都是 1,2。

    反灰與「無法選擇」對話框只由變體 CSV 決定(實機 A/B,
    res-lab/validation/20260930-rate-reject-ab),類別 hook 管不到。
    """
    saved, PL.WITH_RATE_ALL_OPEN = PL.WITH_RATE_ALL_OPEN, True   # 2026-10-02 起預設關
    try:
        rows = [(nm, PL.rate_row_csv(IMG, res)) for res, _desc, nm in PL.RATE_ROW_CSV]
    finally:
        PL.WITH_RATE_ALL_OPEN = saved
    for nm, csv in rows:
        assert _rate_flags(csv) == [(b"1", b"2")] * 10, (nm, _rate_flags(csv))
        assert csv.endswith(b"\r\n") and len(csv) <= PL.RATE_ROW_SLOT, nm


def test_turning_all_open_off_restores_stock_greying():
    """關掉開關要回到原廠反灰 —— 否則「全開」其實是別的東西造成的。"""
    saved, PL.WITH_RATE_ALL_OPEN = PL.WITH_RATE_ALL_OPEN, False
    try:
        excl4 = next(r for r, _d, n in PL.RATE_ROW_CSV if n == "B2_5_5_excl4")
        got = _rate_flags(PL.rate_row_csv(IMG, excl4))
    finally:
        PL.WITH_RATE_ALL_OPEN = saved
    # 只到 59.94:100 / 119.88 灰,第十列 240 繼承第九列也灰
    assert got == [(b"1", b"2")] * 7 + [(b"0", b"0")] * 3, got


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
