#!/usr/bin/env python3
"""rv_tables.py — rawview tone 表的整數定義(卡片與測試共用)。

四組,每組 31 張(ISO 由低到高),共 124 張;組 = 曲線(SA/GA)× 對比度(0/1,AEL 頁,使用者 2026-09-26):
    組 0 = SA、對比 0:官方 12.5 檔照 709 檔距壓進(rv_curves.sa709;削波 → 白、底部 → 液晶黑位)
    組 1 = GA、對比 0:文件 709 LUT + 暗部墊腳(index 1 → DMIN,到顯示 DK 接回文件曲線;rv_curves.disp_lv)
    組 2 = SA、對比 1:缺失 1.6 檔的做法,預覽看得到的 10.9 檔照 709 檔距壓進(index 1 → 液晶黑位)
    組 3 = GA、對比 1:原做法,SIGMA fp Rec709 LUT Guide v3 的 ISO 相依 709 LUT(依飽和點 W 內插)
所有組 index 0 = 純黑(只代表壓死;2026-09-26 起,原本 SA ISO 100 的 index 0 會是 11 % 灰)。
LOG[i] = log2(i/1918)(Q16)由 launcher 開機時算(log_q16:CLZ + LT[257] 分段線性,與這裡逐位元相同;
    2026-09-27 為了放進 fpSup-Merge 縮小卡片,原本 LOG 8 KiB 放在卡上)。
每張表 = max(取樣曲線, 直線)(兩者之一可以沒有):
    x = (LOG[i]·K >> 16) + A(Q16);x < 0(只有 index 0)→ 0
    GA:K = 1、A = W − S0 → x = 相對中灰檔數 − S0(S0 = −8);取樣 SAMP[ISO] = 文件曲線
    SA:K = N709 / T、A = −S0 → x = (相對削波檔數 × K) − S0;共用一條 SAMP[31] = 709 OETF(2^y)(sa709 化成 y 的函數)
    取樣:以 S0 + j·0.1 取樣、線性內插(j = x·10 >> 16,f = 低 16 位)
    直線:x < XK → C + (M·x >> 24)(M = LSB/檔 Q8,C = x = 0 處的 LSB)
    再夾到 0..B。GA 對比 0 另加墊腳直線。
卡片上帶:LT[257] u32 | LOGW s32 | REC[124] × {K, A, GRP, M, C, XK} s32 | B | THR[30] | SAMP[32][NSP] u16。
`python3 rv_tables.py` 會和 rv_curves(浮點)逐點比對。
"""
import math, pathlib, struct, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'tools'))
from rv_curves import ISO_STEPS, w_of, l_of, disp, disp_card, ga_toe, oetf709, LV_FLOOR, N709, DMIN, DK  # noqa: E402

N = 2048
WHITE = 1918
OUT_MAX = 8190
LIFT, GAIN = 16.9, 0.936          # 顯示端實測(README「每檔等寬表上機驗證」)
REL100 = 117
LOG0 = -32 * 65536                # i = 0
SETS = (('stops', 0), ('lut709', 0), ('stops', 1), ('lut709', 1))   # (曲線, 對比度)
NTAB = len(ISO_STEPS)
NREC = len(SETS) * NTAB
RECW = 6                          # REC 每筆 word 數
NLT = 257                         # log2(1 + j/256) 表
S0 = -8.0
STEP = 0.1
NS = 146
NSP = NS + (NS & 1)
XK_NONE = -0x80000000             # 不用直線
XK_ALL = 0x7FFFFFFF               # 整張都是直線


def lt():
    """LT[j] = log2(1 + j/256)(Q16),j = 0..256。"""
    return [round(math.log2(1 + j / 256) * 65536) for j in range(NLT)]


def _log2_q16(i, LT):
    """log2(i)(Q16),1 ≤ i < 2^11;launcher 逐步相同:n = 31 − clz(i),f = (i << (20 − n)) − 2^20。"""
    n = i.bit_length() - 1
    f = (i << (20 - n)) - (1 << 20)
    j, r = f >> 12, f & 0xFFF
    return (n << 16) + LT[j] + (((LT[j + 1] - LT[j]) * r) >> 12)


def logw():
    return _log2_q16(WHITE, lt())


def log_q16():
    """LOG[i] = log2(i/1918)(Q16);i = 0 → LOG0。與 launcher 開機時算的逐位元相同。"""
    LT, w = lt(), logw()
    return [LOG0] + [_log2_q16(i, LT) - w for i in range(1, N)]


def white():
    return round(OUT_MAX * (1 - LIFT / 255) / GAIN)


def _lsb(d):
    return OUT_MAX * (d - LIFT / 255) / GAIN


