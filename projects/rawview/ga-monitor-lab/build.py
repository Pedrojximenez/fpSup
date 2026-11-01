#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""GA Monitor Lab: reproduce the pinned offline 2026-11-01 experiments.

No card access, firmware flashing, automatic downloads or production-builder
changes. User-supplied baseline and licensed LUT remain local. See README.md.
"""
import argparse
import hashlib
import math
from pathlib import Path
import json
import struct
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / 'fpSup/fp_usb_shell'))

BASE_SHA = '701532fe8bcb2a7c374b891bff83f80105d36b579b5c1dc95fc4130cfddcf71c'
LUT_SHA = '241aff344709aa90b468f8658144888db38f29f9aa1b3c0d917cf327ca3b354e'
EXPECTED = {
    'log-only': 'c307f07c393fa20dfbba26bccd49b52059eb6375cca69e1e64a75942cc5a11d2',
    'arri-reference': '81430080e7ebaef36186f80f0389032e7dddbd6c052ca91ed667339bcf1d7e52',
    'combined': 'a5402bd5ecdbdfac77871f4db6250dc084c37ee393fa6743f23e779d11717160',
    'shadowlift2': 'e6ea96b59823f86cdf1e57c51fad1d75e86a40486a7afbf16114133ba46f4c9b',
}
ROW_BASE, ROW_END, STRIDE, REC_BASE = 0x3AD0, 0x5E2C, 292, 0x2EB4
GRAY, LIMIT, FLOOR, GAIN, SCALE = 2921, 8170, 16.9 / 255, .936, 8190


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pinned(data, expected, label):
    if sha(data) != expected:
        raise ValueError(label + ' SHA256 mismatch')


def logc3(scene):
    """LogC3 exposure encoding, EI800; scene gray=0.18, not LogC4."""
    if scene > .010591:
        return .247190 * math.log10(5.555556 * scene + .052272) + .385537
    return 5.367655 * scene + .092809


def encode(signal):
    return max(0, min(LIMIT, round(SCALE * (signal - FLOOR) / GAIN)))


def decode(code):
    """Model display signal; not a measured LCD luminance/IRE value."""
    return FLOOR + GAIN * code / SCALE


def neutral_axis(data):
    pinned(data, LUT_SHA, 'Official user-supplied cube')
    lines = data.decode('ascii').splitlines()
    if lines[0] != 'LUT_3D_SIZE 33':
        raise ValueError('Expected published full-domain 33-point cube')
    cube = [tuple(map(float, line.split())) for line in lines[1:] if line.strip()]
    if len(cube) != 33**3 or not all(len(v) == 3 and all(math.isfinite(c) and 0 <= c <= 1 for c in v) for v in cube):
        raise ValueError('Invalid cube')
    values = [sum(cube[(i*33+i)*33+i])/3 for i in range(33)]
    if any(a > b for a, b in zip(values, values[1:])):
        raise ValueError('Non-monotone neutral axis')
    return values


def interpolate(values, x):
    if not math.isfinite(x) or not 0 <= x <= 1:
        raise ValueError('Input outside [0,1]')
    p = x * (len(values)-1)
    i = min(int(p), len(values)-2)
    return values[i] + (values[i+1]-values[i]) * (p-i)


def lift1(code):
    if code >= GRAY:
        return code
    t = code / GRAY
    return code + 16*112*t*t*(1-t)*(1-t)


def lift2(code):
    if not math.isfinite(code) or not 0 <= code <= LIMIT:
        raise ValueError('Code outside [0,8170]')
    if code >= GRAY:
        return code
    t = code / GRAY
    return code + 350*(256/27)*t*(1-t)**3


def rewrite_rows(data, transform):
    output = bytearray(data)
    for i in range(31):
        row = struct.unpack_from('<146H', data, ROW_BASE+i*STRIDE)
        values = [round(transform(c)) for c in row]
        if any(not 0 <= c <= LIMIT for c in values):
            raise ValueError('Tone transform escaped range')
        struct.pack_into('<146H', output, ROW_BASE+i*STRIDE, *values)
    return bytes(output)


def set_rows(data, values):
    output = bytearray(data)
    for i in range(31):
        struct.pack_into('<146H', output, ROW_BASE+i*STRIDE, *values)
    return bytes(output)


def preview_tables(data):
    weights, amount = (.2126, .7152, .0722), 1.03
    saturation = [[amount*(i == j)+(1-amount)*weights[j] for j in range(3)] for i in range(3)]
    output = bytearray()
    for level in range(2):
        rec = struct.unpack_from('<I9hH', data, 0x1374+level*24)
        if rec[0] != 0x24:
            raise ValueError('Unexpected preview table')
        rr, rg, rb, gg, gr, gb, bb, br, bg = rec[1:10]
        original = [[rr, rg, rb], [gr, gg, gb], [br, bg, bb]]
        result = []
        for i in range(3):
            row = [round(sum(saturation[i][k]*original[k][j] for k in range(3))) for j in range(3)]
            row[i] += 512-sum(row)
            result.append(row)
        rr, rg, rb = result[0]
        gr, gg, gb = result[1]
        br, bg, bb = result[2]
        output += struct.pack('<I9hH', 0x24, rr, rg, rb, gg, gr, gb, bb, br, bg, 0)
    return bytes(output)


def movw(register, immediate):
    if not 0 <= immediate <= 65535:
        raise ValueError('MOVW immediate out of range')
    return 0xE3000000 | register << 12 | (immediate & 0xF000) << 4 | immediate & 0xFFF


def add_preview(data):
    # Reuse the repository assembler; no duplicate loader or ARM toolchain.
    import armasm
    helper = armasm.assemble(HERE / 'preview_color.S')
    symbols = armasm.symbols(HERE / 'preview_color.S')
    if len(data) != 38644 or symbols['preview_color'] != 0 or symbols['preview_tables'] != len(helper) or len(helper) != 84:
        raise ValueError('Unexpected pinned layout')
    if struct.unpack_from('<I', data, 0x4EC)[0] != movw(1, len(data)):
        raise ValueError('Unexpected scratch offset instruction')
    if data[0x1658:0x1660] != struct.pack('<II', 0xE3A00001, 0xE59FC994):
        raise ValueError('Inactive branch landing differs')
    output = bytearray(data + helper + preview_tables(data))
    struct.pack_into('<I', output, 8, len(output))
    struct.pack_into('<I', output, 0x4EC, movw(1, len(output)))
    struct.pack_into('<III', output, 0x1620, 0xE59341CC, movw(12, len(data)), 0xE084F00C)
    block = struct.unpack_from('<I', output, 12)[0]
    for low in range(0, 4096, 4):
        scratch = (low+len(output)+4095) & ~4095
        if scratch < low+len(output) or scratch+0x82000 > low+block:
            raise ValueError('Helper/scratch allocation overlap')
    if output[0x1374:0x1554] != data[0x1374:0x1554] or output[0x165C:0x1660] != data[0x165C:0x1660]:
        raise ValueError('Original SAT/DNG data or inactive branch changed')
    return bytes(output)


def build_all(original, cube):
    pinned(original, BASE_SHA, 'Original v0.3.0 RAWV')
    data = bytearray(original)
    # Exact known-good diagnostic settings: RAW On, SA. Later stages use GA.
    struct.pack_into('<7I', data, 36, 1, 0, 0, 0, 0, 0, 0)
    for i in range(31):
        struct.pack_into('<iii', data, REC_BASE+(31+i)*24+12, 0, 0, -0x80000000)
    data = set_rows(data, [encode(logc3(.18*2**(i/10-8))) for i in range(146)])
    products = {'log-only': data}
    axis = neutral_axis(cube)
    gray = interpolate(axis, logc3(.18))
    row = []
    for i in range(146):
        y = interpolate(axis, logc3(.18*2**(i/10-8)))
        row.append(encode(y + FLOOR*(1-y)*(1-y/gray)))
    data = bytearray(set_rows(data, row))
    struct.pack_into('<I', data, 40, 1)  # Exact saved GA selection of good control.
    data = bytes(data)
    products['arri-reference'] = data
    combined = add_preview(rewrite_rows(data, lift1))
    products['combined'] = combined
    products['shadowlift2'] = rewrite_rows(combined, lift2)
    for name, payload in products.items():
        pinned(payload, EXPECTED[name], name)
    return products


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original', type=Path, required=True)
    parser.add_argument('--cube', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True, help='New local directory, never a mounted volume')
    args = parser.parse_args()
    target = args.out.resolve()
    if target == Path('/Volumes') or Path('/Volumes') in target.parents or target == REPO or REPO in target.parents:
        raise SystemExit('Output must be outside the repository and /Volumes')
    products = build_all(args.original.read_bytes(), args.cube.read_bytes())
    target.mkdir(parents=True, exist_ok=False)
    for name, payload in products.items():
        folder = target / name
        folder.mkdir()
        (folder / '45RAWV.BIN').write_bytes(payload)
    report = {'name': 'GA Monitor Lab', 'source_only_experiment': True,
              'hardware_success_claimed': False, 'card_written': False,
              'products': {k: {'bytes': len(v), 'sha256': sha(v)} for k, v in products.items()}}
    (target / 'build-receipt.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
