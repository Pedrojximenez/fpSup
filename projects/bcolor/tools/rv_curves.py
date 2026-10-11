#!/usr/bin/env python3
"""rv_curves.py — 照 BMCC 做法產生 rawview 的每 ISO 曲線表(純離線)。

BMCC 6K 的做法(bmcc6k,已獨立重算驗證):
  一條固定的 Gen 5 Film 編碼;每條 ISO 曲線只換輸入比例(每 1/3 EV ×2^(1/3)),
  白點隨之移動;監看用一個固定的 Film→Video 轉換,所有 ISO 共用。

rawview 照搬這個分工:
  編碼 E   : 12-bit 感光元件碼 → 8-bit LV 碼。形狀固定(Gen 5 Film 縮放到 8-bit),
             每個 ISO 只換輸入比例:感光元件滿位 = 中灰以上 W(ISO) 檔。
  顯示 D   : 8-bit LV 碼 → 8-bit 顯示碼。所有 ISO 共用;中性軸參考 BMCC Film→Video。

W(ISO) 取自 SIGMA 官方表(CinemaDNG 12-bit / HDMI RAW,reference/fp_dual_base_iso_2020.pdf);
1/3 檔 ISO 是內插,標 interp。MOV 與 8/10-bit(Base 100/640)官方沒給表,不產生。

輸出(--out 目錄):
  curves.json          每 ISO 參數與摘要
  enc_iso<N>.u8        4096 bytes,12-bit 輸入 → 8-bit
  display.u8           256 bytes,LV 碼 → 顯示碼
  curves.csv           逐檔摘要,方便畫圖
硬體封裝(表長、節點、暫存器)要等 12→8-bit 的實際設定位置確定後再轉。
"""
import argparse, csv, json, math, pathlib
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
BMCC_NEUTRAL = (HERE.parents[2] / 'bmcc6k/analysis-20260924/'
                'bmcc6k-liveview-rec709-20260924/luts/neutral_axis.csv')

# 官方表(12-bit CDNG / HDMI RAW):中灰以上檔數。
# 2026-09-25 使用者指定權威:SIGMA fp Rec709 LUT & Operations Guide v3(Ole Berek,依若松白皮書)p.2 動態範圍圖,
# 第一迴路 ISO 100–800、第二迴路 ISO 3200–5000 逐 1/3 檔;其餘沿用 SIGMA 官方表(1600、6400 以上)。
W_OFFICIAL = {100: 3.09, 125: 3.42, 160: 3.75, 200: 4.09, 250: 4.42, 320: 4.76, 400: 5.09, 500: 5.42,
              640: 5.76, 800: 6.09, 1600: 6.09, 3200: 5.42, 4000: 5.75, 5000: 6.09,
              6400: 6.09, 12800: 6.09, 25600: 6.09, 51200: 6.09, 102400: 6.09}
ISO_STEPS = [100, 125, 160, 200, 250, 320, 400, 500, 640, 800, 1000, 1250, 1600, 2000,
             2500, 3200, 4000, 5000, 6400, 8000, 10000, 12800, 16000, 20000, 25600,
             32000, 40000, 51200, 64000, 80000, 102400]


# 官方表:中灰以下檔數(暗部底線)
L_OFFICIAL = {100: 9.41, 125: 9.08, 160: 8.75, 200: 8.41, 250: 8.08, 320: 7.74, 400: 7.41, 500: 7.08,
              640: 6.74, 800: 6.41, 1600: 6.07, 3200: 7.04, 4000: 6.71, 5000: 6.37,
              6400: 6.21, 12800: 5.63, 25600: 4.89, 51200: 4.04, 102400: 3.15}


def l_of(iso):
    """中灰以下檔數。官方整檔直接用;其他在同一增益區段內對數內插。"""
    if iso in L_OFFICIAL:
        return L_OFFICIAL[iso], 'official'
    if iso < 800:                       # 只改標籤:每檔 −1
        return 9.41 - math.log2(iso / 100), 'interp'
    if 1600 < iso < 3200:               # 3200 換 HCG,不跨過去內插;沿 800→1600 的斜率外推
        return 6.07 + (6.07 - 6.41) * math.log2(iso / 1600), 'interp'
    pts = sorted(L_OFFICIAL)
    lo = max(p for p in pts if p < iso); hi = min(p for p in pts if p > iso)
    t = math.log2(iso / lo) / math.log2(hi / lo)
    return L_OFFICIAL[lo] + t * (L_OFFICIAL[hi] - L_OFFICIAL[lo]), 'interp'


