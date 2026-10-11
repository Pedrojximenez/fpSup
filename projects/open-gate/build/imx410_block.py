#!/usr/bin/env python3
"""AXIS / 表 / RECIPE 三個區塊的二進位佈局,以及主機端的參考模型。

`og3krecipe.S` 在相機上要產生的東西,這裡用 Python 產生一份一模一樣的。
兩邊逐字比對就是它的回歸測試(見 test_imx410_recipe.py)——這比「看起來有動」
強得多,而且不用上機。

    AXIS    選單寫的七個軸(9 個字)
    RATE    格率常數表(11 筆 x 12 bytes),避免相機上做浮點
    TMG     時序預算表(6 種 hmax x 11 個格率 x 4 bytes)
            ★ 全 70 個模式只用到 6 種 hmax,所以時序是**查表不是除法**。
              這顆核心的 ARM 模式有沒有 udiv 沒有確認過(只在 Thumb 碼裡
              見過,0xC0630F74),繞開它比賭它安全。
    RECIPE  og3krecipe 算出來的結果,其他 payload 讀它
"""
from __future__ import annotations

import struct

from imx410_full import (ALIGN, ALIGN_SAFE, CANVAS_PLANE, CLOCK, HIRATE_ABOVE,
                         RATES, RWZM_UNITY, Registry, MARGIN_W, MARGIN_H,
                         canvas_pairs)

# ---- 佈局 ------------------------------------------------------------------
# AXIS:選單的七個軸。crop 與 bin 各塞一個字的上下半。
AXIS_WORDS = 9
A_BIT, A_RATE, A_RW, A_RH, A_BIN, A_ZH, A_ZV, A_CROP, A_MODE = range(AXIS_WORDS)

# RECIPE:前 9 個字是 AXIS 的快照,用來判斷要不要重算 —— 不需要世代計數器,
# 也就不需要 hook 七個 setter。
R_SNAP = 0                      # +0x00 .. +0x20
R_VALID = 9                     # +0x24  1 = 解出來了;0 = 沒有 mode -> FHD fallback
R_MODE = 10                     # +0x28  感測器模式 id
R_IDX = 11                      # +0x2C  metadata / timing 的列索引
R_TW0 = 12                      # +0x30  hmax | tail<<16     -> 寫 timing 列 +4
R_TW1 = 13                      # +0x34  vmax | x_start<<16  -> 寫 timing 列 +8
R_RECW, R_RECH = 14, 15         # +0x38 +0x3C  記錄矩陣
R_ACTW, R_ACTH = 16, 17         # +0x40 +0x44  可見 / DNG 裁切
R_NOM = 18                      # +0x48  整數標稱格率(快門角度 wrapper 用)
R_EFPS = 19                     # +0x4C  引擎格率 float bits(畫布 +0x030)
R_ASPECT = 20                   # +0x50  長寬比 enum(0xC0B4CAB8 的索引)
# 目前 donor 的**原廠**時序兩個字。imx410_fmt 每次命中都會改 donor 的時序
# 記錄,而 donor 是變動的 —— 不還原的話,配方借過 mode 106 之後切回原廠
# FHD30 就拿到我們的時序。
#
# 原本想做一張 70 筆的備份表(560 B),但 cave 裡沒有那麼大的連續空間,
# 而且根本不需要:og3krecipe 跑在 imx410_fmt 寫入**之前**,所以它讀到的就是
# 還沒被動過的原廠值,就地存兩個字即可。換配方時先還原再存新的,
# 新舊 donor 相同也正確。
R_SAVE0 = 21                    # +0x54
R_SAVE1 = 22                    # +0x58
# 這四個要餵進畫布,所以放成連續的(模板的來源代碼直接用位移)。
# ★ 沒有它們的話 hbin/vbin 與 RWZM 兩個軸**什麼都不會做** —— 只把宣告的
#   幾何縮小、卻不真的程式化硬體,就是「producer 的有效區釘在 1936 寬、
#   錄出來只有左上一塊有畫面」那個 bug(OG3K_RWZM_AND_BUILD_PIPELINE §1)。
R_HBIN_E = 23                   # +0x5C  CRCT hbin 列舉 0/1/2 = x1/x3/x5
R_VBIN_E = 24                   # +0x60  CRCT vbin 列舉 0/1   = x1/x3
R_ZH = 25                       # +0x64  RWZM 水平(1024 = unity)
R_ZV = 26                       # +0x68  RWZM 垂直
RECIPE_WORDS = 27

# 長寬比表 0xC0B4CAB8,每筆 8 bytes = 字面的比例對。**共 8 筆,不是 4 筆** ——
# og3kaspect.S 的註解只列了 1..4,實際上還有:
#     1 = 4:3   2 = 3:2   3 = 16:9   4 = 1:1   5 = 21:9
#     6 = 7:6   7 = 141:100   8 = 161:129     第 9 筆是 ASCII 垃圾,不可用
#
# 只用 1..5。6/7/8 存在於表裡,但它們在**顯示鏈**這條路上沒有任何先例
# (原廠一律用 3,OG3K 證明了 2 可以),語意也不明,不拿來賭。
#
# ⚠ 1 / 4 / 5 同樣沒有實機先例。挑最接近的仍然比「一律宣告 16:9」好得多:
#   2.39:1 的畫面宣告 16:9 是差 35%(明顯拉長),宣告 21:9 只差 2.4%。
#   失效模式是矩形適配不準(視覺),不是凍結。
ASPECT_TABLE = {1: (4, 3), 2: (3, 2), 3: (16, 9), 4: (1, 1), 5: (21, 9)}
ASPECT_PROVEN = (2, 3)          # 實機驗證過的只有這兩個
ASPECT_Q = 1024                 # 比例的定點刻度


