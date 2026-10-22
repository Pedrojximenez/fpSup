#!/usr/bin/env python3
"""og3krecipe.S 對 imx410_block.expected_recipe() 的逐字差分。

在 unicorn 上跑**真的 payload**,對著**真的韌體映像**(metadata / timing 兩張
表是從 out/MAIN_c0000000.bin 映進去的),把它算出來的二十個字和 Python 模型
算出來的二十個字逐字比。不一樣就是其中一邊錯了。

這是 og3krecipe 上機前唯一的把關,所以最後一個測試是**突變檢查**:故意把
payload 的一個字改掉,確認測試會失敗。測試不會失敗就不算測試。

    python3 test_imx410_recipe.py
"""
from __future__ import annotations

import pathlib
import struct
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from unicorn import UC_ARCH_ARM, UC_MODE_ARM, Uc
from unicorn.arm_const import (UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0,
                               UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
                               UC_ARM_REG_R12, UC_ARM_REG_SP)

from armasm import assemble
from imx410_block import (AXIS_WORDS, A_ZH, A_ZV, CANVAS_MAX_PAIRS, RECIPE_WORDS, R_VALID, R_MODE, R_IDX,
                          R_RECW, R_RECH, R_ACTW, R_ACTH, R_SAVE0, R_SAVE1,
                          R_TW0, R_TW1,
                          aspect_q_table, axis_words, canvas_template,
                          expected_canvas, expected_recipe, rate_table,
                          timing_table)
from imx410_full import FIRMWARE, RWZM_UNITY, Registry

B = 0xC0000000
CODE = 0x40000000            # payload 放這裡,與相機上的 cave 無關
AXIS = 0x40010000
RECIPE = 0x40010040
RATETAB = 0x40010100
TMGTAB = 0x40010200
CTMPL = 0x40010400
CANVAS = 0x40010500
ASPTAB = 0x40010700
STACK = 0x40020000
DONE = 0x40030000            # 返回這裡代表跑完
IMAGER = 0xC343B588
DESC = 0xC2F1E654

REG = Registry()
IMG = FIRMWARE.read_bytes()
# donor 是不是空殼,決定模板要不要含那六欄(安裝時就決定,payload 不判斷)
import imx410_plan as _PL
_FILL = _PL._fill_for()


def _blob():
    return assemble("og3krecipe.S",
                    defines=[f"AXIS={AXIS:#x}", f"RECIPE={RECIPE:#x}",
                             f"RATETAB={RATETAB:#x}", f"TMGTAB={TMGTAB:#x}",
                             f"CTMPL={CTMPL:#x}", f"CANVAS={CANVAS:#x}",
                             f"ASPTAB={ASPTAB:#x}"])


def run(axis, blob=None, recipe_seed=None):
    """把 AXIS 餵進去跑一次,回傳 RECIPE 的二十個字。"""
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    mu.mem_map(0x40000000, 0x00040000)
    mu.mem_map(0xC0B00000, 0x00100000)        # metadata / timing 兩張表
    mu.mem_map(0xC2F00000, 0x00100000)        # 描述子
    mu.mem_map(0xC3400000, 0x00100000)        # imager 物件

    # 真的表,從真的映像搬進來
    mu.mem_write(0xC0B00000, IMG[0xC0B00000 - B: 0xC0C00000 - B])
    # 描述子與 imager 指標鏈 —— 值就是 2026-09-28 在相機上讀到的那四個字
    mu.mem_write(DESC, struct.pack("<4I", 0xC0B59500, 70, 0xC0B59DC0, 70))
    mu.mem_write(IMAGER, struct.pack("<I", DESC))

    mu.mem_write(CODE, blob if blob is not None else _blob())
    mu.mem_write(RATETAB, rate_table())
    mu.mem_write(TMGTAB, timing_table())
    mu.mem_write(CTMPL, canvas_template(_FILL, tuple(axis)))
    mu.mem_write(ASPTAB, aspect_q_table())
    mu.mem_write(CANVAS, b"\xCC" * (4 + CANVAS_MAX_PAIRS * 8))
    mu.mem_write(AXIS, struct.pack(f"<{AXIS_WORDS}I", *axis))
    seed = recipe_seed if recipe_seed is not None else [0] * RECIPE_WORDS
    mu.mem_write(RECIPE, struct.pack(f"<{RECIPE_WORDS}I", *seed))

    # 進入時的暫存器塞垃圾。全零會讓「movw r0,#0 改成 mov r0,r1」這種突變
    # 剛好等價 —— 那不是 payload 正確,是測法太寬。
    for r, v in ((UC_ARM_REG_R0, 0x5A5A0001), (UC_ARM_REG_R1, 0x5A5A0002),
                 (UC_ARM_REG_R2, 0x5A5A0003), (UC_ARM_REG_R3, 0x5A5A0004),
                 (UC_ARM_REG_R12, 0x5A5A000C)):
        mu.reg_write(r, v)
    mu.reg_write(UC_ARM_REG_SP, STACK)
    mu.reg_write(UC_ARM_REG_LR, DONE)
    mu.emu_start(CODE, DONE, count=2_000_000)
    global LAST_CANVAS, LAST_MU
    LAST_MU = mu
    n = struct.unpack("<I", mu.mem_read(CANVAS, 4))[0]
    LAST_CANVAS = ([] if n == 0 or n > CANVAS_MAX_PAIRS else
                   list(struct.unpack(f"<{2 * n}I",
                                      mu.mem_read(CANVAS + 4, 8 * n))))
    return list(struct.unpack(f"<{RECIPE_WORDS}I",
                              mu.mem_read(RECIPE, RECIPE_WORDS * 4)))