def w_of(iso):
    """中灰以上檔數。官方整檔直接用;其他依機制內插。"""
    if iso in W_OFFICIAL:
        return W_OFFICIAL[iso], 'official'
    if iso < 800:                       # 100–800:只改亮度標籤,每檔 +1
        return 3.09 + math.log2(iso / 100), 'interp'
    if iso < 3200:                      # 800–3200 前:LCG 加類比增益,白點與中灰同步降
        return 6.09, 'interp'
    return 6.09, 'interp'               # 5000 以上(文件 5000、官方 6400 以上)全是 6.09


G709 = 1.099 * 0.18 ** 0.45 - 0.099     # BT.709 OETF(18% 灰) ≈ 0.409
MODES = ('stops', 'lut709', 'smooth', 'twolog')   # 顯示對應;卡片帶 stops(SA)與 lut709(GA)

# GA = 文件的「LA - SIGMA Rec709 ISO N」LUT(v2/v3,p.4),數位化於 reference/lut709/lut709_digitized.json。
# 曲線只取決於飽和點 W(ISO 800 與 5000 同 W 幾乎重合、3200 落在 400 與 800 之間)→ 依 W 在各圖之間線性內插。
LUT709_JSON = HERE.parent / 'reference' / 'lut709' / 'lut709_digitized.json'
_LUT709 = None


def _lut709_curves():
    global _LUT709
    if _LUT709 is None:
        d = json.loads(LUT709_JSON.read_text())['curves']
        f = {k: (np.array(v['s']), np.array(v['ire']) / 100) for k, v in d.items()}
        s8, y8 = f['800']; s5, y5 = f['5000']
        grid = np.arange(-9, 9.001, 0.05)
        avg = (np.interp(grid, s8, y8, left=np.nan) + np.interp(grid, s5, y5, left=np.nan)) / 2
        m = ~np.isnan(avg)
        _LUT709 = sorted([(3.09, f['100']), (4.09, f['200']), (5.09, f['400']), (5.42, f['3200']),
                          (6.09, (grid[m], avg[m]))], key=lambda t: t[0])
    return _LUT709


def _curve_eval(c, s):
    cs, cy = c
    y = np.interp(s, cs, cy, right=cy[-1])
    k = (cy[5] - cy[0]) / (cs[5] - cs[0])              # 圖左端(約 −8.5 檔)以外:沿端點斜率外推到 0
    return np.where(s < cs[0], np.maximum(cy[0] + k * (s - cs[0]), 0), y)


def lut709(s, W):
    """文件 709 LUT:相對中灰檔數 s → 顯示(%IRE / 100),依 W 在數位化曲線間內插。
    中灰以下直接內插數值;中灰以上以「到飽和點的比例」u = s / W 對齊後內插(高光長度不同,直接混會到不了頂)。"""
    s = np.asarray(s, float)
    cs = _lut709_curves()
    Ws = [w for w, _ in cs]
    W = min(max(W, Ws[0]), Ws[-1])
    for (w0, c0), (w1, c1) in zip(cs, cs[1:]):
        if w0 <= W <= w1:
            break
    t = 0 if w1 == w0 else (W - w0) / (w1 - w0)
    lo = (1 - t) * _curve_eval(c0, s) + t * _curve_eval(c1, s)
    u = np.maximum(s, 0) / W
    hi = (1 - t) * _curve_eval(c0, u * w0) + t * _curve_eval(c1, u * w1)
    return np.clip(np.where(s < 0, lo, hi), 0, 1)


def segments(mode, W, L):
    """顯示 D(s)(s = 相對中灰檔數,−L ≤ s ≤ W)以中灰為原點的兩段三次式:
    D = c0 + c1·s + c2·s² + c3·s³,s ≥ 0 用 up、s < 0 用 lo。回傳 (c0, up, lo),up/lo = (c1, c2, c3)。
      stops : 每檔等寬,D = (s + L)/(W + L)。
      twolog: 中灰 = 709 中灰 G,上下各自均分(中灰處有折角)。
      smooth: 同樣過 (−L, 0)、(0, G)、(W, 1),以單調三次 Hermite(PCHIP,Fritsch–Carlson 權重)連接。
    (lut709 不是多項式,見 lut709()。)"""
    if mode == 'stops':
        T = W + L
        return L / T, (1 / T, 0.0, 0.0), (1 / T, 0.0, 0.0)
    G = G709
    d1, d2 = G / L, (1 - G) / W
    if mode == 'twolog':
        return G, (d2, 0.0, 0.0), (d1, 0.0, 0.0)
    assert mode == 'smooth', mode
    h1, h2 = L, W
    w1, w2 = 2 * h2 + h1, h2 + 2 * h1
    mg = (w1 + w2) / (w1 / d1 + w2 / d2)

    def end(dn, df, hn, hf):
        m = ((2 * hn + hf) * dn - hn * df) / (hn + hf)
        return 0.0 if m < 0 else min(m, 3 * dn)
    m_lo, m_hi = end(d1, d2, h1, h2), end(d2, d1, h2, h1)
    up = (mg, (3 * d2 - 2 * mg - m_hi) / h2, (mg + m_hi - 2 * d2) / h2 ** 2)
    lo = (mg, (m_lo + 2 * mg - 3 * d1) / h1, (m_lo + mg - 2 * d1) / h1 ** 2)
    return G, up, lo


