#!/usr/bin/env python3
"""Readable row range per vertical merge (user 2026-10-23: is the full-height row count a formula of the merge?).
Lens capped. Per readout class: firmware switch to the full-height plan with EXTRA more output rows than the planner
allows, one dark frame; rows the sensor did not send read ~1 (smc_m1: V2 rows 2034+), so the last row with a black
level is the end of the readout. Reported per class: last valid receiver row L, valid rows from y0, and vbin*(L+1)
(the end in sensor rows) to compare across merges. Nothing is written to the settings area or the card.

    rowrange.py OUT KEY...        e.g. 12 12h2 2x2 12v2 3x3 12v3 3x6
    rowrange.py report OUT
"""
import json, pathlib, subprocess, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / 'offline'))
import numpy as np

EXTRA = 40          # output rows beyond the planned full height; capped so the receiver frame stays <= 4096 rows (the
                    # tool's limit) and, for V2, at the 2046 lines the sensor sends (+40 gave no frame, r1)
EXTRA_CAP = {2: 12}


def capture_one(key, out, force_extra=None):
    import resweep as R, smc, readout_cfg as C, smc_validate as V
    import vmode
    vmode.KEEP_WINDOW = True       # r1/r2 forgot this: vmode then rewrote the window and every full-height frame lost
                                   # its texture below sensor row ~3076 (flat black or 4090) -- a tool artifact
    r = C.BY_KEY[key]; w = max(r['fmt'])
    p = C.plan(key, w * r['mh'] if r['mh'] > 1 else w, 4040, (w // 16) * 16, C.full_rows(key))
    planned = p['out_h']
    a0 = smc.attrs_from_plan(p)
    extra = min(EXTRA, EXTRA_CAP.get(r['mv'], EXTRA), 4096 - (a0['y0'] + planned)) if force_extra is None else force_extra
    p['out_h'] += extra; p['receiver_lines'] += extra
    p['soc']['vmax'] += extra; p['soc']['rx_end'] = p['soc'].get('rx_end', 0) + extra
    a, rows, how = smc.create(p)
    rows = {t: bytes(v) for t, v in rows.items()}
    if r.get('new'):
        import struct
        rows['R10'] = struct.pack('<II', V.R10[a['cls']], 10)
    d = out / key; d.mkdir(parents=True, exist_ok=True)
    b = R.Base(d, 'V2' if p['bits'] == 14 else 'V1', rows=rows); s = b.s; s.pair = True
    try:
        # r1 (2026-10-23): the lens was OPEN and the single frame was exposed only down to ~3/4 of its height (first
        # frame after the switch) -- grab a pair after settling, judge the second frame, and check the exposure
        time.sleep(1.0)
        ok = s.grab(d / 'dark')
    finally:
        b.close()
    meta = dict(key=key, vbin=r['mv'], hbin=r['mh'], y0=a['y0'], planned=planned, out_h=p['out_h'], extra=extra, ok=bool(ok))
    (d / 'meta.json').write_text(json.dumps(meta, indent=1))
    print(key, 'ok' if ok else 'NO FRAME', flush=True)


def report(out):
    import resweep as R
    print(f"{'class':8s} {'v':>2s} {'y0':>4s} {'frame':>6s} {'last':>6s} {'rows':>6s} {'planned':>7s} {'v*(L+1)':>8s}  first-level-step")
    for d in sorted(p for p in out.iterdir() if (p / 'meta.json').exists()):
        m = json.loads((d / 'meta.json').read_text())
        if not m['ok']:
            print(m['key'], 'no frame'); continue
        fr, _ = R.decode(d / 'dark')
        f = fr[-1].astype(float)[:, 16:-16]
        rs = f.std(1)
        tex = np.nonzero(rs > 3 * np.median(rs[2:10]) + 2)[0]
        m['lit'] = bool(len(tex) > 0.5 * len(rs))
        if m['lit']:                                  # lens open: the image ends at the last textured row
            m['tex_first'], m['tex_last'] = int(tex.min()), int(tex.max())
            nxt = f[tex.max() + 2:tex.max() + 6].mean() if tex.max() + 6 < len(f) else None
            m['after'] = None if nxt is None else round(float(nxt))
            print(f"{m['key']:8s} v{m['vbin']} y0 {m['y0']:4d}  textured {tex.min()}..{tex.max()}  rows from y0 {tex.max() + 1 - m['y0']}"
                  f"  planned {m['planned']}  v*(last+1) {m['vbin'] * (tex.max() + 1)}  then {m['after']}  frame {f.shape[0]}")
            (d / 'meta.json').write_text(json.dumps(m, indent=1))
            continue
        rp = f.mean(1)
        live = np.nonzero(rp > 30)[0]
        L = int(live.max())
        gaps = [int(i) for i in np.nonzero(rp[:L] <= 30)[0]]
        step = next((i for i in range(2, 80) if abs(rp[i] - np.median(rp[2:12])) > 0.6), None)
        m.update(last=L, frame_rows=int(f.shape[0]), valid_from_y0=L + 1 - m['y0'], end_sensor=m['vbin'] * (L + 1), gaps=gaps[:10], step=step)
        (d / 'meta.json').write_text(json.dumps(m, indent=1))
        print(f"{m['key']:8s} {m['vbin']:2d} {m['y0']:4d} {f.shape[0]:6d} {L:6d} {L + 1 - m['y0']:6d} {m['planned']:7d} {m['vbin'] * (L + 1):8d}  {step}"
              + (f"  holes {gaps[:6]}" if gaps else ''))


def _try(key, extra, out):
    r = subprocess.run([sys.executable, '-c', 'import sweep; sweep.KEEP=None; sweep.fastreboot()'], cwd=HERE, capture_output=True, timeout=300)
    if r.returncode:
        raise SystemExit('camera did not come back -- stopping')
    r = subprocess.run([sys.executable, '-u', '-c', f'import rowrange, pathlib; rowrange.capture_one({key!r}, pathlib.Path({str(out)!r}), {extra})'],
                       cwd=HERE, capture_output=True, text=True, timeout=300)
    ok = 'ok' in (r.stdout.strip().splitlines() or [''])[-1].split()
    print(f'  {key} +{extra}: {"frame" if ok else "no frame"}', flush=True)
    return ok


def search(out, keys, hi=40):
    """largest extra receiver rows that still give a frame (= the lines the sensor sends), binary search; the frame at
    that extra is kept in OUT/<key> for the tail analysis (r3, 2026-10-23: with the window kept, +40 gave no frame)"""
    res = {}
    for key in keys:
        import readout_cfg as C, smc
        r = C.BY_KEY[key]; w = max(r['fmt'])
        p = C.plan(key, w * r['mh'] if r['mh'] > 1 else w, 4040, (w // 16) * 16, C.full_rows(key))
        top = 4096 - (smc.attrs_from_plan(p)['y0'] + p['out_h'])
        lo, h = 0, min(hi, top)
        if _try(key, h, out / '_hi'):
            lo = h
        else:
            while h - lo > 1:
                mid = (lo + h) // 2
                if _try(key, mid, out / '_mid'):
                    lo = mid
                else:
                    h = mid
        _try(key, lo, out)
        res[key] = dict(max_extra=lo, capped=lo == min(hi, top))
        print(key, 'max extra', lo, '(tool cap)' if res[key]['capped'] else '', flush=True)
    (out / 'search.json').write_text(json.dumps(res, indent=1))


def main():
    if sys.argv[1] == 'search':
        search(pathlib.Path(sys.argv[2]), sys.argv[3:]); report(pathlib.Path(sys.argv[2])); return
    if sys.argv[1] == 'report':
        report(pathlib.Path(sys.argv[2])); return
    out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    for key in sys.argv[2:]:
        r = subprocess.run([sys.executable, '-c', 'import sweep; sweep.KEEP=None; sweep.fastreboot()'], cwd=HERE, capture_output=True, timeout=300)
        if r.returncode:
            print('camera did not come back -- stopping'); break
        try:
            import thermal
            print('  temp', thermal.read_c(), flush=True)
        except Exception:                               # noqa: BLE001
            pass
        r = subprocess.run([sys.executable, '-u', '-c', f'import rowrange, pathlib; rowrange.capture_one({key!r}, pathlib.Path({str(out)!r}))'],
                           cwd=HERE, capture_output=True, text=True, timeout=300)
        print((r.stdout.strip().splitlines() or ['?'])[-1], ('ERR ' + (r.stderr.strip().splitlines() or ['?'])[-1][:200]) if r.returncode else '', flush=True)


if __name__ == '__main__':
    main()
