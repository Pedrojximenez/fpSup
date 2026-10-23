#!/usr/bin/env python3
"""Compare Z CAM's IMX410 write set (zcam_imx410_tables.json) with the fp's mode table (70 modes x 161 regs).

    python3 -I zcam_compare.py            # writes compare_*.csv next to this file, prints a summary

Z CAM writes deltas (0xFFFF = not written, i.e. power-on value); the fp writes all 161 every mode switch.
"""
import csv, json, pathlib
from collections import defaultdict

H = pathlib.Path(__file__).resolve().parent
A = H.parents[3] / 'research' / 'imx410' / 'analysis'
Z = json.load(open(H / 'zcam_imx410_tables.json'))
fpm = list(csv.DictReader(open(A / 'imx410_modes.csv')))
geo = {r['mode_id']: r for r in csv.DictReader(open(A / 'imx410_mode_geometry.csv'))}
tim = {r['mode_id']: r for r in csv.DictReader(open(A / 'imx410_timing.csv'))}
FP_REGS = [int(k[4:], 16) for k in fpm[0] if k.startswith('reg_')]
FP = {m['mode_id']: {int(k[4:], 16): int(v) for k, v in m.items() if k.startswith('reg_')} for m in fpm}
FP_PERFRAME = [0x041F, 0x05E2, 0x05A6, 0x05A8, 0x05E1, 0x3D, 0x3E, 0x3F, 0x40, 0x05, 0x06, 0x07, 0x08]
FP_EXTRA = [0x0011, 0x00CE, 0x00D1, 0x00D2, 0x00D3]          # outside the table (window 0003/0022-25 is in it)
FP_ALL = set(FP_REGS) | set(FP_PERFRAME) | set(FP_EXTRA)
SONY = {a: v for a, v in json.load(open(H.parents[1] / 'captures' / 'sony_const_list.json'))}
SPEED = {16: '14bit', 17: 'normal', 18: 'normal', 20: 'normal', 22: 'normal', 19: 'fast', 21: 'fast', 23: 'fast'}
WINDOW = {0x0003, 0x0022, 0x0023, 0x0024, 0x0025}
attr = {i: dict(f50=int(geo[i]['field_0x50']), f60=int(geo[i]['field_0x60']),
                speed=SPEED[int(geo[i]['field_0x60'])], hmax=int(tim[i]['hmax_cycles'])) for i in FP}


def det(reg, key):
    seen = {}
    return all(seen.setdefault(attr[i][key], FP[i][reg]) == FP[i][reg] for i in FP)


def family(reg):
    if reg in WINDOW:
        return 'C-window'
    if len({FP[i][reg] for i in FP}) == 1:
        return 'const'
    if det(reg, 'speed'):
        return 'A-ADspeed'
    if det(reg, 'f50'):
        return 'B-vdrive'
    if det(reg, 'f60'):
        return 'C-format'
    return 'mixed'


FAM = {r: family(r) for r in FP_REGS}
used = sorted({m['readout'] for m in Z['modes']})
RO = Z['readouts']
zrows = Z['regs']
zw = defaultdict(dict)            # addr -> readout -> value (written only)
for r in zrows:
    for k, v in enumerate(r['val']):
        if v != 0xFFFF:
            zw[r['addr']][k] = v
AE = {a['addr']: a['name'] for a in Z['ae_registers']}
Z_ALL = set(zw) | set(AE) | {0x0000}


def zctx(a):
    if a in AE:
        return 'AE (init + per-frame)'
    vals = zw[a]
    if len(vals) == 33 and len(set(vals.values())) == 1:
        return 'init/common'
    return 'mode (per readout)'


def zvals(a, only_used=True):
    vals = zw.get(a, {})
    by = defaultdict(list)
    for k, v in vals.items():
        if not only_used or k in used:
            by[v].append(k)
    return '; '.join(f'{v:02X}@r{",".join(map(str, ks))}' if len(ks) < 33 else f'{v:02X}@all'
                     for v, ks in sorted(by.items()))


# --- classify each Z readout by family: A (speed set), B (vbin column), C (0001) ---
REP = {}                                   # representative fp mode per speed set / per vbin
for i in FP:
    REP.setdefault(('speed', attr[i]['speed']), i)
    REP.setdefault(('vbin', attr[i]['f50']), i)
AREGS = [r for r in FP_REGS if FAM[r] == 'A-ADspeed']
BREGS = [r for r in FP_REGS if FAM[r] == 'B-vdrive']


def fit(k, regs, i):
    """Z readout k vs fp mode i on regs Z writes; Z skip counts as unknown (not compared)."""
    c = [a for a in regs if k in zw.get(a, {})]
    return [a for a in c if zw[a][k] != FP[i][a]], len(c)


cls = {}
for k in range(33):
    sp = min(('14bit', 'normal', 'fast'), key=lambda s: len(fit(k, AREGS, REP[('speed', s)])[0]))
    vb = min((1, 2, 3, 6), key=lambda v: len(fit(k, BREGS, REP[('vbin', v)])[0]))
    am, an = fit(k, AREGS, REP[('speed', sp)])
    bm, bn = fit(k, BREGS, REP[('vbin', vb)])
    if bn < 5:                      # 07xx block left at power-on (all 0) = the fp's vbin-6 column
        vb = 6
        bm, bn = fit(k, BREGS, REP[('vbin', vb)])
    fp_same = [i for i in FP if attr[i]['speed'] == sp and attr[i]['f50'] == vb]
    cls[k] = dict(speed=sp, vbin=vb, am=am, an=an, bm=bm, bn=bn, fp_same=fp_same,
                  f60=sorted({attr[i]['f60'] for i in fp_same}),
                  fp0001=sorted({FP[i][1] for i in fp_same}))
