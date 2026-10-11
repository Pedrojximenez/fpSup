#!/usr/bin/env python3
"""imx410_plan 的配置與順序檢查。

位址是手挑的,所以每一條規則都要有測試擋著,而且**檢查器自己要被驗**:
故意擺一個重疊、故意把 hook 排到 payload 前面,檢查器沒抓到就是它壞了。

    python3 test_imx410_plan.py
"""
from __future__ import annotations

import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import imx410_plan as PL
from imx410_block import AXIS_WORDS, RECIPE_WORDS
from imx410_full import FIRMWARE

IMG = FIRMWARE.read_bytes()
B = 0xC0000000


def test_layout_is_clean():
    assert PL.layout_errors() == []


def test_hooks_are_stock_in_the_image():
    assert PL.hook_errors(IMG) == []


def test_frame_rate_hook_rejects_a_nonstock_instruction():
    mutant = bytearray(IMG)
    struct.pack_into("<I", mutant, PL.RAT_HOOK - B, 0xE1A00000)
    assert any(hex(PL.RAT_HOOK) in error for error in PL.hook_errors(mutant))


def test_order_is_clean():
    assert PL.order_errors() == []


def test_nothing_lands_on_a_reused_og3k_region():
    """全功能版仍要用 og3k_plan 的 sel/name/aspect/out/gs/fmt/restore/fps。

    第一版的 og3krecipe 就壓在 NAME(解析度名字串)與 FPS_CODE 上。
    """
    reused = PL._reused_regions()
    assert reused, "禁區清單是空的 —— 推導壞了"
    for lo, hi, name in PL.regions():
        for f0, f1 in reused:
            assert not (lo < f1 and f0 < hi), \
                f"{name} [{lo:#x},{hi:#x}) 壓到 og3k_plan 的 [{f0:#x},{f1:#x})"


def test_payload_constants_match_the_layout():
    """payload 裡編進去的位址,必須等於計畫真的寫過去的位址。

    這兩邊各有一份常數,漂掉的話 payload 會去讀一塊沒人寫過的記憶體 ——
    而且完全不會報錯,只會行為怪異。
    """
    bl = PL.blobs()

    def has_movw_movt(blob, value):
        lo, hi = value & 0xFFFF, value >> 16
        ws = [struct.unpack_from("<I", blob, i)[0]
              for i in range(0, len(blob) - 4, 4)]
        imm = lambda w: ((w >> 4) & 0xF000) | (w & 0xFFF)
        for i, w in enumerate(ws[:-1]):
            if w & 0x0FF00000 == 0x03000000 and imm(w) == lo:
                rd = (w >> 12) & 0xF
                for nxt in ws[i + 1:i + 6]:
                    if (nxt & 0x0FF00000 == 0x03400000 and imm(nxt) == hi
                            and (nxt >> 12) & 0xF == rd):
                        return True
        return False

    for value, label, who in (
            (PL.AXIS, "AXIS", "og3krecipe"),
            (PL.RECIPE, "RECIPE", "og3krecipe"),
            (PL.RATETAB, "RATETAB", "og3krecipe"),
            (PL.TMGTAB, "TMGTAB", "og3krecipe"),
            (PL.CTMPL, "CTMPL", "og3krecipe"),
            (PL.CANVAS, "CANVAS", "og3krecipe"),
            (PL.ASPTAB, "ASPTAB", "og3krecipe"),
            (PL.RECIPE, "RECIPE", "imx410_aspect"),
            (PL.RECIPE, "RECIPE", "imx410_fmt"),
            (PL.RECIPE_CODE, "RECIPE_CODE", "imx410_fmt"),
            (PL.ENTRY_ADDR, "ENTRY", "imx410_fmt"),
            (PL.CANVAS, "CANVAS", "imx410_canvas")):
        assert has_movw_movt(bl[who], value), \
            f"{who} 裡找不到 {label} = {value:#x}"


def test_hook_branches_point_at_the_payloads():
    """四個 hook 都要指對,而且**用對的指令**。

    長寬比那兩個是 B 不是 BL:payload 用 bx ip 自己回去,用 BL 會蓋掉呼叫端
    的 lr。
    """
    items = PL.plan()
    HOOKS = ((PL.PIK_HOOK, PL.FMT_CODE, 0xEA),   # B —— 見 test_branch_kind_matches_og3k_plan
             (PL.ROW_HOOK, PL.CANVAS_CODE, 0xEB),
             (PL.ASP_HOOK, PL.ASP_CODE, 0xEA),
             (PL.ASP2_HOOK, PL.ASP2_CODE, 0xEA),
             (PL.GS_HOOK, PL.GS_CODE, 0xEA),
             *(((PL.RNG_HOOK, PL.RNG_CODE, 0xEA),) if PL.WITH_RANGE else ()),
             (PL.SEL_HOOK, PL.SEL_CODE, 0xEA),
             (PL.NAM_HOOK, PL.NAME_CODE, 0xEA),
             (PL.OFM_HOOK, PL.OGFMT_CODE, 0xEA),
             *(((PL.RAT_HOOK, PL.RATE_CODE, 0xEA),) if PL.WITH_RATE else ()),
             (PL.OUT_HOOK, PL.OUT_CODE, 0xEA)) + tuple(
                 (a, PL.FPS_CODE, 0xEB) for a, _, _ in PL.FPS_HOOKS) + tuple(
                 (a, target, 0xEA) for a, target, _, _, _ in PL.RATE_NATIVE.HOOKS
                 if PL.WITH_RATE_NATIVE and a not in PL.RATE_NATIVE.NOT_ARMED) + (
                 ((PL.SELLOG.SITE, PL.SELLOG.CODE, 0xEA),) if PL.WITH_SEL_LOG else ())
    tail = {a: v for a, v, _ in items[-len(HOOKS):]}
    assert len(tail) == len(HOOKS), tail
    for hook, target, op in HOOKS:
        v = tail[hook]
        assert v >> 24 == op, (hex(hook), hex(v), hex(op))
        off = v & 0xFFFFFF
        off -= 0x1000000 if off & 0x800000 else 0
        assert hook + 8 + off * 4 == target, (hex(hook), hex(target))


