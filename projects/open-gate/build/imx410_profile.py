"""我們自己宣告的 PARAM profile —— 一整列 65 個字的公式(2026-10-04)。

原本的做法是「借一列原廠 profile,只覆寫幾欄」(OG3K 借 p83)。借來的那一列
的其餘欄位綁死在它自己的幾何上:p83 是**拍照類**,預覽緩衝給 3032 寬的讀出
設計,6064 寬的讀出塞進去就溢出(r67 / r69 兩次花屏凍結)。

這裡改成**每一欄都由公式宣告**。公式的證據:

  原廠 78 組影片 profile(raw-profiles.json 的 movie_routes):UHD / UHD CROP /
  FHD / FHD CROP x 格率 x 位元深度,全部 16:9。declare() 對每一組的輸入算出的列
  必須與原廠列**逐字相同**(test_imx410_profile.test_reproduces_every_stock_movie_row)。

  外部專案實機錄過的 3:2 6K 讀出(research/other/external/):fpsup-formats OG3.5K
  (p171 底、6062x4040、錄影 RWZM 1792、預覽 2016x1345 / 2000x1334)、FP3K
  (p429 底、預覽高 1344 / 1334)。它們證明了 3:2 的預覽與「只改錄影那組 RWZM」。

欄位分三類:
  FORMULA  由輸入算出(rec、act、視窗、bin、RWZM、預覽、producer、scale、平面格式…)
  VIDEO    影片類 profile 全部相同的常數(78 組一致),意義不一定知道
  ROW      其他 34 欄:306 列中影片類全部相同,直接取底列(底列一律是影片類)

拍照類(p83)的值**不在這裡**:那是 M98 這組沿用 OG3K 已驗證組態時的底列,
見 imx410_plan.PROFILE。
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

RWZM_UNITY_STOCK = 1023         # 原廠寫 unity 的方式(1023 被夾成 1024)

# 預覽可以用的 RWZM:原廠預覽欄出現過的值(IMX410_FULL_DESIGN §12.25 的訂正:
# 錄影 1024/1500/1600、預覽 1024/1280/1536/1600/2048/3072)。
PREVIEW_ZOOMS = (1536, 1600, 2048, 3072)
PREVIEW_SRC_MAX = 2100          # 預覽來源寬的上限(原廠最寬 2088,UHD CROP / FHD CROP)
PREVIEW_VIS_MAX_W = 2000        # 原廠預覽可見寬的上限(UHD 2000)
PREVIEW_32_H = 1334             # 3:2 的預覽可見高(OG3K / formats / FP3K / GTAB 一致)
PREVIEW_KNOWN_H = (1125, PREVIEW_32_H)   # 寬 2000 時驗證過的可見高:16:9 原廠、3:2
PREVIEW_MARGIN = (16, 10)       # 預覽光柵 = 可見 + 邊距(原廠四種幾何全部吻合)
BIN3_WINDOW_W = 6000            # 全寬讀出:預覽用 CRCT ÷3(原廠 UHD、外部三家都是)
HBIN_E = {1: 0, 3: 1, 5: 2}     # FUN_c022ee10 的列舉
PLANE = {8: (10, 10), 10: (10, 9), 12: (7, 7)}   # +0x80 / +0x84,依位元深度


def fbits(x: float) -> int:
    return struct.unpack("<I", struct.pack("<f", x))[0]


@dataclass(frozen=True)
class Want:
    window: tuple           # 感測器讀出(mode 光柵),+0xF4/+0xF8
    rec: tuple              # 記錄矩陣
    act: tuple              # 可見輸出(DNG DefaultCrop)
    zoom: tuple             # 錄影 RWZM(H, V);沒縮放寫 1023
    bits: int = 12
    hirate: bool = False    # > 60 fps
    scale: tuple = (1.0, 1.0)   # mode 自己的縮減倍數(mode metadata +0x4C/+0x50)
    bin: tuple = (1, 1)         # 錄影的 CRCT bin(原廠錄影一律 1;面板可以設 hbin 3/5、vbin 3)


def record_factors(w: Want):
    """錄影每一軸的倍數:視窗像素 -> 錄下的像素,x1024(CRCT bin x RWZM)。"""
    return w.bin[0] * max(w.zoom[0], 1024), w.bin[1] * max(w.zoom[1], 1024)


def record_preview(w: Want):
    """Binning needs the matching record tap, when it fits the preview."""
    rh, rv = record_factors(w)
    return w.bin != (1, 1) and w.window[0] * 1024 // rh <= PREVIEW_SRC_MAX


def preview_factors(w: Want):
    """預覽的倍數(視窗像素 -> 預覽像素,x1024),回傳 (ph, pv)。

    ★ 2026-10-04 實機:兩軸不同的預覽縮放(M12 AUTO 2048 / 1023、預覽 1008 寬)讓
    錄影一開始 LV 底部錯位約 1 秒;原廠 UHD、M7、M12 RAW(都是兩軸相同、約 2016 寬)
    都沒有。r78 等向預覽經使用者確認正常;2026-10-09 v11 把不等軸縮放也導到
    C,重現同一個首秒錯位。無 bin 的錄影恢復 r78 規則;只有 binning 在抽頭
    寬度可容納時沿用完整錄影 bin/RWZM。ROM 選擇器只證明配置,不證明 LCD pitch。
    無 bin 預覽沿用原廠規則:
    全寬讀出 ÷3;錄影倍數夠小就沿用;不夠再挑原廠預覽縮放。
    相同倍數的不同 bin/RWZM 組合不代表相同硬體路徑。"""
    ww = w.window[0]
    rh, rv = record_factors(w)
    # ★ 路徑分支 C(2026-10-05,使用者「開始做 hbin vbin 之前的 C 方案」):錄影有 bin 時,
    #   預覽的 bin 與 RWZM 必須**逐軸等於**錄影的,選擇器 FUN_c0325228 才會開 Hbin2
    #   抽頭、主管線吃錄影的 bin 與 RWZM。所以預覽倍數 = 錄影倍數(每軸各自),
    #   只要預覽來源仍在原廠上限內;否則照舊(落在 E,bin 不作用)。
    if record_preview(w):
        return rh, rv
    f = min(rh, rv)
    if ww >= BIN3_WINDOW_W:
        return 3 * 1024, 3 * 1024
    for cand in (f,) + tuple(c for c in PREVIEW_ZOOMS if c > f):
        if ww * 1024 // cand <= PREVIEW_SRC_MAX:
            return cand, cand
    raise ValueError(f"no stock preview zoom brings {ww} under {PREVIEW_SRC_MAX}")


def preview_path(w: Want):
    """預覽的 (hbin 列舉, vbin 列舉, RWZM H, RWZM V, 來源寬高)。全部整數、x1024
    (相機端 sl_modes.c 照抄,要逐字相同)。"""
    ww, wh = w.window
    ph, pv = preview_factors(w)
    stock = lambda z: RWZM_UNITY_STOCK if z <= 1024 else z
    if record_preview(w):
        # Preserve the actual bin and zoom pair, including no-bin zoom >= 3x.
        return (HBIN_E[w.bin[0]], HBIN_E[w.bin[1]], stock(w.zoom[0]), stock(w.zoom[1]),
                (ww * 1024 // ph, wh * 1024 // pv))

    def axis(p):
        if p >= 3 * 1024:
            return HBIN_E[3], max(1024, p // 3)
        return HBIN_E[1], p
    bh, zh = axis(ph)
    bv, zv = axis(pv)
    return bh, bv, stock(zh), stock(zv), (ww * 1024 // ph, wh * 1024 // pv)


def ceil16(x):
    return (x + 15) // 16 * 16


def preview_visible(w: Want, src):
    """預覽可見區 = **錄影的可見範圍(act)換算成預覽像素**,兩軸各自換算:
    act x 錄影倍數 / 預覽倍數。顯示框的比例是錄下像素的比例(R_ASPECT),所以
    M12 AUTO(錄影 2048 / 1024、act 992x662)的可見 1984x662 會顯示成 3:2。
    來源邊緣仍須保留預覽邊距。

    原廠直接就是這條:UHD 3840x2160 x 1600/3072 = 2000x1125;FHD 1920x1080 x 1;
    UHD CROP 3840x2160 x 1024/2048 = 1920x1080 -> 高被來源限制在 1077。
    超出來源(扣邊距)或寬超過 2000 就照比例縮;寬取 16 的倍數(進位);寬 2000 時
    高貼齊原廠 / OG3K 的 1125 / 1334(不超出來源)。"""
    fh, fv = record_factors(w)
    ph, pv = preview_factors(w)
    aw, ah = w.act[0] * fh // ph, w.act[1] * fv // pv          # act in preview pixels
    if aw <= 0 or ah <= 0:
        raise ValueError('empty preview visible region')
    sw, sh = src[0] - PREVIEW_MARGIN[0], src[1] - PREVIEW_MARGIN[1]
    if sw <= 0 or sh <= 0:
        raise ValueError('preview source cannot hold the margins')
    vw, vh = aw, ah
    cap = min(sw, PREVIEW_VIS_MAX_W)
    # The existing two-step rounding is calibrated for isotropic preview.
    # On unequal-axis binned taps it must instead fit in preview coordinates:
    # the former act * record V/H ratio silently assumed ph == pv.
    if vw > cap:
        vw, vh = cap, (cap * ah // aw if ph != pv else (cap * w.act[1] // w.act[0]) * fv // fh)
    if vh > sh:
        vh = sh
        vw = vh * aw // ah if ph != pv else (vh * w.act[0] // w.act[1]) * fh // fv
    vw = ceil16(vw)
    if vw > sw // 16 * 16:
        vw = sw // 16 * 16
        vh = vw * ah // aw if ph != pv else (vw * w.act[1] // w.act[0]) * fv // fh
        vh = min(vh, sh)
    if vw <= 0 or vh <= 0:
        raise ValueError('preview source cannot hold the visible region')
    # ★ 貼齊不可以超出來源(2026-10-04 r71 實機:M98 1344 > 1341,LV 花屏、錄一格就停)
    if vw == PREVIEW_VIS_MAX_W:
        for known in PREVIEW_KNOWN_H:
            if abs(vh - known) <= 4 and known <= sh:
                vh = known
    return vw, vh


STANDBY_WINDOW = (2016, 1344)   # 六個待機預覽 profile 的視窗:固定的 3x3 全片幅讀出
STANDBY_VIS_MAX = (2000, 1334)  # 它們的光柵 2016x1344 扣掉邊距


def standby_visible(w: Want):
    """待機 LV 的可見寬高 = 錄影中 LV 顯示的那塊感測器區域,換算到待機視窗
    (2026-10-04:錄影預覽比待機多裁 ~0.8%,按下錄影畫面放大 ~10 px)。

    一個預覽像素涵蓋 (p·sx, p·sy)/1024 個感測器像素,待機視窗的一個像素涵蓋 3 個。
    扁像素也成立:M12 RAW 預覽 2000x662 -> 待機 2000x1324,兩者在同一個 21:9 顯示框裡
    一樣扁。"""
    ph, pv = preview_factors(w)
    *_, src = preview_path(w)
    vw, vh = preview_visible(w, src)
    sx, sy = int(w.scale[0]) or 1, int(w.scale[1]) or 1
    return (min(STANDBY_VIS_MAX[0], vw * ph * sx // (3 * 1024)),
            min(STANDBY_VIS_MAX[1], vh * pv * sy // (3 * 1024)))


def declare(w: Want, base_row: list) -> list:
    """宣告一整列(65 個字)。base_row 只提供 ROW 類欄位(影片類全部相同的 34 欄)。"""
    row = list(base_row)
    put = lambda off, v: row.__setitem__(off // 4, v)
    binh, binv, zph, zpv, src = preview_path(w)
    vis = preview_visible(w, src)
    prev = (vis[0] + PREVIEW_MARGIN[0], vis[1] + PREVIEW_MARGIN[1])

    put(0x00, w.rec[0]); put(0x04, w.rec[1])
    put(0xDC, w.rec[0]); put(0xE4, w.rec[1])
    put(0x24, w.act[0]); put(0x2C, w.act[1])
    put(0xF4, w.window[0]); put(0xF8, w.window[1])
    put(0x0C, prev[0]); put(0x10, prev[1])
    put(0xD8, prev[0]); put(0xE0, prev[1])
    put(0x20, vis[0]); put(0x28, vis[1])
    put(0x58, binh); put(0xC4, binv)              # 預覽 bin
    put(0x60, zph); put(0xD0, zpv)                # 預覽 RWZM(兩軸各自,跟著錄影的形狀)
    put(0x64, w.zoom[0]); put(0xD4, w.zoom[1])    # 錄影 RWZM
    put(0x5C, HBIN_E[w.bin[0]]); put(0xC8, HBIN_E[w.bin[1]])   # 錄影 bin(列舉)
    put(0xFC, fbits(w.scale[0])); put(0x100, fbits(w.scale[1]))
    put(0x80, PLANE[w.bits][0]); put(0x84, PLANE[w.bits][1])
    put(0xB0, 1 if w.hirate else 0)
    put(0x38, 16 if binh == HBIN_E[3] else 1)     # 影片類:只有 ÷3 預覽(UHD)是 16
    put(0x1C, 1)                                  # 影片類一律 1(拍照類 p83 / 空殼 p13 是 2)
    put(0x88, 0)                                  # 影片類一律 0(p83 是 4)
    put(0x90, 1); put(0xC0, 0)                    # 影片類一律(p83 / p13 相反)
    return row


# 影片類 profile 中,公式不管、但 78 組全部相同的欄位(由測試確認)。
FORMULA_OFFSETS = (0x00, 0x04, 0x0C, 0x10, 0x1C, 0x20, 0x24, 0x28, 0x2C, 0x38, 0x58, 0x5C,
                   0x60, 0x64, 0x80, 0x84, 0x88, 0x90, 0xB0, 0xC0, 0xC4, 0xC8, 0xD0, 0xD4,
                   0xD8, 0xDC, 0xE0, 0xE4, 0xF4, 0xF8, 0xFC, 0x100)
# 相機端 sl_modes.c 寫進宣告列的欄位:公式欄位扣掉平面格式與 >60 旗標(0x80 / 0x84 /
# 0xB0 依選單的位元深度與格率,由畫布模板每次組態時寫)。
DECLARED_BY_PANEL = tuple(o for o in FORMULA_OFFSETS if o not in (0x80, 0x84, 0xB0))
ENGINE_FPS = 0x30               # imx410_canvas 從 FPSLATCH 寫,不屬於幾何
