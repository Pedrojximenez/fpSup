#!/usr/bin/env python3
"""All per-mode tables of the IMX410 driver (TIM, META, R10, R28, R38, R14, R68) for the 70 modes, and which mode
attributes determine each 16-bit field (the same method as mode_deps.py for the sensor registers).

    mode_tables.py            -> offline/mode_tables.csv (one row per mode, one column per 16-bit field)
                                 and a dependency report on stdout
Attributes come from the geometry record (imx410_mode_geometry.csv: width, height, f44 h-bin, f48 v-add, f50 v-bin,
f60 readout class ...) and the timing (HMAX, VMAX, bit depth).
"""
import csv, itertools, pathlib, struct
A = pathlib.Path(__file__).resolve().parents[3] / 'research' / 'imx410' / 'analysis'
IMG = pathlib.Path(__file__).resolve().parents[3] / 'out' / 'MAIN_c0000000.bin'
img = IMG.read_bytes(); B = 0xC0000000
T = {'TIM': (0xC0B59500, 0x20, 0), 'META': (0xC0B59DC0, 100, 0), 'R10': (0xC0B5B918, 8, 1), 'R28': (0xC0B5BB48, 0x28, 0),
     'R38': (0xC0B5C638, 0x38, 0), 'R14': (0xC0B5D588, 0x14, 0), 'R68': (0xC0B5DB00, 0x68, 0)}
rows = {}
for name, (base, st, key) in T.items():
    for i in range(70):
        w = struct.unpack_from(f'<{st // 2}H', img, base - B + i * st)
        mode = struct.unpack_from('<I', img, base - B + i * st + 4 * key)[0]
        rows.setdefault(mode, {})
        for k, h in enumerate(w):
            if name == 'R10' and k >= 2 or name != 'R10' and k < 2:
                continue                                              # skip the mode id word
            rows[mode][f'{name}+{2 * k:02X}'] = h
geo = {int(r['mode_id']): r for r in csv.DictReader(open(A / 'imx410_mode_geometry.csv'))}
tim = {int(r['mode_id']): r for r in csv.DictReader(open(A / 'imx410_timing.csv'))}
NAMES = {'field_0x04': 'width', 'field_0x08': 'height', 'field_0x44': 'hbin', 'field_0x48': 'vadd', 'field_0x4c': 'f4c',
         'field_0x50': 'vbin', 'field_0x54': 'f54', 'field_0x5c': 'f5c', 'field_0x60': 'cls'}
attrs = {m: {**{n: int(geo[m][f]) for f, n in NAMES.items()}, 'hmax': int(tim[m]['hmax_cycles']),
             'vmax': int(tim[m]['vmax_lines']), 'bits': int(tim[m]['raw_bit_depth'])} for m in rows if m in geo}
modes = sorted(attrs)
cols = sorted({c for m in modes for c in rows[m]})
with open(pathlib.Path(__file__).with_name('mode_tables.csv'), 'w', newline='') as f:
    w = csv.writer(f); w.writerow(['mode'] + list(attrs[modes[0]]) + cols)
    for m in modes:
        w.writerow([m] + list(attrs[m].values()) + [rows[m].get(c, '') for c in cols])
an = list(attrs[modes[0]])
def det(keys, col):
    seen = {}
    for m in modes:
        k = tuple(attrs[m][x] for x in keys)
        if seen.setdefault(k, rows[m][col]) != rows[m][col]:
            return False
    return True
for col in cols:
    vals = sorted({rows[m][col] for m in modes})
    if len(vals) == 1:
        continue
    found = next((ks for n in (1, 2) for ks in itertools.combinations(an, n) if det(ks, col)), None)
    print(f'{col:8s} {len(vals):3d} values  <- {"+".join(found) if found else "??"}   e.g. {vals[:6]}')
