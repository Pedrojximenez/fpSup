#!/usr/bin/env python3
"""bc_bmcc.py — bCOLOR 用的 BMCC 6K 色彩資料(唯一定義;離線,資料來自 bmcc6k/ 研究歸檔)。

BMCC 6K 的流程(bmcc6k/analysis-20260924,datapack 與原廠 LUT):
    相機 RGB(白平衡後)─FM─▶ XYZ D65 ─▶ BMWG 線性 ─Gen5 Film─▶ Film code ─33³ LUT─▶ Rec.709 / BT.1886

fp 的硬體只有「3×3 矩陣 → 每通道同一條 tone」,所以 33³ LUT 拆成:
    tone(s)   中性軸:18% 灰以上 s 檔的線性 → Film → LUT 對角線(四面體內插在對角線上 = 線性內插)
    LUT 矩陣  BMWG 線性 → 「709 線性」的 3×3:對中低飽和色,LUT 輸出逐通道反查 tone 回線性,最小平方擬合(列和 1)
LUT 的高飽和軟壓縮與 Video 的不對稱,3×3 + 1D 做不到(擬合殘差見 report())。

校準(datapack camera record,mode 1/2,欄位意義由數值驗算:CM2·FM2ᵀ 為對角、FM 欄和 = 白點):
    field 4 / 5   ColorMatrix1 / 2(XYZ → 相機,StdA 2856K / D65)
    field 6 / 7   ForwardMatrix1 / 2(白平衡後相機 → XYZ D65,以轉置存)
"""
import json, math, pathlib
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
AN = ROOT / 'bmcc6k' / 'analysis-20260924'
LUTDIR = AN / 'bmcc6k-decompile-20260924/payload_audit/extracted/payload/restore/user/luts'
CUBES = {'video': 'Blackmagic Gen 5 Film to Video.cube',
         'extended': 'Blackmagic Gen 5 Film to Extended Video.cube'}
RECORDS = AN / 'bmcc6k-liveview-rec709-20260924/controls/camera_records.json'

# BMWG Gen5 原色(datapack 0x840,與官方 Gen5 技術文件逐項 float32 相同)
BMWG_XY = [(0.7177215, 0.3171181), (0.228041, 0.861569), (0.1005841, -0.0820452)]
D65_XY = (0.3127170, 0.3290312)
M709 = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750],
                 [0.0193339, 0.1191920, 0.9503041]])          # 線性 709 → XYZ


def film(x):
    """Gen 5 Film 編碼(官方公式)。"""
    x = np.asarray(x, float)
    return np.where(x < 0.005, 8.283605932402494 * x + 0.09246575342465753,
                    0.08692876065491224 * np.log(np.maximum(x, 0) + 0.005494072432257808)
                    + 0.5300133392291939)


def _xyz(x, y):
    return np.array([x / y, 1.0, (1 - x - y) / y])


def bmwg_to_xyz():
    P = np.array([_xyz(*p) for p in BMWG_XY]).T
    return P * np.linalg.solve(P, _xyz(*D65_XY))


_CUBE = {}


def cube(name):
    """33³ LUT,索引 [b, g, r](.cube 的 r 最快)。"""
    if name not in _CUBE:
        rows = []
        for line in (LUTDIR / CUBES[name]).read_text().splitlines():
            p = line.split()
            if len(p) == 3:
                try:
                    rows.append([float(v) for v in p])
                except ValueError:
                    pass
        t = np.array(rows)
        assert t.shape == (33 ** 3, 3), t.shape
        _CUBE[name] = t.reshape(33, 33, 33, 3)
    return _CUBE[name]


def apply(name, rgb):
    """四面體內插(相機手冊 p.110–112);rgb 形狀 (..., 3),Film code 0..1。"""
    L = cube(name)
    n = L.shape[0] - 1
    c = np.clip(np.asarray(rgb, float), 0, 1) * n
    i = np.minimum(np.floor(c).astype(int), n - 1)
    f = c - i
    r, g, b = i[..., 0], i[..., 1], i[..., 2]
    fr, fg, fb = f[..., 0:1], f[..., 1:2], f[..., 2:3]
    V = lambda dr, dg, db: L[b + db, g + dg, r + dr]
    c000, c111 = V(0, 0, 0), V(1, 1, 1)
    out = np.empty(c.shape)
    # 六個四面體,依 fr、fg、fb 大小排序
    conds = [((fr >= fg) & (fg >= fb)), ((fr >= fb) & (fb > fg)), ((fb > fr) & (fr >= fg)),
             ((fg > fr) & (fr >= fb)), ((fg >= fb) & (fb > fr)), ((fb > fg) & (fg > fr))]
    order = [((1, 0, 0), (1, 1, 0), fr, fg, fb), ((1, 0, 0), (1, 0, 1), fr, fb, fg),
             ((0, 0, 1), (1, 0, 1), fb, fr, fg), ((0, 1, 0), (1, 1, 0), fg, fr, fb),
             ((0, 1, 0), (0, 1, 1), fg, fb, fr), ((0, 0, 1), (0, 1, 1), fb, fg, fr)]
    for cond, (a, bb, t1, t2, t3) in zip(conds, order):
        v = (1 - t1) * c000 + (t1 - t2) * V(*a) + (t2 - t3) * V(*bb) + t3 * c111
        out = np.where(cond, v, out)
    return out