def test_aspect_variants_differ_only_in_back():
    """同一份原始碼組兩次,只有回跳位址不同 —— 別的都一樣才算真的共用。"""
    bl = PL.blobs()
    a, b = bl["imx410_aspect"], bl["imx410_aspect2"]
    assert len(a) == len(b)
    diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    assert len(diff) == 1, diff          # 只有 BACK 的低位元組
    assert PL.ASP2_HOOK - PL.ASP_HOOK == b[diff[0]] - a[diff[0]]


def test_axis_written_before_the_payloads():
    """og3krecipe 一被叫到就讀 AXIS,所以初值要先就位。"""
    items = PL.plan()
    axis_at = max(i for i, (a, _, _) in enumerate(items)
                  if PL.AXIS <= a < PL.AXIS + AXIS_WORDS * 4)
    code_at = min(i for i, (a, _, _) in enumerate(items)
                  if PL.RECIPE_CODE <= a < PL.RECIPE_CODE + 4)
    assert axis_at < code_at


def test_branch_kind_matches_og3k_plan():
    """★ 每一個共用的 hook 點,B/BL 必須與 og3k_plan.HOOKS 一致。

    2026-09-28 上機:picker 我用了 BL,og3k_plan 寫的是 B。BL 會把 lr 蓋成
    hook 的下一條位址;pass 路徑還原它之後,位移的原廠 push 就把「跳回自己
    第二條指令」當成返回位址存起來 —— 原廠函式 pop {...,pc} 跳回自己中間,
    每一次查詢都如此,相機 3 秒內死。

    這種事不該靠我挑對,要靠比對。
    """
    import og3k_plan as P
    want = {site: kind for site, _code, _stock, kind, _note in P.HOOKS}
    got = {}
    for _name, group in PL._stages():
        for site, _target, op, _note in group:
            got[site] = op
    shared = set(want) & set(got)
    assert len(shared) >= 10, f"只比對到 {len(shared)} 個共用 hook"
    bad = [(hex(s), got[s], want[s]) for s in sorted(shared) if got[s] != want[s]]
    assert not bad, bad
    assert got[PL.PIK_HOOK] == "b", "picker 必須是 B"


def test_payloads_only_touch_owned_cave():
    """★ payload 組出來的每一個 cave 位址,都要落在計畫擁有的區域裡。

    2026-09-28 上機抓到:`imx410_fmt.S` 的 `.equ HITS, 0xC0730700` 是寫死的,
    計畫沒傳 HITS —— 而 0xC0730700 落在 **imx410_aspect2 的 payload 裡**。
    每一次 picker 命中都會遞增一個活著的指令。當時還沒爆只因為 FLAG=0、
    一次都沒命中過。

    `test_payload_constants_match_the_layout` 抓不到:它只驗「計畫傳的常數有
    出現在 blob 裡」,不管 payload 自己還指了哪些地方。這一個是反向的。
    """
    import struct

    def cave_consts(blob):
        ws = [struct.unpack_from("<I", blob, i)[0]
              for i in range(0, len(blob) - 4, 4)]
        imm = lambda w: ((w >> 4) & 0xF000) | (w & 0xFFF)
        out = set()
        for i, w in enumerate(ws[:-1]):
            if w & 0x0FF00000 == 0x03000000:
                rd = (w >> 12) & 0xF
                for nx in ws[i + 1:i + 6]:
                    if nx & 0x0FF00000 == 0x03400000 and (nx >> 12) & 0xF == rd:
                        out.add((imm(nx) << 16) | imm(w))
                        break
        # 只看 4 位元組對齊的 —— 未對齊的一定是掃描器把兩條無關指令
        # 湊成一對的偽陽性(例:0xC07307D2)。
        return {v for v in out
                if PL.CAVE_LO <= v < PL.CAVE_HI and v % 4 == 0}

    regions = PL.regions()
    bad = []
    for name, blob in PL.blobs().items():
        for v in sorted(cave_consts(blob)):
            if not any(lo <= v < hi for lo, hi, _ in regions):
                bad.append(f"{name} 指向 {v:#010x},沒有任何區域擁有它")
            else:
                owner = next(n for lo, hi, n in regions if lo <= v < hi)
                starts = {addr: n for n, _, addr in PL.payloads()}
                others = {n for n, _, _ in PL.payloads()} - {name}
                # 指到別人 payload 的**進入點**是呼叫,合法;指到中間就是
                # 把別人的指令當資料用 —— HITS 那個 bug 就是這樣。
                if owner in others and v != [a for a, n in starts.items()
                                             if n == owner][0]:
                    bad.append(f"{name} 指向 {v:#010x},那是 {owner} 的 payload 中間")
    assert not bad, "\n  ".join([""] + bad)


