#!/usr/bin/env python3
"""rv_dngcm.py — RAW 模式錄 CinemaDNG 時寫入的 ColorMatrix1/2(與 LCD 的矩陣程度一致),唯一定義。

韌體(FUN_c02c4a50,blk_c02.c:123708):CM = inv(P)·C,P = makernote 0x11f 逐台校正,C = ROM double[9]:
  OFF    CM1 0xC096FD74、CM2 0xC096FCE4(= sRGB 反矩陣 × 逐列縮放 → cam→709 為單位矩陣)
  非 OFF CM1 0xC096FD2C、CM2 0xC096FC9C(機型校正;只留作對照)
卡片把 OFF 分支載入 C 位址的 movw/movt(0xC02C4BE4/BE8、0xC02C4C98/C9C)改指常駐緩衝;stub_gs 依飽和度 k 填入 C_k:
  M = rv_color.cam_to_709()(白平衡後相機 → 709)、M_k = I + k(M − I)(與 LCD 同一個 M_k)、
  W = 校正光源的白(CM1 標準光源 A、CM2 D65)、n = O·W(原廠 OFF 常數 O 在 W 下的相機中性)、
  C_k = diag(n) · inv(M_k) · A · Bradford(W → D65),A = XYZ→709。第 0 級 = 原廠 OFF 常數(位元組照抄;
  CM1 不合此式:原廠 OFF 在 StdA 解碼離單位矩陣 0.4,原廠既有,不動,但它解出的白同樣是 W)。
  DNG 解碼器在白 W 成像 709 = A · Bradford(W → D65) · inv(C_k) · diag(n) = M_k:CM1、CM2 都與 LCD 一致,
  且同一個相機中性在每一級解出的白都與第 0 級相同(白平衡不隨飽和度改變)。
2026-10-04 以前(Luka 指出,fp-view-pack v0.2 / rv-chartfit.patch):C_k = D · inv(M_k) · A(D = O ÷ A 的逐列縮放),
  k = 1 → 非 OFF 常數 N。AsShotNeutral 是相機量的,與標籤無關;標籤決定這個中性代表哪個白。
  O 與 N 對同一個中性給出不同的白:OFF 的 D65 中性用 N 解成 7614 K(OFF 6503 K)→ 舊式 +1 在 Resolve 白點偏約 1100 K。
  dcraw 式每列正規化的驗算看不到(正規化本身就是「白 → 白」),所以 tables() assert 解出的白,__main__ 以舊式為必須失敗的對照。
"""
import pathlib, struct
import numpy as np

ROM = pathlib.Path(__file__).resolve().parents[3] / 'out' / 'MAIN_c0000000.bin'
OFF_CM1, OFF_CM2, NON_CM1, NON_CM2 = 0xC096FD74, 0xC096FCE4, 0xC096FD2C, 0xC096FC9C
SITES = [  # (位址, 原廠字, 載入哪個常數)
    (0xC02C4BE4, 0xE30F2D74, 'movw r2 CM1'), (0xC02C4BE8, 0xE34C2096, 'movt r2 CM1'),
    (0xC02C4C98, 0xE30F2CE4, 'movw r2 CM2'), (0xC02C4C9C, 0xE34C2096, 'movt r2 CM2'),
]
A = np.array([[3.2404542, -1.5371385, -0.4985314], [-0.9692660, 1.8760108, 0.0415560],
              [0.0556434, -0.2040259, 1.0572252]])
W_A, W_D65 = np.array([1.09850, 1, 0.35585]), np.array([0.95047, 1, 1.08883])
BFD = np.array([[0.8951, 0.2664, -0.1614], [-0.7502, 1.7135, 0.0367], [0.0389, -0.0685, 1.0296]])   # Bradford
from rv_color import SAT_LEVELS as LEVELS, sat_k  # noqa: E402  k = ui / SAT_MAX


def const(a):
    d = ROM.read_bytes()
    return np.array(struct.unpack('<9d', d[a - 0xC0000000:a - 0xC0000000 + 72])).reshape(3, 3)


def bradford(src, dst):
    return np.linalg.inv(BFD) @ np.diag((BFD @ dst) / (BFD @ src)) @ BFD


def m_k(k):
    import rv_color
    return np.eye(3) + k * (np.array(rv_color.cam_to_709()) - np.eye(3))


def c_k(k, O, W):
    """照明白 W 的第 k 級 C(XYZ → 相機,未乘 inv(P))。"""
    assert np.allclose(np.diag((O / A).mean(1)) @ A, O, atol=1e-6)    # OFF 常數 = D·A(逐列縮放)
    return np.diag(O @ W) @ np.linalg.inv(m_k(k)) @ A @ bradford(W, W_D65)


def c_k_old(k, N, O):
    """2026-10-04 以前的做法(白會跑),只留作必須失敗的對照。"""
    D = np.diag((O / A).mean(1))
    M = A @ np.linalg.inv(N) @ D
    return D @ np.linalg.inv(np.eye(3) + k * (M - np.eye(3))) @ A


