#!/usr/bin/env python3
"""OG2K 3x3 的後製幾何修正:G2/B 內容向上移 1/3 CFA 平面列(§7.58.2、§7.61)。

    python3 og2k3x3_fix.py in.dng out.dng [--kernel lanczos6|fourier|cr] [--no-lastrow]

只處理未壓縮 12-bit、單一 strip、RGGB 的 fp CinemaDNG(OG2K 2016x1344)。
解包後與 rawpy 逐像素比對,打包後再讀回比對,任何一步不一致就拒絕寫檔。

--no-lastrow:新素材若已用 072A=168 修好末列(§7.55),不要再用 r−2 蓋掉真資料。
舊素材(末列 = 2/3 亮度)預設以同色 r−2 列修補,再內插,避免壞列擴散(§7.51)。
"""
import argparse, struct, sys
import numpy as np
import rawpy


def tags(buf):
    """讀第一個 IFD 的 StripOffsets / StripByteCounts / 尺寸 / 位元 / 壓縮。"""
    e = '<' if buf[:2] == b'II' else '>'
    off = struct.unpack(e + 'I', buf[4:8])[0]
    n = struct.unpack(e + 'H', buf[off:off + 2])[0]
    out = {}
    size = {3: 2, 4: 4}
    for i in range(n):
        t, typ, cnt, val = struct.unpack(e + 'HHII', buf[off + 2 + 12 * i: off + 14 + 12 * i])
        if typ in size and cnt == 1:
            v = val if typ == 4 else struct.unpack(e + 'H', buf[off + 10 + 12 * i: off + 12 + 12 * i])[0]
            out[t] = v
    return out


def unpack12(b, h, w):
    a = np.frombuffer(b, np.uint8).reshape(h, w * 3 // 2).astype(np.uint16)
    b0, b1, b2 = a[:, 0::3], a[:, 1::3], a[:, 2::3]
    out = np.empty((h, w), np.uint16)
    out[:, 0::2] = (b0 << 4) | (b1 >> 4)
    out[:, 1::2] = ((b1 & 0xF) << 8) | b2
    return out


def pack12(p):
    p = p.astype(np.uint16)
    p0, p1 = p[:, 0::2], p[:, 1::2]
    out = np.empty((p.shape[0], p.shape[1] * 3 // 2), np.uint8)
    out[:, 0::3] = p0 >> 4
    out[:, 1::3] = ((p0 & 0xF) << 4) | (p1 >> 8)
    out[:, 2::3] = p1 & 0xFF
    return out.tobytes()


def lanczos(P, d, a=6):
    """out[s] = P[s+d],floor-based,a 瓣 Lanczos,邊界複製。"""
    n = P.shape[0]
    s = np.arange(n) + d
    i0 = np.floor(s).astype(int)
    f = s - i0
    ks = range(-a + 1, a + 1)
    W = np.array([np.sinc(f - k) * np.sinc((f - k) / a) for k in ks])
    W /= W.sum(0)
    out = np.zeros(P.shape, np.float64)
    for j, k in enumerate(ks):
        out += W[j][:, None] * P[np.clip(i0 + k, 0, n - 1)]
    return out


def fourier(P, d, pad=96):
    e = np.concatenate([P[pad:0:-1], P, P[-2:-pad - 2:-1]])
    f = np.fft.fftfreq(e.shape[0])[:, None]
    return np.real(np.fft.ifft(np.fft.fft(e, axis=0) * np.exp(2j * np.pi * f * d), axis=0))[pad:pad + P.shape[0]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('--kernel', default='lanczos6', choices=('lanczos6', 'fourier', 'cr'))
    ap.add_argument('--no-lastrow', action='store_true')
    ap.add_argument('--one-sided', action='store_true',
                    help='只移 G2/B 1/3(舊做法);預設兩邊各移 1/6,四平面經過鏡像核,雜訊/銳利度相等')
    a = ap.parse_args()

    buf = bytearray(open(a.src, 'rb').read())
    t = tags(buf)
    w, h, bits, comp, so, sb = t[256], t[257], t[258], t[259], t[273], t[279]
    assert (bits, comp) == (12, 1) and sb == w * h * 3 // 2, (bits, comp, sb)
    raw = unpack12(bytes(buf[so:so + sb]), h, w)
    with rawpy.imread(a.src) as r:
        ref = r.raw_image_visible.copy()
        assert (r.raw_pattern == np.array([[0, 1], [3, 2]])).all(), r.raw_pattern
    assert ref.shape == raw.shape and (ref == raw).all(), '解包與 rawpy 不一致'

    x = raw.astype(np.float64)
    if not a.no_lastrow:
        x[-1] = x[-3]                        # 同色 r−2(§7.51 缺陷一)
    # 相對位移:G2/B 對 R/G1 取 out[s] = P[s − 1/3](§7.58.2)。
    # 兩邊各 1/6(§7.62):f = 1/6 與 5/6 的核互為鏡像,振幅響應相同 → G1/G2 雜訊與銳利度相等。
    shifts = {1: -1.0 / 3.0} if a.one_sided else {1: -1.0 / 6.0, 0: +1.0 / 6.0}
    def shift(P, d):
        if a.kernel == 'lanczos6':
            return lanczos(P, d, 6)
        if a.kernel == 'fourier':
            return fourier(P, d)
        sys.path.insert(0, __file__.rsplit('/', 1)[0])
        from rowfix import cr_shift_rows
        return cr_shift_rows(P, d)
    for parity, d in shifts.items():         # 列奇偶:0 = R/G1,1 = G2/B
        for c in (0, 1):
            x[parity::2, c::2] = shift(x[parity::2, c::2], d)
    out = np.clip(np.round(x), 0, 4095).astype(np.uint16)

    buf[so:so + sb] = pack12(out)
    open(a.dst, 'wb').write(buf)
    with rawpy.imread(a.dst) as r:
        assert (r.raw_image_visible == out).all(), '寫回後讀取不一致'
    print('%s → %s  kernel=%s split=%s lastrow=%s  改動像素 %.1f%%' % (
        a.src.rsplit('/', 1)[-1], a.dst, a.kernel, not a.one_sided, not a.no_lastrow, 100 * (out != raw).mean()))


if __name__ == '__main__':
    main()
