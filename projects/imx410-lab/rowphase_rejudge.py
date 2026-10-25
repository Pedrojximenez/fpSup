#!/usr/bin/env python3
"""Re-judge the rowphase check of stored configs with the current rowphase.judge (offline, no camera).

    python3 rowphase_rejudge.py captures/full_v1 --db captures/full_v1.json [--write]

Only configs whose stored rowphase failed are re-read: a failing config keeps every frame (smc_validate main), so its
longest-VMAX frame v<N>/ is still on disk -- the same frame and crop run_one judged.  --write puts the new result in
the db (old one kept as rowphase_v1) and recomputes PASS.
"""
import argparse, json, pathlib, subprocess, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / 'offline'))
import readout_cfg as C, resweep as R, rowphase


def frame(d, bits):
    for z in d.glob('*.raw.zst'):
        o = pathlib.Path(str(z)[:-4])
        if not o.exists():
            subprocess.run(['zstd', '-dqf', str(z), '-o', str(o)], check=True)
    if bits == 14:
        m = json.loads((d / 'frame.json').read_text()); m['bits'] = 14; (d / 'frame.json').write_text(json.dumps(m))
    fr, _ = R.decode(d)
    for z in d.glob('*.raw.zst'):                       # keep only the compressed copy
        pathlib.Path(str(z)[:-4]).unlink(missing_ok=True)
    return fr


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('cap'); ap.add_argument('--db', required=True)
    ap.add_argument('--tag', default='light'); ap.add_argument('--write', action='store_true')
    a = ap.parse_args()
    cap, dbp = pathlib.Path(a.cap), pathlib.Path(a.db)
    db = json.loads(dbp.read_text())
    n = flipped = 0
    for pid, ent in db.items():
        res = ent.get(a.tag)
        if not res or res['checks'].get('rowphase', {}).get('PASS', True):
            continue
        d = cap / pid.replace(':', '_').replace('>', '_')
        vs = sorted((p for p in d.glob('v*') if p.name[1:].isdigit()), key=lambda p: -int(p.name[1:]))
        if not vs:
            print(f'{pid:44s} no stored frame'); continue
        at = res['attrs']; top, out_h = at['y0'], at['height']
        fb = frame(vs[0], at['bits'])[0].astype(float)[top + 10:top + out_h - 10, 32:-32]
        key = pid.split(':')[0]
        new = rowphase.judge(fb, C.BY_KEY[key]['mv'])
        n += 1; flipped += new['PASS']
        print(f"{pid:44s} {fb.shape[0]:5d} rows  dy {new['dy']} dx {new['dx']} exp {new['expected']:+.3f}  "
              f"{'PASS' if new['PASS'] else 'FAIL'}")
        if a.write:
            res['checks'].setdefault('rowphase_v1', res['checks']['rowphase'])
            res['checks']['rowphase'] = new
            res['PASS'] = all(c['PASS'] for k, c in res['checks'].items() if k != 'rowphase_v1')
    print(f'{n} re-judged, {flipped} now pass')
    if a.write:
        dbp.write_text(json.dumps(db, indent=1, default=float))


if __name__ == '__main__':
    main()