LAST_CANVAS = []
LAST_MU = None


# ---- 測試 ------------------------------------------------------------------
CASES = [
    ("OG3K 等價", dict(bit=12, rate="30", raster=(3032, 2012))),
    ("OG2K 等價", dict(bit=12, rate="60", raster=(2016, 1344))),
    ("HSW 等價", dict(bit=12, rate="240", raster=(2016, 672))),
    ("HSW 120", dict(bit=12, rate="120", raster=(2016, 672))),
    ("全幅 24p", dict(bit=12, rate="24", raster=(6064, 4042))),
    ("全幅 hbin3 vbin3", dict(bit=12, rate="24", raster=(6064, 4042),
                              hbin=3, vbin=3)),
    ("全幅 hbin5 vbin3", dict(bit=12, rate="24", raster=(6064, 4042),
                              hbin=5, vbin=3)),
    ("RWZM 1600", dict(bit=12, rate="30", raster=(3032, 2012),
                       rwzm=(1600, 1600))),
    ("RWZM 長寬不同", dict(bit=12, rate="30", raster=(3032, 2012),
                           rwzm=(1024, 2048))),
    ("8-bit", dict(bit=8, rate="30", raster=(3032, 2012))),
    ("10-bit", dict(bit=10, rate="30", raster=(3032, 2012))),
    ("14-bit 全幅 18p", dict(bit=14, rate="24", raster=(6064, 4042))),
    # 全幅那組挑不到 donor(RAW14 全高的上限是 19.55p);下面三組才是真的
    # 會借到 RAW14 感測器模式的,平面碼走 (7, 8) 那條。見 §4.3 / §4.4。
    ("14-bit 5.7K 24p", dict(bit=14, rate="24", raster=(5712, 3216))),
    ("14-bit 3968x2640 25p", dict(bit=14, rate="25", raster=(3968, 2640))),
    ("14-bit 4176x2174 30p", dict(bit=14, rate="30", raster=(4176, 2174))),
    ("指定 mode 117", dict(bit=12, rate="30", raster=(3032, 2012), mode=117)),
    ("指定 mode 143", dict(bit=12, rate="30", raster=(3032, 2012), mode=143)),
    ("自訂裁切", dict(bit=12, rate="30", raster=(3032, 2012),
                      crop=(2880, 1920))),
    ("沒有 mode:3032 跑 120", dict(bit=12, rate="120", raster=(3032, 2012))),
    ("沒有 mode:光柵不存在", dict(bit=12, rate="30", raster=(1234, 5678))),
    ("2088x1174 16:9", dict(bit=12, rate="50", raster=(2088, 1174))),
    ("3032x1708 48p", dict(bit=12, rate="48", raster=(3032, 1708))),
]


def test_matches_model():
    blob = _blob()
    bad = []
    for label, kw in CASES:
        ax = axis_words(**kw)
        want = expected_recipe(REG, ax)
        got = run(ax, blob)
        if got != want:
            diff = [(i, hex(w), hex(g))
                    for i, (w, g) in enumerate(zip(want, got)) if w != g]
            bad.append(f"{label}: {diff}")
    assert not bad, "\n  ".join([""] + bad)


