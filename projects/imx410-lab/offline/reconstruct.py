#!/usr/bin/env python3
"""Reconstruction test (user, 2026-10-22): can the 8 per-mode tables of all 70 stock modes be rebuilt from the mode
attributes alone, by rules -- not by copying a donor? Every field that cannot is a gap in our understanding.

    python3 offline/reconstruct.py [--table REG] [--show-unknown]

Inputs per mode (attributes a user-level request maps to): cls (readout class 16-23), hbin, vbin, vadd, bits,
width, height (raster), hmax, vmax, tail, f5c (META+5C, minimum vertical blanking).
For every field (16-bit words of TIM/META/R10/R28/R38/R14/R68; one value per register of REG) try, in order:
  const      one value for all 70 modes
  cat:X      a lookup on categorical attributes X (finite: cls, hbin, vbin, vadd, bits, or pairs) that is consistent
  lin:X|G    value = round/floor(a*X + b) exactly, per group G of a categorical attribute (a rational, X numeric)
  unknown    none of the above
Fields with an explicit rule in mode_rules.py (META/R14/R28/R38/R68, from their firmware consumers) skip the search:
  exact       formula over generator attributes reproduces all 70
  exact+hand  formula + documented per-mode HAND values (mode_rules.HAND: value, live/dead, reason)
  adj         R68 SensorAdjustment parameters (only the 11 defect-calibration modes; 0 for a new mode)
  class       REG lookup on the readout class (cls): the 8-entry class catalog a generator picks from
A field is 'reproduced' when its rule gives all 70 modes. --show-hand lists the hand values, --loo runs the
leave-one-out (explicit rules: formulas, R28 constants refitted; generic rules: re-searched).
"""
import argparse, csv, itertools, pathlib, struct, sys
from fractions import Fraction
HERE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import readout_export as X
sys.path.insert(0, str(HERE / 'offline'))
import mode_rules as MR

CAT = ['cls', 'hbin', 'vbin', 'vadd', 'bits']
NUM = ['width', 'height', 'hmax', 'vmax', 'tail', 'f5c', 'x0', 'x1', 'y0', 'y1', 'fpsn', 'wstart', 'wh', 'rows']
CAT += ['win', 'acq', 'crop', 'cont']


import json
NAMES = {int(k): v for k, v in json.load(open(HERE / 'offline' / 'mode_names.json')).items()}


def load():
    info = {int(r['mode']): r for r in csv.DictReader(open(HERE / 'offline' / 'mode_tables.csv'))}
    modes = sorted(info)
    attrs = {}
    for m in modes:
        r = info[m]
        tim = X.row('TIM', m)
        attrs[m] = dict(cls=int(r['cls']), hbin=int(r['hbin']), vbin=int(r['vbin']), vadd=int(r['vadd']), bits=int(r['bits']),
                        width=int(r['width']), height=int(r['height']), hmax=struct.unpack_from('<H', tim, 4)[0],
                        tail=struct.unpack_from('<H', tim, 6)[0], vmax=struct.unpack_from('<H', tim, 8)[0], f5c=int(r['f5c']),
                        x0=struct.unpack_from('<H', tim, 0xA)[0], x1=struct.unpack_from('<H', tim, 0xC)[0],
                        y0=struct.unpack_from('<H', tim, 0xE)[0], y1=struct.unpack_from('<H', tim, 0x10)[0],
                        fpsn=struct.unpack_from('<H', X.row('META', m), 0x40)[0])
        reg = X.row('REG', m)
        rv = lambda rr: struct.unpack_from('<I', reg, 4 * (1 + X.REG_ORDER.index(rr)))[0]
        nm = NAMES.get(m, '')
        attrs[m].update(acq=int(nm.startswith('ACQ')), crop=int('CROP' in nm), cont=int('CONTINUOUS' in nm),
                        win=rv(0x0003), wstart=rv(0x0022) | rv(0x0023) << 8, wh=rv(0x0024) | rv(0x0025) << 8,
                        rows=attrs[m]['y1'] - attrs[m]['y0'])
    fields = {}
    for t in ('TIM', 'META', 'R28', 'R38', 'R14', 'R68'):
        for m in modes:
            rw = X.row(t, m)
            for o in range(4, len(rw) - 1, 2):
                fields.setdefault((t, o), {})[m] = struct.unpack_from('<H', rw, o)[0]
    for t in ('TIM', 'META', 'R28', 'R38', 'R14', 'R68'):
        for m in modes:
            rw = X.row(t, m)
            for o in range(4, len(rw) - 3, 4):
                fields.setdefault((t + '32', o), {})[m] = struct.unpack_from('<I', rw, o)[0]
    # R10 (key at +4, value at +0)
    for m in modes:
        o = X.ROM['TIM']  # placeholder to keep the loop shape
    for m in modes:
        rw = X.row('REG', m)
        for i, reg in enumerate(X.REG_ORDER):
            fields.setdefault(('REG', reg), {})[m] = struct.unpack_from('<I', rw, 4 * (1 + i))[0]
    return modes, attrs, fields