def test_preview_height_follows_the_recipe():
    """★ 待機預覽的可見高要跟著配方的顯示比,不能寫死。

    2026-09-28 上機:分組表設 0 組 -> 長寬比 hook 報 3:2,而六個預覽 profile
    仍宣告 2000x1125(16:9)-> **畫面被拉長**。og3k 寫死 1334 是因為它永遠
    3:2;我們不是。
    """
    from imx410_block import axis_words
    # 16:9 要**正好**等於原廠值 —— 那是唯一一個已知good的數字
    assert PL.preview_visible_height(
        axis_words(bit=12, rate="48", raster=(3032, 1708))) == PL.PREV_STOCK_H
    # 3:2 要等於 og3k 用的 1334
    assert PL.preview_visible_height() == 1334
    # 更方的比例夾在上限(左右留黑,而不是拉長)
    assert PL.preview_visible_height(
        axis_words(bit=12, rate="30", raster=(3032, 2012),
                   crop=(2656, 2000))) == PL.PREV_MAX_H

    items = {a: v for a, v, _ in PL.plan()}
    assert items[PL.GTAB] == 2, "分組表兩組:可見高、可見寬"
    g1 = PL.GTAB + 16 + len(PL.PREV_PROFILES) * 4
    assert (items[g1], items[g1 + 4], items[g1 + 8]) == (len(PL.PREV_PROFILES), 2000, 2000)
    assert tuple(items[g1 + 12 + 4 * i] for i in range(6)) == PL.prev_width_addrs()
    assert items[PL.GTAB + 4] == len(PL.PREV_PROFILES)
    assert items[PL.GTAB + 8] == PL.preview_visible_height()
    assert items[PL.GTAB + 12] == PL.PREV_STOCK_H, "未選值必須是原廠 —— 那六個是 FHD 共用的"
    for i, a in enumerate(PL.PREV_PROFILES):
        assert items[PL.GTAB + 16 + i * 4] == a


def test_armed_hooks_are_a_subset_of_og3k():
    """★ 不要武裝「能用的產品」沒武裝的東西。

    2026-09-28:我們與 OG3K 的武裝清單逐一比對,**唯一多出來的是範圍檢查
    0xC043D258**,而唯一失敗的步驟就是錄影。OG3K 的 WITH_RANGE 是 False
    而它錄得起來。反編譯顯示那顆是管線分派器十六個範圍測試之一,
    第一個命中的決定用哪一條管線 —— 錄影路徑也會走。

    要多加一顆就要有明確的旗標和單獨的驗證,不能順手打開。
    """
    import json
    import os
    import subprocess
    src = ("import sys;sys.path.insert(0,'.');import og3k_plan as P,json;"
           "print(json.dumps([h[0] for h in P.HOOKS]))")
    r = subprocess.run([sys.executable, "-c", src],
                       cwd=str(pathlib.Path(__file__).resolve().parent),
                       capture_output=True, text=True,
                       env={**os.environ, "OG_TARGET": "og3k"})
    og = set(json.loads(r.stdout))
    ours = {site for _n, g in PL._stages() for site, _t, _o, _x in g}
    extra = ours - og
    # ★ 允許的例外必須逐顆列名,而且要有旗標 —— 不是把這條測試放寬。
    #   容器格率 hook(FUN_c00c9bd0)是 OG3K 沒有的站點,理由與單獨驗證
    #   寫在 imx410_plan.WITH_RATE 的註解裡。
    allowed = {PL.RAT_HOOK} if PL.WITH_RATE else set()
    if PL.WITH_RATE_NATIVE:
        # Dedicated guards/ABI/native roundtrips: test_imx410_rate_native.py.
        allowed.update(site for site, _, _, _, _ in PL.RATE_NATIVE.HOOKS)
    if PL.WITH_SEL_LOG:
        # 診斷:路徑選擇器紀錄(imx410_sellog,原廠先跑、只寫自己的紀錄區)
        allowed.add(PL.SELLOG.SITE)
    if PL._with_binfilt():
        # x3 Soft / Sharp 縮減核(imx410_binfilt;test_imx410_binfilt.py)
        allowed.update(site for site, _, _ in PL.BINFILT.SITES)
    assert extra <= allowed, ("武裝了 OG3K 沒有、也沒列進例外的 hook:"
                              + ", ".join(hex(a) for a in sorted(extra - allowed)))


