#!/usr/bin/env python3
"""Module 1 -> module 3 (notes/ARCHITECTURE.md): turn a readout_cfg plan into a res-custom virtual mode
(SEC_VMODES: a stock donor + whole-word overrides {kind, offset, value} on TIM/META/R28/R38/R14/R68/REG).

    readout_export.py KEY --crop WxH --out WxH [--fps F]     prints donor + overrides (JSON)

Offline: the stock rows come from the ROM tables in out/MAIN_c0000000.bin. The donor is the stock mode of the same
readout class (mode_tables.csv 'cls') and the same raster width, tallest first, so only the height / timing /
blanking (and for the 1x1 fast class the Family A set) need overriding. Kinds follow res-custom ogc_layout.TABLES:
TIM 0, META 1, R28 2, R38 3, R14 4, R68 5, REG 6.
"""
import argparse, csv, json, pathlib, struct, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import readout_cfg as C
import bins

ROOT = HERE.parents[1]
IMAGE = ROOT / 'out' / 'MAIN_c0000000.bin'
BASE = 0xC0000000
ROM = {'TIM': (0xC0B59500, 0x20, 0), 'META': (0xC0B59DC0, 100, 0), 'R28': (0xC0B5BB48, 0x28, 0),
       'R38': (0xC0B5C638, 0x38, 0), 'R14': (0xC0B5D588, 0x14, 0), 'R68': (0xC0B5DB00, 0x68, 0), 'REG': (0xC0B5FDAC, 0x288, 0)}
KIND = {'TIM': 0, 'META': 1, 'R28': 2, 'R38': 3, 'R14': 4, 'R68': 5, 'REG': 6}
N = 70
CLS = {'14': 16, '12': 17, '12fast': 17, '12fastW': 17, '2x2': 18, '2x2fast': 19, '3x3': 20, '3x3fast': 21, '3x6': 22, '3x6fast': 23}
REG_ORDER = [int(k[6:], 16) for k in bins.MODES['10'] if k.startswith('reg_')]
_img = None


def row(table, mode):
    global _img
    _img = _img or IMAGE.read_bytes()
    addr, stride, key = ROM[table]
    o = addr - BASE
    for i in range(N):
        r = _img[o + i * stride:o + (i + 1) * stride]
        if struct.unpack_from('<I', r, key)[0] == mode:
            return bytearray(r)
    raise KeyError(f'mode {mode} not in {table}')


def modes_info():
    return {int(r['mode']): r for r in csv.DictReader(open(HERE / 'offline' / 'mode_tables.csv'))}


def pick_donor(p):
    info = modes_info()
    want_cls, fmt = CLS[p['key']], p['fmt_w']
    same = [m for m, r in info.items() if int(r['cls']) == want_cls]
    exact = [m for m in same if int(info[m]['width']) == fmt]
    pool = exact or same
    return max(pool, key=lambda m: int(info[m]['height'])), bool(exact)


def export(p):
    donor, width_match = pick_donor(p)
    rows = {t: row(t, donor) for t in ROM}
    new = {t: bytearray(r) for t, r in rows.items()}
    # REG: sensor writes (+ the fast Family A set) at word 1 + index in the table order
    writes = list(p['sensor'])
    if p['fast_set']:
        writes = list(bins.diff('8', '139')) + writes
    for reg, val in writes:
        if reg not in REG_ORDER:
            raise ValueError(f'register {reg:04X} is not a table register')
        struct.pack_into('<I', new['REG'], 4 * (1 + REG_ORDER.index(reg)), val)
    # TIM: HMAX/tail, VMAX, rows (+0xE first, +0x10 last), line length/DCLP width only for the 1x1 fast narrow class
    tim = new['TIM']
    hm, vm = p['soc']['hmax'], p['soc']['vmax']
    struct.pack_into('<HH', tim, 4, hm, hm)
    struct.pack_into('<H', tim, 8, vm)
    y0 = struct.unpack_from('<H', tim, 0xE)[0]
    struct.pack_into('<H', tim, 0x10, y0 + p['out_h'])
    # horizontal receiver window (TIM +0xA start, +0xC end): stock 4176/2088 modes crop a 6064/3032 format this way
    # (mode 102: 952..5128, mode 132: 476..2564 = x0 + (format - width)/2)
    x0d, x1d = struct.unpack_from('<HH', rows['TIM'], 0xA)
    fmt_d = x1d - x0d
    xs = x0d + (fmt_d - p['raster_w']) // 2 if p['raster_w'] < fmt_d else x0d
    struct.pack_into('<HH', tim, 0xA, xs, xs + p['raster_w'])
    if p['rows']['R38_words'] and not width_match:
        struct.pack_into('<H', new['R38'], 8, p['rows']['R38_words'])
    # META: raster size, three copies (+4/+8, +0x14/+0x18, +0x24/+0x28)
    for off in (0x08, 0x18, 0x28):
        struct.pack_into('<I', new['META'], off, p['out_h'])
    for off in (0x04, 0x14, 0x24):
        struct.pack_into('<I', new['META'], off, p['raster_w'])
    ovr = []
    for t in ROM:
        a, b = rows[t], new[t]
        for o in range(4, len(a), 4):
            if a[o:o + 4] != b[o:o + 4]:
                ovr.append((KIND[t], o, struct.unpack_from('<I', b, o)[0]))
    if len(ovr) > 256:
        raise ValueError(f'{len(ovr)} overrides > res-custom limit 256')
    return dict(id=p['id'], donor=donor, donor_width_match=width_match, overrides=ovr, n_overrides=len(ovr),
                raster=[p['raster_w'], p['out_h']], tim_x=list(struct.unpack_from('<HH', tim, 0xA)), hmax=hm, vmax=vm, fps=p['fps'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('key', choices=[r['key'] for r in C.READOUTS])
    ap.add_argument('--crop', required=True); ap.add_argument('--out', required=True); ap.add_argument('--fps', type=float)
    a = ap.parse_args()
    cw, ch = (int(x) for x in a.crop.split('x')); ow, oh = (int(x) for x in a.out.split('x'))
    e = export(C.plan(a.key, cw, ch, ow, oh, a.fps))
    e['overrides'] = [dict(kind=k, off=f'0x{o:X}', value=f'0x{v:08X}') for k, o, v in e['overrides']]
    print(json.dumps(e, indent=1))


if __name__ == '__main__':
    main()
