#!/usr/bin/env python3
"""Run readout_validate on a list of planner configurations, one fresh boot each (DEV_PLAN D1 milestone 2).

    readout_batch.py OUT [--set core|matrix] [--only KEY,KEY]      each line: KEY CROP OUT FPS  (CROP/OUT as WxH)
Already-passed ids are skipped; a config that raises in planning is recorded as skipped.
"""
import argparse, json, pathlib, subprocess, sys, time
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import readout_cfg as C

CORE = [  # (key, crop, out, fps) -- one per readout, at a size each can do, fps = its own max (None)
    ('12',      (6060, 3408), (3840, 2160), None),
    ('12',      (3840, 2160), (3840, 2160), None),
    ('14',      (4152, 2160), (3840, 2160), None),
    ('12fast',  (4176, 2016), (4160, 2016), None),
    ('12fastW', (6060, 3408), (3840, 2160), None),
    ('2x2',     (6060, 3408), (1920, 1080), None),
    ('2x2fast', (3840, 2160), (1920, 1080), None),
    ('3x3',     (6060, 3408), (1920, 1080), None),
    ('3x3fast', (5760, 3240), (1920, 1080), None),
    ('3x6',     (6060, 4040), (1008, 662), None),
    ('3x6fast', (6060, 4040), (1008, 662), None),
]


MATRIX = []                                            # every new readout class at full frame (readout_cfg matrix)
for _r in C.READOUTS:
    if _r.get('new'):
        _w = max(_r['fmt'])
        MATRIX.append((_r['key'], (_w * _r['mh'] if _r['mh'] > 1 else _w, 4040), (_w, int(4040 / _r['mv']) // 2 * 2), None))


HDR_H1 = ['12', '14', '12fastW', '12v2', '12v3', '14v2', '14v3', 'f12v2', 'f12v3']   # 1x1 / vertical merges (§30)
HDR_PROBE = ['12h2', '12h3', '2x2', '3x3']                                          # horizontal merges: expected not to work


def hdr_set():
    out = []
    for key in HDR_H1 + HDR_PROBE:                      # full frame, 0738 = 0x20
        r = C.BY_KEY[key]; w = max(r['fmt']); cw = w * r['mh'] if r['mh'] > 1 else w
        out.append((key, (cw, 4040), ((cw // r['mh']) // 16 * 16, int(4040 / r['mv']) // 2 * 2), None, 0x20))
    for key in HDR_H1:                                  # crops: 3/4 width, windows 3408 / 2160 rows
        r = C.BY_KEY[key]; w = max(r['fmt'])
        cw = int(w * 0.75) // 12 * 12
        out.append((key, (cw, 4040), (cw // 16 * 16, int(4040 / r['mv']) // 2 * 2), None, 0x20))
        for ch in (3408, 2160):
            out.append((key, (w, ch), (w // 16 * 16, int(ch / r['mv']) // 2 * 2), None, 0x20))
    return sorted(out, key=lambda c: C.BY_KEY[c[0]]['bits'] == 14)   # 14-bit last: the V2 base entry wedged twice


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out'); ap.add_argument('--only', default=''); ap.add_argument('--set', default='core', choices=('core', 'matrix', 'hdr')); ap.add_argument('--fresh', action='store_true')
    a = ap.parse_args()
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    done = C.validated()

    def focus():                                       # user rule: AF after every (re)boot and at the start of a run
        subprocess.run([sys.executable, 'bufa_probe.py', 'focus', '--hold', '1.0'], cwd=HERE, capture_output=True, timeout=90)
    focus()
    cfgs = {'matrix': MATRIX, 'hdr': hdr_set(), 'core': CORE}[a.set]
    for key, (cw, ch), (ow, oh), fps, *more in cfgs:
        hdr = more[0] if more else 0
        if a.only and key not in a.only.split(','):
            continue
        try:
            p = C.plan(key, cw, ch, ow, oh, fps, hdr=hdr)
        except ValueError as e:
            print(f'{key} {cw}x{ch}>{ow}x{oh}: skipped ({e})', flush=True); continue
        if done.get(p['id'], {}).get('PASS'):
            print(f"{p['id']}: already passed", flush=True); continue
        print(f"== {p['id']}  ({p['fps']:.1f} fps, RS {p['rolling_ms']:.2f} ms)", flush=True)
        chk = subprocess.run([sys.executable, '-c', 'import vmode; vmode.check_stock()'], cwd=HERE, capture_output=True, text=True, timeout=120)
        if a.fresh and not chk.returncode:             # --fresh: poff before every config (matrix round 2: the shell
            chk = subprocess.CompletedProcess([], 1)   # died at config 3 and 7 after a boot -- accumulated state?)
        if chk.returncode:                             # only reboot when the previous config left something behind
            print('  not stock -> fastreboot', flush=True)
            rb = subprocess.run([sys.executable, '-c', 'import sweep; sweep.KEEP=None; sweep.fastreboot()'], cwd=HERE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
            if rb.returncode:
                print('camera did not come back -- stopping', flush=True); break
            focus()
        try:                                           # sensor temperature before every config (user 10-23: runs hot)
            import thermal
            _t = thermal.wait_cool(); thermal.log(out / 'thermal.jsonl', p['id'])
            print(f"  temp {_t.get('C')}", flush=True)
        except Exception as _e:                        # noqa: BLE001
            print('  temp read failed', _e, flush=True)
        try:
            r = subprocess.run([sys.executable, '-u', '-c',
                            f'import json,pathlib,readout_validate as V; V.run(json.loads({json.dumps(json.dumps(p, default=str))!s}), pathlib.Path({str(out)!r}) / {p["id"].replace(":", "_").replace(">", "_")!r})'],
                               cwd=HERE, capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired as e:         # matrix round 2: f12h2 hung the shell -- keep what it printed, stop
            (out / (p['id'].replace(':', '_').replace('>', '_') + '.log')).write_text(str(e.stdout or '') + '\n--- stderr\n' + str(e.stderr or ''))
            print('  TIMEOUT -- shell probably wedged; stopping the batch', flush=True)
            break
        (out / (p['id'].replace(':', '_').replace('>', '_') + '.log')).write_text(r.stdout + '\n--- stderr\n' + r.stderr)
        for line in r.stdout.splitlines():
            if line.startswith(('lines', 'bayer', 'rowphase', 'linearity', 'burst', 'RESULT')):
                print('  ' + line[:200], flush=True)
        if r.returncode:
            print('  ERROR', (r.stderr.strip().splitlines() or ['?'])[-1][:200], flush=True)


if __name__ == '__main__':
    main()