def test_payload_profile_matches_the_plan():
    """★ payload 裡的 PROFILE 必須等於計畫挑的那一個。

    2026-09-28:計畫算出 p83,但 imx410_fmt.S / imx410_canvas.S 的
    `#ifndef PROFILE .equ PROFILE, 13` 從來沒被覆寫 —— 整個 donor 選擇的
    改動根本沒到相機上,那一輪測的還是 p13。

    `test_payloads_only_touch_owned_cave` 抓不到,因為 13 不是位址。
    非位址的常數要另外比對。
    """
    d = PL.defines()
    for name in ("imx410_fmt", "imx410_canvas"):
        got = [x for x in d[name] if x.startswith(("PROFILE=", "PROFILE_ID="))]
        assert got == [f"PROFILE_ID={PL.PROFILE_ID:#x}"], (name, got)
        src = pathlib.Path(f"{name}.S").read_text()
        assert '#error "PROFILE_ID comes from imx410_plan"' in src, f"{name}.S 沒有擋住缺少 PROFILE_ID"
        assert "#PROFILE" not in src, f"{name}.S 還有寫死的 profile id"
    # 2026-10-04 起 id 是私有的:計畫公布 87,mapping[87] 指向引擎挑的底列
    from imx410_block import R_RECH, R_RECW, expected_recipe, pick_profile
    r = expected_recipe(PL.Registry(), PL.INITIAL_AXIS)
    assert PL.PROFILE == pick_profile((r[R_RECW], r[R_RECH]))[0]
    items = {a: v for a, v, _ in PL.plan()}
    img = PL.FIRMWARE.read_bytes()
    assert items[PL.PROFILE_ID] == PL.PRIVATE_PROFILE
    assert 0 < PL.PROFILE_ID - PL.RECIPE < 4096          # imx410_fmt 以 [r7, #偏移] 讀它
    assert PL._img_word(img, PL.MAPPING + PL.PRIVATE_PROFILE * 4) == 0xFFFFFFFF    # 原廠空槽
    assert items[PL.MAPPING + PL.PRIVATE_PROFILE * 4] == PL._img_word(img, PL.MAPPING + PL.PROFILE * 4)


def test_menu_keeps_three_rows():
    """UHD/FHD 只能用 Enabled 開關(預設開),**不能刪列**。

    刪列會讓 enum 重新編號(enum<->列 配對表是照列數建的),og3ksel 的
    `cmp r1,#4` 就會選到別的東西。
    """
    csv = PL._CSV
    rows = [l for l in csv[3:].split(b"\r\n") if l]
    assert len(rows) == 4, rows                 # 標頭 + 3 列
    flags = b"1,2" if PL.WITH_RES_STOCK_ROWS else b"0,0"   # 2026-10-02 起預設保留
    assert rows[1] == b"1,0313,blank," + flags, rows[1]   # UHD 沒有被刪掉
    assert rows[2] == b"2,0314,blank," + flags, rows[2]   # FHD
    assert rows[3].startswith(b"3,CUSTOM,"), rows[3]
    assert len(csv) <= PL.CSV_SLOT, len(csv)


def test_name_string_is_cust():
    """picker 的鍵前綴 = 解析度名。標籤比對是一個 32-bit 字,所以只能四字元。"""
    items = {a: v for a, v, _ in PL.plan()}
    assert items[PL.NAME] == int.from_bytes(b"CUST", "little")


def test_result_blocks_start_cleared():
    """故障安全:valid=0、畫布對數 0 = 還沒算出配方。"""
    items = {a: v for a, v, _ in PL.plan()}
    assert items[PL.RECIPE + 9 * 4] == 0, "valid 開機值要是 0"
    assert items[PL.CANVAS] == 0, "畫布對數開機值要是 0"


def test_plan_is_deterministic():
    assert PL.plan() == PL.plan()


# ---- 檢查器自己會不會抓 ----------------------------------------------------
def test_overlap_checker_catches_an_overlap():
    old = PL.CANVAS
    try:
        PL.CANVAS = PL.RECIPE          # 故意重疊
        assert PL.layout_errors(), "重疊沒被抓到"
    finally:
        PL.CANVAS = old
    assert PL.layout_errors() == []


def test_forbidden_checker_catches_a_reused_region():
    old = PL.CANVAS_CODE
    try:
        import og3k_plan as P
        # 禁區現在只剩**回放那組**(還沒接,位置留著)。其餘 og3k_plan 的
        # payload 都由這份計畫自己擺,拿它們當樣本會報成「重疊」不是「禁區」。
        PL.CANVAS_CODE = P.PBSEL_CODE  # 壓到 og3kpbsel(回放,位置保留中)
        assert any("禁區" in e for e in PL.layout_errors()), PL.layout_errors()
    finally:
        PL.CANVAS_CODE = old
    assert PL.layout_errors() == []


def test_order_checker_catches_hook_before_payload():
    items = PL.plan()
    hook = items[-1]
    bad = [hook] + [it for it in items if it is not hook]
    assert PL.order_errors(bad), "hook 排在 payload 之前卻沒被抓到"


def test_shell_scratch_is_off_limits():
    """0xC072F800..FE00 是 USB shell 的檔案傳輸暫存區。2026-09-12 畫布 hook
    指著那裡,每一次 getfile/putfile 都覆寫它 -> 相機凍結。"""
    old = PL.CANVAS_CODE
    try:
        PL.CANVAS_CODE = 0xC072F900
        assert PL.layout_errors(), "shell 暫存區沒被擋"
    finally:
        PL.CANVAS_CODE = old


# ---- 選單第四列 14 bit ------------------------------------------------------

def test_bit_depth_pair_table_already_has_the_fourteen_bit_row():
    """位元深度的 enum<->列 配對表**原廠就有四筆**,不用搬表。

    這是這一列之所以便宜的全部理由 —— 格率那張(0xC2E44EE4)九筆零預留,
    要動 §8.3 那招;這張原廠就留好了。見 §4.1。
    """
    pairs = struct.unpack_from("<8I", IMG, 0xC2E401CC - B)
    assert list(zip(pairs[0::2], pairs[1::2])) == [(4, 0), (3, 1), (0, 2), (1, 3)]


