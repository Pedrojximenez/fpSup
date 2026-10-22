#!/usr/bin/env python3
"""IMX410 全功能版 —— 七軸組合引擎。

OG3K / OG2K / OG6K / HSW 各自是「一組寫死的格式表」。全功能版把那張表變成
**由使用者七個選項即時算出來的一列**:

    位元深度  8 / 10 / 12 / 14            picker 三張表 + 一張我們自己的
    格率      23.976 .. 239.760           時序自己解,0 ppm
    原始解析度 16 個原廠光柵族             含「怎麼柴切全尺寸」
    hbin      1 / 3 / 5                   CRCT,感測器讀出之後
    vbin      1 / 3                       CRCT,**沒有 ÷5**
    RWZM      長寬各一個任意數字           1024 = unity,值是除數 ×1024
    最終裁切  對齊到硬體封裝粒度的尺寸      見 ALIGN
    mode      以上選完之後剩下的感測器模式

這個檔案**只讀韌體映像,不碰相機**,而且不產生任何寫入 —— 它只回答
「這組選項合不合法、剩下哪些 mode、最後會錄出多大」。寫入計畫由
og3k_plan.py 那一側依這裡解出的 Recipe 產生。

    ./imx410_full.py rasters                     原始解析度選單的內容
    ./imx410_full.py modes --raster 3032x2012    mode 選單的內容
    ./imx410_full.py crops --bit 12 --size 3032x2012
    ./imx410_full.py resolve --bit 12 --fps 29.97 --raster 3032x2012 \
                             --hbin 1 --vbin 1 --rwzm 1024x1024
"""
from __future__ import annotations

import argparse
import collections
import dataclasses
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
FIRMWARE = ROOT / "out" / "MAIN_c0000000.bin"
B = 0xC0000000

# ---- 韌體裡的表 ------------------------------------------------------------
META = 0xC0B59DC0          # 感測器模式 metadata,70 筆 x 0x64
TIMING = 0xC0B59500        # 時序表,70 筆 x 0x20
MODE_NAME = 0xC0B575CC     # 模式名,mode_id x 0x20 的固定字串槽
PICKER = {8: 0xC0BE5810, 10: 0xC0BE59B0, 12: 0xC0BE5B50}   # 26 筆 x 0x10
CLOCK = 72_000_000         # 感測器時脈

# 感測器全開閘的外框。官方 active 是 6064x4040,韌體用 4042,兩行差距不要
# 當成已確認的有效感光點 —— 這裡只拿它算覆蓋率。
FULL_W, FULL_H = 6064, 4042


# ---- 對齊規則 --------------------------------------------------------------
# 來源:FUN_c0630e90(raw-packed-row-registers.asm)。它依位元深度寫
# 0x3018220C 的封裝模式,並把**每列 bytes ÷ 4** 寫進 0x30182214:
#
#     8-bit   r5 = w >> 2                     每列 w      bytes
#    10-bit   r5 = (w + w<<2) >> 4            每列 w*5/4
#    12-bit   r5 = ((w*3) >> 1) >> 2          每列 w*3/2
#    14-bit   r5 = ((w<<3) - w) >> 4          每列 w*7/4
#    16-bit   r5 = w >> 1                     每列 w*2
#
# 那個除法是整數右移,不是四捨五入 —— 寬度沒對齊就少算,DMA 每列少搬幾個
# byte,列與列之間累積位移(= LIVE_VIEW_DISPLAY_CHAIN.md 說的 stride 不匹配)。
# 所以「寬度必須讓每列 bytes 是 4 的倍數」是硬約束,不是建議。
ALIGN = {8: 4, 10: 16, 12: 8, 14: 16, 16: 2}
# 原廠 raw 路徑上每一個可見寬度都是 16 的倍數(6000 / 3840 / 3008 / 1920 /
# 4096 / 2000)。16 同時滿足四個深度,所以切換位元深度不必重算幾何。
ALIGN_SAFE = 16
# 高度:封裝暫存器不看高度,原廠可見高度也有奇數(1125 / 1077 / 1687 / 667)。
# 但 CFA 是 2x2,裁切原點與高度都是奇數時拜爾相位會翻 —— 取偶數。
ALIGN_H = 2
# 原廠影片邊界慣例:光柵 = 可見 + 16 寬 / + 10 高(1936x1090 -> 1920x1080、
# 3856x2170 -> 3840x2160、2016x1344 -> 2000x1334)。不是硬約束(p365
# 4096x2160 的可見寬度就等於光柵寬),但留邊是原廠在做的事。
MARGIN_W, MARGIN_H = 16, 10

# ---- CRCT 的合法抽頭 --------------------------------------------------------
# FUN_c022ee10(hbin):0->1  1->3  2->5   其他 -> assert 之後 while(true)
# FUN_c022ee90(vbin):0->1  1->3         其他 -> assert 之後 while(true)
# ⚠ 非法值不是畫面壞掉,是**相機當場鎖死,只能抽電池**。所以引擎這一側
#   就要擋掉,不能指望韌體回錯誤。
HBIN_TAPS = {1: 0, 3: 1, 5: 2}
VBIN_TAPS = {1: 0, 3: 1}

# ---- RWZM ------------------------------------------------------------------
# ★ 2026-09-28 訂正:這四欄的配對**不是**「(H,V) 各一組」,而是
#   「H 一組、V 一組,每組兩條路徑」。舊的讀法差一個槽,UHD 因此解不開(§12.25)。
#
#       H 區塊   +0x58 hbin 預覽   +0x5C hbin 錄影   +0x60 RWZM 預覽  +0x64 RWZM 錄影
#       V 區塊   +0xC4 vbin 預覽   +0xC8 vbin 錄影   +0xD0 RWZM 預覽  +0xD4 RWZM 錄影
#
#   韌體兩個方向的計算都證明了這件事(blk_c03.c 13671 逆向、13772 正向):
#       local_70 = (w / hbin << 10) / [obj+0xA0]   <- obj+0xA0 = profile +0x60
#       local_6c = (h / vbin << 10) / [obj+0xA4]   <- obj+0xA4 = profile +0xD0
#   +0x60 除的是**寬**、+0xD0 除的是**高**,而且是**同一條路徑** ——
#   所以 +0x60/+0x64 不可能是同一條路徑的 H/V。`FUN_c0438018` 的搬運分組
#   (+0x64 配 +0xD4 配 +0x5C 配 +0xC8)給出同一個答案。
#   這跟 hbin/vbin 的排法完全對稱,而那一組的標註本來就是對的。
#
# 值是**除數 x1024**:1024 = unity、1600 = 原廠 FHD 的 1.5625x 縮小。
#
# ★ 韌體把值**下夾在 1024**(`DAT_c0b56538 == 1024`,正逆兩個方向都夾)。
#   所以原廠表裡的 1023 生效時就是 1024 = unity —— 寫 1024 與原廠等價,
#   不是沒有先例的值。
RWZM_UNITY = 1024
RWZM_CLAMP = 1024                     # 韌體的下夾值 DAT_c0b56538
RWZM_MIN, RWZM_MAX = 1024, 16384      # 只縮不放;放大沒有原廠先例