GREY = 0.18


def tone(name, s):
    """中性軸:18% 灰以上 s 檔 → 顯示值 0..1。"""
    s = np.asarray(s, float)
    f = film(GREY * np.power(2.0, s))
    return apply(name, np.stack([f, f, f], -1))[..., 0]


def tone_inv(name, d):
    """tone 的反函數(單調段;以密集取樣反查)。"""
    s = np.linspace(-12, 11, 23001)
    t = np.maximum.accumulate(tone(name, s))
    return np.interp(d, t, s, left=-12, right=11)


def _samples():
    """擬合用色:線性 BMWG,中性 ±(0.5–1 倍)色差,曝光 −3..+2 檔;只取 709 色域內(LUT 不必軟壓縮)。"""
    rng = np.random.default_rng(410)
    X = bmwg_to_xyz()
    to709 = np.linalg.inv(M709) @ X
    out = []
    while len(out) < 4000:
        e = GREY * 2.0 ** rng.uniform(-3, 2)
        chroma = rng.normal(0, 0.35, 3)
        v709 = e * np.exp(chroma - chroma.mean())
        if v709.min() <= 0:
            continue
        out.append(np.linalg.solve(to709, v709))
    return np.array(out)


_FIT = {}


def lut_matrix(name):
    """BMWG 線性 → 709 線性(列和 1)的 3×3,使 tone(M·x) ≈ LUT(Film(x))。"""
    if name in _FIT:
        return _FIT[name]
    x = _samples()
    o = apply(name, film(x))
    ok = (o > 0.03).all(1) & (o < 0.97).all(1)
    y = GREY * np.power(2.0, tone_inv(name, o[ok]))       # 逐通道反查回線性
    x = x[ok]
    M = np.zeros((3, 3))
    for i in range(3):                                      # 列和 1:y − x₂ = a(x₀ − x₂) + b(x₁ − x₂)
        A = np.stack([x[:, 0] - x[:, 2], x[:, 1] - x[:, 2]], 1)
        a, b = np.linalg.lstsq(A, y[:, i] - x[:, 2], rcond=None)[0]
        M[i] = (a, b, 1 - a - b)
    _FIT[name] = M
    return M


def calibration():
    """(CM1, CM2, FM1, FM2):datapack mode 1 的 BMCC 6K 校準。CM = XYZ → 相機;FM = 白平衡後相機 → XYZ D65。"""
    d = json.loads(RECORDS.read_text())
    cal = d['cameras'][0]['profiles'][0]['modes'][0]['calibration']
    assert [u['value'] for u in cal['u16_fields_0_to_3']] == [2856, 6500, 2856, 6500]
    M = {m['field']: np.array(m['raw_storage_order_9']).reshape(3, 3) for m in cal['inline_float32_matrices']}
    for n in cal['nested_float32_coefficients']:
        M[n['field']] = np.array([r['values'] for r in n['rows']]).T
    CM1, CM2, FM1, FM2 = M[4], M[5], M[6], M[7]
    wd65 = _xyz(*D65_XY)
    for CM, FM in ((CM1, FM1), (CM2, FM2)):
        assert np.allclose(FM.sum(1), wd65, atol=1e-4)                 # 白 → D65
    D = CM2 @ FM2                                                     # = diag(相機中性值)
    assert np.abs(D - np.diag(np.diag(D))).max() < 1e-6
    return CM1, CM2, FM1, FM2


def xyz_to_bmwg():
    return np.linalg.inv(bmwg_to_xyz())


def report():
    for name in CUBES:
        M = lut_matrix(name)
        x = _samples()
        o = apply(name, film(x))
        p = tone(name, np.log2(np.maximum(x @ M.T, 1e-9) / GREY))
        ok = (o > 0.03).all(1) & (o < 0.97).all(1)
        e = np.abs(p - o)[ok]
        print(f'{name}: tone(0) {float(tone(name, 0)):.4f}  LUT 矩陣\n{np.round(M, 4)}'
              f'\n  中低飽和 3×3+1D 誤差:平均 {e.mean():.4f}、95% {np.percentile(e, 95):.4f}、最大 {e.max():.4f}(顯示值)')


if __name__ == '__main__':
    report()
    CM1, CM2, FM1, FM2 = calibration()
    print('BMCC CM2\n', np.round(CM2, 4), '\nBMCC FM2\n', np.round(FM2, 4))
