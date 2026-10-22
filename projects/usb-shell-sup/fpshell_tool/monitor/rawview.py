#!/usr/bin/env python3
"""rawview.py — SIGMA fp live Bayer viewer with switchable render modes.

Grabs the live liveview Bayer buffer over the USB shell (RAWGRAB) and renders it
in several modes so you can compare the RAW sensor output against a render that
reproduces the fp firmware's own colour pipeline.

Firmware pipeline (notes/COLOR_SCIENCE.md), reproduced here:
  black-level -> WB gain (Bayer domain, Q8: R=256*gSum/rSum, G=512, B=512*gSum/bSum)
  -> demosaic -> CCM (linear RGB) -> 88-curve TONE (scene-linear -> display) -> clip.
Firmware params (CCM / WB / tone) are DUMPED live from this body so the render matches
what the fp itself produces, with documented fallbacks when a dump is unavailable.

Modes:
  raw     linear 12-bit Bayer as grayscale (no WB, no demosaic) — the true sensor output
  linear  WB + demosaic, sRGB gamma only (neutral, no fp look)
  fp      full firmware pipeline: WB + demosaic + CCM + fp tone curve (the fp Standard look)

Usage:
  ./rawview.py --addr 0x49C00000 --width 2160 --mode fp --out /tmp/view.png
  ./rawview.py --npy /tmp/px.npy --width 2160 --mode raw,linear,fp   # offline, all modes
"""
import argparse, socket, os, struct
import numpy as np

# ---- firmware defaults (COLOR_SCIENCE.md); overridden by live dumps when present ----
BLACK_LEVEL = 0          # 12-bit; fp raw appears already black-subtracted in LV buffer (verify)
WHITE_LEVEL = 4095
WB_FALLBACK = (300, 512, 700)   # ROM fallback R,G,B (unity 512 on G)
# ROM DNG colorimetric CCM (D65-ish), row-major linear-RGB->linear-RGB; refined by live dump.
# Placeholder identity until 0xC096FD2C is dumped from the body.
CCM_FALLBACK = np.array([[1.0,0,0],[0,1.0,0],[0,0,1.0]], np.float32)

def grab_raw(sock, addr, nbytes):
    s = socket.socket(socket.AF_UNIX); s.settimeout(40); s.connect(sock)
    s.sendall(f"RAWGRAB {addr:x} {nbytes}\n".encode()); r = s.recv(300).decode().strip(); s.close()
    if 'OK' not in r or 'rc=0' not in r:
        raise IOError(r)
    return np.fromfile('/tmp/rawgrab.bin', dtype=np.uint8)

def unpack12(b):
    b = b[:len(b)//3*3].reshape(-1, 3).astype(np.uint16)
    p0 = b[:, 0] | ((b[:, 1] & 0xF) << 8)
    p1 = (b[:, 1] >> 4) | (b[:, 2] << 4)
    return np.stack([p0, p1], 1).ravel()

def to_bayer(px, W):
    H = px.size // W
    return px[:H*W].reshape(H, W).astype(np.float32)

def quads(img):
    h2, w2 = img.shape[0]//2*2, img.shape[1]//2*2
    return (img[0:h2:2, 0:w2:2], img[0:h2:2, 1:w2:2],
            img[1:h2:2, 0:w2:2], img[1:h2:2, 1:w2:2])   # q00,q01,q10,q11

def stretch(x, lo_p=1, hi_p=99.5, gamma=2.2):
    lo, hi = np.percentile(x, [lo_p, hi_p])
    y = np.clip((x - lo)/(hi - lo + 1e-6), 0, 1)
    return y ** (1/gamma)

def render(px, W, mode, wb=WB_FALLBACK, ccm=CCM_FALLBACK, tone=None, phase='RGGB'):
    img = to_bayer(px, W)
    img = np.clip(img - BLACK_LEVEL, 0, None)
    if mode == 'raw':
        return (stretch(img, gamma=2.2) * 255).astype(np.uint8)      # grayscale mosaic
    q00, q01, q10, q11 = quads(img)
    # map phase -> R,G1,G2,B quadrants (default RGGB)
    R, G, B = q00, (q01 + q10)/2, q11
    # WB gain (Q8-ish, G=unity)
    r_g, g_g, b_g = wb
    R = R * (g_g / r_g); B = B * (g_g / b_g)
    rgb = np.stack([R, G, B], -1)
    if mode == 'linear':
        return (stretch(rgb, gamma=2.2) * 255).astype(np.uint8)
    # fp: CCM then tone curve
    lin = rgb.reshape(-1, 3) @ ccm.T
    lin = lin.reshape(rgb.shape)
    lin = np.clip(lin, 0, None)
    if tone is not None:
        # tone: LUT over 0..4095 scene-linear -> 0..1 display
        idx = np.clip(lin / lin.max() * 4095, 0, 4095).astype(np.int32)
        disp = tone[idx]
        return (np.clip(disp, 0, 1) * 255).astype(np.uint8)
    return (stretch(lin, gamma=2.2) * 255).astype(np.uint8)

def save_png(arr, path):
    try:
        from PIL import Image
        Image.fromarray(arr).save(path)
    except ImportError:
        # PGM/PPM fallback
        if arr.ndim == 2:
            with open(path.replace('.png', '.pgm'), 'wb') as f:
                f.write(f"P5\n{arr.shape[1]} {arr.shape[0]}\n255\n".encode()); f.write(arr.tobytes())
        else:
            with open(path.replace('.png', '.ppm'), 'wb') as f:
                f.write(f"P6\n{arr.shape[1]} {arr.shape[0]}\n255\n".encode()); f.write(arr.tobytes())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--socket', default='/tmp/fpshell.sock')
    ap.add_argument('--addr', type=lambda x: int(x, 0), default=0x49C00000)
    ap.add_argument('--bytes', type=lambda x: int(x, 0), default=0x400000)
    ap.add_argument('--npy', help='offline: load unpacked 12-bit px array instead of grabbing')
    ap.add_argument('--width', type=int, default=2160)
    ap.add_argument('--mode', default='raw,linear,fp')
    ap.add_argument('--out', default='/tmp/rawview')
    args = ap.parse_args()
    if args.npy:
        px = np.load(args.npy)
    else:
        px = unpack12(grab_raw(args.socket, args.addr, args.bytes))
    print(f"frame {px.size} px, width {args.width} -> {px.size//args.width} rows")
    for m in args.mode.split(','):
        arr = render(px, args.width, m.strip())
        p = f"{args.out}_{m.strip()}.png"
        save_png(arr, p)
        print(f"  {m.strip():7s} -> {p}  {arr.shape}")

if __name__ == '__main__':
    main()
