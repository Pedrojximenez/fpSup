"""Diagnostic CRCT path-selector logger (imx410_sellog.S); source-only coordinates."""
from pathlib import Path
import struct
from armasm import assemble

SITE, STOCK = 0xC0325228, 0xE92D00F0       # push {r4, r5, r6, r7}
CODE = 0xC0735000
LOG = 0xC0735100                            # +0 count, 8 slots x 0x90
LOG_BYTES = 0x10 + 8 * 0x90
FIX_MAIN_HBIN = True


def payloads():
    return [('imx410_sellog', str(Path(__file__).with_suffix('.S')), CODE)]


def defines(binfilt=False):
    # FLAG: also set the main pipeline hbin to 1 on branch C (Hbin2 bins horizontally)
    return {'imx410_sellog': [f'LOG={LOG:#x}'] + (['FLAG=0xc0731c08'] + (['BINFILT=0xc0731cb0'] if binfilt else []) if FIX_MAIN_HBIN else [])}


def check(img):
    if struct.unpack_from('<I', img, SITE - 0xC0000000)[0] != STOCK:
        raise ValueError('path selector C0325228 is not the stock push')
