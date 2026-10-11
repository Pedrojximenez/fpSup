#!/usr/bin/env python3
"""fp 監看 tone 曲線:產生、驗證、與 ROM 原曲線比對。

格式(由 Ver.5.02 ROM 量出):
  索引表  0xC0971118   88 筆 × 8 bytes = {uint32 ptr, uint32 id}，ptr 間距 4096
  曲線庫  0xC0971F34   88 條 × 4096 bytes
  每條    2048 點 × uint16 little-endian
  定義域  index 0..2047（11-bit 亮度輸入）
  值域    0..8191（77 條上限 8190、11 條 8190→8191，兩者都是原廠值）
  約束    非遞減

  ⚠ slot 與 id 差 1：索引表第 N 筆（slot N）的 id 欄位是 N+1。
     colour mode "Off" 用的是 **slot 82 / id 83** @ 0xC09C3F34。
     本腳本一律用 **slot**（0..87）；要用 id 請自行減 1。

  88 = 8 家族 × 11 對比階，slot = family*11 + (contrast+5)。
  原廠各家族的硬切點不同：
     family 0-3 (slot  0-43)  到頂 index 1919
     family 4   (slot 44-54)  到頂 index 2047  ← 完全不硬切，max 8191
     family 5   (slot 55-65)  到頂 index 1919
     family 6   (slot 66-76)  到頂 index 1873 / 1875
     family 7   (slot 77-87)  到頂 index 1918  ← Off 所在家族

子命令:
  dump   <slot>                    從 ROM 取出原曲線 → .bin + .csv（slot 0..87，Off 是 82）
  make   --shape <名稱>            產生一條曲線 → .bin
  from1d <file.cube|csv>           把 1D LUT 重採樣成本格式
  check  <file.bin>                驗證格式與約束
  diff   <a.bin> <b.bin>           比較兩條曲線

⚠ 本腳本只產生/驗證「曲線資料」。怎麼把它換進相機是另一件事（見 README 的安全切換協議）。
"""
import argparse, os, re, struct, sys
import numpy as np

ROM = '/Users/dido/Developer.localized/SIGMAfp_re/out/MAIN_c0000000.bin'
BASE = 0xC0000000
IDX_TABLE = 0xC0971118
N_CURVES = 88
POINTS = 2048
OUT_MAX = 8191          # 原廠有 11 條用到 8191；產生新曲線建議停在 8190
CURVE_BYTES = POINTS * 2


def rom_index():
    d = open(ROM, 'rb').read()
    out = []
    for i in range(N_CURVES):
        o = IDX_TABLE - BASE + i * 8
        ptr, cid = struct.unpack('<II', d[o:o + 8])
        out.append((ptr, cid))
    return d, out


def rom_curve(slot):
    """slot 是 0..87（索引表筆序）。id 欄位 = slot + 1。"""
    if not 0 <= slot < N_CURVES:
        raise SystemExit('slot %d 超出範圍 0..%d' % (slot, N_CURVES - 1))
    d, idx = rom_index()
    ptr, cid = idx[slot]
    o = ptr - BASE
    return ptr, cid, np.frombuffer(d[o:o + CURVE_BYTES], dtype='<u2').copy()