def try_const(vals):
    return len(set(vals.values())) == 1


def try_cat(vals, attrs, keys):
    seen = {}
    for m, v in vals.items():
        k = tuple(attrs[m][a] for a in keys)
        if seen.setdefault(k, v) != v:
            return False
    return True


def try_lin(vals, attrs, xname, group):
    groups = {}
    for m, v in vals.items():
        groups.setdefault(attrs[m][group] if group else 0, []).append((attrs[m][xname], v))
    rules = {}
    for g, pts in groups.items():
        xs = {p[0] for p in pts}
        if len(xs) == 1:
            if len({p[1] for p in pts}) != 1:
                return None
            rules[g] = (Fraction(0), Fraction(pts[0][1]))
            continue
        (x1, y1), (x2, y2) = sorted(set(pts))[0], sorted(set(pts))[-1]
        if x1 == x2:
            return None
        a = Fraction(y2 - y1, x2 - x1).limit_denominator(64)
        ok = False
        for b in {Fraction(y1) - a * x1, Fraction(y2) - a * x2}:
            for rnd in (lambda z: int(z), lambda z: int(z + Fraction(1, 2))):
                if all(rnd(a * x + b) == y for x, y in pts):
                    ok = True; rules[g] = (a, b); break
            if ok:
                break
        if not ok:
            return None
    return rules


def try_byte(vals, attrs):
    for xn in NUM:
        for sh in (0, 8):
            if all(((attrs[m][xn] >> sh) & 0xFF) == v for m, v in vals.items()):
                return f'byte:{xn}>>{sh}'
    return None


def try_gated(vals, attrs):
    """zero for some modes, a single-attribute linear rule for the rest; the gate is a categorical lookup"""
    nz = {m: v for m, v in vals.items() if v}
    if not nz or len(nz) == len(vals):
        return None
    for g in CAT + [None]:
        gate_ok = True
        if g:
            seen = {}
            for m, v in vals.items():
                if seen.setdefault(attrs[m][g], bool(v)) != bool(v):
                    gate_ok = False; break
        if not gate_ok:
            continue
        for xn in NUM:
            for grp in [None] + CAT:
                if try_lin(nz, attrs, xn, grp) is not None:
                    return f'gated:{g or "?"}->lin:{xn}' + (f'|{grp}' if grp else '')
    return None