def aspect_q_table() -> bytes:
    """每個 enum 的比例 x/y,定點 x1024。相機上就不必對每一筆做除法。"""
    return struct.pack(f"<{len(ASPECT_TABLE)}I",
                       *(x * ASPECT_Q // y
                         for _, (x, y) in sorted(ASPECT_TABLE.items())))


def aspect_enum(act_w, act_h, scale=(1, 1), rwzm=None):
    """挑最接近的長寬比 enum。

    ★ 兩個坑:

    1. **不能比 `|w*y - h*x|`** —— 那個量會被 y 縮放。2000x662 用它會選到
       1:1(差 202%)而不是 21:9(差 29%)。改成先把畫面比例算成定點
       `w*1024/h`,再和每個 enum 的定點比例比絕對差。
    2. **像素不一定是方的。** mode 12 是 3x6 非對稱縮減,光柵 2000x662 的
       實際顯示比例要乘 sx/sy = 1/2 -> 1.51,也就是 3:2。出貨的 HSW 把長寬比
       寫死成 2 正是這個原因。所以要吃 donor 的 geometry scale。
    """
    sx, sy = scale
    num = act_w * ASPECT_Q * sx
    den = act_h * sy
    if den == 0:
        return 3
    r = num // den
    # ★ 3. **RWZM 也會改變像素涵蓋的感測器區域。** 一個輸出像素涵蓋
    #    `scale * zoom/1024` 個感測器像素,所以非等向的 RWZM 會把顯示比例
    #    再扭一次。2026-09-29 上機抓到:mode 12(scale 3x6)配 RWZM 2048/1024
    #    本來是**修正**非對稱(3x2=6 對 6x1=6,像素變方形、輸出正好 3:2),
    #    但這裡只吃 scale 就會算成 992x3 : 662x6 = 0.749 —— **直式** ——
    #    於是顯示鏈把畫面塞進一個窄高的框,左右大黑邊、內容縱向拉長。
    #
    #    分兩步算是為了相機端不溢位:`t*1024*sx*zh` 會超過 32 位元。
    #    先算 t(約 1500)再乘 zoom 比,最大約 t*3072 = 4.6e6,安全。
    if rwzm:
        zh, zv = rwzm
        if zh and zv:
            r = r * zh // zv
    best, berr = 0, None
    for e, (x, y) in sorted(ASPECT_TABLE.items()):
        err = abs(r - x * ASPECT_Q // y)
        if berr is None or err < berr:
            best, berr = e, err
    return best

# 時序表的 hmax 索引。全 70 個模式只用到這六種。
HMAX_SET = (330, 360, 395, 445, 450, 911)
# tail 的下限。原廠 70 筆用過的 16 種 tail 最小 330、最大 2151,取這個下限
# 解出來的 tail 一定落在有先例的範圍裡。
MIN_TAIL = 330

RATE_KEYS = tuple(RATES)        # 索引就是 AXIS 的 rate 欄位


# ---- 表 --------------------------------------------------------------------
def rate_table() -> bytes:
    """11 筆 x 12 bytes:(週期數, 整數標稱格率, 引擎格率 float bits)。

    週期數先算好,相機上就不必做 72e6/fps;float bits 也先算好,不必有浮點。
    """
    out = b""
    for k in RATE_KEYS:
        fps = RATES[k]
        cycles = round(CLOCK / fps)
        nominal = round(fps)
        efps = struct.unpack("<I", struct.pack("<f", fps))[0]
        out += struct.pack("<3I", cycles, nominal, efps)
    return out


def ratestr_table() -> bytes:
    """11 筆 x 8 bytes:鍵尾碼的 ASCII 字串,NUL 補滿。索引 = 格率索引。

    ★ **選單選的格率本來就在 picker 的鍵裡面。** 鍵是「標籤 + 格率字串」
    (原廠的字串池在 `0xC0BE4800`:`400 240 120 100 23_98 60 50 48 30 25 24`),
    而 `imx410_fmt` 只比對前四個位元組的標籤,後面整段一直被丟掉。

    比對尾碼就能把選單的格率還原成索引寫進 AXIS —— **不用新增任何 hook**,
    因為那支 hook 已經掛著、鍵也已經在手上了。見 §8.10。

    最長的是 `23_98`(5 字元),補 NUL 到 8 讓相機端可以用固定步距。
    """
    out = b""
    for k in RATE_KEYS:
        s = k.encode("ascii")
        if len(s) > 7:
            raise SystemExit(f"格率字串 {k!r} 放不進 8 bytes")
        out += s + b"\0" * (8 - len(s))
    return out


def ratnum_table() -> bytes:
    """11 筆 x {分子, 分母} —— CinemaDNG FrameRate 標籤的有理數。

    對齊原廠 `FUN_c00c9bd0` 的慣例:NTSC 系(非整數)用 /1001,整數用 /1000。
    逐筆對得上原廠那張表(24000/1001、24000/1000、25000/1000、30000/1001、
    48000/1000、50000/1000、60000/1001、100000/1000、120000/1001),
    原廠沒有的 240 就照同一條規則補成 240000/1001。
    """
    out = b""
    for k in RATE_KEYS:
        fps = RATES[k]
        if float(fps).is_integer():
            num, den = int(fps) * 1000, 1000
        else:
            num, den = round(fps * 1001), 1001
        out += struct.pack("<2I", num, den)
    return out


def timing_table() -> bytes:
    """6 種 hmax x 11 個格率,每格一個字 `vmax | tail<<16`。

    解不出來(vmax 或 tail 溢位 16 位元)的格子寫 0,相機上當「這個組合不行」。
    """
    out = b""
    for hmax in HMAX_SET:
        for k in RATE_KEYS:
            cycles = round(CLOCK / RATES[k])
            tail = cycles % hmax
            while tail < MIN_TAIL:
                tail += hmax
            vmax = (cycles - tail) // hmax + 1
            ok = 2 <= vmax <= 0xFFFF and tail <= 0xFFFF
            assert not ok or hmax * (vmax - 1) + tail == cycles
            out += struct.pack("<I", (vmax | (tail << 16)) if ok else 0)
    return out


# ---- AXIS ------------------------------------------------------------------
def axis_words(*, bit, rate, raster, hbin=1, vbin=1,
               rwzm=(RWZM_UNITY, RWZM_UNITY), crop=(0, 0), mode=0):
    w = [0] * AXIS_WORDS
    w[A_BIT] = bit
    w[A_RATE] = RATE_KEYS.index(rate)
    w[A_RW], w[A_RH] = raster
    w[A_BIN] = hbin | (vbin << 16)
    w[A_ZH], w[A_ZV] = rwzm
    w[A_CROP] = crop[0] | (crop[1] << 16)
    w[A_MODE] = mode
    return w


# ---- 參考模型:og3krecipe.S 必須產生逐字相同的結果 --------------------------
def expected_recipe(reg: Registry, axis) -> list:
    """AXIS -> RECIPE。**這是 og3krecipe.S 的規格。**

    每一步都刻意寫成相機上做得到的樣子:沒有浮點、沒有 64 位元、除法只出現在
    幾何(rwzm 是任意數字,躲不掉),時序純查表。
    """
    r = [0] * RECIPE_WORDS
    r[R_SNAP:R_SNAP + AXIS_WORDS] = list(axis)

    bit = axis[A_BIT]
    hbin, vbin = axis[A_BIN] & 0xFFFF, axis[A_BIN] >> 16
    rw, rh = axis[A_RW], axis[A_RH]
    zh, zv = axis[A_ZH], axis[A_ZV]

    # 幾何。整數除法,截斷 —— 與 imx410_full.record_raster 同一套規則。
    step = max(ALIGN_SAFE, ALIGN[bit])
    rec_w = ((rw // hbin) * RWZM_UNITY // zh) // step * step
    rec_h = ((rh // vbin) * RWZM_UNITY // zv) // 2 * 2
    r[R_RECW], r[R_RECH] = rec_w, rec_h

    # 裁切。AXIS 給 0 就用原廠留邊慣例(16 寬 / 10 高)。
    cw, ch = axis[A_CROP] & 0xFFFF, axis[A_CROP] >> 16
    if cw == 0 or ch == 0:
        cw = (rec_w - MARGIN_W) // step * step
        ch = (rec_h - MARGIN_H) // 2 * 2
    r[R_ACTW], r[R_ACTH] = cw, ch
    # CRCT 的列舉,不是倍率。FUN_c022ee10:0->1 1->3 2->5;FUN_c022ee90:0->1 1->3。
    r[R_HBIN_E] = {1: 0, 3: 1, 5: 2}[hbin]
    r[R_VBIN_E] = {1: 0, 3: 1}[vbin]
    r[R_ZH], r[R_ZV] = zh, zv
    # 長寬比要等 donor 挑好才算得出來(需要它的 geometry scale),見下面。

    # 格率常數
    ridx = axis[A_RATE]
    fps = RATES[RATE_KEYS[ridx]]
    cycles = round(CLOCK / fps)
    r[R_NOM] = round(fps)
    r[R_EFPS] = struct.unpack("<I", struct.pack("<f", fps))[0]

    # donor:掃 metadata,挑出通過的,再依 §5.2 的四個理由排序。
    # 相機上是一次掃描帶著「目前最好的」走,不是先收集再排序 —— 這裡寫成
    # 同樣的形狀,讓兩邊的優先順序逐條對得起來。
    best = None
    for m in reg.modes:
        if (m.raw[0], m.raw[1]) != (rw, rh):
            continue
        if m.depth != (14 if bit == 14 else 12):
            continue
        if axis[A_MODE] and m.mid != axis[A_MODE]:
            continue
        if m.hmax not in HMAX_SET:
            continue
        # 消隱餘裕:cycles/hmax - rows >= vblank,寫成不必除法的形式
        if cycles < (m.raw[1] + m.vblank) * m.hmax:
            continue
        # 相機上不能比浮點。「原廠時序就等於目標」改成**整數週期相等**,
        # 這比浮點比較更嚴謹,而且兩邊做的是同一件事。
        native = m.hmax * (m.vmax - 1) + m.tail == cycles
        quiet = bit != 14 and m.hmax >= 445
        # 排名壓成一個可比較的 32-bit 字,與相機上的做法完全相同:
        #   bit31 不是 quiet   bit30 不是 native   bit9..18 (1023-hmax)   bit0..8 mid
        key = ((0 if quiet else 1) << 31) | ((0 if native else 1) << 30) \
            | ((1023 - m.hmax) << 9) | m.mid
        if best is None or key < best[0]:
            best = (key, m)
    if best is None:
        return r                      # valid = 0 -> FHD fallback
    m = best[1]

    ent = timing_table()
    off = (HMAX_SET.index(m.hmax) * len(RATE_KEYS) + ridx) * 4
    packed = struct.unpack_from("<I", ent, off)[0]
    if packed == 0:
        return r
    vmax, tail = packed & 0xFFFF, packed >> 16
    r[R_VALID] = 1
    r[R_MODE], r[R_IDX] = m.mid, m.idx
    # 像素的形狀,不換算感測器(2026-10-04,使用者:壓扁才是真實的樣子)
    r[R_ASPECT] = aspect_enum(r[R_ACTW], r[R_ACTH])
    # donor 的原廠時序,還原用。模型直接取映像值;相機上是讀那時還沒被改過的
    # 時序記錄 —— 兩者相同,因為 og3krecipe 跑在 imx410_fmt 寫入之前。
    r[R_SAVE0] = m.hmax | (m.tail << 16)
    r[R_SAVE1] = m.vmax | (m.x_start << 16)
    r[R_TW0] = m.hmax | (tail << 16)
    r[R_TW1] = vmax | (m.x_start << 16)
    return r


def recipe_bytes(reg: Registry, axis) -> bytes:
    return struct.pack(f"<{RECIPE_WORDS}I", *expected_recipe(reg, axis))


if __name__ == "__main__":
    reg = Registry()
    print(f"RATE 表 {len(rate_table())} bytes   TMG 表 {len(timing_table())} bytes")
    for lab, kw in (("OG3K 等價", dict(bit=12, rate="30", raster=(3032, 2012))),
                    ("OG2K 等價", dict(bit=12, rate="60", raster=(2016, 1344))),
                    ("HSW 等價", dict(bit=12, rate="240", raster=(2016, 672))),
                    ("全幅 3x3", dict(bit=12, rate="24", raster=(6064, 4042),
                                      hbin=3, vbin=3))):
        r = expected_recipe(reg, axis_words(**kw))
        print(f"{lab:<10} valid {r[R_VALID]} mode {r[R_MODE]:3d} "
              f"rec {r[R_RECW]}x{r[R_RECH]} act {r[R_ACTW]}x{r[R_ACTH]} "
              f"tw0 {r[R_TW0]:#010x} tw1 {r[R_TW1]:#010x}")


# ---- 畫布欄位 --------------------------------------------------------------
# 全功能版借的是 **p13**,不是 OG3K 借的 p83。OG3K 把 active/producer/preview
# 三組關掉,理由是「p83 原廠就對了」—— 那個理由對 p13 不成立(OG2K 借 p13,
# 三組全開),而且我們的幾何是任意的,更不能假設。所以**三組全寫**。
#
# hirate 的 "90"/"C0" 不是給高格率用的:p83/p13 的 +0x090/+0x0C0 與八個原廠
# 影片 profile 不同,每個格率都要修(notes/OG3K_ENGINE_CONFIG_THREE_FIELDS.md)。
# 真正只有 >60 fps 才要的是另外五欄。
HIRATE_ALWAYS = ("90", "C0")
# 2026-10-04:FC/100(scale float)不再在 >60 時寫死 2.0 —— scale 是 mode 自己的
# 縮減倍數,由宣告列(sl_modes.c declare_post)依 mode 寫;預設的 p83 本來就是 2.0。
HIRATE_OVER60 = ("B0", "DC", "E4")

# 模板 29 筆,>60 fps 時全部生效。32 是留餘裕 —— 這個數字同時綁著
# imx410_canvas.S 的 MAX_PAIRS、CANVAS 區塊大小與測試 harness,
# test_canvas_block_is_big_enough 會擋住它們漂開。
CANVAS_MAX_PAIRS = 32


def expected_canvas(reg: Registry, axis, fill=None) -> list:
    """這組配方要寫進畫布的 (位移, 值) 陣列 —— og3krecipe 要產生逐字相同的。

    `fill` 是**安裝時**決定的(donor 是不是空殼),不是每個配方各自算 ——
    模板寫進 cave 之後就固定了。給 None 才依這組配方推導(獨立使用時)。
    """
    r = expected_recipe(reg, axis)
    if not r[R_VALID]:
        return []
    fps = RATES[RATE_KEYS[axis[A_RATE]]]
    hirate = HIRATE_ALWAYS + (HIRATE_OVER60 if fps > HIRATE_ABOVE else ())
    rec = (r[R_RECW], r[R_RECH])
    # 感測器視窗 +0x0F4/+0x0F8:**只有空殼 donor 要補**。
    # HSW 需要它是因為 p13 宣告 2016x1344 而 mode 12 只讀 672 行;OG3K 借的
    # p83 原生視窗就是對的,所以它的 write_window=False。條件掛在**借來的
    # profile 的原廠視窗**上 —— 幾何相符的 donor 不必補。
    # (2026-09-28 訂正:原本寫「一律寫」,那是在還寫死 p13 的時候。)
    # 空殼 donor **必須**填滿(OG2K/HSW 的做法);原生完整的只補差異
    # (OG3K 的做法)。兩條路各自有出貨產品驗證,混著用就是 2026-09-28 的三次凍結。
    if fill is None:
        _pid, fill, _d, _nat = pick_profile(rec)
    st = gate_state(axis, fill)
    pairs = canvas_pairs(rec=rec, act=(r[R_ACTW], r[R_ACTH]), depth=axis[A_BIT],
                         preview=fill, active=True, producer=fill,
                         window=st[CG_WINDOW], hirate=hirate, plane_raw=True)
    if st[CG_BIN]:
        pairs.update({0x5C: r[R_HBIN_E], 0xC8: r[R_VBIN_E]})     # 錄影那一對;預覽由宣告列
    if st[CG_ZOOM]:
        # H 區塊兩欄都吃 ZH、V 區塊兩欄都吃 ZV —— 與上面 hbin/vbin 的排法
        # 對稱。2026-09-28 訂正,見 CANVAS_TEMPLATE 的註解。
        pairs.update({0x64: r[R_ZH], 0xD4: r[R_ZV]})              # 錄影那一對;預覽由宣告列
    return sorted(pairs.items())


# ---- 畫布模板:og3krecipe 走這張表產生 (位移, 值) 陣列 ----------------------
# 不把 21 對硬編成指令(那是 og3kcanvas 現在 104 個字的由來),改成資料 +
# 一個迴圈。值的來源用代碼表示:
CS_RECW, CS_RECH, CS_ACTW, CS_ACTH = 0, 1, 2, 3
CS_PLANE_P, CS_PLANE_R = 4, 5
CS_ONE, CS_ZERO, CS_2F = 6, 7, 8
# 9..12 直接對到 RECIPE 的 R_HBIN_E..R_ZV(連續四個字)
CS_HBIN, CS_VBIN, CS_ZH, CS_ZV = 9, 10, 11, 12
# 閘門:0 = 一律寫,1 = 只有 >60 fps 才寫,4 = RWZM 非 unity 才寫
CG_ALWAYS, CG_OVER60, CG_FILL, CG_BIN, CG_ZOOM, CG_WINDOW = 0, 1, 2, 3, 4, 5

# ★ 相機端自己判斷的閘門 —— `canvas_emit` 用位元圖分派(bit N = 閘門 N 成立),
#   所以這裡**不要**在安裝時解掉它們。其餘的仍然是安裝時常數。
#   編號就是位元位置,所以加新的閘門時 og3krecipe 那側不用改分派邏輯。
RUNTIME_GATES = (CG_OVER60, CG_ZOOM)

# ★ **預覽那四欄(+0x0C/+0x10/+0x20/+0x28)與 producer 那兩欄(+0xD8/+0xE0)
#   不寫。** 2026-09-28 使用者指出:預覽管線只能趨近 fp 的 LCD 解析度。
#   原廠值就是證據 —— p13 預覽光柵 1920x1280、p83 是 2024x1341,而 LCD 是
#   1024x682。那些是**顯示路徑的緩衝**,大約 LCD 的兩倍,與錄影光柵無關。
#   把它們撐到 3024x2012 是種類上的錯,不只是大小:
#       全部 24 對 -> 33.5 MB   拿掉預覽 -> 21.5 MB   再拿掉 producer -> 13.7 MB
#   而 `memmgr bufuse` 顯示 IMAGE 池 total 17.8 MB、**remaining 只剩 3,520 B**。
#
#   預覽的**比例**本來就有正確的處理方式:GTAB 那一組改六個預覽 profile 的
#   可見高(1125 <-> 1334)。OG3K 就是這樣做的,它的畫布一欄預覽都不寫
#   (write_active/producer/preview 全 False)。
CANVAS_TEMPLATE = (
    (0x000, CS_RECW,    CG_ALWAYS), (0x004, CS_RECH,    CG_ALWAYS),
    (0x024, CS_ACTW,    CG_ALWAYS), (0x02C, CS_ACTH,    CG_ALWAYS),
    # 只有空殼 donor 要填的六欄
    (0x00C, CS_RECW,    CG_FILL), (0x010, CS_RECH,    CG_FILL),
    (0x020, CS_ACTW,    CG_FILL), (0x028, CS_ACTH,    CG_FILL),
    (0x0D8, CS_RECW,    CG_FILL), (0x0E0, CS_RECH,    CG_FILL),
    (0x080, CS_PLANE_P, CG_ALWAYS), (0x084, CS_PLANE_R, CG_ALWAYS),
    (0x090, CS_ONE,     CG_ALWAYS), (0x0B0, CS_ONE,     CG_OVER60),
    (0x0C0, CS_ZERO,    CG_ALWAYS),
    (0x0DC, CS_RECW,    CG_OVER60),
    (0x0E4, CS_RECH,    CG_OVER60), (0x0F4, CS_RECW,    CG_WINDOW),
    (0x0F8, CS_RECH,    CG_WINDOW),
    # CRCT 的 hbin/vbin。PARAM +0x58 預覽 hbin、+0x5C 錄影 hbin、
    # +0xC4 預覽 vbin、+0xC8 錄影 vbin(REDUCTION_INVENTORY §2)。
    # 四個都要寫 —— 只讓錄影那一對生效、預覽留原值會花屏後凍結(§6c)。
    # ★ 2026-10-04:只寫**錄影**那一對。預覽的 bin / RWZM 由宣告列給
    #   (sl_modes.c declare_post、imx410_profile.preview_path):全寬讀出 ÷3、不縮放,
    #   與原廠 UHD 及外部三家相同。以前預覽跟著錄影寫,6064 寬讀出的預覽
    #   被撐到 ~3800 寬,塞進 p83 的 2024 寬緩衝 —— r69 的花屏凍結。
    #   §6c「只動錄影那對會凍結」是預覽留在 1600、錄影 unity 的反向組合;
    #   錄影縮放、預覽 ÷3 不縮放正是原廠 UHD30(p131/p151/p171)。
    (0x05C, CS_HBIN,    CG_BIN), (0x0C8, CS_VBIN,    CG_BIN),
    # RWZM 四欄。★ 2026-09-28 訂正:排法與 hbin/vbin **完全對稱** ——
    # +0x60/+0x64 是「H 的預覽/錄影」,+0xD0/+0xD4 是「V 的預覽/錄影」,
    # 不是「預覽 H/V」與「錄影 H/V」(imx410_full 的 RWZM 段有證據)。
    # 舊的排法把 ZV 寫進 +0x64(錄影的 **H**)、把 ZH 寫進 +0xD0(預覽的 **V**),
    # 兩條路徑都變成各自的單一值。ZH == ZV 時逐字相同,所以已出貨的組態
    # (RWZM 全 unity)不受影響 —— 但只要使用者把長寬設成不同就是錯的。
    # 同樣不能拆:只讓錄影那一對 unity、預覽留 1600 會花屏後凍結
    # (OG3K_RWZM_AND_BUILD_PIPELINE §6c)。
    (0x064, CS_ZH,      CG_ZOOM), (0x0D4, CS_ZV,      CG_ZOOM),
)


CANVAS_TEMPLATE = tuple(sorted(CANVAS_TEMPLATE))


def _recipe_rec(reg):
    r = expected_recipe(reg, axis_words(bit=12, rate="30", raster=(3032, 2012)))
    return (r[R_RECW], r[R_RECH])


# ★ 只在某個軸**真的要求**時才偏離 donor 的原廠值。
#
# 2026-09-28:預設配方(bin ÷1、RWZM unity)我卻把 p83 的 RWZM 從
# 1536/1023/1536/1023 全部改成 1024,而 OG3K 一欄都不寫(WITH_RWZM=False)。
# RWZM 正是筆記裡「open gate 的關鍵」、寫錯會「錄影變花屏、相機隨後凍結」的
# 那一組。**使用者沒要求縮放就不要動它。**
#
# 原則:預設配方要逐欄等於 OG3K 已驗證的組態。
def gate_state(axis, fill):
    hbin, vbin = axis[A_BIN] & 0xFFFF, axis[A_BIN] >> 16
    return {CG_FILL: bool(fill),
            CG_BIN: hbin != 1 or vbin != 1,
            CG_ZOOM: axis[A_ZH] != RWZM_UNITY or axis[A_ZV] != RWZM_UNITY,
            # 視窗:donor 幾何相符時它原廠就對了(OG3K 的 write_window=False);
            # 空殼 donor 才要補(HSW 的理由)。
            CG_WINDOW: bool(fill)}


def canvas_template(fill=None, axis=None) -> bytes:
    """一筆一個字:位移 16 位元 | 來源 8 位元 | 閘門 8 位元。0xFFFFFFFF = 表尾。

    `fill`(要不要填滿空殼 donor)是**安裝時就決定**的常數,所以在這裡就篩掉,
    payload 只需要處理「一律寫」與「>60 fps」兩種閘門。
    """
    if fill is None:
        from imx410_full import Registry as _R
        fill = pick_profile(_recipe_rec(_R()))[1]
    st = gate_state(axis or axis_words(bit=12, rate="30", raster=(3032, 2012)), fill)
    # ★ 執行期閘門不在這裡解 —— 留著讓 og3krecipe 的 canvas_emit 自己判斷。
    #   2026-09-29:CG_ZOOM 搬進 payload。在那之前 RWZM 是**安裝時**的常數,
    #   執行期改 AXIS 只會讓 RECIPE 正確地跟著變而硬體不動(§12.29 的假通過)。
    #   CG_BIN 沒搬:CRCT 對 CDNG 只是個宣告,本來就不該給使用者(§6.1)。
    #   CG_FILL / CG_WINDOW 沒搬:它們跟著 donor 走,而 donor id 編進 picker
    #   表項,執行期換不了。
    for g in RUNTIME_GATES:
        st.pop(g, None)
    out = b""
    for off, src, gate in CANVAS_TEMPLATE:
        if gate in st:
            if not st[gate]:
                continue
            gate = CG_ALWAYS
        assert off <= 0xFFFF and src <= 0xFF and gate <= 0xFF
        out += struct.pack("<I", off | (src << 16) | (gate << 24))
    return out + struct.pack("<I", 0xFFFFFFFF)      # 表尾


# 原廠時序的備份不是一張表。曾經想做 70 筆 x 8 bytes = 560 B,但 cave 裡沒有
# 那麼大的連續空間 —— 而且根本不需要,見 R_SAVE0/R_SAVE1 的說明。


# ---- donor PARAM profile:依配方的幾何挑,不能寫死 -------------------------
# 2026-09-28 上機三次凍結的根因。
#
#     p13  rec = 0x0        act = 0x0         <- **未使用的空殼**
#     p83  rec = 3032x2012  act = 3008x2000   <- 原生就是我們要的
#
# OG2K 能借 p13 是因為它把 write_active/producer/preview 全開,**把空殼填滿**。
# 我為了壓低配置把那六欄關掉,等於拿一個 rec=0/act=0 的 profile 去錄影 ——
# 65 欄裡我們只覆寫 18 欄,其餘 47 欄仍然是空殼的值。
#
# OG3K 只需要覆寫約 5 欄,正是因為它挑了**原生幾何相符**的 p83。
#
# 挑法:原生 rec 與我們的記錄矩陣最接近的那一列。差太多就明講,不要硬撐。
_PROFILE_JSON = ("research/other/external/FP3K-technical-handoff-2026-09-10"
                 "/analysis/firmware/raw-profiles.json")


# PARAM profile 的一列是 65 個字,位移 = 索引 x 4。求解器要用到的那些:
P_RECW, P_RECH = 0, 1           # +0x00 +0x04  記錄矩陣
P_ACTW, P_ACTH = 9, 11          # +0x24 +0x2C  可見
P_PREVW, P_PREVH = 3, 4         # +0x0C +0x10  預覽
P_HBIN_P, P_HBIN_R = 22, 23     # +0x58 +0x5C  hbin 預覽 / 錄影
P_VBIN_P, P_VBIN_R = 49, 50     # +0xC4 +0xC8  vbin 預覽 / 錄影
P_ZH_P, P_ZH_R = 24, 25         # +0x60 +0x64  RWZM **水平** 預覽 / 錄影
P_ZV_P, P_ZV_R = 52, 53         # +0xD0 +0xD4  RWZM **垂直** 預覽 / 錄影
P_WINW, P_WINH = 61, 62         # +0xF4 +0xF8  感測器窗口
P_SCALEX, P_SCALEY = 63, 64     # +0xFC +0x100 幾何 scale,**float**
HBIN_ENUM = {0: 1, 1: 3, 2: 5}  # FUN_c022ee10
VBIN_ENUM = {0: 1, 1: 3}        # FUN_c022ee90


def _param_json():
    import json
    import pathlib as _p
    root = _p.Path(__file__).resolve().parent.parent.parent.parent
    return json.loads((root / _PROFILE_JSON).read_text())


def param_words():
    """全部 306 列的原始 65 個字,依 profile id。逆向求解器的驗證資料。"""
    return {r["profile_ids"][0]: r["words"] for r in _param_json()["rows"]}


def _param_rows():
    out = {}
    for r in _param_json()["rows"]:
        w = r["words"]
        out[r["profile_ids"][0]] = dict(rec=(w[P_RECW], w[P_RECH]),
                                        act=(w[P_ACTW], w[P_ACTH]),
                                        prev=(w[P_PREVW], w[P_PREVH]))
    return out


# **只從有實機先例的 donor 裡挑。** 純幾何不夠:p43 的原生 rec 也是 3032x2012,
# 但 `OG3K_PLAYBACK_PROFILE_CLASSES` 明寫它不能用(+0x44 == 0,宣告「不需要
# 解碼緩衝」)。profile 有類別,而類別不在幾何裡。
#
#   fill=False  原生幾何完整,只覆寫少數欄位            OG3K 的做法
#   fill=True   空殼 rec=0x0,**必須**把 active/producer/preview 全填滿
#               OG2K / HSW 的做法。配置會比較高,那是代價不是浪費。
#
# ★ 2026-09-28 我兩邊的壞處都拿到了:挑了需要填滿的 p13,又為了壓配置把填滿
#   的那六欄關掉,於是拿一個 rec=0/act=0 的 profile 去錄影。三次凍結。
PROVEN_DONORS = {
    83: dict(fill=False, note="OG3K 用它,3032x2012 錄影已驗證"),
    13: dict(fill=True, note="OG2K / HSW 用它;空殼,必須填滿"),
}


# 幾何「夠近」的門檻。近就用原生完整的那一列(只覆寫少數欄位);不夠近就用
# 空殼並**強制填滿**。OG2K 的 rec 2016x1344 離 p83 有 1684,它選的正是後者。
PROFILE_NEAR = 256


def pick_profile(rec, act=None):
    """挑 donor PARAM profile。回傳 (profile, 要不要填滿, 差距, 原生 rec)。

    只在**有實機先例**的 donor 裡挑。幾何夠近就用原生完整的;不夠近就用空殼
    並強制填滿 —— 兩條路各自都有出貨產品驗證過,混著用才會出事。
    """
    rows = _param_rows()
    near = [(abs(rows[p]["rec"][0] - rec[0]) + abs(rows[p]["rec"][1] - rec[1]), p)
            for p, c in PROVEN_DONORS.items() if not c["fill"]]
    d, pid = min(near)
    if d <= PROFILE_NEAR:
        return pid, False, d, rows[pid]["rec"]
    shell = min(p for p, c in PROVEN_DONORS.items() if c["fill"])
    return shell, True, d, rows[shell]["rec"]


# ---- 逆向幾何求解器 --------------------------------------------------------
# 2026-09-28。原廠 profile 是**逆向**解出來的:先選定輸出,再回推窗口/bin/RWZM。
# 韌體兩個方向都算(blk_c03.c 13671 是逆向、13772 是正向):
#
#     正向  out = (in / bin) * 1024 / rwzm
#     逆向  in  = bin * (rwzm * out + 512) >> 10
#
# 規則是「**產出 >= 目標,多的裁掉**」,不是「產出 == 目標」——
# FHD60 產出 1940x1093 而 rec 是 1936x1090,FHD60CROP 產出 2088x1174 也是 1936x1090。
# 同一個輸出可以有多組解,UHD30 與 UHD30CROP 就是同一個 3856x2170 的兩組:
# UHD30 用 1600 從 6064x3412 縮下來,UHD30CROP 用 unity 從 4176x2174 直接裁。
#
# ★ 2026-09-28 訂正:RWZM 的六個值是把**預覽欄**混進來才有的。
#   分成兩條路徑之後(見 imx410_full 的 RWZM 段):
#       錄影(+0x64 / +0xD4)  306 列只出現 1024 / 1500 / 1600     <- 求解器用這個
#       預覽(+0x60 / +0xD0)  1024 / 1280 / 1536 / 1600 / 2048 / 3072
#   舊的 RWZM_SET 讓求解器拿得到 2048/3072,那是預覽才有的值。
#
# 韌體把值下夾在 1024(RWZM_CLAMP),所以原廠表裡的 1023 生效時就是 unity ——
# 這裡一律寫 1024,與原廠等價。
RWZM_SET = (RWZM_UNITY, 1500, 1600)
RWZM_SET_PREVIEW = (RWZM_UNITY, 1280, 1536, 1600, 2048, 3072)
HBIN_SET = (1, 3, 5)
VBIN_SET = (1, 3)

# ⚠ 原廠 306 列**沒有一列**的 H 與 V RWZM 不相等。欄位與正向計算都支援非等向
#   (+0x64 除寬、+0xD4 除高,各自獨立),但沒有實機先例 —— 跟 ASPECT_PROVEN
#   一樣,能算不等於驗過。要非等向的長寬比,hbin/vbin 才是有先例的那條路。
RWZM_ANISOTROPIC_PROVEN = False


def solve_geometry(window, want, hbin_opts=HBIN_SET, vbin_opts=VBIN_SET):
    """給視野(感測器窗口)與目標輸出,解出 (hbin, vbin, rwzm_h, rwzm_v, 產出)。

    兩軸**各自獨立**解。RWZM 的欄位與韌體的正向計算都是各軸獨立的
    (`blk_c03.c` 13772:`+0x64` 除寬、`+0xD4` 除高),所以長寬可以用
    不同比例壓縮。

    ⚠ 但長寬比例不同 = **非方形像素**。目標比例與光柵比例不符時會自然發生,
      而原廠 306 列零例外都是 ZH == ZV(比例差異用裁切吸收)。所以這是
      **有意義但沒有原廠先例**的組合 —— UI 要講清楚,不要讓使用者以為
      「輸入什麼解析度就得到什麼畫面」。見 §12.25 的 RWZM_ANISOTROPIC_PROVEN。

    偏好:bin 不動(CRCT 是額外一層,原廠四個定點的錄影側全是 ÷1),
    然後 RWZM 取**最大**的可行值(縮最多 = 後段頻寬最省)。
    解不出來回 None —— 例如目標比窗口還大。
    """
    def axis(win, out, bins, rset):
        best = None
        for b in bins:
            for z in sorted(rset, reverse=True):
                got = (win // b) * 1024 // z
                if got >= out:
                    cand = (b != 1, -z, b, z, got)   # bin 不動優先,再取最大 rwzm
                    if best is None or cand < best:
                        best = cand
                    break            # 這個 bin 下最大的 rwzm 就是它
        return best

    h = axis(window[0], want[0], hbin_opts, RWZM_SET)
    v = axis(window[1], want[1], vbin_opts, RWZM_SET)
    if h is None or v is None:
        return None
    return h[2], v[2], h[3], v[3], (h[4], v[4])