# 四個欄位不能拆 —— 只讓錄影那一對 unity、預覽留 1600 會花屏後凍結
# (notes/OG3K_RWZM_AND_BUILD_PIPELINE.md §6c)。所以畫布一律 H 兩欄同寫、
# V 兩欄同寫。

# ---- 描述子池:寫入跟不上時「錄一下下就自動停」的機制 ----------------------
# 見 notes/HSW_240FPS_MODE12.md §53(源碼層面已解)。
#
# vbuf(0xC0379E08)是**每一格**的進入點,第一件事是跟池子要一個描述子:
#     FUN_c0374268(pool, 1 /* CinemaDNG */, 0)
#     CinemaDNG 那條的門檻是 `1 < 剩餘`,池子總數 0x60 = 96
# 所以最多配到剩 2 個 ⇒ **在途上限 94**。要不到就回 -1,錄影**正常停止**,
# 停止原因寫成字串進 0xC359BE70。七種原因(vbuf/vmed/vidx/vcnt/cnt/data/mem)
# 全部是乾淨停止。
#
# ★ 所以「資料率不足」的正確行為是**錄一小段然後自己停**,不是凍結。
#   實測:240 fps + SD = 94/94 `vbuf` 乾淨停(A001_020)。
#   反過來,寫得完的時候描述子每格歸還,池子永遠不見底(A001_120 寫了 1177 格)。
#
# **凍結發生在 vbuf 的控制流之外**,與吞吐無關 —— 見 CANVAS_REQUIRED。
POOL_TOTAL = 96
POOL_INFLIGHT = 94          # 門檻 `1 < 剩餘` 夾出來的在途上限
# 池深可以加大:OG_POOLDEPTH=300 改 v2/v4 的界線常數 + 執行期換池子。
# 每格在途成本約 1.02 MB,300 格 = 306 MB,RAW 區有 708 MB。
POOL_DEEP_MAX = 1024

# ---- 畫布:凍結的真正預測器 -------------------------------------------------
# 漏一欄的後果不是畫面壞掉,是**寫入端有格子永遠不會被標成完成**,停止路徑
# 一直等 → `fin_cnt < req_cnt ⇒ 卡住`(§25)。兩批都是實機證明出來的:
#
#   +0x0F4/+0x0F8  感測器視窗。donor 宣告的行數與實際讀出不符時必寫 ——
#                  p13 宣告 2016x1344 而 mode 12 只讀 672 行,不補的話 22 格
#                  請求永遠不會完成,錄影結束不了(§20、§25.2)。
#   >60 fps 的七欄 +0x90/+0xB0/+0xC0/+0xDC/+0xE4/+0xFC/+0x100。
#                  沒有它 119.88 會讓錄影凍結(2026-09-20 實機證明)。
CANVAS_BASE = (0x00, 0x04, 0x24, 0x2C, 0x80, 0xD8, 0xE0)
CANVAS_WINDOW = (0xF4, 0xF8)
CANVAS_HIRATE = (0x90, 0xB0, 0xC0, 0xDC, 0xE4, 0xFC, 0x100)
HIRATE_ABOVE = 60.0

# ---- 格率 ------------------------------------------------------------------
# 選單那九列 + enum 11/12。發射器 FUN_c043caf0 的界線原廠就是 cmp r3,#12,
# 字串池 0xC0BE4800 是 '400 240 120 100 23_98 .. 60 50 48 30 25 24'。
# **480 / 960 連字串都沒有**,而且見 CEILING 的註解:沒有任何光柵跑得到。
RATES = {
    "23_98": 24000 / 1001, "24": 24.0, "25": 25.0, "30": 30000 / 1001,
    "48": 48.0, "50": 50.0, "60": 60000 / 1001, "100": 100.0,
    "120": 120000 / 1001, "240": 240000 / 1001, "400": 400.0,
}
# 選單上已經有列的(九列)。240 需要補有理數 + 第十列 + 控制器上限,HSW 做過。
RATES_STOCK = ("23_98", "24", "25", "30", "48", "50", "60", "100", "120")
RATES_EXTRA = ("240", "400")


@dataclasses.dataclass(frozen=True)
class Mode:
    idx: int                 # metadata 索引(時序表也用同一個索引)
    mid: int                 # imager mode_list 的編號
    name: str
    raw: tuple               # 光柵 寬高
    scale: tuple             # 有效 geometry X/Y scale(+0x4C/+0x50)
    depth: int               # 8 / 12 / 14 / 16
    aspect: int              # 0=4:3 1=16:9 2=3:2 3=9:16 4=1:1
    crop_enum: int           # +0x58  0=full 1=crop
    cluster: int             # +0x60  readout cluster
    hmax: int
    vmax: int
    tail: int
    x_start: int
    vblank: int

    @property
    def coverage(self):
        """這個模式實際涵蓋感測器上多大一塊(光柵 x geometry scale)。"""
        return self.raw[0] * self.scale[0], self.raw[1] * self.scale[1]

    @property
    def fps(self):
        return CLOCK / (self.hmax * (self.vmax - 1) + self.tail)

    @property
    def rolling_us(self):
        """捲簾 = 有效行讀出時間。只有感測器這一層能改善它。"""
        return self.hmax * self.raw[1] / CLOCK * 1e6

    @property
    def fps_ceiling(self):
        """這個光柵的物理上限:blanking 全歸零,只剩有效行讀出。"""
        return CLOCK / (self.hmax * self.raw[1])

    @property
    def fingerprint(self):
        """quiet / fast / RAW14 —— 類比指紋分群,實測有畫質意義。"""
        if self.depth == 14:
            return "R14"
        return "Q12" if self.hmax >= 445 else "F12"


