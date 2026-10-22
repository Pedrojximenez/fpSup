#!/usr/bin/env python3
"""tile 幾何規劃 + 壓縮量估算 —— SIGMA fp 0x300D 無損 JPEG 引擎

用法:
    ./tileplan.py geom                     列出各格式的最佳 tile 幾何
    ./tileplan.py cost <DNG> [--predictor N] [tw th ...]
                                             估壓縮大小與最新實測引擎時間
    ./tileplan.py engine <DNG>             讀 Compression=7 檔案的引擎實際輸出比

引擎硬約束(FUN_c062fff8):tileW 32..512 且為 32 倍數;tileH 2..512 且為偶數。
TIFF 6.0 另要求 TileWidth/TileLength 為 16 的倍數 —— 預設只列標準相容解。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ljcost import load_uncompressed
from tilegeom import padded_cost

HDR = 78848        # CinemaDNG 每幀固定表頭(實測,frame+0x14C)
# 四個既有硬體測點的 least-squares fit；校準殘差 <= 1.7 us。
FIXED_US = 2179.0
PIXEL_US_PER_MPIX = 4954.40352197
TILE_US = 40.92647059
MIN_HEADER_GAP = 3326
IFD_BYTES = 2 + 59 * 12 + 4
MAX_TILES = (MIN_HEADER_GAP - IFD_BYTES) // 8

FORMATS = [("FHD",  1936, 1090),
           ("OG3K", 3024, 2010),
           ("UHD",  3840, 2160),
           ("6K",   6064, 4042)]

def engine_us(pixels, tiles):
    return FIXED_US + PIXEL_US_PER_MPIX * pixels / 1e6 + TILE_US * tiles

def legal_geoms(W, H, cap=MAX_TILES):
    out = []
    for tw in range(32, 513, 32):          # 引擎:32 的倍數
        for th in range(16, 513, 16):      # 引擎:偶數 / TIFF:16 的倍數
            c = -(-W // tw); r = -(-H // th)
            if c * r > cap: continue
            px = c * tw * r * th
            n = c * r
            out.append((engine_us(px, n), px, n, tw, th))
    out.sort()
    return out

def cmd_geom():
    print(f"{'format':<7}{'tile':>9}{'tiles':>6}{'pad Mpix':>10}{'pad%':>7}{'enc ms':>8}{'fps cap':>8}")
    for name, W, H in FORMATS:
        real = W * H
        seen = set()
        for us, px, n, tw, th in legal_geoms(W, H):
            if (px, n) in seen: continue
            seen.add((px, n))
            print(f"{name:<7}{f'{tw}x{th}':>9}{n:6d}{px/1e6:10.3f}"
                  f"{100*(px-real)/real:6.2f}%{us/1000:8.2f}{1e6/us:8.1f}")
            if len(seen) >= 2: break
        for tw, th in ((256, 256), (512, 512)):
            c = -(-W//tw); r = -(-H//th); px = c*tw*r*th
            us = engine_us(px, c*r)
            print(f"{'':<7}{f'[{tw}x{th}]':>9}{c*r:6d}{px/1e6:10.3f}"
                  f"{100*(px-real)/real:6.2f}%{us/1000:8.2f}{1e6/us:8.1f}")

def cmd_cost(path, geoms, predictor=1):
    img, W, H, bps = load_uncompressed(path)
    raw = HDR + W * H * bps // 8
    print(f"{os.path.basename(path)}  {W}x{H} {bps}-bit  未壓縮 {raw/1e6:.3f} MB/幀"
          f"  ({raw*23.976/1e6:.1f} MB/s @24, {raw*29.97/1e6:.1f} @30)")
    print(f"{'tile':>9}{'tiles':>6}{'pad Mpix':>10}{'file MB':>9}{'ratio':>7}"
          f"{'enc ms':>8}{'MB/s@24':>9}{'MB/s@30':>9}")
    for tw, th in geoms:
        b, n, px = padded_cost(img, bps, tw, th, predictor)
        f = HDR + b
        print(f"{f'{tw}x{th}':>9}{n:6d}{px/1e6:10.3f}{f/1e6:9.3f}{raw/f:7.3f}"
              f"{engine_us(px,n)/1000:8.2f}{f*23.976/1e6:9.1f}{f*29.97/1e6:9.1f}")

def cmd_engine(path):
    from tiff import parse, read_ifd
    d, e, end, ifds = parse(path)
    for so in ifds[0].get(330, (0,0,[]))[2]:
        st, _ = read_ifd(d, so, end)
        if st.get(259, (0,0,[0]))[2][0] != 7 or 324 not in st: continue
        W, H = st[256][2][0], st[257][2][0]
        bps = st[258][2][0]; tw, th = st[322][2][0], st[323][2][0]
        tb = st[325][2]
        px = (-(-W//tw)*tw) * (-(-H//th)*th)
        tot = sum(tb)
        aligned_raw = px * bps / 8
        active_raw = W * H * bps / 8
        print(f"{W}x{H} {bps}-bit  tile {tw}x{th}  {len(tb)} 個  "
              f"輸出 {tot/1e6:.2f} MB  對齊比 {aligned_raw/tot:.3f}:1  "
              f"有效樣本比 {active_raw/tot:.3f}:1")

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "geom":
        cmd_geom()
    elif sys.argv[1] == "cost":
        args = sys.argv[3:]
        predictor = 1
        if "--predictor" in args:
            i = args.index("--predictor")
            predictor = int(args[i+1])
            del args[i:i+2]
        g = [(int(args[i]), int(args[i+1])) for i in range(0, len(args), 2)]
        cmd_cost(sys.argv[2], g or [(256,256),(512,512)], predictor)
    elif sys.argv[1] == "engine":
        cmd_engine(sys.argv[2])
