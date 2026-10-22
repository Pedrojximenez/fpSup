#!/usr/bin/env python3
"""XCI 圖示的解碼與編碼。

格式(2026-09-14 由 xcitrace.S 追出來,三張樣本交叉驗證):

    +0x00  "XC\\0\\0"
    +0x04  u32  frame 總長 = block + 23
    +0x08  u16  寬
    +0x0A  u16  高
    +0x0C  u32  0x00000400
    +0x10  u16  0x0202
    +0x14  零到 +0x1F
    +0x20  04 22 4D 18        LZ4 frame magic
    +0x24  88 10              FLG / BD
    +0x26  u32  = block + 19  (其後 4 bytes 為零)
    +0x2E  00                 HC
    +0x2F  u32  block 長度
    +0x33  block 資料
    尾端   00 00 00 00        LZ4 EndMark

內容是 16bpp:每像素小端序 u16,低位元組 = 亮度,高位元組 = alpha。
原廠圖示是純白抗鋸齒,亮度 == alpha == 覆蓋率。

blob 總長 = 0x33 + block + 4。要就地覆寫必須不超過原本的空間。
"""
import struct

import numpy as np

HDR = 0x33
MAGIC = b'XC\x00\x00'


def decode(buf, off=0):
    """回傳 (寬, 高, L 陣列, A 陣列)。"""
    if buf[off:off + 4] != MAGIC:
        raise ValueError('不是 XCI')
    w, h = struct.unpack_from('<HH', buf, off + 8)
    blk = struct.unpack_from('<I', buf, off + 0x2F)[0] & 0x7FFFFFFF
    raw = _lz4_block(buf[off + HDR:off + HDR + blk])
    v = np.frombuffer(raw[:w * h * 2], dtype='<u2').reshape(h, w)
    return w, h, (v & 0xFF).astype(np.uint8), ((v >> 8) & 0xFF).astype(np.uint8)


def encode(L, A):
    """把亮度/alpha 兩張圖打包成一個完整的 XCI blob。"""
    import lz4.block
    h, w = L.shape
    v = (A.astype(np.uint16) << 8) | L.astype(np.uint16)
    raw = v.astype('<u2').tobytes()
    blk = lz4.block.compress(raw, store_size=False, mode='high_compression',
                             compression=12)
    out = bytearray(HDR)
    out[0:4] = MAGIC
    struct.pack_into('<I', out, 0x04, len(blk) + 23)
    struct.pack_into('<HH', out, 0x08, w, h)
    struct.pack_into('<I', out, 0x0C, 0x00000400)
    struct.pack_into('<H', out, 0x10, 0x0202)
    out[0x20:0x24] = b'\x04\x22\x4d\x18'
    out[0x24] = 0x88
    out[0x25] = 0x10
    struct.pack_into('<I', out, 0x26, len(blk) + 19)
    struct.pack_into('<I', out, 0x2F, len(blk))
    return bytes(out) + blk + b'\x00\x00\x00\x00'


def _lz4_block(src):
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        tok = src[i]
        i += 1
        ll = tok >> 4
        if ll == 15:
            while True:
                b = src[i]
                i += 1
                ll += b
                if b != 255:
                    break
        out += src[i:i + ll]
        i += ll
        if i + 2 > n:
            break
        off = src[i] | (src[i + 1] << 8)
        i += 2
        if off == 0:
            break
        ml = tok & 0xF
        if ml == 15:
            while True:
                b = src[i]
                i += 1
                ml += b
                if b != 255:
                    break
        ml += 4
        st = len(out) - off
        for k in range(ml):
            out.append(out[st + k])
    return bytes(out)


def text_tile(text, w=86, h=49, cap=24, font=None, index=0, ss=8,
              lo=0.30, hi=0.68):
    """照原廠圖塊的樣子排一行字:純白抗鋸齒、垂直置中、左右置中。

    原廠 UHD 量到的是 86x49、大寫高 26px、墨水框 x[11..75] y[12..37]。
    四個字母要塞下就得矮一點,cap 預設 24。
    """
    from PIL import Image, ImageDraw, ImageFont
    font = font or '/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf'
    maxw = w - 12
    for size in range(70, 8, -1):
        f = ImageFont.truetype(font, size * ss, index=index)
        big = Image.new('L', (w * ss, h * ss), 0)
        ImageDraw.Draw(big).text((w * ss // 2, h * ss // 2), text,
                                 font=f, fill=255, anchor='mm')
        a = np.array(big)
        ys, xs = np.where(a > 30)
        if not len(xs):
            continue
        if (ys.max() - ys.min() + 1) / ss <= cap and (xs.max() - xs.min() + 1) / ss <= maxw:
            small = np.array(big.resize((w, h), Image.LANCZOS)).astype(np.float32) / 255
            # 原廠的邊只有很薄一圈半透明(6.8% 的像素),LANCZOS 直接降取樣
            # 會糊成 17%。收緊過渡帶讓邊緣銳利到和原廠同一個調性。
            small = np.clip((small - lo) / (hi - lo), 0, 1)
            small = (small * 255 + 0.5).astype(np.uint8)
            # 置中到與原廠相同的墨水框位置
            ys, xs = np.where(small > 10)
            dy = (h - (ys.max() - ys.min() + 1)) // 2 - ys.min()
            dx = (w - (xs.max() - xs.min() + 1)) // 2 - xs.min()
            small = np.roll(np.roll(small, dy, axis=0), dx, axis=1)
            return small, small          # L == A,和原廠一樣
    raise ValueError('排不下')
