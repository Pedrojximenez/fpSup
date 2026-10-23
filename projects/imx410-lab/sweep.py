#!/usr/bin/env python3
"""Detailed register sweeps: many values per register, two readout modes,
reboot only between registers, thresholds from a measured noise floor.

    sweep.py run   PLAN.json OUT_DIR          capture every point (resumable: existing points are skipped)
    sweep.py judge OUT_DIR                    compare every point with its mode's references

PLAN.json: {"registers": [{"reg": "0x5A9", "values": ["0x01", ...], "with": [["0x5A9","0x01"], ...],
                           "sticky": true}, ...], "modes": [10, 8]}
  with    other overrides applied together with each value (e.g. 05A9 bit 0 for a partner hunt)
  sticky  the register is outside the mode table: fastreboot after its last value
For each mode, two back-to-back references open the run; one is retaken every `ref_every` registers and after every reboot + AF;
the ref-vs-ref difference is the noise floor that `judge` measures against.

Mode 10 (1:1): override armed for mode 10, entered through magnify (OK), left again after the capture.
Mode 8 (3x binned live view): override armed for mode 8, set by entering and leaving magnify; after the
capture the override is cleared and the toggle repeated, so stock mode 8 is loaded again.
"""
import argparse, json, pathlib, subprocess, sys, time

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
SHELL = HERE.parents[1] / 'fpSup' / 'fp_usb_shell'
OK = ['--pre', 'key OKON', '--pre', 'key OKOFF']
OKP = ['--post', 'key OKON', '--post', 'key OKOFF']


def probe(*args, timeout=600, log=None):
    r = subprocess.run([sys.executable, '-B', str(HERE / 'bufa_probe.py'), *args], cwd=HERE,
                       capture_output=True, text=True, timeout=timeout)
    if log:                                          # the last step before a wedge is in here
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(r.stdout + r.stderr)
    bad = [l for l in (r.stdout + r.stderr).splitlines()
           if any(k in l for k in ('Error', 'refused', 'no frame', 'did not', 'invalid', 'SystemExit'))]
    return r.returncode == 0 and not bad, bad


KEEP = None                                          # set by cmd_run: the run's buffer file (bufa_probe --keep)
KEEP_SIZE = 20 << 20                                 # >= a mode 10 frame (2062 x 2274 words = 18.8 MB)


YEND = None                                          # plan 'yend': receiver window end row (a smaller frame)


def capture(out, mode, overrides):
    while (HERE / 'captures' / 'PAUSE').exists():   # touch captures/PAUSE: the camera is free between two captures
        time.sleep(2)
    pre, post = [], []
    for n, (reg, val) in enumerate(overrides):
        pre += ['--pre', f'imager mode_reg_add {n} {reg} {val}']
    if overrides:
        pre += ['--pre', f'imager mode_reg_test 1 {mode}']
    if mode == 10:
        pre += OK
        post += OKP
        if overrides:
            post += ['--post', 'imager mode_reg_test 0 10']
    else:                                            # mode 8: in and out of magnify sets mode 8
        pre += OK + OK
        if overrides:
            post += ['--post', 'imager mode_reg_test 0 8'] + OKP + OKP
    keep = ['--keep', str(KEEP), '--keep-size', str(KEEP_SIZE)] if KEEP else []
    if YEND:
        keep += ['--yend', str(YEND)]
    return probe('frame', str(out), '--ystart', '0', '--bus', '--heap-class', '10', *keep, *pre, *post, '--settle', '1.5',
                 log=out / 'probe.log')