def disp(mode, s, W, L):
    """numpy:相對中灰檔數 s → 顯示 D(0..1),s 先夾到 [−L, W](lut709 不夾底線:文件曲線自己收到 0)。"""
    if mode == 'lut709':
        return lut709(np.minimum(np.asarray(s, float), W), W)
    c0, up, lo = segments(mode, W, L)
    s = np.clip(np.asarray(s, float), -L, W)
    c = [np.where(s >= 0, u, l) for u, l in zip(up, lo)]
    return np.clip(c0 + s * (c[0] + s * (c[1] + s * c[2])), 0, 1)


# 預覽 tone 表輸入線性、削波在 index 1918;最暗可分的是 index 1(離削波 log2(1918) ≈ 10.9 檔)。
# 2026-09-26 上機([0] 黑、[1..31] 白):查表不內插,最底 1.6 檔以「雜訊點密度」出現在 index 0/1 的交界。
# 使用者:這個模式要分得出高光／暗部是否削波 → index 0 = 純黑(只代表壓死)、index 1 = DMIN(液晶上看得到的最暗階)。
LV_FLOOR = -math.log2(1918)             # index 1 相對削波的檔數 ≈ −10.905
DMIN = 0.10                             # index 1 的顯示值(液晶黑位約 6.6 %,見 rv_tables.LIFT)
DK = 0.16                               # GA 墊腳接回文件曲線的顯示值


def disp_lv(mode, s, W, L=None):
    """卡上實際用的曲線(index ≥ 1;index 0 由 rv_tables 固定為黑)。s = 相對中灰檔數。
      stops (SA):官方 12.5 檔(底部 −L → 0、削波 W → 1)每檔等距壓進 709(使用者 2026-09-26:SA 對比 0 必須每檔
                  等距、整個 12.5 檔一起壓縮,不能只壓低檔位)。最底 1.6 檔落在 index 0/1 之間,只以 index 1 亮度的噪點出現。
      lut709(GA):文件曲線;顯示值 < DK 的暗部加一條每檔等寬的墊腳 (s1, DMIN) → (s_k, DK),取兩者較大,
                  s_k 以上照文件不動。s1 以下兩者都照直線延伸(給取樣表內插用)。"""
    s = np.minimum(np.asarray(s, float), W)
    s1 = W + LV_FLOOR
    if mode == 'stops':
        return disp('stops', s, W, L)
    assert mode == 'lut709', mode
    base = lut709(s, W)
    sk = ga_toe(W)
    if sk <= s1:
        return base
    toe = DMIN + (DK - DMIN) * (s - s1) / (sk - s1)
    return np.clip(np.where(s < sk, np.maximum(base, toe), base), 0, 1)


LCD_BLACK = 16.9 / 255                  # 液晶黑位(顯示端實測 lift,rv_tables.LIFT)
N709 = -math.log2(LCD_BLACK / 4.5)      # 709 OETF 從白到液晶黑位的檔數 ≈ 6.09(線性段 V = 4.5 L)


def oetf709(x):
    x = np.asarray(x, float)
    return np.where(x < 0.018, 4.5 * x, 1.099 * np.power(np.maximum(x, 0.018), 0.45) - 0.099)


def sa709(s, W, T):
    """SA(2026-09-27 使用者:必須照 709 的檔位,是用來看的):T 檔(削波 → 底部)等比例壓進 709 從白到液晶黑位的
    N709 檔,再用 709 OETF 顯示 → 每檔間距照 709(亮部寬、暗部窄)。削波 → 100 %,底部 → 液晶黑位(看起來黑)。"""
    s = np.minimum(np.asarray(s, float), W)
    return np.clip(oetf709(np.power(2.0, (N709 / T) * (s - W))), 0, 1)