def test_cache_skips_recompute():
    """AXIS 沒變就不重算 —— 把 RECIPE 的結果欄塗髒,再跑一次應該原封不動。"""
    ax = axis_words(bit=12, rate="30", raster=(3032, 2012))
    first = run(ax)
    dirty = list(first)
    for i in range(AXIS_WORDS, RECIPE_WORDS):
        dirty[i] = 0xDEADBEEF
    again = run(ax, recipe_seed=dirty)
    assert again == dirty, "快照相同卻重算了"


def test_axis_change_forces_recompute():
    a1 = axis_words(bit=12, rate="30", raster=(3032, 2012))
    a2 = axis_words(bit=12, rate="24", raster=(3032, 2012))
    seed = run(a1)
    got = run(a2, recipe_seed=seed)
    assert got == expected_recipe(REG, a2)
    assert got[R_TW0] != seed[R_TW0], "格率換了時序卻沒換"


def test_no_mode_leaves_valid_zero():
    """故障安全:沒有 mode 對應時 valid = 0,而且不留半套結果。"""
    ax = axis_words(bit=12, rate="120", raster=(3032, 2012))
    got = run(ax)
    assert got[R_VALID] == 0
    assert got[R_MODE] == 0 and got[R_TW0] == 0 and got[R_TW1] == 0


def test_reproduces_shipped_donors():
    """三個出貨目標的 donor 與時序,payload 自己要算得出來。"""
    for kw, mid, tw0, tw1 in (
            (dict(bit=12, rate="30", raster=(3032, 2012)), 98,
             445 | (735 << 16), 5398 | (4 << 16)),
            (dict(bit=12, rate="60", raster=(2016, 1344)), 139,
             445 | (590 << 16), 2699 | (6 << 16)),
            (dict(bit=12, rate="240", raster=(2016, 672)), 12,
             330 | (330 << 16), 910 | (6 << 16))):
        got = run(axis_words(**kw))
        assert got[R_VALID] == 1, kw
        assert got[R_MODE] == mid, (kw, got[R_MODE], mid)
        assert got[R_TW0] == tw0, (kw, hex(got[R_TW0]), hex(tw0))
        assert got[R_TW1] == tw1, (kw, hex(got[R_TW1]), hex(tw1))


def test_geometry_alignment():
    """每一個案例算出來的記錄矩陣與裁切都要對得齊。"""
    for label, kw in CASES:
        got = run(axis_words(**kw))
        if not got[R_VALID]:
            continue
        assert got[R_RECW] % 16 == 0, (label, got[R_RECW])
        assert got[R_RECH] % 2 == 0, (label, got[R_RECH])
        assert got[R_ACTW] % 16 == 0, (label, got[R_ACTW])
        assert got[R_ACTH] % 2 == 0, (label, got[R_ACTH])
        assert got[R_ACTW] <= got[R_RECW] and got[R_ACTH] <= got[R_RECH], label


# 突變用的案例:刻意挑成會走到不同分支的一組。只拿一個案例去打,
# 14-bit、指定 mode、自訂裁切、fail 路徑那幾段永遠不會被碰到。
MUTATION_CASES = [kw for label, kw in CASES if label in (
    "OG3K 等價", "HSW 等價", "全幅 hbin5 vbin3", "RWZM 長寬不同",
    "14-bit 全幅 18p", "指定 mode 117", "自訂裁切",
    "沒有 mode:3032 跑 120", "10-bit")]


def test_canvas_matches_model():
    """畫布 (位移, 值) 陣列要與模型逐對相同,順序也一樣。"""
    bad = []
    for label, kw in CASES:
        ax = axis_words(**kw)
        run(ax)
        got = [(LAST_CANVAS[i], LAST_CANVAS[i + 1])
               for i in range(0, len(LAST_CANVAS), 2)]
        want = expected_canvas(REG, ax, _FILL)
        if got != want:
            bad.append(f"{label}: got {[(hex(a), b) for a, b in got]} "
                       f"want {[(hex(a), b) for a, b in want]}")
    assert not bad, "\n  ".join([""] + bad)


