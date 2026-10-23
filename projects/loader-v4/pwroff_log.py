#!/usr/bin/env python3
"""Read what the last power-off decided (v4 build with --pwroff-log).

    python3 -B projects/loader-v4/pwroff_log.py LABEL     # e.g. usb-1, nousb-3

Run right after the camera is up again (read-only: mem get only).  Appends one
JSON line to projects/loader-v4/validation/pwroff_log.jsonl.

Records (fpSup/loader-v4/sloader4.c, PWROFF_LOG):
  early  XC_CommonSaveData + 0x210 (0xC307544C), 28 words, written by the core's
         power-off routine before the settings flush -> survives a cold boot.
  late   a cave block (address = early[2]), 13 words, written by the wrapper
         around the stock veto callback C0023B60, inside C0122F90 just before it
         writes 0x2D000400 -> survives only a warm (self-refresh) restart.
This boot: 0x2D000280 bit0 = 1 means IPL took the self-refresh path (instant start).
"""
import json, pathlib, sys, time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'fpSup/fp_usb_shell'))
from putfile import mem_get

STORE, WORDS = 0xC307544C, 28
MAGIC, LMAGIC = 0x314C5750, 0x4C4C5750
EARLY = ['magic', 'seq', 'late_at', 'calls', 'reason', 't_us', 'mgr_08', 'mgr_60', 'mgr_68', 'mgr_6C', 'mgr_70',
         'pmu_300', 'pmu_304', 'pmu_308', 'pmu_30C', 'pmu_280', 'cb', 'cb_230', 'cb_234', 'armed', 'boot_id']
LATE = ['magic', 'seq', 'stage', 'ret', 't_us', 'pmu_300', 'pmu_304', 'pmu_308', 'pmu_30C', 'cb_230', 'cb_234',
        'pmu_280', 't_us_after']


def rd(a, n):
    for _ in range(6):
        w = mem_get(a, n)
        if None not in w:
            return w
    raise SystemExit(f'read {a:#x}: words missing')


def predict(e, l):
    """The command C0122F90 wrote, from the records (IMAGE_RETENTION.md §2a)."""
    if e['mgr_60'] in (3, 4, 6):
        return 0x20, 'reason 3/4/6 -> mode 2'
    if l is None:
        return None, 'no late record (cold boot, or the callback path was not reached)'
    if e['cb_230'] == 2:
        r5 = l['cb_234'] == 1 and bool(l['pmu_308'] or l['pmu_30C'])
    else:   # r5 == 0 made C0122F90 clear 308/30C to -1 before the callback
        cleared = l['pmu_308'] == 0xFFFFFFFF and l['pmu_30C'] == 0xFFFFFFFF
        r5 = not cleared
    if l['stage'] != 2:
        return 0x40 if r5 else None, 'stock callback did not return (its own reset path)'
    why = 'wake factors' if r5 else ('callback veto' if l['ret'] else 'none')
    return (0x40 if (r5 or l['ret']) else 0x10), why


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else time.strftime('%H%M%S')
    now280 = rd(0x2D000280, 1)[0]
    s = rd(STORE, WORDS)
    out = {'label': label, 'time': time.strftime('%Y-%m-%d %H:%M:%S'),
           'this_boot_pmu_280': hex(now280), 'this_boot_instant': bool(now280 & 1)}
    if s[0] != MAGIC:
        out['early'] = None
        print(json.dumps(out, indent=1))
        print('no early record: not a --pwroff-log build, or no power-off since it went on the card')
    else:
        e = dict(zip(EARLY, s))
        out['early'] = {k: (hex(v) if k not in ('seq', 'calls', 'reason', 'armed') else v) for k, v in e.items()}
        l = None
        if e['late_at']:
            w = rd(e['late_at'], len(LATE))
            if w[0] == LMAGIC and w[1] == e['seq']:
                l = dict(zip(LATE, w))
        out['late'] = {k: (hex(v) if k not in ('seq', 'stage', 'ret') else v) for k, v in l.items()} if l else None
        cmd, why = predict(e, l)
        out['command'] = hex(cmd) if cmd is not None else None
        out['why'] = why
        print(json.dumps(out, indent=1))
        print(f"\nseq {e['seq']}  reason {e['reason']}/mgr+60 {e['mgr_60']}  mgr+08 {e['mgr_08']:#x}  "
              f"wake 308/30C at early {e['pmu_308']:#x}/{e['pmu_30C']:#x}  armed {e['armed']}")
        print(f"command {out['command']} ({why});  this boot {'INSTANT' if now280 & 1 else 'cold'}")
    log = ROOT / 'projects/loader-v4/validation/pwroff_log.jsonl'
    with log.open('a') as f:
        f.write(json.dumps(out) + '\n')


if __name__ == '__main__':
    main()