def disp_card(mode, con, s, W, L):
    """卡上四組曲線(index ≥ 1;index 0 由 rv_tables 固定為黑)。使用者 2026-09-26:
      對比 0 = 12.5 檔壓進 709(SA 照 709 檔距,sa709;GA 暗部墊腳,最底 1.6 檔以噪點看得到)
      對比 1 = 缺失 1.6 檔的做法(SA 只把預覽看得到的 10.9 檔照 709 檔距壓進,index 1 → 液晶黑位;GA 完全照文件 LUT)"""
    if mode == 'stops':
        return sa709(s, W, W + L if con == 0 else -LV_FLOOR)   # 對比 0:官方 12.5 檔;對比 1:預覽看得到的 10.9 檔
    if con == 0:
        return disp_lv(mode, s, W, L)
    return disp('lut709', np.minimum(np.asarray(s, float), W), W, L)


def ga_toe(W):
    """GA 墊腳接回文件曲線的位置 s_k(文件曲線第一次 ≥ DK;s1 起算,0.001 檔精度)。"""
    s1 = W + LV_FLOOR
    g = np.arange(round(s1, 3), W, 0.001)
    above = np.nonzero(lut709(g, W) >= DK)[0]
    return float(g[above[0]]) if len(above) else W


def film(x):
    """Gen 5 Film 編碼(官方技術文件公式)。"""
    x = np.asarray(x, float)
    return np.where(x < 0.005, 8.283605932402494 * x + 0.09246575342465753,
                    0.08692876065491224 * np.log(np.maximum(x, 0) + 0.005494072432257808)
                    + 0.5300133392291939)


