#!/usr/bin/env python3
"""Build the guarded, transient IMX410 A/B v10 clone; no camera I/O at import.

Only the four stock gain-byte calls are redirected. All other instructions
and stock calls retain their semantics. The native v10 is not overwritten.
This file currently provides offline build functions; it is not a live runner.
"""
from pathlib import Path
import hashlib
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
SHELL = ROOT / 'fpSup/fp_usb_shell'
sys.path.insert(0, str(SHELL))
from armasm import assemble, symbols

ORIGINAL = 0xC0323818
END = 0xC03239B8
SLOT = 0xC0B5FCF0
WRITER = 0xC0322C70
SUPPRESS = 0xC03258B0
GAIN_SITES = (0xC0323978, 0xC0323988, 0xC0323994, 0xC03239A4)
HELPER = SHELL / 'asm/imx410_ab_gain.S'
FIRMWARE = ROOT / 'out/MAIN_c0000000.bin'
FIRMWARE_SHA256 = '92a8ee993f6c3d66c251e88d45a2ccd5135c6cf7342717784321c2ed506e2fb4'


def branch_target(address, word):
    disp = word & 0xFFFFFF
    if disp & 0x800000:
        disp -= 0x1000000
    return (address + 8 + 4 * disp) & 0xFFFFFFFF


def arm_bl(address, target):
    disp = target - address - 8
    if disp & 3 or not -(1 << 25) <= disp < (1 << 25):
        raise ValueError('ARM BL target outside aligned +/-32 MiB range')
    return 0xEB000000 | ((disp >> 2) & 0xFFFFFF)


def stock_code():
    image = FIRMWARE.read_bytes()
    digest = hashlib.sha256(image).hexdigest()
    if digest != FIRMWARE_SHA256:
        raise ValueError(f'firmware hash mismatch: {digest}')
    code = image[ORIGINAL - 0xC0000000:END - 0xC0000000]
    if len(code) != END-ORIGINAL:
        raise ValueError('short v10 image')
    for site in GAIN_SITES:
        word = struct.unpack_from('<I', code, site-ORIGINAL)[0]
        if word >> 24 != 0xEB or branch_target(site, word) != WRITER:
            raise ValueError('unexpected stock gain call')
    if struct.unpack_from('<I', code, len(code)-4)[0] != 0xE8BD8010:
        raise ValueError('unexpected v10 return')
    return code


def build(address):
    if address & 7 or not 0xC072E064 <= address < 0xC072EFB4:
        raise ValueError('probe requires an aligned named cave claim')
    code = bytearray(stock_code())
    helper = assemble(HELPER)
    sym = symbols(HELPER)
    helper_address = address + len(code)
    redirected = []
    for off in range(0, len(code), 4):
        word = struct.unpack_from('<I', code, off)[0]
        # The known image contains no PC-relative literals/ADR in v10.
        # Capstone-independent guards restrict external relocations to BL.
        if word >> 24 == 0xEB:
            target = branch_target(ORIGINAL+off, word)
            if ORIGINAL+off in GAIN_SITES:
                if target != WRITER:
                    raise ValueError('gain target changed')
                target = helper_address + sym['entry']
                redirected.append(off)
            elif target not in (WRITER, SUPPRESS):
                raise ValueError('unreviewed external call')
            struct.pack_into('<I', code, off, arm_bl(address+off, target))
    if len(redirected) != 4:
        raise ValueError('did not redirect exactly four gain writes')
    blob = bytes(code) + helper
    if address+len(blob) > 0xC072EFB4:
        raise ValueError('probe exceeds claimed arena')
    return blob, dict(address=address, size=len(blob), slot=SLOT, original=ORIGINAL,
                      state=helper_address+sym['state'], state_size=48,
                      helper=helper_address, redirected_offsets=redirected,
                      sha256=hashlib.sha256(blob).hexdigest(),
                      firmware_sha256=FIRMWARE_SHA256)


def config(a, b):
    if not all(type(v) is int and 0 <= v < 0xDFD for v in (a, b)):
        raise ValueError('gain codes must stay below the high-analog threshold')
    return 0x80000000 | a | (b << 12)
