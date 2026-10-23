#!/usr/bin/env python3
"""Compare IMX410 register tables from astro-camera SDKs with the fp mode table and Z CAM.

    python3 -I astro_compare.py

Inputs (static extractions, see notes/ASTRO_IMX410.md):
  asi2400_tables.json  ZWO libASICamera2 (indi-3rdparty libasi/x64): reglist_common, reg_full_12bit,
                       reglist_bin2, reglist_fullsize  ({u16 addr, u16 val}, addr 0xFFFF = delay ms)
  toup_tables.json     ToupTek libtoupcam (indi-3rdparty libtoupcam/x64): 4-byte entries
                       {addr_hi, 0x10, val, addr_lo}; {FF FF, ms} = delay
  qhy410_writes.json   QHY410 FX3 firmware (indi-3rdparty libqhy/firmware/QHY410.img): every constant
                       call of the sensor-write routine 0x4000377c (chip id 0x81, reg16, val8)
Outputs: astro_tables.csv, astro_vs_fp_zcam.csv, astro_only_regs.csv
"""
import csv, json, pathlib

H = pathlib.Path(__file__).resolve().parent
R = H.parents[3]
FP = R / 'research' / 'imx410' / 'analysis'
Z = H.parent / 'zcam' / 'zcam_imx410_tables.json'

# ---------- load astro tables -> {name: [(addr, val)]}
tabs = {}
asi = json.load(open(H / 'asi2400_tables.json'))
for n, L in asi.items():
    tabs['zwo_' + n] = [(a, v) for a, v in L if a != 0xFFFF]
toup = json.load(open(H / 'toup_tables.json'))
for t in toup:
    w = [(r, v) for k, r, v in t['entries'] if k == 'W']
    d = dict(w)
    if len(w) > 100:
        name = {0x29: '14bit_1x1', 0x2F: '12bit_3x3', 0x39: '12bit_2x2'}[d[0x0001]]
    else:
        name = 'misc'
    tabs['toup_%s@%x' % (name, t['file_off'])] = w
qhy = json.load(open(H / 'qhy410_writes.json'))
qfun = {0x40003824: 'qhy_init', 0x40008c2c: 'qhy_cmdB0_sleep_wake',
        0x4000491c: 'qhy_set_SHR(06=hi,05=lo)', 0x40005178: 'qhy_set_BLKLEVEL(5D=hi,5C=lo)',
        0x400051cc: 'qhy_set_BLKLEVEL_dup', 0x40005220: 'qhy_set_APGC_N(3E=hi,3D=lo)',
        0x40005274: 'qhy_set_APGC_S(40=hi,3F=lo)', 0x400052c8: 'qhy_set_HCG(05E1)',
        0x400054e8: 'qhy_set_0003', 0x40005528: 'qhy_set_window(22/23 start, 24/25=(rows-52)/2)'}
for c in qhy:
    if c['reg'] is None:
        continue
    n = qfun.get(c['func'], 'qhy_func_%08x' % c['func'])
    tabs.setdefault(n, []).append((c['reg'], c['val'] if c['val'] is not None else -1))

with open(H / 'astro_tables.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['table', 'order', 'addr', 'value'])
    for n, L in tabs.items():
        for i, (a, v) in enumerate(L):
            w.writerow([n, i, '%04X' % a, '%02X' % v if v >= 0 else 'var'])

# ---------- fp: one representative mode per readout class (f60)
modes = list(csv.DictReader(open(FP / 'imx410_modes.csv')))
geo = {r['mode_id']: r for r in csv.DictReader(open(FP / 'imx410_mode_geometry.csv'))}
fp_by_class = {}
for m in modes:
    c = int(geo[m['mode_id']]['field_0x60'])
    fp_by_class.setdefault(c, m)
def fpregs(cls):
    m = fp_by_class[cls]
    return {int(k[6:], 16): int(v) for k, v in m.items() if k.startswith('reg_')}, m['mode_id']
fp_all = {int(k[6:], 16) for k in modes[0] if k.startswith('reg_')}
# per-frame gain/exposure writes (IMX410_RULES §1/§3) are not in the mode table
fp_all |= {0x0005, 0x0006, 0x0007, 0x0008, 0x003D, 0x003E, 0x003F, 0x0040, 0x041F, 0x05E2, 0x05A6, 0x05A8, 0x05E1}

# ---------- Z CAM: readout index per class
zj = json.load(open(Z))
def zregs(ri):
    return {r['addr']: r['val'][ri] for r in zj['regs'] if r['val'][ri] != 65535}
z_all = {r['addr'] for r in zj['regs']}
z_all |= {int(r['addr'], 16) for r in csv.DictReader(open(H.parent / 'zcam' / 'zcam_ae_registers.csv'))}

WINDOW = {0x0003, 0x0022, 0x0023, 0x0024, 0x0025}
# class -> (fp class, Z readout index, astro tables)
CMP = [
    ('14bit 1x1', 16, 0, ['zwo_reglist_fullsize', 'toup_14bit_1x1@340c140', 'toup_14bit_1x1@3490580', 'qhy_init']),
    ('12bit 1x1 normal', 17, 1, ['zwo_reg_full_12bit']),
    ('12bit 2x2 normal', 18, 17, ['zwo_reglist_bin2', 'toup_12bit_2x2@340c640', 'toup_12bit_2x2@3490a80']),
    ('12bit 3x3 normal', 20, 6, ['toup_12bit_3x3@340c3c0', 'toup_12bit_3x3@3490800']),
]
common = dict(tabs['zwo_reglist_common'])  # ZWO writes this before every mode table
rows = []
for label, cls, zr, names in CMP:
    fp, fpm = fpregs(cls)
    zz = zregs(zr)
    for n in names:
        t = dict(tabs[n])
        if n.startswith('zwo_'):
            t = {**common, **t}
        for a in sorted(set(t) - WINDOW):
            v = t[a]
            fv, zv = fp.get(a), zz.get(a)
            st = []
            if fv is None and a not in fp_all:
                st.append('fp-never')
            elif fv is None:
                st.append('fp-not-in-class')
            elif fv != v:
                st.append('fp-diff')
            if zv is None:
                st.append('z-not-written' if a in z_all else 'z-never')
            elif zv != v:
                st.append('z-diff')
            rows.append([label, n, 'fp mode %s' % fpm, '%04X' % a, '%02X' % v if v >= 0 else 'var',
                         '' if fv is None else '%02X' % fv, '' if zv is None else '%02X' % zv, ' '.join(st) or 'same'])
with open(H / 'astro_vs_fp_zcam.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['class', 'astro_table', 'fp_ref', 'addr', 'astro', 'fp', 'zcam', 'status'])
    w.writerows(rows)

only = {}
for n, L in tabs.items():
    for a, v in L:
        if a not in fp_all and a not in z_all:
            only.setdefault(a, set()).add('%s=%s' % (n, '%02X' % v if v >= 0 else 'var'))
with open(H / 'astro_only_regs.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['addr', 'written_by'])
    for a in sorted(only):
        w.writerow(['%04X' % a, '; '.join(sorted(only[a]))])

# summary
from collections import Counter
print('tables:', {n: len(L) for n, L in tabs.items()})
for label, *_ in CMP:
    c = Counter(r[7] for r in rows if r[0] == label)
    print(label, dict(c))
    for r in rows:
        if r[0] == label and ('diff' in r[7]):
            print('   ', r[1], r[3], 'astro', r[4], 'fp', r[5], 'z', r[6], r[7])
print('astro-only regs:', ' '.join('%04X' % a for a in sorted(only)))