def film_inv(c):
    c = np.asarray(c, float)
    lin = (c - 0.09246575342465753) / 8.283605932402494
    log = np.exp((c - 0.5300133392291939) / 0.08692876065491224) - 0.005494072432257808
    return np.where(c < film(0.005), lin, log)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(HERE.parent / 'curves'))
    ap.add_argument('--black8', type=float, default=27.0, help='8-bit 黑位(現行 LV 實測約 27)')
    ap.add_argument('--top8', type=float, default=250.0, help='最大白點(+6.09 檔)對到的碼值')
    ap.add_argument('--black12', type=float, default=256.0, help='12-bit 感光元件黑位 [未證]')
    ap.add_argument('--white12', type=float, default=4095.0)
    ap.add_argument('--lift', type=float, default=16.9, help='顯示端黑位墊高(8-bit 碼),實測 16.9')
    ap.add_argument('--gain', type=float, default=0.936, help='顯示端斜率,實測 0.936')
    ap.add_argument('--map', choices=[*MODES, 'bmcc'], default='stops',
                    help='tone2048 對應:stops = A 每檔等寬;smooth = B 中灰 709 平滑曲線;twolog = B 折角版;bmcc = 舊外觀版')
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)

    # 固定編碼:8-bit = k*film(x) + c,film(0)→black8,film(0.18*2^Wmax)→top8
    wmax = max(W_OFFICIAL.values())
    f0, f1 = float(film(0)), float(film(0.18 * 2 ** wmax))
    k = (a.top8 - a.black8) / (f1 - f0); c = a.black8 - k * f0
    enc8 = lambda x: k * film(x) + c
    gray8 = float(enc8(0.18))

    raw = np.arange(4096, dtype=float)
    rows, meta = [], {'encode': {'form': '8bit = k*Gen5Film(x) + c', 'k': k, 'c': c,
                                 'gray_code': gray8, 'black8': a.black8, 'top8_at_Wmax': a.top8,
                                 'black12': a.black12, 'white12': a.white12,
                                 'codes_per_stop_mid': float(enc8(0.18 * 4) - enc8(0.18 * 2))},
                      'iso': []}
    for iso in ISO_STEPS:
        w, src = w_of(iso)
        scale = 0.18 * 2 ** w / (a.white12 - a.black12)      # 12-bit 碼 → 相對線性
        x = np.clip(raw - a.black12, 0, None) * scale
        lut = np.clip(np.round(enc8(x)), 0, 255).astype(np.uint8)
        (out / f'enc_iso{iso}.u8').write_bytes(lut.tobytes())
        top = int(lut[-1])
        meta['iso'].append({'iso': iso, 'W_stops_over_gray': round(w, 3), 'W_source': src,
                            'input_scale': scale, 'top_code': top, 'gray_code': round(gray8, 1),
                            'distinct_codes': int(len(np.unique(lut)))})
        rows.append([iso, round(w, 3), src, top, round(gray8, 1)])

    # 顯示:LV 碼 → Film code → BMCC Film→Video 中性軸 → 8-bit
    tab = np.genfromtxt(BMCC_NEUTRAL, delimiter=',', names=True)
    node, video = tab['input_log_rgb'], tab['Blackmagic_Gen_5_Film_to_Videocube']
    lv = np.arange(256, dtype=float)
    filmcode = (lv - c) / k
    disp = np.clip(np.round(255 * np.interp(filmcode, node, video)), 0, 255).astype(np.uint8)
    (out / 'display.u8').write_bytes(disp.tobytes())
    meta['display'] = {'source': str(BMCC_NEUTRAL.relative_to(HERE.parents[2])),
                       'column': 'Blackmagic Gen 5 Film to Video.cube (neutral axis)',
                       'gray_display_code': int(disp[int(round(gray8))])}

    # 硬體 tone LUT 版(RAW 模式實際要裝的):2048 × u16,輸出 0..8190(顯示編碼後的值)。
    # 輸入是線性:index 1918 = 感光元件滿位(OFF 表 = sRGB(i/1918)×8190 已證);
    # 前提是 LUT 之前的數位增益維持 1×。
    idx = np.arange(2048, dtype=float)
    if a.map in MODES:
        # stops(A,每檔等寬,2026-09-24)/ smooth(B,中灰 = 709 中灰的平滑曲線,2026-09-25)/ twolog(B 的折角版,保留比對)
        meta['tone2048'] = {'map': a.map, 'white_index': 1918, 'out_max': 8190, 'gray709': round(G709, 4),
                            'form': 's=log2(i/1918)+W; D=segments(map); out=clip((D-lift/255)/gain)',
                            'lift': a.lift, 'gain': a.gain}
        for iso in ISO_STEPS:
            (w, _), (l, _) = w_of(iso), l_of(iso)
            d = disp(a.map, np.log2(np.maximum(idx / 1918, 1e-12)) + w, w, l)
            d = np.clip((d - a.lift / 255) / a.gain, 0, 1)   # 顯示端補償(實測 螢幕 = 0.936×預期 + 16.9/255)
            t = np.round(8190 * d).astype('<u2')
            (out / f'tone2048_iso{iso}.u16le').write_bytes(t.tobytes())
            r = next(e for e in meta['iso'] if e['iso'] == iso)
            r.update({'L_stops_under_gray': round(l, 3), 'total_stops': round(w + l, 3),
                      'gray_display': round(float(disp(a.map, 0, w, l)), 3)})
    else:
        # 舊版(外觀):每個 ISO 的頂峰對到白,中灰以下照 BMCC,中灰以上把 0..W 檔對到 BMCC 的 0..6.09 檔肩部。
        WREF = wmax
        V = lambda x: np.interp(film(x), node, video)
        v0, vref = float(V(0.18)), float(V(0.18 * 2 ** WREF))
        meta['tone2048'] = {'map': 'bmcc', 'white_index': 1918, 'out_max': 8190, 'wref': WREF}
        for iso in ISO_STEPS:
            w, _ = w_of(iso)
            x = 0.18 * 2 ** w * idx / 1918
            s = np.log2(np.maximum(x, 1e-9) / 0.18)
            hi = v0 + (V(0.18 * 2 ** (np.maximum(s, 0) * WREF / w)) - v0) * (1 - v0) / (vref - v0)
            d = np.where(s <= 0, V(x), hi)
            t = np.clip(np.round(8190 * d), 0, 8190).astype('<u2')
            (out / f'tone2048_iso{iso}.u16le').write_bytes(t.tobytes())
    (out / 'curves.json').write_text(json.dumps(meta, indent=2, ensure_ascii=False))

    # 逐檔摘要:相對中灰 -6..+7 檔
    with open(out / 'curves.csv', 'w', newline='') as fh:
        wr = csv.writer(fh)
        wr.writerow(['stops_over_gray', 'lv_code', 'display_code'])
        for s in np.arange(-6, 7.01, 0.5):
            v = float(enc8(0.18 * 2 ** s))
            wr.writerow([s, round(v, 1), int(disp[int(np.clip(round(v), 0, 255))])])
    (out / 'curves.json').write_text(json.dumps(meta, indent=2, ensure_ascii=False))

    print(f"encode: gray→{gray8:.1f}  {meta['encode']['codes_per_stop_mid']:.1f} 碼/檔  "
          f"display gray→{meta['display']['gray_display_code']}")
    print(' ISO     W     src      top  distinct')
    for r in meta['iso']:
        print(f" {r['iso']:6d} {r['W_stops_over_gray']:5.2f} {r['W_source']:8s} {r['top_code']:4d} {r['distinct_codes']:5d}")


if __name__ == '__main__':
    main()