def test_zoom_gate_is_evaluated_on_the_camera_not_at_install():
    """★ RWZM 是**執行期**的軸 —— 用 unity 的軸安裝,執行期改了照樣生效。

    2026-09-28 的假通過就是這條不成立:畫布模板的閘門在 `canvas_template()`、
    也就是安裝時解掉,所以用預設軸(RWZM unity)裝好之後,執行期怎麼改 AXIS,
    `RECIPE` 都會**完全正確地**跟著變而那四欄根本不在模板裡 —— 硬體從來沒被
    程式化,而且沒有任何徵兆(§12.29)。

    2026-09-29 把 `CG_ZOOM` 搬進 payload(`canvas_emit` 改成位元圖分派)。
    這個測試拿**預設軸建的模板**跑三組不同的執行期 RWZM,證明閘門是在相機上
    判斷的。`_FILL` 與 CASES 用的是同一套模板,所以這裡沒有另開一條路。
    """
    unity = axis_words(bit=12, rate="30", raster=(3032, 2012))
    assert unity[A_ZH] == unity[A_ZV] == RWZM_UNITY, "前提:安裝軸是 unity"

    def emit(ax):
        run(ax)
        return [(LAST_CANVAS[i], LAST_CANVAS[i + 1])
                for i in range(0, len(LAST_CANVAS), 2)]

    ZOOM_OFFS = {0x64, 0xD4}            # 錄影那一對;預覽那一對由宣告列給(2026-10-04)

    # ① 執行期也是 unity -> 那兩欄不可以出現(不要寫沒要求的欄位,§12.21)
    got = emit(unity)
    assert not (ZOOM_OFFS & {o for o, _ in got}), got

    # ② 執行期改成 1600 -> 錄影兩欄都要出現,而且值正確;預覽兩欄不碰
    ax = axis_words(bit=12, rate="30", raster=(3032, 2012), rwzm=(1600, 1600))
    got = dict(emit(ax))
    assert {o: got.get(o) for o in sorted(ZOOM_OFFS)} == {0x64: 1600, 0xD4: 1600}, got
    assert not ({0x60, 0xD0} & set(got)), got

    # ③ 長寬不同 -> H 區塊吃 ZH、V 區塊吃 ZV(§12.25 的槽位修正)
    ax = axis_words(bit=12, rate="30", raster=(3032, 2012), rwzm=(1600, 1500))
    got = dict(emit(ax))
    assert {o: got.get(o) for o in sorted(ZOOM_OFFS)} == {0x64: 1600, 0xD4: 1500}, got

    # 三組都要與主機模型逐對相同 —— 兩邊各自算的
    for kw in (dict(), dict(rwzm=(1600, 1600)), dict(rwzm=(1600, 1500))):
        a = axis_words(bit=12, rate="30", raster=(3032, 2012), **kw)
        assert emit(a) == expected_canvas(REG, a, _FILL), kw


def test_install_template_does_not_depend_on_the_zoom_axis():
    """模板不可以再隨安裝軸變 —— 那正是假通過的來源。"""
    from imx410_block import canvas_template
    a = axis_words(bit=12, rate="30", raster=(3032, 2012))
    b = axis_words(bit=12, rate="30", raster=(3032, 2012), rwzm=(1600, 1600))
    assert canvas_template(_FILL, a) == canvas_template(_FILL, b)


def test_canvas_cleared_when_no_mode():
    """沒有 mode 時畫布陣列要清空 —— 留著舊配方 = 用舊幾何錄新設定。"""
    run(axis_words(bit=12, rate="30", raster=(3032, 2012)))
    assert LAST_CANVAS, "先要有東西"
    run(axis_words(bit=12, rate="120", raster=(3032, 2012)))
    assert LAST_CANVAS == [], LAST_CANVAS


def test_canvas_hirate_gate():
    """>60 fps 才寫的那三欄,60 fps 以下不可以出現;scale float(FC/100)兩邊都不寫
    (2026-10-04 起是宣告列依 mode 給的)。"""
    run(axis_words(bit=12, rate="60", raster=(2016, 1344)))
    offs60 = {LAST_CANVAS[i] for i in range(0, len(LAST_CANVAS), 2)}
    run(axis_words(bit=12, rate="240", raster=(2016, 672)))
    offs240 = {LAST_CANVAS[i] for i in range(0, len(LAST_CANVAS), 2)}
    extra = {0xB0, 0xDC, 0xE4}
    assert not (offs60 & extra), sorted(map(hex, offs60 & extra))
    assert extra <= offs240, sorted(map(hex, extra - offs240))
    assert not ({0xFC, 0x100} & (offs60 | offs240))
    # 一律要寫的那兩欄(p13 的引擎組態)在兩邊都要有
    assert {0x90, 0xC0} <= offs60 and {0x90, 0xC0} <= offs240