def fastreboot():
    """`poff 1` (instant restart, sensor reset -- IMX410_RULES §19), then poll instead of fixed sleeps.
    Never a bare `poff`: that powers the camera off for good."""
    if KEEP and KEEP.exists():
        KEEP.unlink()                                # the buffers die with the boot
    sys.path.insert(0, str(SHELL))
    import putfile
    # An instant restart keeps the firmware image in RAM, the echo slot included. If a capture left echo
    # borrowed, AutoRun's echo lines jump into stale code and the shell never comes back (twice on
    # 2026-10-20, both right after 'echo handler did not become ...'). Restore it, or boot cold.
    try:
        putfile.set_echo_handler(putfile.ECHO_ORIG)
        cmd, wait = 'poff 1', 1.5
    except BaseException:
        cmd, wait = 'reboot', 15
    try:
        putfile.sh(cmd, retries=0, timeout_ms=1500)            # the reply never comes
    except Exception:
        pass
    time.sleep(wait)
    t0 = time.time()
    while time.time() - t0 < 150:
        subprocess.run(['pkill', '-9', '-x', 'fpshd'], capture_output=True)
        d = subprocess.Popen(['./fpshd'], cwd=SHELL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.3)
        r = subprocess.run(['./host/fpsh', 'ping'], cwd=SHELL, capture_output=True, text=True, timeout=10)
        if 'pong' in r.stdout:
            break
        d.kill()
        time.sleep(0.2)
    else:
        raise SystemExit(f'camera did not come back after {cmd}')
    probe('focus', '--hold', '1.0', timeout=60)


def cmd_run(a):
    import fcntl
    lock = open(HERE / 'captures' / '.sweep.lock', 'w')       # one sweep at a time: two once fought over the shell
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('another sweep is running')
    plan = json.loads(pathlib.Path(a.plan).read_text())
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    global KEEP, KEEP_SIZE, YEND
    KEEP = out / 'keep.json'
    if plan.get('yend'):                             # 40 MB of class 10 held across magnify switches looked like
        YEND = plan['yend']                          # the cause of whole-camera freezes (2026-10-20): crop instead
        KEEP_SIZE = (plan['yend'] + 8) * 2274 * 4
    modes = plan.get('modes', [10, 8])
    every = plan.get('ref_every', 4)
    # stock values per mode (research/imx410/analysis/imx410_modes.csv), for xor_bits items
    stock = {m: {int(k, 16): v for k, v in json.loads((HERE / 'captures' / f'mode{m}_regs.json').read_text()).items()}
             for m in modes if (HERE / 'captures' / f'mode{m}_regs.json').exists()}
    log = open(out / 'run.log', 'a')
    say = lambda s: (print(s, flush=True), log.write(s + '\n'), log.flush())

    def ref(tag):
        for m in modes:
            d = out / f'ref_m{m}_{tag}'
            if not captured(d):
                ok, bad = capture(d, m, [])
                if ok:
                    summarize(d)
                    if tag not in ('a', 'b') and not plan.get('keep_raw'):
                        (d / 'frame.raw').unlink()     # only the two noise-floor references keep the frame
                say(f'{time.strftime("%T")} {d.name} {"ok" if ok else bad}')

    fresh = not captured(out / f'ref_m{modes[0]}_a')
    ref('a'); ref('b')                               # the noise floor: two back to back
    if not fresh:                                    # a resume: this boot's AF needs its own reference
        ref(time.strftime('s%H%M%S'))
    fails = 0
    for k, item in enumerate(plan['registers']):
        if (out / 'STOP').exists():
            say('stopped'); break
        # after a reboot the AF may land differently: a fresh reference for every register that follows one
        if k and (k % every == 0 or plan['registers'][k - 1].get('sticky', True)):
            ref(f'r{k:03d}')
        reg = item['reg']
        if item.get('xor_bits'):                      # every bit flipped against the mode's own stock value
            values = {m: [f'0x{stock[m][int(reg, 16)] ^ (1 << b):02X}' for b in range(8)] for m in modes}
        else:
            values = {m: item['values'] for m in modes}
        touched = False                                # wrote this register since the last reset
        for i in range(len(values[modes[0]])):
            for m in modes:
                val = values[m][i]
                d = out / (f'{reg}_b{i}_{val}_m{m}' if item.get('xor_bits') else f'{reg}_{val}_m{m}')
                if captured(d):
                    continue
                if 'no frame seen' in ((d / 'probe.log').read_text() if (d / 'probe.log').exists() else ''):
                    continue                           # a value that stops the sensor: once is enough on a resume
                ok, bad = capture(d, m, [*item.get('with', []), [reg, val]])
                touched = True
                if ok:
                    summarize(d)
                    if not plan.get('keep_raw'):
                        (d / 'frame.raw').unlink()     # the summary is what judging reads
                say(f'{time.strftime("%T")} {d.name} {"ok" if ok else bad}')
                fails = 0 if ok else fails + 1
                if fails >= 2:                         # a value stopped the sensor: reset it, new refs
                    say(f'{time.strftime("%T")} two failures in a row: sensor reset')
                    fastreboot(); ref(f'r{k:03d}x{i}{m}'); fails = 0; touched = False
            if item.get('reboot_each') and touched:
                fastreboot(); ref(f'r{k:03d}v{i}'); touched = False
        if item.get('sticky', True) and not item.get('reboot_each') and touched:
            fastreboot()                               # resumed items that were already done: no reset
    say('done')