match = {k: (None, (cls[k]['fp_same'] or [REP[('speed', cls[k]['speed'])]])[0]) for k in range(33)}

with open(H / 'compare_readout_match.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['z_readout', 'sony_mode', 'w', 'h', 'adc_bits', 'zcam_modes', 'z_0001',
                'A_speed_set', 'A_mismatch/compared', 'A_mismatch_regs', 'B_vbin', 'B_mismatch/compared',
                'B_mismatch_regs', 'fp_class_f60_with_same_A+B', 'fp_0001_for_that_class'])
    for k in range(33):
        c = cls[k]
        w.writerow([k, RO[k]['name'], RO[k]['w'], RO[k]['h'], RO[k]['adc_bits'],
                    ' '.join(str(m['mode']) for m in Z['modes'] if m['readout'] == k) or 'unused',
                    f'{zw[1][k]:02X}', c['speed'], f"{len(c['am'])}/{c['an']}",
                    ' '.join(f'{a:04X}:{zw[a][k]:02X}/fp{FP[REP[("speed", c["speed"])]][a]:02X}' for a in c['am']),
                    c['vbin'], f"{len(c['bm'])}/{c['bn']}",
                    ' '.join(f'{a:04X}:{zw[a][k]:02X}/fp{FP[REP[("vbin", c["vbin"])]][a]:02X}' for a in c['bm']),
                    ' '.join(map(str, c['f60'])) or 'NONE', ' '.join(f'{v:02X}' for v in c['fp0001'])])

# --- (a) Z writes, fp never ---
with open(H / 'compare_a_zcam_only.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['addr', 'context', 'zcam_values (used readouts)', 'ae_name', 'sony_a7III_value'])
    for a in sorted(Z_ALL - FP_ALL):
        w.writerow([f'{a:04X}', zctx(a) if a else 'standby bit0 (0000|=1 / &=FE) + init 04',
                    zvals(a), AE.get(a, ''), f'{SONY[a]:02X}' if a in SONY else ''])
# --- (b) fp table regs Z never writes ---
with open(H / 'compare_b_fp_only.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['addr', 'fp_family', 'fp_values', 'sony_a7III_value'])
    for a in sorted(FP_ALL - Z_ALL):
        fv = sorted({FP[i][a] for i in FP}) if a in FP_REGS else []
        w.writerow([f'{a:04X}', FAM.get(a, 'outside table'), ' '.join(f'{v:02X}' for v in fv),
                    f'{SONY[a]:02X}' if a in SONY else ''])
# --- (c) both write: Z value per used readout vs the fp value expected for the same family column ---
def expected(a, k):
    """fp value for register a in the fp column that matches Z readout k: A by speed set, B by vbin,
    const = the fp constant, C/mixed by an fp mode with the same speed+vbin (None if the fp has no such class)."""
    c = cls[k]
    if FAM[a] == 'A-ADspeed':
        return FP[REP[('speed', c['speed'])]][a], f"{c['speed']}"
    if FAM[a] == 'B-vdrive':
        return FP[REP[('vbin', c['vbin'])]][a], f"vbin{c['vbin']}"
    if FAM[a] == 'const':
        return FP['0'][a], 'const'
    if c['fp_same']:
        vals = sorted({FP[i][a] for i in c['fp_same']})
        return (vals[0] if len(vals) == 1 else vals), f"class{'/'.join(map(str, c['f60']))}"
    return None, 'no fp class'


rows = []
for a in sorted(set(FP_REGS) & set(zw)):
    diffs, skips = [], []
    for k in used:
        ev, col = expected(a, k)
        if k not in zw[a]:
            skips.append((k, ev))
        elif a not in WINDOW and ev is not None and not (zw[a][k] == ev or (isinstance(ev, list) and zw[a][k] in ev)):
            diffs.append((k, zw[a][k], col, ev))
    rows.append((a, FAM[a], diffs, skips))
fmt = lambda v: '/'.join(f'{x:02X}' for x in v) if isinstance(v, list) else ('?' if v is None else f'{v:02X}')
with open(H / 'compare_c_both.csv', 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['addr', 'fp_family', 'fp_values_all_modes', 'zcam_values (used readouts)',
                'diffs r<readout>:Z vs fp<column>=fp', 'zcam_skips r<readout>:(fp value in that column)'])
    for a, fam, diffs, skips in rows:
        w.writerow([f'{a:04X}', fam, ' '.join(f'{v:02X}' for v in sorted({FP[i][a] for i in FP})), zvals(a),
                    ' '.join(f'r{k}:{z:02X}vs{col}={fmt(v)}' for k, z, col, v in diffs),
                    ' '.join(f'r{k}:{fmt(v)}' for k, v in skips)])
print('Z-only:', ' '.join(f'{a:04X}' for a in sorted(Z_ALL - FP_ALL)))
print('fp-only:', len(FP_ALL - Z_ALL), ' '.join(f'{a:04X}' for a in sorted(FP_ALL - Z_ALL)))
print('both:', len(set(FP_REGS) & set(zw)))
from collections import Counter
print('families', Counter(FAM.values()))