def try_div(vals, attrs):
    for xn in NUM:
        for grp in [None] + CAT:
            groups = {}
            for m, v in vals.items():
                groups.setdefault(attrs[m][grp] if grp else 0, []).append((attrs[m][xn], v))
            good = True
            for g, pts in groups.items():
                hit = False
                for k in (2, 3, 4, 6, 8, 12, 16, 24, 32, 40, 48, 64, 128):
                    cs = {v - x // k for x, v in pts}
                    if len(cs) == 1:
                        hit = True; break
                if not hit:
                    good = False; break
            if good:
                return f'div:{xn}' + (f'|{grp}' if grp else '')
    return None


def try_lin2(vals, attrs):
    import numpy as np
    ms = list(vals)
    y = np.array([vals[m] for m in ms], float)
    for xa, xb in itertools.combinations(NUM, 2):
        for grp in [None] + CAT:
            ok = True
            groups = {}
            for m in ms:
                groups.setdefault(attrs[m][grp] if grp else 0, []).append(m)
            for g, mm in groups.items():
                A = np.array([[attrs[m][xa], attrs[m][xb], 1] for m in mm], float)
                yy = np.array([vals[m] for m in mm], float)
                c, *_ = np.linalg.lstsq(A, yy, rcond=None)
                if np.max(np.abs(A @ c - yy)) > 0.51:
                    ok = False; break
            if ok:
                return f'lin2:{xa}+{xb}' + (f'|{grp}' if grp else '')
    return None


def classify(vals, attrs):
    if try_const(vals):
        return 'const', None
    for k in range(1, 3):
        for keys in itertools.combinations(CAT, k):
            if try_cat(vals, attrs, keys):
                return 'cat:' + '+'.join(keys), None
    for xname in NUM:
        for group in [None] + CAT:
            r = try_lin(vals, attrs, xname, group)
            if r is not None:
                return f'lin:{xname}' + (f'|{group}' if group else ''), r
    for f in (try_byte, try_div, try_gated, try_lin2):
        r = f(vals, attrs)
        if r:
            return r, None
    return 'unknown', None


def generic_loo_pred(vals, attrs, m):
    """predict mode m from a generic rule fitted on the other modes (None = cannot)"""
    rest = {k: v for k, v in vals.items() if k != m}
    kind, rule = classify(rest, attrs)
    if kind == 'const':
        return next(iter(rest.values()))
    if kind.startswith('cat:'):
        keys = kind[4:].split('+')
        look = {tuple(attrs[k][a] for a in keys): v for k, v in rest.items()}
        return look.get(tuple(attrs[m][a] for a in keys))
    if kind.startswith('lin:') and rule is not None:
        xn = kind[4:].split('|')[0]; grp = kind.split('|')[1] if '|' in kind else None
        g = attrs[m][grp] if grp else 0
        if g in rule:
            a, b = rule[g]
            for rnd in (lambda z: int(z), lambda z: int(z + Fraction(1, 2))):
                if rnd(a * attrs[m][xn] + b) == vals[m]:
                    return vals[m]
    if kind.startswith('byte:'):
        xn, sh = kind[5:].split('>>')
        return (attrs[m][xn] >> int(sh)) & 0xFF
    return None


R28_K = {0x08: ('K_EVAL_W', 'width', 1, MR._even_round), 0x0A: ('K_EVAL_H', 'height', 1, MR._even_floor),
         0x12: ('K_AF_W', 'width', 2, MR._even_round), 0x14: ('K_AF_H', 'height', 2, MR._even_round)}


def explicit_loo(fields, modes, attrs, field, m):
    """explicit rule, leave-one-out: rules have no per-mode memory; the only fitted numbers are the four R28 grid
    constants, which are refitted without m. HAND values cannot be predicted (count as misses)."""
    t, o = field
    if t == 'R28':
        # the cell sizes carry the constants; positions follow from them
        dep = {0x04: 0x08, 0x08: 0x08, 0x06: 0x0A, 0x0A: 0x0A, 0x0E: 0x12, 0x12: 0x12, 0x10: 0x14, 0x14: 0x14}.get(o)
        if dep is not None:
            name, dim, div, rnd = R28_K[dep]
            pts = [(attrs[k][dim] / div, fields[(t, dep)][k]) for k in modes if k != m]
            iv = MR.fit_k(pts, lambda x: rnd(x), 16)
            if iv is None:
                return None
            old = getattr(MR, name)
            setattr(MR, name, (iv[0] + iv[1]) / 2)
            try:
                return MR.predict(field, m, attrs[m])[0] if (m not in MR.HAND.get(field, {})) else None
            finally:
                setattr(MR, name, old)
    v, how = MR.predict(field, m, attrs[m])
    return None if how == 'hand' else v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--table'); ap.add_argument('--show-unknown', action='store_true'); ap.add_argument('--loo', action='store_true')
    ap.add_argument('--show-hand', action='store_true')
    a = ap.parse_args()
    modes, attrs, fields = load()
    stats, unknown, hand, broken = {}, [], [], []
    vstat = dict(exact=0, adj=0, hand=0, generic=0, unknown=0)
    for (t, o), vals in sorted(fields.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        if t.endswith('32') or (a.table and t != a.table):
            continue
        if (t, o) in MR.EXACT:
            hows = set()
            for m in modes:
                v, how = MR.predict((t, o), m, attrs[m])
                if v != vals[m]:
                    broken.append((t, o, m, v, vals[m])); how = 'unknown'
                hows.add(how); vstat[how] += 1
                if how == 'hand':
                    hand.append((t, o, m, vals[m], MR.HAND[(t, o)][m]))
            k = 'unknown' if 'unknown' in hows else 'adj' if 'adj' in hows else 'exact+hand' if 'hand' in hows else 'exact'
            if k == 'exact' and len(set(vals.values())) == 1:
                k = 'const'
        else:
            kind, rule = classify(vals, attrs)
            k = kind.split(':')[0]
            if k == 'div':
                k = 'lin'
            if k == 'cat' and kind[4:] in ('cls', 'cls+acq'):
                k = 'class'          # readout-class catalog (REG): a generator picks one of the 8 classes
            vstat['unknown' if k == 'unknown' else 'generic'] += len(modes)
            if k == 'unknown':
                unknown.append((t, o, len(set(vals.values())), sorted(set(vals.values()))[:6]))
        stats.setdefault(t, {}).setdefault(k, 0)
        stats[t][k] += 1
    cols = ['const', 'exact', 'exact+hand', 'adj', 'class', 'cat', 'lin', 'byte', 'gated', 'lin2', 'unknown']
    print('table  fields ' + ' '.join(f'{c:>10s}' for c in cols) + '  reproduced')
    tot = [0, 0]
    for t, s in stats.items():
        n = sum(s.values()); ok = n - s.get('unknown', 0)
        tot[0] += n; tot[1] += ok
        print(f"{t:6s} {n:6d} " + ' '.join(f'{s.get(c, 0):10d}' for c in cols) + f'   {100 * ok / n:5.1f} %')
    print(f'ALL    {tot[0]:6d}  reproduced {tot[1]} ({100 * tot[1] / tot[0]:.1f} %)')
    nv = sum(vstat.values())
    print(f"values (field x mode = {nv}): exact formula {vstat['exact']}, factory-adjustment {vstat['adj']}, "
          f"generic rule {vstat['generic']}, per-mode HAND {vstat['hand']} ({100 * vstat['hand'] / nv:.2f} %), "
          f"unexplained {vstat['unknown']}")
    if broken:
        print('RULE BROKEN:', broken[:20])
    if a.show_unknown:
        for t, o, n, ex in unknown:
            print(f"  unknown {t} {'0x%04X' % o if t == 'REG' else '+0x%02X' % o}: {n} values e.g. {ex}")
    if a.show_hand:
        for t, o, m, v, (_, live, why) in hand:
            print(f"  hand {t}+0x{o:02X} mode {m:3d} = {v:5d}  {'LIVE' if live else 'dead'}  {why}")
    if a.loo:
        loo(modes, attrs, fields)


def loo(modes, attrs, fields):
    """leave-one-out: predict every value of mode m from rules built without m. Explicit rules are formulas
    (only the R28 constants are refitted); generic rules are re-searched. A miss = a value a generator could not
    invent for a new mode."""
    res = {}
    bad = {}
    for (t, o), vals in fields.items():
        if t.endswith('32'):
            continue
        exp = (t, o) in MR.EXPLICIT_KEYS
        cls = 'adj' if (t, o) in MR.ADJ_FIELDS else 'explicit' if exp else 'generic'
        for m in modes:
            p = explicit_loo(fields, modes, attrs, (t, o), m) if exp else generic_loo_pred(vals, attrs, m)
            r = res.setdefault(cls, [0, 0])
            r[1] += 1
            if p == vals[m]:
                r[0] += 1
            else:
                bad[(t, o)] = bad.get((t, o), 0) + 1
    ok = sum(r[0] for r in res.values()); tot = sum(r[1] for r in res.values())
    print(f'leave-one-out: {ok}/{tot} right ({100 * ok / tot:.1f} %)  ' +
          ', '.join(f'{k} {r[0]}/{r[1]} ({100 * r[0] / r[1]:.1f} %)' for k, r in res.items()))
    worst = sorted(bad.items(), key=lambda kv: -kv[1])[:30]
    print('misses (field: modes):', ', '.join(f"{t}{'%04X' % o if t == 'REG' else '+%02X' % o}:{n}" for (t, o), n in worst))


if __name__ == '__main__':
    main()