class Registry:
    """從韌體映像解出來的 70 個感測器模式,以及圍繞它們的七軸查詢。"""

    def __init__(self, image: bytes | None = None):
        self.img = image if image is not None else FIRMWARE.read_bytes()
        self.modes = tuple(self._read_mode(i) for i in range(70))
        self.by_id = {m.mid: m for m in self.modes}

    # -- 韌體讀取 ----------------------------------------------------------
    def _w(self, addr):
        return int.from_bytes(self.img[addr - B: addr - B + 4], "little")

    def _str(self, addr):
        off = addr - B
        end = self.img.index(b"\x00", off)
        # 模式名住在 32 bytes 的固定槽裡,尾巴補**空白**不是 NUL。
        return self.img[off:end].decode("ascii", "replace").rstrip()

    def _read_mode(self, i):
        a = META + i * 0x64
        t = TIMING + i * 0x20
        # 時序表每筆 0x20;hmax|tail<<16 與 vmax|x<<16 的排法與 og3k_plan 的
        # 格式表一致(fmt_table() 把 hm | (tl << 16) 寫成一個字)。
        w1, w2 = self._w(t + 4), self._w(t + 8)
        depth = {0: 12, 1: 14, 2: 16, 3: 12, 4: 8}[self._w(a + 0x3C)]
        mid = self._w(a)
        return Mode(idx=i, mid=mid, name=self._str(MODE_NAME + mid * 0x20),
                    raw=(self._w(a + 0x04), self._w(a + 0x08)),
                    scale=(self._w(a + 0x4C), self._w(a + 0x50)),
                    depth=depth, aspect=self._w(a + 0x54),
                    crop_enum=self._w(a + 0x58), cluster=self._w(a + 0x60),
                    hmax=w1 & 0xFFFF, tail=w1 >> 16,
                    vmax=w2 & 0xFFFF, x_start=w2 >> 16,
                    vblank=self._w(a + 0x5C))

    # -- 原始解析度軸 ------------------------------------------------------
    def rasters(self):
        """原始解析度選單:一族 = (光柵, scale, 感測器位深)。

        每一列都標出它在全尺寸上的柴切方式 —— 這正是使用者要看的東西:
        光柵 3032x2012 的 2x2 涵蓋 6064x4024(幾乎全開閘),而光柵更大的
        4176x2174 的 1x1 只涵蓋 69%W x 54%H(中央裁切)。**光柵大不等於視野大。**
        """
        fam = collections.OrderedDict()
        for m in self.modes:
            key = (m.raw, m.scale, m.depth)
            fam.setdefault(key, []).append(m)
        out = []
        for (raw, scale, depth), ms in fam.items():
            cw, ch = raw[0] * scale[0], raw[1] * scale[1]
            out.append(dict(raw=raw, scale=scale, depth=depth,
                            coverage=(cw, ch),
                            cover_x=cw / FULL_W, cover_y=ch / FULL_H,
                            modes=sorted(m.mid for m in ms)))
        out.sort(key=lambda r: (-r["cover_x"] * r["cover_y"], -r["raw"][0]))
        return out

    @staticmethod
    def cut_label(row):
        """「怎麼柴切全尺寸」的一行說明。"""
        fx, fy = row["cover_x"], row["cover_y"]
        if fx > 0.99 and fy > 0.99:
            base = "全開閘"
        else:
            base = f"裁切 {fx * 100:.0f}%W x {fy * 100:.0f}%H"
        sx, sy = row["scale"]
        if sx != sy:
            base += f" ⚠ {sx}x{sy} 非對稱,像素非方形(垂直要後製拉伸 {sy // sx}x)"
        return base

    # -- mode 軸 -----------------------------------------------------------
    def candidates(self, *, raster=None, depth=None, fps=None, aspect=None,
                   full_only=False):
        """前面幾軸選完之後,mode 選單裡還剩下哪些。

        fps 給的是**目標格率**:模式留不留下只看它的光柵跑不跑得到那個格率
        (hmax x 光柵高 < 一格的週期),時序我們自己會改寫 —— 這正是 OG3K
        八個格率共用 mode 98 的做法。
        """
        out = []
        for m in self.modes:
            if raster is not None and m.raw != tuple(raster):
                continue
            if depth is not None and m.depth != depth:
                continue
            if aspect is not None and m.aspect != aspect:
                continue
            if full_only and m.crop_enum != 0:
                continue
            if fps is not None and not self.rate_fits(m, fps):
                continue
            out.append(m)
        return out

    @staticmethod
    def blanking_lines(mode: Mode, fps: float):
        """這個格率下還剩幾行等效消隱。負數 = 有效行根本讀不完。"""
        return CLOCK / fps / mode.hmax - mode.raw[1]

    @staticmethod
    def rate_fits(mode: Mode, fps: float):
        """這個模式跑不跑得到這個格率。

        「有效行塞得進一格」只是必要條件,**不夠**。原廠每個模式的 `+0x5C`
        vblank code 是它自己宣告的消隱需求,剩餘餘裕低於它就不能用:

            M139 @ 119.88   445 x 1344 = 598,080 / 600,600 → 只剩 5.7 行
                            而 vblank code 是 100          → 不要做
            M139 @ 100      剩 273.9 行 ≥ 100               → 可以
            M140 @ 239.76   445 x 672 = 299,040 / 300,300 → 只剩 2.8 行
                            vblank code 70                 → 不要做
            M12  @ 239.76   330 x 672,剩 238 行 ≥ 50       → 這才是 HSW 的 donor

        頭兩列是 SENSOR_MODE_METADATA.md §2 自己做過的判斷,這條規則把它
        變成程式碼 —— 前兩個是回歸測試,後兩個是它推出來的新結論。
        """
        return Registry.blanking_lines(mode, fps) >= mode.vblank

    @staticmethod
    def rate_possible(mode: Mode, fps: float):
        """只問物理:有效行讀得完嗎。消隱歸零的理論上限,用來算天花板。"""
        return mode.hmax * mode.raw[1] < CLOCK / fps

    @staticmethod
    def solve_timing(mode: Mode, fps: float, min_tail=330):
        """給定 hmax(= 換 hmax 就換線時,也就換了類比指紋)解 (vmax, tail)。

        frame_cycles = hmax x (vmax - 1) + tail,時脈 72 MHz。
        廣播格率全部是有理數,所以 cycles 是整數,誤差可以是 0 ppm。
        tail 取 `cycles mod hmax` 再往上補到 min_tail 以上 —— 原廠 16 種 tail
        最小 330、最大 2151,所以這個取法落在有先例的範圍裡。
        """
        cycles = round(CLOCK / fps)
        if mode.hmax * mode.raw[1] >= cycles:
            return None
        tail = cycles % mode.hmax
        while tail < min_tail:
            tail += mode.hmax
        vmax = (cycles - tail) // mode.hmax + 1
        if vmax < 2 or vmax > 0xFFFF or tail > 0xFFFF:
            return None
        assert mode.hmax * (vmax - 1) + tail == cycles
        return vmax, tail

    # -- 裁切軸 ------------------------------------------------------------
    @staticmethod
    def record_raster(width, height, depth):
        """感測器幾何 → **記錄矩陣**(畫布 +0x00/+0x04)。

        記錄矩陣的寬度自己就要對齊 —— OG3K 的感測器光柵是 3032x2012,
        寫進畫布的卻是 **3024x2010**(3024 = 16 x 189;3032 不是 16 的倍數)。
        OG2K 的 2016x1344 本來就對齊,所以原樣使用。這一步不是選項,是前提。
        """
        step = max(ALIGN_SAFE, ALIGN[depth])
        return (width // step) * step, (height // ALIGN_H) * ALIGN_H

    @staticmethod
    def crops(width, height, depth, aspects=None):
        """最終裁切尺寸選單:切成硬體對得齊的樣子。

        `width`/`height` 是 RWZM 之後的感測器幾何;第一步先縮成記錄矩陣,
        所有裁切都在記錄矩陣之內。

        寬度對齊到 `ALIGN_SAFE`(16)—— 它同時滿足 8/10/12/14-bit 四個粒度,
        所以換位元深度不必重算幾何。高度取偶數(CFA 2x2 的相位)。
        原點置中並取偶數,理由同上。
        """
        step = max(ALIGN_SAFE, ALIGN[depth])
        rw, rh = Registry.record_raster(width, height, depth)
        rows = []
        seen = set()

        def add(label, w, h):
            w = (w // step) * step
            h = (h // ALIGN_H) * ALIGN_H
            if w <= 0 or h <= 0 or w > rw or h > rh:
                return
            if (w, h) in seen:
                return
            seen.add((w, h))
            # 原點**不強制取偶**:OG3K 出貨的 3008x2000 就在 (8, 5),奇數 Y
            # 照樣正確 —— DNG 的 CFA pattern 掛在整張光柵上,讀取端會自己
            # 依 DefaultCropOrigin 調相位。硬改成偶數等於偏離已驗證的組態。
            rows.append(dict(label=label, size=(w, h),
                             origin=((rw - w) // 2, (rh - h) // 2),
                             raster=(rw, rh), ratio=w / h,
                             row_bytes=w * depth // 8))

        # ① 原廠慣例:記錄矩陣留邊 16 寬 / 10 高。OG3K 的 3024x2010 → 3008x2000
        #    就是這樣來的,OG2K 的 2016x1344 → 2000x1334 也是。
        add("MAX(原廠留邊)", rw - MARGIN_W, rh - MARGIN_H)
        # ② 整個記錄矩陣不留邊。p365(4096x2160)有先例,但那樣 producer 沒有
        #    padding 可以吸收對齊誤差,風險較高。
        add("FULL(不留邊)", rw, rh)
        # ③ 常見成品比例。長邊先吃滿,再依比例算另一邊。
        for label, num, den in (aspects or (
                ("3:2", 3, 2), ("16:9", 16, 9), ("17:9 DCI", 17, 9),
                ("1.85:1", 37, 20), ("2.00:1", 2, 1), ("2.39:1", 239, 100),
                ("4:3", 4, 3), ("1:1", 1, 1), ("9:16 直式", 9, 16))):
            w = min(rw - MARGIN_W, (rh - MARGIN_H) * num // den)
            add(label, w, w * den // num)
        rows.sort(key=lambda r: (r["label"][:3] not in ("MAX", "FUL"),
                                 -r["size"][0] * r["size"][1]))
        return rows


# ---- 資料率與「錄得到多久」 -------------------------------------------------
def frame_bytes(crop, depth):
    """一格寫出去多少 byte。記錄矩陣的每一列都是封裝後的,見 ALIGN。"""
    return crop[0] * crop[1] * depth // 8


def burst(crop, depth, fps, media_mbps, inflight=POOL_INFLIGHT, *, buffer_bytes=None):
    """以記錄矩陣估吞吐;有實測可用緩衝容量時才給容量模型的格數。

    94 是描述子上限,不是錄影格數的實測下界(A001_150 只有 37 格)。
    buffer_bytes 必須由呼叫端提供;448 MiB 仍是推論,不能暗中當預設。
    frames/seconds 是理想化容量模型範圍,不是保證;未提供容量則為 None。
    RAW14 先按已知的 16 bpp 緩衝估算,CDNG 實際封裝仍待量測。
    """
    if (min(crop) <= 0 or depth not in (8, 10, 12, 14, 16) or fps <= 0
            or media_mbps < 0 or inflight <= 0 or
            (buffer_bytes is not None and buffer_bytes < 0)):
        raise ValueError("invalid geometry, rate or buffer capacity")
    per = frame_bytes(crop, 16 if depth == 14 else depth)
    need = per * fps / 1e6                       # MB/s
    write_fps = media_mbps * 1e6 / per
    if write_fps >= fps:
        return dict(need_mbps=need, write_fps=write_fps, sustained=True,
                    frames=None, seconds=None,
                    why="平均媒體速率足夠;未涵蓋實際寫入延遲與其他管線限制")
    capacity = None if buffer_bytes is None else min(inflight, buffer_bytes // per)
    hi = None if capacity is None else capacity * fps / (fps - write_fps)
    return dict(need_mbps=need, write_fps=write_fps, sustained=False,
                frames=None if capacity is None else (capacity, int(hi)),
                seconds=None if capacity is None else (capacity / fps, hi / fps),
                buffer_bytes=buffer_bytes, frame_bytes=per,
                why=f"寫入約 {write_fps:.1f} fps 跟不上 {fps:.2f} fps → "
                    "緩衝用完時應乾淨停止(不是凍結);" +
                    ("可用 RAW 緩衝容量未知,不提供格數保證" if capacity is None
                     else "格數是輸入容量的模型估計,不是實測保證"))


def canvas_required(donor: Mode, rec_raster, fps):
    """這組配方必須寫進畫布的欄位。**漏一欄就是凍結,不是畫面壞掉。**"""
    need = {off: "錄影矩陣 / 可見 / producer" for off in CANVAS_BASE}
    # 感測器視窗一律要寫。條件掛在**借來的 profile** 的原廠視窗上,不是 donor
    # 的光柵:HSW 的案例是 p13 宣告 2016x1344 而 mode 12 只讀 672 行,不補的話
    # 22 格請求永遠不會完成、錄影結束不了。我們永遠借 p13 又用任意幾何。
    for off in CANVAS_WINDOW:
        need[off] = (f"感測器視窗:借來的 profile 宣告的視窗與我們要錄的 "
                     f"{rec_raster[0]}x{rec_raster[1]} 不同 —— 不補的話請求"
                     f"永遠不會完成,錄影結束不了")
    if fps > HIRATE_ABOVE:
        for off in CANVAS_HIRATE:
            need[off] = f">{HIRATE_ABOVE:.0f} fps 必需(119.88 實機證明)"
    return need


# ---- 七軸的解 --------------------------------------------------------------
@dataclasses.dataclass
class Recipe:
    bit: int
    rate: str
    raster: tuple
    hbin: int
    vbin: int
    rwzm: tuple          # (H, V),1024 = unity
    crop: tuple | None   # (w, h),None = 交給 crops() 的第一列
    mode: int | None     # 感測器模式 id,None = 自動挑
    # 進 CRCT 之前的**有效窗口**。bin 不動時就等於光柵;bin 動了而光柵除不盡
    # 就是柴切過的值(見 resolve 裡的 CRCT 柴切)。
    window: tuple | None = None
    notes: list = dataclasses.field(default_factory=list)
    errors: list = dataclasses.field(default_factory=list)
    canvas: dict = dataclasses.field(default_factory=dict)   # 必寫的畫布欄位
    burst: dict | None = None                                # 錄得到多久

    @property
    def ok(self):
        return not self.errors


# 實測參考值:SD(UHS-II)約 94..107 MB/s,外接 SSD 約 317 MB/s 以上。
MEDIA_SD, MEDIA_SSD = 100.0, 317.0


def resolve(reg: Registry, *, bit, rate, raster, hbin=1, vbin=1,
            rwzm=(RWZM_UNITY, RWZM_UNITY), crop=None, want=None, mode=None,
            media_mbps=MEDIA_SD) -> Recipe:
    """把七個選項解成一張可以交給寫入計畫的配方,並把做不到的地方講清楚。

    兩種方向,`want` 決定走哪一條:

        want=None  **正向**:光柵 + bin + RWZM -> 記錄矩陣 -> 裁切
                   使用者直接轉旋鈕,輸出是結果。
        want=(w,h) **逆向**:光柵(視野)+ 想要的輸出 -> 解出 bin / RWZM
                   §12.23 說的那條。原廠 profile 就是這樣解出來的 ——
                   UHD30 與 UHD30CROP 的輸出一個字都不差,差的是窗口與旋鈕。

    逆向時 `rwzm` 會被解出來的值蓋掉;`hbin`/`vbin` 若不是 1 則**釘住**
    (使用者指定了就尊重),是 1 就讓求解器挑(它偏好不動)。
    """
    r = Recipe(bit=bit, rate=rate, raster=tuple(raster), hbin=hbin, vbin=vbin,
               rwzm=tuple(rwzm), crop=crop, mode=mode)

    # --- 位元深度 -------------------------------------------------------
    if bit not in (8, 10, 12, 14):
        r.errors.append(f"位元深度 {bit} 不在 8/10/12/14")
    elif bit == 14:
        r.notes.append(
            "14-bit 共用 TAB3,RAW14 donor 與原廠 16 bpp 平面碼已接上;"
            "增益政策、CDNG 是否 packed 14-bit 與回放仍待實機驗證。")

    # --- 格率 -----------------------------------------------------------
    if rate not in RATES:
        r.errors.append(f"格率 {rate!r} 沒有對應的發射器 enum;"
                        f"可用:{', '.join(RATES)}(480/960 連字串池裡都沒有)")
        fps = None
    else:
        fps = RATES[rate]
        if rate == "240":
            r.notes.append("240:第十列、配對表與容器有理數已接上;選單格率優先於"
                           "主機 AXIS 初值,時間碼與音訊仍待驗證。")
        elif rate == "400":
            r.notes.append("400:有鍵字但尚無選單列;仍須通過模式的消隱預算。")

    # --- CRCT ------------------------------------------------------------
    if hbin not in HBIN_TAPS:
        r.errors.append(f"hbin {hbin} 非法(只有 1/3/5);"
                        f"寫下去是 assert 之後 while(true),相機鎖死")
    if vbin not in VBIN_TAPS:
        r.errors.append(f"vbin {vbin} 非法 —— **vbin 沒有 ÷5**,"
                        f"FUN_c022ee90 只有 0→1 與 1→3;寫下去相機鎖死")
    # ★ 2026-09-29 實機抓到(A001_166):CRCT 的輸出寬度必須自己就對齊,
    #   所以**進 CRCT 之前的窗口要能被 bin 整除**。
    #   6064/3 = 2021.33 -> 引擎取整 2021、rec 對齊成 2016,但 CRCT 實際吐 2021
    #   -> 每列差 5 px -> 逐列累積位移。錄出來是垂直接縫 + 紫紅偏色(CFA 相位壞)。
    #   跟 §3.1b 的「寬度沒對齊會默默弄壞 stride」同一件事,只是沒對齊的是
    #   CRCT 的輸出不是 rec。
    #
    # 使用者指出:**柴切可以解掉**。把窗口往下裁到可整除的尺寸即可 ——
    #   6064x3412 -> 6048x3408 -> ÷3 -> 2016x1136(正好是原本要的 rec,且 16 對齊)
    #   代價只有 16 欄 / 4 列 = 0.26% 視野。
    # 所以這裡**自動柴切**,不報錯 —— 但要把它講出來,因為視野真的變小了。
    if hbin in HBIN_TAPS and vbin in VBIN_TAPS and (hbin != 1 or vbin != 1):
        step_ = max(ALIGN_SAFE, ALIGN[bit])
        gw_, gh_ = hbin * step_, vbin * ALIGN_H      # 窗口要是它們的倍數
        win_w = (r.raster[0] // gw_) * gw_
        win_h = (r.raster[1] // gh_) * gh_
        if win_w <= 0 or win_h <= 0:
            r.errors.append(
                f"光柵 {r.raster[0]}x{r.raster[1]} 太小,柴切不出能被 "
                f"hbin {hbin} / vbin {vbin} 整除的窗口")
        elif (win_w, win_h) != r.raster:
            r.window = (win_w, win_h)
            lost = (1 - win_w * win_h / (r.raster[0] * r.raster[1])) * 100
            r.notes.append(
                f"CRCT 柴切:窗口 {r.raster[0]}x{r.raster[1]} → "
                f"{win_w}x{win_h}(要能被 bin 整除且除完 {step_} 對齊),"
                f"視野少 {lost:.2f}%。不裁的話 CRCT 吐 "
                f"{r.raster[0] // hbin} 而封裝按對齊值設 → stride 不匹配,"
                f"錄出來是垂直接縫 + 偏色(A001_166)。")
            r.notes.append(
                "⚠ **這條柴切還沒上機驗過** —— 哪個欄位承載「進 CRCT 之前的"
                "窗口」還沒確認:原廠 306 列的 +0xF4/+0xF8 一律等於感測器光柵,"
                "但我們的畫布把 rec 寫進去。要先settle 這件事再試。")
        else:
            r.window = r.raster
    if hbin != vbin and hbin in HBIN_TAPS and vbin in VBIN_TAPS:
        r.notes.append(f"hbin {hbin} ≠ vbin {vbin}:像素會變成非方形,"
                       f"後製要按 {hbin}:{vbin} 拉伸。")

    # --- RWZM ------------------------------------------------------------
    for axis, v in zip("HV", rwzm):
        if not RWZM_MIN <= v <= RWZM_MAX:
            r.errors.append(f"RWZM {axis}={v} 超出 {RWZM_MIN}..{RWZM_MAX}"
                            f"(1024 = unity,值是除數 x1024,只縮不放)")

    if r.errors:
        return r

    # --- 逆向:想要的輸出是**輸入**,回推 bin / RWZM ----------------------
    # ★ 對齊要**先做**。裁切寬是 step 的倍數、高是偶數時,
    #   `rec = floor(產出/step)*step >= want` 等價於 `產出 >= want` ——
    #   所以求解器只要保證「產出 >= 對齊後的 want」,截斷就不會把它掉下去。
    if want is not None:
        from imx410_block import HBIN_SET, VBIN_SET, solve_geometry
        step = max(ALIGN_SAFE, ALIGN[bit])
        tgt = ((want[0] // step) * step, (want[1] // ALIGN_H) * ALIGN_H)
        if tgt != tuple(want):
            r.notes.append(f"目標輸出 {want[0]}x{want[1]} 先對齊成 "
                           f"{tgt[0]}x{tgt[1]}(寬 {step} 的倍數、高取偶)")
        if tgt[0] <= 0 or tgt[1] <= 0:
            r.errors.append(f"目標輸出 {want[0]}x{want[1]} 對齊之後是 0")
            return r
        sol = solve_geometry(r.raster, tgt,
                             (hbin,) if hbin != 1 else HBIN_SET,
                             (vbin,) if vbin != 1 else VBIN_SET)
        if sol is None:
            r.errors.append(
                f"光柵 {r.raster[0]}x{r.raster[1]} 解不出 {tgt[0]}x{tgt[1]} —— "
                f"目標比這個窗口能給的還大。換一個更大的原始解析度,"
                f"或把輸出調小。")
            return r
        hbin, vbin, zh, zv, got = sol
        rwzm = (zh, zv)
        # r.crop 也要設 —— 下面的「已指定裁切」那條路只做驗證、不回填。
        r.hbin, r.vbin, r.rwzm, r.crop, crop = \
            hbin, vbin, rwzm, tgt, tgt
        r.notes.append(
            f"逆向:視野 {r.raster[0]}x{r.raster[1]} + 目標 {tgt[0]}x{tgt[1]} "
            f"→ bin ÷{hbin}/÷{vbin}、RWZM {zh}/{zv},產出 {got[0]}x{got[1]},"
            f"多的裁掉。")
        if zh != zv:
            r.notes.append(
                f"⚠ RWZM 長寬不同({zh}/{zv}):欄位與韌體都支援,但原廠 306 列"
                f"沒有一列這樣用,**沒上機看過**。要非等向的比例,"
                f"hbin/vbin 才是有先例的那條路。")

    # --- 幾何 ------------------------------------------------------------
    # ★ 從**有效窗口**算起,不是光柵 —— bin 開著而光柵除不盡時兩者不同。
    rw, rh = r.window or r.raster
    binned = (rw // hbin, rh // vbin)
    after = (binned[0] * RWZM_UNITY // rwzm[0], binned[1] * RWZM_UNITY // rwzm[1])
    rec = Registry.record_raster(after[0], after[1], bit)
    r.notes.append(f"幾何:光柵 {rw}x{rh} → bin ÷{hbin}/÷{vbin} = "
                   f"{binned[0]}x{binned[1]} → RWZM {rwzm[0]}/{rwzm[1]} = "
                   f"{after[0]}x{after[1]} → 記錄矩陣 {rec[0]}x{rec[1]}")

    options = Registry.crops(after[0], after[1], bit)
    if crop is None:
        if not options:
            r.errors.append(f"{after[0]}x{after[1]} 切不出任何對得齊的尺寸")
            return r
        # ★ 取 **MAX(原廠留邊)**,不是「第一列」。
        #   crops() 的排序是**選單**的排序(MAX/FULL 置頂,再依面積),
        #   FULL 面積較大所以排在前面 —— 拿它當預設有兩個問題:
        #     · 相機那側的預設不是它。`expected_recipe` 在 A_CROP == 0 時走的是
        #       原廠留邊慣例(rec - 16 / rec - 10)= MAX,上機驗過的
        #       DefaultCropSize [3008, 2002] 就是這個。主機與相機的預設不一致,
        #       等於同一組選項在兩邊解出不同的東西。
        #     · FULL 自己的註解就寫了「producer 沒有 padding 可以吸收對齊誤差,
        #       風險較高」。
        #   §12.21:預設配方要逐欄等於已驗證的組態。
        pick = next((o for o in options if o["label"].startswith("MAX")),
                    options[0])
        r.crop = pick["size"]
        r.notes.append(f"最終裁切未指定,取 {pick['label']} "
                       f"{r.crop[0]}x{r.crop[1]}(與相機側 A_CROP=0 的預設相同)")
    else:
        step = max(ALIGN_SAFE, ALIGN[bit])
        if crop[0] % step:
            r.errors.append(f"裁切寬 {crop[0]} 不是 {step} 的倍數 —— "
                            f"{bit}-bit 每列 bytes 要是 4 的倍數,"
                            f"沒對齊 DMA 每列會少搬,列與列累積位移")
        if crop[1] % ALIGN_H:
            r.errors.append(f"裁切高 {crop[1]} 是奇數,CFA 2x2 相位會翻")
        if crop[0] > rec[0] or crop[1] > rec[1]:
            r.errors.append(f"裁切 {crop[0]}x{crop[1]} 超出記錄矩陣 {rec[0]}x{rec[1]}")

    # --- mode ------------------------------------------------------------
    cands = reg.candidates(raster=r.raster, depth=bit if bit == 14 else 12,
                           fps=fps)
    if mode is not None:
        m = reg.by_id.get(mode)
        if m is None:
            r.errors.append(f"mode {mode} 不存在")
        elif m not in cands:
            r.errors.append(f"mode {mode}({m.name})不符合這組選項")
        else:
            cands = [m]
    if not cands:
        # 使用者的決定:沒有 mode 對應就不擋,交給 fallback 錄 FHD。
        r.notes.append("★ 這組選項沒有任何感測器模式對應 —— 選單仍可停在這裡,"
                       "但錄影會落到 FHD fallback(fmttable 查不到鍵時回傳"
                       "原廠 FHD 的表項,而不是原廠那個會把畫面拉長的 UHD30)。")
        return r

    # 排序的四個理由,依序。**順序本身有證據**:
    #  ① quiet 指紋優先。實測 M98 比 M117 雜訊明顯低,而兩者光柵相同;
    #     OG2K 選 M139 的**全部理由**就是它是 2016x1344 唯一的 quiet
    #     ——「換 hmax 就換了線時,也就換了指紋」。畫質排在風險前面。
    #  ② 原廠時序就等於目標格率 → 時序交易是 no-op,少一組風險換零代價。
    #     ①不分勝負時它才生效,而這正是 HSW 在兩個 F12 之間選 mode 12 的理由。
    #  ③ 線時長的優先,④ mode id,讓結果可重現。
    #
    # 這四條合起來重現了兩個出貨選擇:OG2K -> M139(①),HSW -> M12(②)。
    def _rank(m):
        native = abs(m.fps - fps) / fps < 1e-6
        return (m.fingerprint != "Q12", not native, -m.hmax, m.mid)
    cands.sort(key=_rank)
    best = cands[0]
    r.mode = best.mid
    t = Registry.solve_timing(best, fps)
    if t is None:
        r.errors.append(f"mode {best.mid} 解不出 {rate} 的時序")
    else:
        vmax, tail = t
        got = CLOCK / (best.hmax * (vmax - 1) + tail)
        ppm = abs(got - fps) / fps * 1e6
        r.notes.append(f"時序:hmax {best.hmax} tail {tail} vmax {vmax} → "
                       f"{got:.5f} fps({ppm:.3f} ppm),捲簾 "
                       f"{best.rolling_us:.2f} us,指紋 {best.fingerprint}")
    r.notes.append(f"候選 mode:" + ", ".join(
        f"{m.mid}({m.name},{m.fingerprint})" for m in cands))

    # 畫布欄位。這是凍結的**唯一**已知預測器 —— 資料率不是。
    r.canvas = canvas_required(best, rec, fps)
    if any(off in CANVAS_HIRATE for off in r.canvas):
        r.notes.append(f"畫布:>{HIRATE_ABOVE:.0f} fps,那七欄"
                       f"(+0x90/B0/C0/DC/E4/FC/100)必寫,漏了會凍結")
    if any(off in CANVAS_WINDOW for off in r.canvas):
        # 條件掛在**借來的 profile** 宣告的視窗上,不是 donor mode 的光柵
        # (canvas_required 的註解)。原本這裡印的是「donor 光柵 ≠ 記錄矩陣」,
        # 那不是判斷式 —— 兩者相等時會印出一個假的 ≠。
        r.notes.append(f"畫布:借來的 profile 宣告的視窗與要錄的 "
                       f"{rec[0]}x{rec[1]} 不一定相同 → 感測器視窗 "
                       f"+0x0F4/+0x0F8 必寫(不補的話請求不會完成)")

    # 資料率:不是門檻,是「會錄到多久」。
    r.burst = burst(rec, bit, fps, media_mbps)
    b = r.burst
    if b["sustained"]:
        r.notes.append(f"吞吐:需要 {b['need_mbps']:.0f} MB/s,媒體 "
                       f"{media_mbps:.0f} MB/s → 平均速率足夠,持續錄影仍待實測")
    elif b["frames"] is None:
        r.notes.append(f"吞吐:需要 {b['need_mbps']:.0f} MB/s,媒體 "
                       f"{media_mbps:.0f} MB/s;可用 RAW 緩衝容量未量測,"
                       "不能把 94 個描述子當作至少可錄 94 格。")
    else:
        lo, hi = b["frames"]
        slo, shi = b["seconds"]
        r.notes.append(f"吞吐:需要 {b['need_mbps']:.0f} MB/s,媒體 "
                       f"{media_mbps:.0f} MB/s → 錄 {lo}~{hi} 格"
                       f"({slo:.2f}~{shi:.2f} 秒)之後 `vbuf` 乾淨停止。"
                       f"這是正常行為,不是凍結。")
    return r


# ---- 動態配方:靜態表整個消失 ----------------------------------------------
# 使用者 2026-09-27:「我們的 p 還有各種韌體中原有使用的表 都可能要移除掉,
# 改用動態生成的 不然表會爆炸。」
#
# 會爆的不是列數。picker 的鍵是 `<名稱><格率>`,**另外六個軸不出現在鍵裡**,
# 所以表最多十幾列。會爆的是「每一列的內容取決於另外六個活變數」—— 靜態表
# 表達不了,靜態化就只能窮舉組合。
#
# 所以一列都不預先產生。ROM 裡的表(metadata 0xC0B59DC0、時序 0xC0B59500、
# profile 欄)原地不動、執行期讀,我們只產生「當下這一組」:
#
#     AXIS 區塊(7 字,選單 setter 寫)
#        ↓ og3krecipe.S,掛在每個 setter 的出口
#     RECIPE 區塊(donor、時序、幾何、畫布 (位移,值) 陣列、鍵字串)
#        ↓
#     fmttable    生出單一表項 —— 靜態 TABLE 消失
#     og3kcanvas  改走 (位移,值) 陣列的迴圈 —— 32 個 PUT × 3 字變成約 10 字
#     og3kfps     讀 RECIPE 的 nominal fps
#
# 這個模組負責**主機這側**:把 Recipe 編成那兩個區塊。相機上的 og3krecipe.S
# 要做同一件事,所以這裡的編碼就是它的規格,而且可以離線對著三個已出貨目標驗。

# 畫布欄位的值從哪來。`rec` = 記錄矩陣、`act` = 可見/裁切、`one`/`zero`/`f2`
# 是常數。這張表就是 og3kcanvas.S 那 32 個 PUT 的資料化。
_CANVAS_SRC = (
    # (位移, 來源, 需要哪個開關)   開關 None = 一律寫
    (0x00, "rec_w", None), (0x04, "rec_h", None),
    (0x0C, "rec_w", "preview"), (0x10, "rec_h", "preview"),
    (0x20, "act_w", "preview"), (0x28, "act_h", "preview"),
    (0x24, "act_w", "active"), (0x2C, "act_h", "active"),
    (0x80, "plane_preview", None), (0x84, "plane_raw", "plane_raw"),
    (0x90, "one", "hirate:90"),
    (0xB0, "one", "hirate:B0"),
    (0xC0, "zero", "hirate:C0"),
    (0xD8, "rec_w", "producer"), (0xE0, "rec_h", "producer"),
    (0xDC, "rec_w", "hirate:DC"), (0xE4, "rec_h", "hirate:E4"),
    (0xF4, "rec_w", "window"), (0xF8, "rec_h", "window"),
    (0xFC, "f2", "hirate:FC"), (0x100, "f2", "hirate:100"),
)
# 平面格式碼:eRawBitType -> (+0x080 預覽平面, +0x084 RAW 平面)。
# 值域見 FUN_c04356b0 的 bpp_of:7 -> 12-bit、9 -> 10-bit、10 -> 8-bit。
# 這兩欄就是原廠三胞胎(p131/p151/p171)65 欄裡唯一不同的兩欄。
CANVAS_PLANE = {12: (7, 7), 10: (10, 9), 8: (10, 10),
                # 14-bit:**沒有 14 bpp 的平面碼**,bpp_of 只認 12/10/8/16。
                # 原廠的 14-bit profile(p41/p44/p81/p84,光柵正好等於 RAW14
                # 感測器模式的 6064x4042 / 3968x2640)RAW 平面宣告碼 8 = 16 bpp
                # —— RAW14 走的是 **14-in-16 容器**,不是 packed。
                # 預覽沿用 12-bit 的 7(照片列用 0xA=8bpp 是照片路徑的取捨)。
                # 相機端的對應表是 og3krecipe.S 的 plane_tab,兩邊要一起改。
                # 見 §4.3。
                14: (7, 8)}
# og3k_plan 的 hirate 欄位名(十六進位位移的字串形式)。
CANVAS_HIRATE_NAMES = ("90", "B0", "C0", "DC", "E4", "FC", "100")


def canvas_pairs(*, rec, act, depth, preview=False, active=False,
                 producer=False, window=False, hirate=(), plane_raw=False):
    """畫布要寫的 (位移, 值) 陣列 —— og3kcanvas 的迴圈直接吃這個。

    開關的意思與 og3k_plan 的 `write_*` 完全相同:donor profile 原廠就對的
    欄位不要寫(og3k 借 p83,它的 active/producer/preview 原廠已經是對的)。
    """
    plane = CANVAS_PLANE[depth]
    env = dict(rec_w=rec[0], rec_h=rec[1], act_w=act[0], act_h=act[1],
               plane_preview=plane[0], plane_raw=plane[1],
               one=1, zero=0, f2=0x40000000)
    on = {"preview": preview, "active": active, "producer": producer,
          "window": window, "plane_raw": plane_raw}
    on.update({f"hirate:{f}": f in hirate for f in CANVAS_HIRATE_NAMES})
    out = {}
    for off, src, gate in _CANVAS_SRC:
        if gate is None or on.get(gate):
            out[off] = env[src]
    return dict(sorted(out.items()))


# picker 的鍵前綴。fmttable 的 MATCH 比對是**一個 32-bit 字**(TARGET_LABEL),
# 所以內部標籤只能四個字元 —— 選單上那一列仍然叫 CUSTOM,兩者互不相干
# (CSV 的 TEXT 欄是任意字面值,見 FORMAT_REGISTRY_DESIGN §29)。
RECIPE_LABEL = "CUST"


def recipe_words(reg: Registry, r: Recipe, *, preview=False, active=False,
                 producer=False, hirate=("90", "C0")):
    """RECIPE 區塊。相機上的 og3krecipe.S 要產生逐字相同的東西。"""
    m = reg.by_id[r.mode]
    fps = RATES[r.rate]
    vmax, tail = Registry.solve_timing(m, fps)
    rec = Registry.record_raster(
        *(a // b for a, b in zip(
            (r.raster[0] // r.hbin, r.raster[1] // r.vbin),
            (r.rwzm[0] / RWZM_UNITY, r.rwzm[1] / RWZM_UNITY))), r.bit)
    rec = (int(rec[0]), int(rec[1]))
    window = m.raw != rec
    pairs = canvas_pairs(rec=rec, act=r.crop, depth=r.bit, preview=preview,
                         active=active, producer=producer, window=window,
                         hirate=hirate if fps > HIRATE_ABOVE else
                                tuple(f for f in hirate if f in ("90", "C0")))
    key = (RECIPE_LABEL + r.rate).encode()
    return dict(
        mode=m.mid, mode_idx=m.idx,
        timing_w0=m.hmax | (tail << 16), timing_w1=vmax | (m.x_start << 16),
        rec=rec, act=tuple(r.crop), key=key + b"\x00" * (16 - len(key)),
        canvas=pairs, window=window,
    )


# ---- CLI -------------------------------------------------------------------
def _size(s):
    w, h = s.lower().split("x")
    return int(w), int(h)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("rasters", help="原始解析度選單的內容")

    p = sub.add_parser("modes", help="mode 選單的內容")
    p.add_argument("--raster", type=_size)
    p.add_argument("--bit", type=int)
    p.add_argument("--fps", type=float)
    p.add_argument("--full-only", action="store_true")

    p = sub.add_parser("crops", help="最終裁切尺寸選單的內容")
    p.add_argument("--size", type=_size, required=True)
    p.add_argument("--bit", type=int, default=12)

    p = sub.add_parser("resolve", help="解一組七軸選項")
    p.add_argument("--bit", type=int, default=12)
    p.add_argument("--fps", default="30")
    p.add_argument("--raster", type=_size, required=True)
    p.add_argument("--hbin", type=int, default=1)
    p.add_argument("--vbin", type=int, default=1)
    p.add_argument("--rwzm", type=_size, default=(RWZM_UNITY, RWZM_UNITY))
    p.add_argument("--crop", type=_size)
    p.add_argument("--want", type=_size,
                   help="想要的輸出尺寸。給了就走**逆向**:視野 + 目標 -> "
                        "解出 bin/RWZM(--rwzm 會被蓋掉)")
    p.add_argument("--mode", type=int)
    p.add_argument("--media", type=float, default=MEDIA_SD,
                   help="媒體寫入速度 MB/s(SD 約 100、外接 SSD 約 317)")

    a = ap.parse_args(argv)
    reg = Registry()

    if a.cmd == "rasters":
        print(f"{'光柵':>12}  {'scale':<5} {'涵蓋':>12}  {'柴切方式':<34} 深度  modes")
        for row in reg.rasters():
            rw, rh = row["raw"]
            cw, ch = row["coverage"]
            print(f"{rw:5d}x{rh:<6d} {row['scale'][0]}x{row['scale'][1]:<3} "
                  f"{cw:5d}x{ch:<6d} {Registry.cut_label(row):<36}"
                  f"RAW{row['depth']:<2} {row['modes']}")
        return 0

    if a.cmd == "modes":
        ms = reg.candidates(raster=a.raster, depth=a.bit, fps=a.fps,
                            full_only=a.full_only)
        print(f"{'mode':>5} {'名稱':<26} {'光柵':>12} {'指紋':<5} "
              f"{'hmax':>5} {'原廠fps':>9} {'上限fps':>9} {'捲簾ms':>8}")
        for m in sorted(ms, key=lambda m: (m.fingerprint, -m.hmax, m.mid)):
            print(f"{m.mid:5d} {m.name:<26} {m.raw[0]:5d}x{m.raw[1]:<6d} "
                  f"{m.fingerprint:<5} {m.hmax:5d} {m.fps:9.3f} "
                  f"{m.fps_ceiling:9.1f} {m.rolling_us / 1000:8.2f}")
        if not ms:
            print("  (沒有符合的模式 —— 錄影會落到 FHD fallback)")
        return 0

    if a.cmd == "crops":
        rr = Registry.record_raster(a.size[0], a.size[1], a.bit)
        print(f"感測器幾何 {a.size[0]}x{a.size[1]} → 記錄矩陣 {rr[0]}x{rr[1]}"
              f"(寬對齊 {max(ALIGN_SAFE, ALIGN[a.bit])}、高取偶)")
        print(f"{'標籤':<18} {'尺寸':>12} {'原點':>10} {'比例':>7} {'每列bytes':>10}")
        for c in Registry.crops(a.size[0], a.size[1], a.bit):
            print(f"{c['label']:<20} {c['size'][0]:5d}x{c['size'][1]:<6d} "
                  f"{c['origin'][0]:4d},{c['origin'][1]:<5d} "
                  f"{c['ratio']:7.3f} {c['row_bytes']:10d}")
        return 0

    r = resolve(reg, bit=a.bit, rate=a.fps, raster=a.raster, hbin=a.hbin,
                vbin=a.vbin, rwzm=a.rwzm, crop=a.crop, want=a.want,
                mode=a.mode,
                media_mbps=a.media)
    for n in r.notes:
        print("  ·", n)
    for e in r.errors:
        print("  ✗", e)
    if r.ok:
        c = r.crop
        print(f"\n  => mode {r.mode}  {c[0]}x{c[1]}  {r.bit}-bit  {r.rate} fps")
    return 0 if r.ok else 1


if __name__ == "__main__":
    sys.exit(main())