def describe(slot):
    return 'slot %d（id %d，family %d，對比階 %+d）' % (slot, slot + 1, slot // 11, slot % 11 - 5)


def check(cur, label=''):
    errs, warns = [], []
    if len(cur) != POINTS: errs.append('點數 %d,應為 %d' % (len(cur), POINTS))
    if cur.max() > OUT_MAX: errs.append('最大值 %d 超過 %d' % (cur.max(), OUT_MAX))
    if cur.max() > 8190: warns.append('最大值 %d：原廠只有 family 4 用到 8191，其餘都停在 8190' % cur.max())
    if cur.min() < 0: errs.append('有負值')
    if np.any(np.diff(cur.astype(int)) < 0): errs.append('非遞減約束被破壞')
    if cur[0] != 0: warns.append('起點不是 0（原廠都是 0）')
    top = int(np.argmax(cur >= cur.max()))
    if cur.max() < 5000: warns.append('最大值只有 %d —— log 型曲線正常（fpLog 是 4730）,一般監看曲線則偏暗' % cur.max())
    return errs, warns, top


SHAPES = {
    'identity':  lambda x: x,
    'linear':    lambda x: x,
    'gamma22':   lambda x: x ** (1 / 2.2),
    'log':       lambda x: np.log1p(x * 63) / np.log(64),          # 類 log 監看，高光壓縮
    'log-soft':  lambda x: np.log1p(x * 15) / np.log(16),
}


def make(shape, headroom):
    """headroom：把輸入的頂端保留多少比例不被壓到最大值（0 = 用滿）"""
    x = np.linspace(0, 1, POINTS)
    y = SHAPES[shape](x)
    y = y / y.max()
    top = OUT_MAX * (1.0 - headroom)
    cur = np.round(y * top).astype(np.int64)
    cur = np.maximum.accumulate(cur)
    return np.clip(cur, 0, OUT_MAX).astype('<u2')


def read_1d(path):
    vals = []
    n = None
    for line in open(path, encoding='utf-8', errors='replace'):
        s = line.strip()
        if not s or s.startswith('#'): continue
        if s.upper().startswith('LUT_1D_SIZE'): n = int(s.split()[-1]); continue
        if s.upper().startswith('LUT_3D_SIZE'):
            raise SystemExit('這是 3D LUT。fp 沒有 3D 引擎,請用 cube2fp.py')
        p = s.replace(',', ' ').split()
        if p and re.match(r'^[-\d.]', p[0]):
            vals.append(float(p[0]) if len(p) == 1 else float(np.mean([float(v) for v in p[:3]])))
    if not vals: raise SystemExit('讀不到資料')
    return np.array(vals)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    d = sub.add_parser('dump');   d.add_argument('slot', type=int, help='0..87（不是 id；Off 是 82）')
    d.add_argument('-o', default=None)
    m = sub.add_parser('make');   m.add_argument('--shape', choices=SHAPES, default='log')
    m.add_argument('--headroom', type=float, default=0.0); m.add_argument('-o', required=True)
    f = sub.add_parser('from1d'); f.add_argument('file'); f.add_argument('-o', required=True)
    c = sub.add_parser('check');  c.add_argument('file')
    df = sub.add_parser('diff');  df.add_argument('a'); df.add_argument('b')
    a = ap.parse_args()

    if a.cmd == 'dump':
        ptr, cid, cur = rom_curve(a.slot)
        o = a.o or 'curve_slot%02d.bin' % a.slot
        open(o, 'wb').write(cur.tobytes())
        with open(os.path.splitext(o)[0] + '.csv', 'w') as fh:
            fh.write('index,value\n')
            for i, v in enumerate(cur): fh.write('%d,%d\n' % (i, v))
        errs, warns, top = check(cur)
        print('%s @0x%08X → %s（%d bytes）' % (describe(a.slot), ptr, o, CURVE_BYTES))
        print('  min %d  max %d  到頂 index %d（%.1f%%）' % (cur.min(), cur.max(), top, 100 * top / (POINTS - 1)))

    elif a.cmd == 'make':
        cur = make(a.shape, a.headroom)
        open(a.o, 'wb').write(cur.tobytes())
        errs, warns, top = check(cur)
        print('shape=%s headroom=%.2f → %s' % (a.shape, a.headroom, a.o))
        print('  max %d  到頂 index %d（%.1f%%）  取樣 %s'
              % (cur.max(), top, 100 * top / (POINTS - 1),
                 [(i, int(cur[i])) for i in (0, 256, 1024, 1919, 2047)]))
        for e in errs: print('  ✗ ' + e)
        for w in warns: print('  ⚠ ' + w)

    elif a.cmd == 'from1d':
        v = read_1d(a.file)
        x = np.linspace(0, 1, len(v))
        y = np.interp(np.linspace(0, 1, POINTS), x, v)
        y = np.maximum.accumulate(y)
        cur = np.clip(np.round(y / max(y.max(), 1e-9) * OUT_MAX), 0, OUT_MAX).astype('<u2')
        open(a.o, 'wb').write(cur.tobytes())
        print('%s（%d 點）→ %s  max %d' % (a.file, len(v), a.o, cur.max()))

    elif a.cmd == 'check':
        raw = open(a.file, 'rb').read()
        if len(raw) != CURVE_BYTES: raise SystemExit('大小 %d,應為 %d' % (len(raw), CURVE_BYTES))
        cur = np.frombuffer(raw, dtype='<u2')
        errs, warns, top = check(cur)
        print('%s  min %d max %d  到頂 index %d（%.1f%%）'
              % (a.file, cur.min(), cur.max(), top, 100 * top / (POINTS - 1)))
        for e in errs: print('  ✗ ' + e)
        for w in warns: print('  ⚠ ' + w)
        print('  ' + ('通過' if not errs else '不合格 —— 不要寫進相機'))
        sys.exit(1 if errs else 0)

    elif a.cmd == 'diff':
        A = np.frombuffer(open(a.a, 'rb').read(), dtype='<u2').astype(int)
        B = np.frombuffer(open(a.b, 'rb').read(), dtype='<u2').astype(int)
        dd = B - A
        print('最大差 %d  平均絕對差 %.1f  相同=%s' % (np.abs(dd).max(), np.abs(dd).mean(), np.array_equal(A, B)))
        for i in (0, 256, 512, 1024, 1536, 1919, 2047):
            print('   index %4d: %5d → %5d  (%+d)' % (i, A[i], B[i], dd[i]))


if __name__ == '__main__':
    main()
