#!/usr/bin/env python3
"""rv_dngcm.py — bCOLOR 錄 CinemaDNG 時寫入的 ColorMatrix1/2,唯一定義(由 rawview 的同名檔 fork)。

bCOLOR:cm_tab 三級,stub_gs 以 eff ? lat + 1 : 0 選:
    0  原廠 OFF 常數(不生效時;一般錄影的 DNG 不變)
    1  FC:原廠非 OFF 常數(fp 自己的校準)
    2  BC:BMCC 6K 的 ColorMatrix1(StdA 2856K)/ ColorMatrix2(D65)(datapack field 4/5,bc_bmcc.calibration)
韌體照常乘 inv(P)(逐台通道修正),BMCC 矩陣同樣經過它。以下是 rawview 原本的說明:

韌體(FUN_c02c4a50,blk_c02.c:123708):CM = inv(P)·C,P = makernote 0x11f 逐台校正,C = ROM double[9]:
  OFF    CM1 0xC096FD74、CM2 0xC096FCE4(= sRGB 反矩陣 × 逐列縮放 → cam→709 為單位矩陣)
  非 OFF CM1 0xC096FD2C、CM2 0xC096FC9C(機型校正;cam→709 = LCD 用的 rv_color 矩陣)
卡片把 OFF 分支載入 C 位址的 movw/movt(0xC02C4BE4/BE8、0xC02C4C98/C9C)改指常駐緩衝;stub_gs 依飽和度 k 填入 C_k:
  D = O ÷ A 的逐列縮放(O = D·A)、M = A·inv(N)·D、C_k = D · inv(I + k(M − I)) · A,A = XYZ→709。
  k = 0 → O、k = 1 → N(兩端精確;CM1、CM2 各自算)。
中間 k 與 LCD 的 M_k 只差白平衡對角,由 AsShotNeutral 吸收(研究代理驗算,scratchpad/dngcm/cm.py)。
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
from rv_color import SAT_LEVELS as LEVELS, sat_k  # noqa: E402  k = ui / SAT_MAX


def const(a):
    d = ROM.read_bytes()
    return np.array(struct.unpack('<9d', d[a - 0xC0000000:a - 0xC0000000 + 72])).reshape(3, 3)


def c_k(k, N, O, W=None):
    D = np.diag((O / A).mean(1))          # OFF 常數 = D·A(逐列縮放)
    assert np.allclose(D @ A, O, atol=1e-6)
    M = A @ np.linalg.inv(N) @ D          # 相機 → 709(以 OFF 的相機座標)
    return D @ np.linalg.inv(np.eye(3) + k * (M - np.eye(3))) @ A


def tables():
    """[(CM1 C_k, CM2 C_k)],k 依 LEVELS;兩端 assert 等於原廠常數。"""
    N1, O1, N2, O2 = const(NON_CM1), const(OFF_CM1), const(NON_CM2), const(OFF_CM2)
    out = [(c_k(sat_k(u), N1, O1, W_A), c_k(sat_k(u), N2, O2, W_D65)) for u in LEVELS]
    assert np.allclose(out[0][0], O1, atol=1e-9) and np.allclose(out[0][1], O2, atol=1e-9)
    assert np.allclose(out[-1][0], N1, atol=1e-9) and np.allclose(out[-1][1], N2, atol=1e-9)
    return out


def bc_blob():
    """bCOLOR 的 cm_tab:3 級 × (CM1, CM2) × 9 double。"""
    import bc_bmcc
    d = ROM.read_bytes()
    raw = lambda a: d[a - 0xC0000000:a - 0xC0000000 + 72]
    CM1, CM2 = bc_bmcc.calibration()[:2]
    return (raw(OFF_CM1) + raw(OFF_CM2) + raw(NON_CM1) + raw(NON_CM2)
            + struct.pack('<9d', *CM1.ravel()) + struct.pack('<9d', *CM2.ravel()))


NCM = 3


def blob():
    return bc_blob()


def rawview_blob():
    """rawview 原本的(len(LEVELS) 級 × (CM1, CM2) × 9 double;第 0 級(k = 0)直接用原廠 OFF 常數位元組。"""
    d = ROM.read_bytes()
    out = []
    for u, (c1, c2) in zip(LEVELS, tables()):
        if u == 0:
            out.append(d[OFF_CM1 - 0xC0000000:OFF_CM1 - 0xC0000000 + 72] + d[OFF_CM2 - 0xC0000000:OFF_CM2 - 0xC0000000 + 72])
        elif u == LEVELS[-1]:
            out.append(d[NON_CM1 - 0xC0000000:NON_CM1 - 0xC0000000 + 72] + d[NON_CM2 - 0xC0000000:NON_CM2 - 0xC0000000 + 72])
        else:
            out.append(struct.pack('<9d', *c1.ravel()) + struct.pack('<9d', *c2.ravel()))
    return b''.join(out)


if __name__ == '__main__':
    import rv_color
    for u, (c1, c2) in zip(LEVELS, tables()):
        # 驗算:以 C_k 做 Resolve 式換算(cam_rgb = C·inv(A) 每列正規化、取反)≈ LCD 的 M_k(D65)
        c = c2 @ np.linalg.inv(A); c = c / c.sum(1, keepdims=True); m = np.linalg.inv(c)
        lcd = np.array(rv_color.sat_table(u)).astype(float) / 512
        (rr, rg, rb, gg, gr, gb, bb, br, bg) = lcd
        lcd = np.array([[rr, rg, rb], [gr, gg, gb], [br, bg, bb]])
        print(f'飽和度 {u}: |DNG cam→709 − LCD| 最大 {np.abs(m - lcd).max():.4f}')
    print(len(blob()), 'B')