# ---- judging -----------------------------------------------------------------------------------
sys.path.insert(0, str(HERE))


def load(d):
    from decode12 import decode12
    m = json.loads((d / 'frame.json').read_text())
    img = decode12((d / 'frame.raw').read_bytes(), m['height'], m['line_words']).astype(np.float64)
    top = m['window'] >> 16
    black = img[1:top - 3].mean()
    return img[top:] - black, black


def summarize(d):
    """Everything judge/rawlv/rowgroup need from one frame, ~0.3 MB instead of 19 MB (the disk filled up on
    2026-10-20 at 56 GB of frames). Written once per capture; judging prefers it to frame.raw."""
    from decode12 import decode12
    m = json.loads((d / 'frame.json').read_text())
    img = decode12((d / 'frame.raw').read_bytes(), m['height'], m['line_words']).astype(np.float64)
    top = m['window'] >> 16
    black = img[1:top - 3].mean()
    a = img[top:]
    f = features(a - black)
    ob = img[2:top - 3, 100:-100]
    def blk(q, b=32):
        h, w = (q.shape[0] // b) * b, (q.shape[1] // b) * b
        return q[:h, :w].reshape(h // b, b, w // b, b).mean(axis=(1, 3))
    np.savez_compressed(d / 'summary.npz', t=time.time(), black=black, shape=np.array(a.shape),
                        means=f['means'], tex=f['tex'], **{f'rows{i}': r for i, r in enumerate(f['rows'])},
                        **{f'cols{i}': c for i, c in enumerate(f['cols'])},
                        ob=np.array([ob[0::2].mean(), ob[1::2].mean()]),
                        obnoise=np.array([np.std(np.diff(ob[q::2], axis=1)) / np.sqrt(2) for q in (0, 1)]),
                        act=np.array([a[i::2, j::2].mean() for i in (0, 1) for j in (0, 1)]), std=a.std(),
                        **{f'blk{i}{j}': blk(a[i::2, j::2] - black) for i in (0, 1) for j in (0, 1)})


def load_summary(d):
    z = np.load(d / 'summary.npz')
    f = dict(means=z['means'], tex=z['tex'], rows=[z[f'rows{i}'] for i in range(4)], cols=[z[f'cols{i}'] for i in range(4)])
    return f, float(z['black']), tuple(z['shape']), float(z['t'])


def captured(d):
    return (d / 'summary.npz').exists() or ((d / 'frame.raw').exists() and (d / 'frame.json').exists())


def feat(d):
    """(features, black, shape, time) from the summary, making one from frame.raw if needed."""
    if not (d / 'summary.npz').exists():
        summarize(d)
    return load_summary(d)


def features(x):
    """Per-phase means, row and column profiles (per phase), local texture."""
    ph = [x[i::2, j::2] for i in (0, 1) for j in (0, 1)]
    return dict(means=np.array([p.mean() for p in ph]),
                rows=[p.mean(axis=1) for p in ph], cols=[p.mean(axis=0) for p in ph],
                tex=np.array([np.abs(np.diff(p, axis=1)).mean() for p in ph]))


def compare(fx, fr):
    """Largest normalised deviations of x against a reference."""
    mr = np.log(np.maximum(fx['means'], 1e-3) / np.maximum(fr['means'], 1e-3))
    tr = np.log(np.maximum(fx['tex'], 1e-3) / np.maximum(fr['tex'], 1e-3))
    rd = max(np.abs(np.log(np.maximum(a, 1e-3) / np.maximum(b, 1e-3)) - np.median(np.log(np.maximum(a, 1e-3) / np.maximum(b, 1e-3)))).max()
             for a, b in zip(fx['rows'], fr['rows']))
    cd = max(np.abs(np.log(np.maximum(a, 1e-3) / np.maximum(b, 1e-3)) - np.median(np.log(np.maximum(a, 1e-3) / np.maximum(b, 1e-3)))).max()
             for a, b in zip(fx['cols'], fr['cols']))
    return dict(phase=mr, spread=float(mr.max() - mr.min()), tex=float(np.abs(tr).max()), rows=float(rd), cols=float(cd))


def cmd_judge(a):
    out = pathlib.Path(a.out)
    pts = [d for d in out.iterdir() if captured(d)]
    F = {d: feat(d) for d in pts}
    pts.sort(key=lambda d: F[d][3])
    refs = {}
    for d in pts:
        if d.name.startswith('ref_m'):
            refs.setdefault(int(d.name.split('_')[1][1:]), []).append(d)
    floor = {}
    for m, rs in refs.items():
        f = [F[r][0] for r in rs[:2]]
        c = compare(f[0], f[1])
        floor[m] = dict(phase=float(np.abs(c['phase']).max()), spread=c['spread'], tex=c['tex'], rows=c['rows'], cols=c['cols'])
        print(f'mode {m} noise floor (ref a vs b): {floor[m]}')
    rows = []
    for d in pts:
        if d.name.startswith('ref_m'):
            continue
        m = int(d.name.rsplit('_m', 1)[1])
        ref = max([r for r in refs[m] if F[r][3] < F[d][3]] or refs[m][:1], key=lambda r: F[r][3])
        (fx, xb, xs, _), (fr, rb, rs_, _) = F[d], F[ref]
        if xs != rs_:
            print(f'** {d.name}: shape {xs} vs {rs_}'); continue
        c = compare(fx, fr)
        fl = floor[m]
        score = dict(level=float(np.abs(c['phase']).max()) / max(fl['phase'], 0.005),
                     colour=c['spread'] / max(fl['spread'], 0.005), tex=c['tex'] / max(fl['tex'], 0.005),
                     rows=c['rows'] / max(fl['rows'], 0.005), cols=c['cols'] / max(fl['cols'], 0.005),
                     black=abs(xb - rb))
        hit = max(score['level'], score['colour'], score['tex'], score['rows'], score['cols']) > a.k or score['black'] > 2
        rows.append(dict(point=d.name, ref=ref.name, hit=bool(hit), phase_ratio=np.round(np.exp(c['phase']), 3).tolist(),
                         **{k: round(v, 2) for k, v in score.items()}))
        print(('** ' if hit else '   ') + f'{d.name:22s} ratio {np.round(np.exp(c["phase"]), 3).tolist()}  '
              f'×floor: level {score["level"]:.1f} colour {score["colour"]:.1f} tex {score["tex"]:.1f} '
              f'rows {score["rows"]:.1f} cols {score["cols"]:.1f}  dblack {score["black"]:.1f}')
    (out / 'judge.json').write_text(json.dumps(dict(floor=floor, points=rows), indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('run'); s.set_defaults(f=cmd_run); s.add_argument('plan'); s.add_argument('out')
    s = sub.add_parser('judge'); s.set_defaults(f=cmd_judge); s.add_argument('out')
    s.add_argument('--k', type=float, default=4.0, help='a point is a hit above k x the ref-vs-ref floor')
    a = ap.parse_args()
    a.f(a)


if __name__ == '__main__':
    main()