def test_saves_donor_stock_timing():
    """挑好 donor 之後要存下它的**原廠**時序 —— 還原時要用。"""
    for kw, w0, w1 in (
            (dict(bit=12, rate="30", raster=(3032, 2012)),
             0x01BD01BD, 0x0004082E),          # mode 98 原廠
            (dict(bit=12, rate="240", raster=(2016, 672)),
             0x014A014A, 0x0006038E)):         # mode 12 原廠
        got = run(axis_words(**kw))
        assert got[R_SAVE0] == w0, (kw, hex(got[R_SAVE0]), hex(w0))
        assert got[R_SAVE1] == w1, (kw, hex(got[R_SAVE1]), hex(w1))


def test_restores_previous_donor_on_axis_change():
    """★ 換配方時,上一個 donor 的時序要被還原成原廠值。

    imx410_fmt 每次命中都會改 donor 的時序記錄,而 donor 是變動的。不還原的話,
    配方借過 mode 106 之後切回原廠 FHD30 就拿到我們的時序 —— 那會弄壞一個
    我們根本沒打算碰的原廠格式。
    """
    a1 = axis_words(bit=12, rate="30", raster=(3032, 2012))     # mode 98
    a2 = axis_words(bit=12, rate="240", raster=(2016, 672))     # mode 12
    first = run(a1)
    idx98 = first[R_IDX]
    rec98 = 0xC0B59500 + idx98 * 0x20

    # 模擬 imx410_fmt 已經把 mode 98 的時序改掉,然後換配方
    mu = Uc(UC_ARCH_ARM, UC_MODE_ARM)
    mu.mem_map(0x40000000, 0x00040000)
    mu.mem_map(0xC0B00000, 0x00100000)
    mu.mem_map(0xC2F00000, 0x00100000)
    mu.mem_map(0xC3400000, 0x00100000)
    mu.mem_write(0xC0B00000, IMG[0xC0B00000 - B: 0xC0C00000 - B])
    mu.mem_write(DESC, struct.pack("<4I", 0xC0B59500, 70, 0xC0B59DC0, 70))
    mu.mem_write(IMAGER, struct.pack("<I", DESC))
    mu.mem_write(CODE, _blob())
    mu.mem_write(RATETAB, rate_table())
    mu.mem_write(TMGTAB, timing_table())
    mu.mem_write(CTMPL, canvas_template(_FILL, tuple(a2)))
    mu.mem_write(ASPTAB, aspect_q_table())
    mu.mem_write(AXIS, struct.pack(f"<{AXIS_WORDS}I", *a2))
    mu.mem_write(RECIPE, struct.pack(f"<{RECIPE_WORDS}I", *first))
    mu.mem_write(rec98 + 4, struct.pack("<2I", 0xDEAD0001, 0xDEAD0002))
    mu.reg_write(UC_ARM_REG_SP, STACK)
    mu.reg_write(UC_ARM_REG_LR, DONE)
    mu.emu_start(CODE, DONE, count=2_000_000)

    back = struct.unpack("<2I", mu.mem_read(rec98 + 4, 8))
    assert back == (0x01BD01BD, 0x0004082E), \
        f"mode 98 沒被還原:{[hex(x) for x in back]}"
    out = list(struct.unpack(f"<{RECIPE_WORDS}I",
                             mu.mem_read(RECIPE, RECIPE_WORDS * 4)))
    assert out == expected_recipe(REG, a2)