def samples(g):
    """取樣組 g:0..30 = GA 文件曲線(ISO 序號);31 = SA 共用曲線 709 OETF(2^y),y = S0 + j·0.1。"""
    import numpy as np
    s = S0 + np.arange(NS) * STEP
    if g == NTAB:
        d = np.clip(oetf709(np.power(2.0, s)), 0, 1)
    else:
        iso = ISO_STEPS[g]
        d = disp('lut709', s, w_of(iso)[0], l_of(iso)[0])
    return [int(v) for v in np.clip(np.round(_lsb(d)), 0, white())]


def sa_t(w, l, con):
    """SA 壓進 709 的檔數 T:對比 0 = 官方 W + L,對比 1 = 預覽看得到的 10.9 檔(rv_curves.disp_card)。"""
    return w + l if con == 0 else -LV_FLOOR


def _line(a, b):
    """顯示 D = a + b·s(s = 相對中灰檔數)→ (M Q8 LSB/檔, C LSB at x = 0),x = s − S0。"""
    m = OUT_MAX / GAIN * b
    return round(m * 256), round(_lsb(a + b * S0))


def rec(k):
    """(K Q16, A Q16, GRP, M, C, XK)。"""
    (mode, con), iso = SETS[k // NTAB], ISO_STEPS[k % NTAB]
    g = k % NTAB
    w, l = w_of(iso)[0], l_of(iso)[0]
    a = round((w - S0) * 65536)
    s1 = w + LV_FLOOR
    if mode == 'stops':                                           # SA:共用曲線,y = 相對削波檔數 × N709/T
        return (round(N709 / sa_t(w, l, con) * 65536), round(-S0 * 65536), NTAB, 0, 0, XK_NONE)
    if con == 1:
        return (65536, a, g, 0, 0, XK_NONE)
    sk = ga_toe(w)
    if sk <= s1:
        return (65536, a, g, 0, 0, XK_NONE)
    b = (DK - DMIN) / (sk - s1)
    return (65536, a, g, *_line(DMIN - b * s1, b), round((sk - S0) * 65536))


def coefs():
    """(REC[124], SAMP[32], B)。"""
    return [rec(k) for k in range(NREC)], [samples(g) for g in range(NTAB + 1)], white()


def table(k, LOG=None, REC=None, SAMP=None, B=None):
    """和 launcher 完全相同的整數運算。"""
    LOG = LOG or log_q16()
    if REC is None:
        REC, SAMP, B = coefs()
    kq, a, grp, m, c, xk = REC[k]
    out = []
    for lv in LOG:
        x = ((lv * kq) >> 16) + a
        if x < 0:
            out.append(0)
            continue
        v = -0x80000000
        if grp >= 0:
            y = SAMP[grp]
            t = x * 10
            j, f = t >> 16, t & 0xFFFF
            v = y[NS - 1] if j >= NS - 1 else y[j] + (((y[j + 1] - y[j]) * f) >> 16)
        if x < xk:
            v = max(v, c + ((m * x) >> 24))
        out.append(0 if v < 0 else B if v > B else v)
    return out


def table_addr_off(k):
    """表 k 相對 T0 的位置:前 62 張 k·0x1000,其餘接在常駐區(0x42000)之後。"""
    return (k if k < 62 else k + 4) * 0x1000


def thresholds():
    return [round(REL100 * 2 ** ((k + 0.5) / 3)) for k in range(NTAB - 1)]


def blob():
    REC, SAMP, B = coefs()
    return (struct.pack(f'<{NLT}I', *lt()) + struct.pack('<i', logw())
            + b''.join(struct.pack(f'<{RECW}i', *r) for r in REC) + struct.pack('<i', B)
            + struct.pack(f'<{NTAB - 1}I', *thresholds())
            + b''.join(struct.pack(f'<{NSP}H', *(y + [y[-1]] * (NSP - NS))) for y in SAMP))


def reference(k):
    """浮點參考(rv_curves.disp / disp_lv),四捨五入到表值;index 0 = 0。"""
    import numpy as np
    (mode, con), iso = SETS[k // NTAB], ISO_STEPS[k % NTAB]
    w, l = w_of(iso)[0], l_of(iso)[0]
    idx = np.arange(N, dtype=float)
    s = np.log2(np.maximum(idx / WHITE, 2.0 ** -32)) + w
    d = disp_card(mode, con, s, w, l)
    d[0] = 0
    return np.clip(np.round(_lsb(d)), 0, white()).astype(int)


def check():
    import numpy as np
    LOG = log_q16(); REC, SAMP, B = coefs()
    return max(int(np.abs(np.array(table(k, LOG, REC, SAMP, B)) - reference(k)).max()) for k in range(NREC))


if __name__ == '__main__':
    w = check()
    print(f'max |int − float| over {len(SETS) * NTAB} tables: {w} LSB   blob {len(blob())} bytes')
