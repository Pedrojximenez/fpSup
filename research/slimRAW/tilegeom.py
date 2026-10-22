import numpy as np
from ljcost import tile_cost

def pad_image(img, tw, th):
    """引擎的補滿方式(由 _SDI0011 的邊緣 tile 解出):對補滿樣本一律送 diff=0。
    解碼後的效果 = 水平複製最後一組 CFA 欄對;垂直則整列塌成上一列的首組值。
    兩者的殘差都是 0,所以補滿樣本只花 SSSS=0 的碼長(約 1 bit),不是全價。"""
    H, W = img.shape
    cols = -(-W // tw); rows = -(-H // th)
    padW = cols * tw; padH = rows * th
    out = np.zeros((padH, padW), img.dtype)
    out[:H, :W] = img
    if padW > W:                                   # 水平:複製最後一組同相位欄對
        k = -(-(padW - W) // 2)
        out[:H, W:] = np.tile(img[:, -2:], (1, k))[:, :padW - W]
    if padH > H:                                   # 垂直:整列 = 上一列首組值
        a, b = out[H-1, 0], out[H-1, 1]
        row = np.empty(padW, img.dtype); row[0::2] = a; row[1::2] = b
        out[H:, :] = row
    return out, cols * rows, padW * padH

def padded_cost(img, P, tw, th, predictor=1):
    pad, n, px = pad_image(img, tw, th)
    H, W = pad.shape
    tot = 0
    for y in range(0, H, th):
        for x in range(0, W, tw):
            tot += tile_cost(pad[y:y+th, x:x+tw], P, predictor)
    return tot, n, px