def white(C, n):
    """單一矩陣的 DNG 解碼器由相機中性 n 解出的白(XYZ 正規化成 xy)。"""
    X = np.linalg.solve(C, n)
    return X[:2] / X.sum()


def decoded(C, n, W):
    """解碼器在白 W 的成像:白平衡後相機 → linear 709(Bradford W → D65)。"""
    return A @ bradford(W, W_D65) @ np.linalg.inv(C) @ np.diag(n)


def cct(xy):                             # McCamy
    n = (xy[0] - 0.3320) / (0.1858 - xy[1])
    return 449 * n ** 3 + 3525 * n ** 2 + 6823.3 * n + 5520.33


def tables():
    """[(CM1 C_k, CM2 C_k)],k 依 LEVELS;第 0 級 = 原廠 OFF 常數,其餘 assert 白不動、解碼 = LCD 的 M_k。"""
    O1, O2 = const(OFF_CM1), const(OFF_CM2)
    out = [(O1, O2)]                     # 第 0 級原廠;CM1 在 StdA 本來就與單位矩陣差 0.4(原廠既有,不動)
    for u in LEVELS[1:]:
        out.append((c_k(sat_k(u), O1, W_A), c_k(sat_k(u), O2, W_D65)))
        for C, O, W in zip(out[-1], (O1, O2), (W_A, W_D65)):
            assert np.allclose(decoded(C, O @ W, W), m_k(sat_k(u)), atol=1e-9), (u, W, '解碼 ≠ LCD 的 M_k')
    for C, O, W in ((c, O, W) for lv in out for c, O, W in zip(lv, (O1, O2), (W_A, W_D65))):
        assert np.allclose(white(C, O @ W), W[:2] / W.sum(), atol=1e-9), (W, '解出的白跑掉')
    return out


def blob():
    """len(LEVELS) 級 × (CM1, CM2) × 9 double;第 0 級(k = 0)直接用原廠 OFF 常數位元組。"""
    d = ROM.read_bytes()
    out = []
    for u, (c1, c2) in zip(LEVELS, tables()):
        if u == 0:
            out.append(d[OFF_CM1 - 0xC0000000:OFF_CM1 - 0xC0000000 + 72] + d[OFF_CM2 - 0xC0000000:OFF_CM2 - 0xC0000000 + 72])
        else:
            out.append(struct.pack('<9d', *c1.ravel()) + struct.pack('<9d', *c2.ravel()))
    return b''.join(out)


if __name__ == '__main__':
    import rv_color
    O1, O2, N1, N2 = const(OFF_CM1), const(OFF_CM2), const(NON_CM1), const(NON_CM2)
    for u, (c1, c2) in zip(LEVELS, tables()):
        # 驗算 1:以 C_k 做 Resolve 式換算(cam_rgb = C·inv(A) 每列正規化、取反)≈ LCD 的 M_k(D65)
        c = c2 @ np.linalg.inv(A); c = c / c.sum(1, keepdims=True); m = np.linalg.inv(c)
        lcd = np.array(rv_color.sat_table(u)).astype(float) / 512
        (rr, rg, rb, gg, gr, gb, bb, br, bg) = lcd
        lcd = np.array([[rr, rg, rb], [gr, gg, gb], [br, bg, bb]])
        # 驗算 2:原廠 OFF 在標準光源 A / D65 的相機中性,解出的白
        t1, t2 = cct(white(c1, O1 @ W_A)), cct(white(c2, O2 @ W_D65))
        print(f'飽和度 {u}: |DNG cam→709 − LCD| 最大 {np.abs(m - lcd).max():.4f}  白 CM1 {t1:.0f} K、CM2 {t2:.0f} K')
    # 對照(必須失敗):舊式在最高級 = 原廠非 OFF 常數 N,白跑掉;每列正規化驗算照樣通過
    k = sat_k(LEVELS[-1])
    for nm, O, N, W, ref in (('CM1', O1, N1, W_A, 2856), ('CM2', O2, N2, W_D65, 6504)):
        old = c_k_old(k, N, O)
        assert np.allclose(old, N, atol=1e-9)
        c = old @ np.linalg.inv(A); c = c / c.sum(1, keepdims=True)
        t = cct(white(old, O @ W))
        rn = f';每列正規化驗算 {np.abs(np.linalg.inv(c) - m_k(k)).max():.1e}(照樣通過,看不到)' if nm == 'CM2' else ''
        print(f'對照 舊式 {nm} 最高級:解成 {t:.0f} K(應 {ref} K){rn}')
    assert abs(cct(white(c_k_old(k, N2, O2), O2 @ W_D65)) - 6504) > 500, '對照沒失敗:白的驗算看不到舊式的錯'
    print(len(blob()), 'B')
