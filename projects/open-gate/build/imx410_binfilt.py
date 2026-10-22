"""CRCT x3 binning kernels per axis + record mode (imx410_binfilt.S)."""
from pathlib import Path
import struct
from armasm import assemble

B = 0xC0000000
BINFILT = 0xC0731CB0            # bits 0-3 H kernel, 4-7 V kernel (KERNELS), bit 8 record 1; sl_modes.c
SITES = ((0xC032DDF0, 0xC0635DB0, 0xC0735600), (0xC032DE70, 0xC0635DC8, 0xC0735800))   # (site, writer, code: source-only)
# (name, horizontal /64, vertical /4096), in sl_modes.c's order
KERNELS = (("1,1,1", (21, 22, 21), (1365, 1366, 1365)),
           ("1,2,1", (16, 32, 16), (1024, 2048, 1024)),      # stock record 0's own
           ("1,4,1", (11, 42, 11), (683, 2730, 683)),
           ("1,6,1", (8, 48, 8), (512, 3072, 512)),
           ("1,14,1", (4, 56, 4), (256, 3584, 256)),        # stock record 1's own
           ("0,1,0", (0, 64, 0), (0, 4096, 0)))


def _blx_target(word, site):
    if word >> 25 != 0x7D:      # 1111 101H
        return None
    off = (word & 0xFFFFFF) << 2 | ((word >> 24) & 1) << 1
    off -= 1 << 26 if off & (1 << 25) else 0
    return site + 8 + off


def check(img):
    for site, target, _ in SITES:
        w = struct.unpack_from('<I', img, site - B)[0]
        if _blx_target(w, site) != target:
            raise ValueError(f'CRCT writer call {site:#x} is not the stock blx {target:#x}')


def payloads():
    src = str(Path(__file__).with_suffix('.S'))
    return [(f'imx410_binfilt_{i}', src, code) for i, (_, _, code) in enumerate(SITES, 1)]


def defines(flag, axis):
    return {f'imx410_binfilt_{i}': [f'FLAG={flag:#x}', f'AXIS={axis:#x}', f'BINFILT={BINFILT:#x}',
                                     f'TARGET={target:#x}']
            for i, (_, target, _) in enumerate(SITES, 1)}


def hooks():
    return [(site, code, "bl", f"CRCT x3 縮減核(逐軸) -> {target:#x}") for site, target, code in SITES]