def test_fourteen_bit_label_is_a_stock_string_id():
    """字串 0308 = "14 bit" 原廠就在語言表裡,接在 0305/0306/0307 之後。

    所以 TEXT 欄放的是資源 ID 而不是字面字串 —— 字面字串不會跟著語言切換。
    """
    import re
    assert PL.BIT_ROW_TEXT == b"0308"
    pat = re.compile(rb"0308\x00([\x20-\x7e]{1,20})\x00")
    hits = {m.group(1) for m in pat.finditer(IMG)}
    assert b"14 bit" in hits, hits


def test_bit_row_csv_fits_the_slot_and_inherits_enabled():
    for res, desc, nm in PL.BIT_ROW_CSV:
        csv = PL.bit_row_csv(IMG, res)
        assert len(csv) <= PL.BIT_ROW_SLOT, (nm, len(csv))
        rows = [l for l in csv[3:].split(b"\r\n") if l]
        assert len(rows) == 5, (nm, rows)          # 標頭 + 四列
        assert rows[4].startswith(b"4,0308,"), rows[4]
        # 第四列的 Enabled/Enabled2 必須逐字等於第三列的
        assert rows[4].split(b",")[4:] == rows[3].split(b",")[4:], (nm, rows[3:])


def test_every_generated_csv_keeps_its_trailing_crlf():
    """★ 結尾 CRLF 不能省 —— 上機驗過,少了它最後一列不會被畫出來(§8.9)。

    2026-09-29:位元深度四列為了塞進 116 B 的槽拿掉了結尾 CRLF,結果畫面上
    只有三列。把 IMAGE **整欄**拿掉之後空間就夠了,CRLF 留得住。
    這條測試守的是那次的教訓。
    """
    for res, _desc, nm in PL.BIT_ROW_CSV:
        csv = PL.bit_row_csv(IMG, res)
        assert csv.endswith(b"\r\n"), nm
        assert len(csv) <= PL.BIT_ROW_SLOT, (nm, len(csv))
    for res, _desc, nm in PL.RATE_ROW_CSV:
        csv = PL.rate_row_csv(IMG, res)
        assert csv.endswith(b"\r\n"), nm
        assert len(csv) <= PL.RATE_ROW_SLOT, (nm, len(csv))


def test_image_column_is_dropped_not_left_empty():
    """★ IMAGE 要**整欄拿掉**,留空的話那一列不會被畫出來(§8.9)。

    格率第十列先前用 `1,0316,Popup,,1,2`(留空)—— 選得到但看不見。
    位元深度改成 `1,0305,Popup,1,2`(整欄拿掉)之後四列全部畫出來。
    """
    for f, csvs in ((PL.bit_row_csv, PL.BIT_ROW_CSV),
                    (PL.rate_row_csv, PL.RATE_ROW_CSV)):
        for res, _desc, nm in csvs:
            csv = f(IMG, res)
            rows = [l for l in csv[3:].split(b"\r\n") if l]
            assert b"IMAGE" not in rows[0], (nm, rows[0])
            ncol = len(rows[0].split(b","))
            for r in rows:
                assert len(r.split(b",")) == ncol, (nm, r)
                assert b",," not in r, (nm, r)      # 沒有留空的欄


def test_bit_row_cap_is_the_only_three_row_list_in_the_group():
    """上限記錄是靠**列數指紋**認出來的,把那個推理釘住。

    B2_5_1..B2_5_5 的列數是 (2, 3, 2, 2, 9),五筆同簽名記錄的 max 依序是
    (1.0, 2.0, 1.0, 1.0, 8.0) = 列數 - 1,而最後兩筆是獨立已知的
    B2_5_4 / B2_5_5。所以中間那筆 max=2.0 的就是三列的 B2_5_2。
    """
    import re
    sig = bytes.fromhex("0001000e0000002800024fe000000005ffffffff")
    recs = []
    for m in re.finditer(re.escape(sig), IMG):
        a = B + m.start()
        if not (0xC1A60000 <= a < 0xC1A80000):
            continue
        if struct.unpack_from(">I", IMG, m.start() + 0x18)[0] != 3:
            continue          # obj 3 = 清單本身,不是頁框
        recs.append((a, struct.unpack_from(">f", IMG, m.start() + 0x20)[0]))
    # 每個選單頁的 blob 有兩筆 obj 3,前一筆是清單本身、後一筆是頁框。
    firsts = recs[0::2]
    assert [round(f[1], 3) for f in firsts] == [1.0, 2.0, 1.0, 1.0, 8.0], firsts
    assert firsts[1][0] + 0x20 == PL.BIT_ROW_CAP, hex(firsts[1][0])
    assert firsts[3][0] + 0x20 == 0xC1A709BC          # B2_5_4,og3k_plan 已知
    assert firsts[4][0] + 0x20 == PL.RATE_ROW_CAP     # B2_5_5,已上機驗過