def test_aspect_is_the_pixel_shape():
    """顯示比例 = 錄下的像素(2026-10-04 使用者:「壓扁才是他真實的樣子」)。
    M12(2016x672、縮減 3x6)RAW 2000x662 是 3:1 的扁像素 -> 21:9(最接近的 enum),
    不再被 scale 還原成 3:2;用 RWZM 2048/1024 把寬壓掉之後是 3:2;mode 10
    (6064x2022、1x1)本來就是 21:9。ARM 與模型都要這樣算。"""
    import imx410_block as KB
    for kw, want in ((dict(bit=12, rate="240", raster=(2016, 672)), 5),
                     (dict(bit=12, rate="120", raster=(2016, 672), rwzm=(2048, 1024)), 2),
                     (dict(bit=12, rate="24", raster=(6064, 2022)), 5),
                     (dict(bit=12, rate="30", raster=(3032, 2012)), 2)):
        ax = axis_words(**kw)
        got = run(ax)
        m = expected_recipe(REG, ax)
        assert got[KB.R_VALID] == m[KB.R_VALID] == 1, kw
        assert got[KB.R_ASPECT] == m[KB.R_ASPECT] == want, (kw, got[KB.R_ASPECT], m[KB.R_ASPECT])


def test_mutation_is_caught():
    """突變檢查:把 payload 的每一個字依序改掉,至少要有一個案例抓到。

    不做這個,上面那些測試可能只是在測 Python 對 Python。
    先用最快的案例篩一遍,活下來的才拿其餘案例再打 —— 不然要跑上千次模擬。
    """
    blob = bytearray(_blob())
    axes = [axis_words(**kw) for kw in MUTATION_CASES]
    wants = [expected_recipe(REG, a) for a in axes]
    # **畫布也要比。** 不比的話新增的 82 個字(模板走訪)全部 NOP 化都不會
    # 被抓到 —— 2026-09-28 加完畫布之後突變率從 81% 掉到 68%,就是這個原因。
    cwants = [expected_canvas(REG, a, _FILL) for a in axes]
    # 種子塞垃圾而不是零:清零迴圈與快照複製壞掉才看得見。
    DIRTY = [0xBAADF00D] * RECIPE_WORDS
    # 快取情境:種子已經帶著正確的快照 + 哨兵,payload 應該原封不動返回。
    cache_axis = axes[0]
    cache_seed = list(expected_recipe(REG, cache_axis))
    for i in range(AXIS_WORDS, RECIPE_WORDS):
        cache_seed[i] = 0xC0FFEE00 + i

    def probe(mutant):
        for a, want, cwant in zip(axes, wants, cwants):
            if run(a, mutant, recipe_seed=DIRTY) != want:
                return True
            got = [(LAST_CANVAS[i], LAST_CANVAS[i + 1])
                   for i in range(0, len(LAST_CANVAS), 2)]
            if got != cwant:
                return True
        return run(cache_axis, mutant, recipe_seed=cache_seed) != cache_seed

    survived = []
    for off in range(0, len(blob), 4):
        orig = bytes(blob[off:off + 4])
        blob[off:off + 4] = b"\x00\x00\xa0\xe1"      # 0xE1A00000 = mov r0,r0 = NOP
        try:
            caught = probe(bytes(blob))
        except Exception:
            caught = True                              # 爆掉也算被抓到
        if not caught:
            survived.append(off)
        blob[off:off + 4] = orig
    ratio = 1 - len(survived) / (len(blob) // 4)
    # 量到 81%(264 個字,存活 49)。抽樣看過存活的,分成三類,都不是漏測:
    #   ① **真的等價** —— 例:裁切寬的 `bic #15`。rec_w 已經對齊 16,
    #      所以 rec_w-16 必然也對齊,那條 bic 永遠沒有作用(高度同理:
    #      偶數減 10 還是偶數)。Python 模型有同樣的冗餘,兩邊一起冗餘。
    #   ② **資料字** —— hmax_set 那六個。這些案例只用到 330/445/911,
    #      改掉 360/395/450 不會有人發現。
    #   ③ **NOP 化之後剛好無害的載入/搬移** —— 值隨即被覆寫。
    # 門檻設在量到的值之下一點:它是絆線,不是目標。掉下去代表測試變弱了。
    assert ratio > 0.78, (f"只有 {ratio:.0%} 的字改掉會被抓到,"
                          f"存活 {len(survived)} 個:{[hex(o) for o in survived[:24]]}")
    return ratio


def _run():
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    bad = 0
    for n, f in fns:
        try:
            r = f()
            print(f"  ok   {n}" + (f"  ({r:.0%} 突變被抓到)" if r else ""))
        except AssertionError as e:
            bad += 1
            print(f"  FAIL {n}: {e}")
    print(f"\n{len(fns) - bad}/{len(fns)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(_run())
