"""lossless JPEG (SOF3) 編碼器。

預設照 0x300D 的實測輸出:2 個 component(CFA 偶/奇欄)、predictor 1、
Al=0、逐 tile 自適應 Huffman。predictor 2..7 只供主機端相容性與成本研究；
目前沒有證據說 0x300D 能切換它。
"""
import numpy as np

def _huff_lengths(freq):
    """JPEG Annex K 的碼長產生:保留全 1 碼點,長度上限 16。"""
    f = dict(freq)
    DUMMY = 256
    f[DUMMY] = 1                      # 保留一個碼點,避免全 1 碼
    syms = [s for s, c in f.items() if c > 0]
    if len(syms) == 1:
        return {syms[0]: 1}
    others = {s: 0 for s in syms}
    nodes = {s: f[s] for s in syms}
    children = {}
    nxt = 512
    while len(nodes) > 1:
        a = min(nodes, key=lambda k: (nodes[k], -k))
        va = nodes.pop(a)
        b = min(nodes, key=lambda k: (nodes[k], -k))
        vb = nodes.pop(b)
        children[nxt] = (a, b); nodes[nxt] = va + vb; nxt += 1
    root = next(iter(nodes))
    def walk(n, dep):
        if n in children:
            walk(children[n][0], dep + 1); walk(children[n][1], dep + 1)
        else:
            others[n] = dep
    walk(root, 0)
    lens = {s: l for s, l in others.items() if s != DUMMY}
    # 長度上限 16(JPEG 的標準調整程序)
    while max(lens.values(), default=0) > 16:
        bits = {}
        for s, l in lens.items(): bits.setdefault(l, []).append(s)
        L = max(bits)
        victim = bits[L].pop()
        j = L - 2
        while j > 0 and j not in bits: j -= 1
        partner = bits[j].pop()
        lens[victim] = j + 1; lens[partner] = j + 1
    return lens

def _canonical(lens):
    counts = [0] * 17
    for l in lens.values(): counts[l] += 1
    order = sorted(lens, key=lambda s: (lens[s], s))
    code = 0; codes = {}; k = 0
    for l in range(1, 17):
        for _ in range(counts[l]):
            codes[order[k]] = (l, code); code += 1; k += 1
        code <<= 1
    return counts[1:17], order, codes

class _BW:
    def __init__(self): self.out = bytearray(); self.acc = 0; self.n = 0
    def put(self, code, length):
        for i in range(length - 1, -1, -1):
            self.acc = (self.acc << 1) | ((code >> i) & 1); self.n += 1
            if self.n == 8:
                self.out.append(self.acc & 0xFF)
                if self.acc & 0xFF == 0xFF: self.out.append(0)
                self.acc = 0; self.n = 0
    def flush(self):
        while self.n: self.put(1, 1)
        return bytes(self.out)

def _diffs(comp, P, predictor=1):
    if predictor not in range(1, 8):
        raise ValueError("lossless JPEG predictor 必須是 1..7")
    c = comp.astype(np.int32)
    pred = np.empty_like(c)
    pred[0, 1:] = c[0, :-1]             # 第一列一律用 Ra
    pred[1:, 0] = c[:-1, 0]
    pred[0, 0] = 1 << (P - 1)
    if c.shape[0] > 1 and c.shape[1] > 1:
        ra = c[1:, :-1]
        rb = c[:-1, 1:]
        rc = c[:-1, :-1]
        interior = {
            1: ra,
            2: rb,
            3: rc,
            4: ra + rb - rc,
            5: ra + ((rb - rc) >> 1),
            6: rb + ((ra - rc) >> 1),
            7: (ra + rb) >> 1,
        }[predictor]
        pred[1:, 1:] = interior
    d = c - pred
    return ((d + 0x8000) & 0xFFFF) - 0x8000

def _ssss(d):
    a = np.abs(d).astype(np.int32)
    s = np.zeros_like(a); nz = a > 0
    s[nz] = np.floor(np.log2(a[nz])).astype(np.int32) + 1
    return s

def encode_tile(tile, P, predictor=1):
    """tile: (th, tw) uint16 CFA。回傳完整的 JPEG bitstream(SOI..EOI)。"""
    th, tw = tile.shape
    comps = [tile[:, c::2] for c in (0, 1)]
    D = [_diffs(c, P, predictor) for c in comps]
    S = [_ssss(d) for d in D]
    tables = []
    for s in S:
        u, cnt = np.unique(s, return_counts=True)
        lens = _huff_lengths(dict(zip(u.tolist(), cnt.tolist())))
        tables.append(_canonical(lens))
    out = bytearray(b'\xFF\xD8')
    out += b'\xFF\xC3' + (14).to_bytes(2, 'big') + bytes([P]) + \
           th.to_bytes(2, 'big') + (tw // 2).to_bytes(2, 'big') + b'\x02' + \
           b'\x00\x11\x00' + b'\x01\x11\x00'
    for i, (counts, order, codes) in enumerate(tables):
        body = bytes([i]) + bytes(counts) + bytes(order)
        out += b'\xFF\xC4' + (len(body) + 2).to_bytes(2, 'big') + body
    out += b'\xFF\xDA' + (10).to_bytes(2, 'big') + \
           b'\x02\x00\x00\x01\x10' + bytes([predictor, 0, 0])
    bw = _BW()
    codes0, codes1 = tables[0][2], tables[1][2]
    d0, d1 = D[0].tolist(), D[1].tolist()
    s0, s1 = S[0].tolist(), S[1].tolist()
    for y in range(th):
        r0, r1, t0, t1 = d0[y], d1[y], s0[y], s1[y]
        for x in range(tw // 2):
            for dv, sv, cd in ((r0[x], t0[x], codes0), (r1[x], t1[x], codes1)):
                l, c = cd[sv]; bw.put(c, l)
                if sv and sv != 16:
                    bw.put(dv if dv > 0 else dv + (1 << sv) - 1, sv)
    return bytes(out) + bw.flush() + b'\xFF\xD9'