def test_bit_row_cap_write_only_touches_its_own_four_bytes():
    """上限沒有字對齊,靠讀改寫。相鄰位元組一個都不能動。"""
    assert PL.BIT_ROW_CAP % 4 != 0, "對齊的話就不需要讀改寫了"
    items = {a: v for a, v, n in PL.plan() if "位元深度清單" in n}
    lo = PL.BIT_ROW_CAP & ~3
    span = (PL.BIT_ROW_CAP + 4 + 3) & ~3
    got = struct.pack(f"<{(span - lo) // 4}I", *(items[lo + i * 4]
                                                 for i in range((span - lo) // 4)))
    orig = IMG[lo - B: span - B]
    want = bytearray(orig)
    want[PL.BIT_ROW_CAP - lo: PL.BIT_ROW_CAP - lo + 4] = PL.BIT_ROW_CAP_NEW
    assert got == bytes(want), (got.hex(), bytes(want).hex())
    assert struct.unpack(">f", got[PL.BIT_ROW_CAP - lo:
                                   PL.BIT_ROW_CAP - lo + 4])[0] == 3.0


def test_qs_has_no_bit_depth_item_so_the_fourth_row_needs_no_qs_work():
    """QS 的 CINE 項目清單(Y2_3_CINE)裡**沒有**位元深度。

    這是「14 bit 那一列不用碰 QS」的全部理由。QS 有 format(20) /
    resolution(21) / fps(22),就是沒有 bitdepth。見 §8.5。
    """
    res, sz = 0xC0F930D4, 1540
    body = IMG[res - B: res - B + sz]
    rows = [l for l in body.split(b"\r\n") if l][1:]
    ids = {}
    for r in rows:
        f = r.split(b",")
        if len(f) < 3:
            continue
        ids[int(f[1])] = f[2]
    assert ids.get(20) == b"menu_cine_format", ids.get(20)
    assert ids.get(21) == b"menu_cine_resolution", ids.get(21)
    assert ids.get(22) == b"menu_cine_fps", ids.get(22)
    assert not [v for v in ids.values() if b"bit" in v.lower()], ids


def test_menu_and_qs_share_one_summary_rate_converter():
    """格率轉換器出現在兩個**不同**的指標陣列裡,但是同一個函式。

    這只證明共用摘要轉換器；真正輸入、合法值與顯示物件還有獨立路徑。
    如果哪天這個假設破了(兩邊指向不同函式),這個測試會先叫。見 §8.5。
    """
    fn = 0xC06CB6D0
    words = struct.unpack_from(f"<{len(IMG) // 4}I", IMG, 0)
    hits = [B + i * 4 for i, v in enumerate(words) if v == fn]
    assert len(hits) == 2, [hex(h) for h in hits]

    # 而且這個函式是格率配對表的**唯一**供應者:整個映像裡只有它用
    # movw/movt 拼出 0xC2E44EE4。所以改它的立即值就改掉了所有消費端。
    def imm(v):
        return ((v >> 16) & 0xF) << 12 | (v & 0xFFF)

    sources = []
    for i in range(len(words) - 1):
        a, b_ = words[i], words[i + 1]
        if (a >> 20) & 0xFF != 0x30 or (b_ >> 20) & 0xFF != 0x34:
            continue
        if ((a >> 12) & 0xF) != ((b_ >> 12) & 0xF):
            continue
        if (imm(b_) << 16) | imm(a) == 0xC2E44EE4:
            sources.append(B + i * 4)
    assert sources == [0xC06CB6DC], [hex(s) for s in sources]


def test_everything_written_outside_the_cave_is_accounted_for():
    """cave 外的每一個位址都要落在一個**具名的**許可區段裡。

    既有的 hook 子集護欄只管分支站點,所以 §8.3 的三個 `movw/movt/mov`
    立即值 —— 寫進韌體程式碼、不是 hook —— 整個繞過了它。
    這條把缺口補上:cave 外只准有 hook、選單資源、描述子、控制器上限,
    以及那三個立即值。多出任何一個位址就是有人偷偷寫了沒人知道的地方。
    """
    hooks = {s for _, g in PL._stages() for s, _, _, _ in g}
    ok = [(a, a + 4, "hook") for a in hooks]
    for res, desc, nm in PL.RATE_ROW_CSV:
        ok.append((res, res + PL.RATE_ROW_SLOT, f"{nm} 資源"))
        ok.append((desc + 12, desc + 16, f"{nm} 描述子長度"))
    for res, desc, nm in PL.BIT_ROW_CSV:
        ok.append((res, res + PL.BIT_ROW_SLOT, f"{nm} 資源"))
        ok.append((desc + 12, desc + 16, f"{nm} 描述子長度"))
    ok.append((PL.RATE_ROW_CAP, PL.RATE_ROW_CAP + 4, "格率清單上限"))
    ok.append((PL.BIT_ROW_CAP & ~3, ((PL.BIT_ROW_CAP + 4 + 3) & ~3),
               "位元深度清單上限(讀改寫)"))
    ok.append((PL.CSV_ADDR, PL.CSV_ADDR + 96, "解析度清單 CSV"))
    ok.append((PL.CTRL_CAP, PL.CTRL_CAP + 4, "解析度清單上限"))
    slot = PL.MAPPING + PL.PRIVATE_PROFILE * 4
    ok.append((slot, slot + 4, "列對照表:私有 profile 的空槽"))
    # source-only 座標:只是 USER packer 的標籤,不會在相機上寫到這些位址
    bl = PL.blobs()
    for name, _src, addr in PL.payloads():
        if name in PL.SOURCE_ONLY_PAYLOADS:
            ok.append((addr, addr + len(bl[name]), f"{name}(source-only,packer 搬進 USER)"))
    if PL.WITH_SEL_LOG:
        ok.append((PL.SELLOG.LOG, PL.SELLOG.LOG + PL.SELLOG.LOG_BYTES, "SELLOG(source-only)"))
    if PL.WITH_RATE_PAIR:
        for a in (PL.RATE_PAIR_LO, PL.RATE_PAIR_HI, PL.RATE_PAIR_CNT):
            ok.append((a, a + 4, "配對表立即值"))

    if PL.WITH_RATE_NATIVE:
        ok.extend((a, a + 4, note) for a, _stock, note in PL.RATE_NATIVE.MAPPING_SITES)
        # 六個原廠格率 switch 的跳表字(internal 8 -> 119.88 那一格),見 imx410_rate_native.RATE_SWITCHES
        ok.extend(((c + 20 + PL.RATE_NATIVE.INTERNAL) & ~3, ((c + 20 + PL.RATE_NATIVE.INTERNAL) & ~3) + 4,
                   "rate switch table") for c, _t in PL.RATE_NATIVE.RATE_SWITCHES)
    if PL.WITH_RATE_UI:
        ok.append((PL.RATE_UI.SET_START & ~3, (PL.RATE_UI.SET_END + 3) & ~3,
                   "240 Settings summary NBU set"))

    if PL.WITH_RATE_LV:
        ok.extend((s['start'], s['end'], s['name'] + " fps label")
                  for s in PL.RATE_LV.SET_SPANS)

    stray = []
    for a, _v, note in PL.plan():
        if PL.CAVE_LO <= a < PL.CAVE_HI:
            continue
        if not any(lo <= a < hi for lo, hi, _ in ok):
            stray.append((a, note))
    assert not stray, [(hex(a), n) for a, n in stray[:8]]


def test_rate_pair_table_copies_the_stock_nine_verbatim():
    """搬過去的前九筆必須**逐字**等於原廠,只多第十筆。

    抄比算安全:原廠那九筆的列序就是 CSV 的列序,重新產生等於多一個
    會漂的來源。見 §8.3。
    """
    tbl = PL.rate_pair_table(IMG)
    assert len(tbl) == PL.RATE_PAIR_N * 8
    stock = IMG[PL.RATE_PAIR_STOCK_TBL - B:
                PL.RATE_PAIR_STOCK_TBL - B + PL.RATE_PAIR_STOCK_N * 8]
    assert tbl[:len(stock)] == stock
    assert struct.unpack_from("<II", tbl, len(stock)) == (
        PL.RATE_PAIR_NEW_ENUM, PL.RATE_PAIR_STOCK_N)


def test_summary_pair_uses_export_eleven_for_240():
    # Independent of PL.RATE_PAIR_NEW_ENUM: export 5 asserts in the picker,
    # internal 5 is 59.94. Neither is the native export 11 for the 240 suffix.
    assert struct.unpack_from("<II", PL.rate_pair_table(IMG), 9 * 8) == (11, 9)


def test_all_three_frame_rate_maxima_cover_row_ten():
    """格率選單有三個上限(List / MenuItem_Select / IconChange),三個都要 9.0。

    2026-10-01 實機:只改了前兩個,IconChange 的 8.0 把原廠通知寫回的列 9
    夾成 8,再觸發回呼把 239.76 的記憶體記號清掉。從最終寫入計畫讀,
    不看來源模組 —— 漏掉任何一個都會在這裡失敗。
    """
    im = bytearray(IMG)
    for a, v, _ in PL.plan():
        struct.pack_into("<I", im, a - 0xC0000000, v)
    got = {name: struct.unpack(">f", bytes(im[a - 0xC0000000:a - 0xC0000000 + 4]))[0]
           for name, a in (("List", 0xC1A74B44), ("MenuItem_Select", 0xC1A73D63),
                           ("IconChange", 0xC1A744F5))}
    assert got == {"List": 9.0, "MenuItem_Select": 9.0, "IconChange": 9.0}, got


def test_native_tables_precede_mapping_code_and_hooks():
    items = PL.plan()
    order = {a: i for i, (a, _, _) in enumerate(items)}
    private = [a + i for _, a, data in PL.RATE_NATIVE.tables(IMG)
               for i in range(0, len(data), 4)]
    written = [a for a in PL.RATE_NATIVE.EXTERNAL_SITES if a not in PL.RATE_NATIVE.NOT_ARMED]
    assert max(order[a] for a in private) < min(order[a] for a in written)
    # Independent hook lookup: each named branch must be an armed stage,
    # and the one-row-240 design must not arm the list hooks.
    armed = {s for _, group in PL._stages() for s, _, _, _ in group}
    assert {h[0] for h in PL.RATE_NATIVE.HOOKS} - PL.RATE_NATIVE.NOT_ARMED <= armed
    assert not (PL.RATE_NATIVE.NOT_ARMED & armed)
    assert all(a not in order for a in PL.RATE_NATIVE.NOT_ARMED)


def test_rate_pair_instructions_decode_back_to_what_we_meant():
    """手工編的 movw/movt/mov 要能**解回**原意 —— 編錯了會指到別處。"""
    items = {a: v for a, v, n in PL.plan() if "配對表" in n and "十筆" not in n}
    lo = items[PL.RATE_PAIR_LO]
    hi = items[PL.RATE_PAIR_HI]
    cnt = items[PL.RATE_PAIR_CNT]

    def imm(v):
        return ((v >> 16) & 0xF) << 12 | (v & 0xFFF)

    assert (lo >> 20) & 0xFF == 0x30 and (lo >> 12) & 0xF == 2
    assert (hi >> 20) & 0xFF == 0x34 and (hi >> 12) & 0xF == 2
    assert (imm(hi) << 16) | imm(lo) == PL.RATE_PAIR
    assert (cnt >> 20) & 0xFF == 0x3A and (cnt >> 12) & 0xF == 2
    assert cnt & 0xFFF == PL.RATE_PAIR_N


def test_rate_pair_table_is_written_before_the_pointer_is_moved():
    """順序:表先寫,指令後改。反過來會有一瞬間指向全 0 的表。"""
    order = {}
    for i, (a, _v, n) in enumerate(PL.plan()):
        order.setdefault(a, i)
    last_word = max(order[PL.RATE_PAIR + k * 4]
                    for k in range(PL.RATE_PAIR_N * 2))
    first_patch = min(order[a] for a in (PL.RATE_PAIR_LO, PL.RATE_PAIR_HI,
                                         PL.RATE_PAIR_CNT))
    assert last_word < first_patch, (last_word, first_patch)


# ---- NBU 資源集索引(§8.8)---------------------------------------------------

NBU_INDEX = 0xC18EB49C
NBU_BASE = 0xC18C0460
NBU_STRIDE = 0x20
B2_5_HASH = 0xD570BB11
B2_5_ROW = 0xC18ECA9C
B2_5_SET = 0xC1A5C590


def test_nbu_set_index_row_for_b2_5_is_where_we_think():
    """`B2_5` 的索引列與它的集合位移欄 —— 改指向就是改那一個大端字。

    釘住三件事:索引是 0x20 步距、依 FNV hash 遞增、`+0x0C` 是集合位移。
    位址漂了會先叫,而不是讓我們往一個錯的地方寫。見 §8.8。
    """
    fnv, name, one, off = struct.unpack_from(">4I", IMG, B2_5_ROW - B)
    assert fnv == B2_5_HASH, hex(fnv)
    assert one == 1, one
    assert NBU_BASE + off == B2_5_SET, hex(NBU_BASE + off)
    # 前後兩列的 hash 必須嚴格遞增 —— 證明步距是 0x20 而不是別的
    prev = struct.unpack_from(">I", IMG, B2_5_ROW - NBU_STRIDE - B)[0]
    nxt = struct.unpack_from(">I", IMG, B2_5_ROW + NBU_STRIDE - B)[0]
    assert prev < fnv < nxt, (hex(prev), hex(fnv), hex(nxt))


def test_nbu_index_hash_is_fnv1a_of_the_set_name():
    """key 是短名的 FNV-1a —— 跟 NBR 目錄同一套,所以新集合的 key 算得出來。"""
    def fnv1a(data):
        v = 0x811C9DC5
        for byte in data:
            v = ((v ^ byte) * 0x01000193) & 0xFFFFFFFF
        return v
    assert fnv1a(b"B2_5") == B2_5_HASH, hex(fnv1a(b"B2_5"))


def test_b2_5_set_is_followed_immediately_by_the_next_set():
    """集合首尾相接,所以**原地長大一定會蓋到隔壁** —— 這是要改指向的理由。"""
    nxt_row = B2_5_ROW + NBU_STRIDE
    # 索引是按 hash 排的,不是按位址,所以要掃全表找位址上的下一個
    ends = []
    for i in range(221):
        a = NBU_INDEX + i * NBU_STRIDE
        off = struct.unpack_from(">I", IMG, a - B + 0x0C)[0]
        ends.append(NBU_BASE + off)
    after = sorted(x for x in ends if x > B2_5_SET)
    assert after and after[0] - B2_5_SET == 118123, after[0] - B2_5_SET


def test_resolution_csv_obeys_the_two_rules_we_learned_on_camera():
    """解析度 CSV 要符合 §8.9 上機驗出來的兩條規則。

    2026-09-30 在相機上讀到 `3,CUSTOM,,1,2k,1,2` —— 三個錯疊在一起:
    第 1/2 列用 LF、最後一列沒有 CRLF、IMAGE 欄留空,再加上寫入時保留了
    原廠尾巴。這條測試把四件事一起守住。
    """
    csv = PL._CSV
    assert csv.endswith(b"\r\n"), "最後一列沒有 CRLF -> 不會被 parse"
    assert b",," not in csv, "留空的欄位 -> 那一列畫不出來"
    body = csv[3:]
    assert b"\n" not in body.replace(b"\r\n", b""), "有裸的 LF"
    rows = [l for l in body.split(b"\r\n") if l]
    ncol = len(rows[0].split(b","))
    for r in rows:
        assert len(r.split(b",")) == ncol, r
    assert len(rows) == 4, rows            # 標頭 + 三列
    assert rows[-1].startswith(b"3,CUSTOM,"), rows[-1]
    assert len(csv) <= PL.CSV_SLOT


def test_resolution_csv_write_leaves_no_stock_tail():
    """整個槽都要被寫到 —— 只覆蓋前面會讓最後一列接上原廠殘留。"""
    got = {a: v for a, v, n in PL.plan() if n == "選單 CSV"}
    assert len(got) == PL.CSV_SLOT // 4, len(got)
    import struct as _s
    blob = b"".join(_s.pack("<I", got[PL.CSV_ADDR + i * 4])
                    for i in range(PL.CSV_SLOT // 4))
    assert blob[:len(PL._CSV)] == PL._CSV
    assert set(blob[len(PL._CSV):]) <= {0}, blob[len(PL._CSV):]


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
