#!/usr/bin/env python3
"""Read \\fpSup\\PWROFF.LOG (build_v4.py --pwroff-file) and say what the last
power-off saw.  Read-only: getfile of one 128 B file plus one register read.

    python3 -B projects/loader-v4/pwroff_file.py <label>

The record is written by the core's power-off routine from XC_PowerOffMgr's
lists, while the card is still mounted, so it survives a cold boot.  It is
taken BEFORE C0122F90 decides 0x10/0x40, so it shows the inputs of that
decision, not the decision itself; this boot's 0x2D000280 bit0 says which way
it went (1 = instant/self-refresh, 0 = cold).  A missing file, or a sequence
that did not advance since the last run, means the routine did not run.
Appends to projects/loader-v4/validation/pwroff_file.jsonl.
"""
import json, pathlib, struct, subprocess, sys, tempfile, time

HERE = pathlib.Path(__file__).resolve().parent
SH = HERE.parents[1] / 'fpSup' / 'fp_usb_shell'
sys.path.insert(0, str(SH))
from putfile import mem_get                                    # noqa: E402

PATH, WORDS, MAGIC = '\\fpSup\\PWROFF.LOG', 32, 0x31465750
OUT = HERE / 'validation' / 'pwroff_file.jsonl'
CB_STOCK = 0xC0023B60
F = ['magic', 'seq', 'call', 'reason', 't_us', 'now_ms', 'mgr_08', 'mgr_60', 'mgr_68', 'mgr_6C', 'mgr_70',
     'pmu_300', 'pmu_304', 'pmu_308', 'pmu_30C', 'pmu_314', 'pmu_280', 'ext_power', 'busy', 'cb', 'cb_230',
     'cb_234', 'fusb_switch', 'fusb_armed', 'fusb_wrapper', 'boot_id', 'load_done_us']


def read_file():
    with tempfile.TemporaryDirectory() as t:
        dst = pathlib.Path(t) / 'p.log'
        subprocess.run(['python3', '-B', str(SH / 'getfile.py'), PATH, str(dst), '--size', str(4 * WORDS)],
                       capture_output=True, text=True, cwd=SH)
        return dst.read_bytes() if dst.exists() else None


def last_seq():
    if not OUT.exists():
        return None
    for line in reversed(OUT.read_text().splitlines()):
        try:
            r = json.loads(line).get('record')
            if r:
                return r['seq']
        except Exception:
            pass
    return None


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else time.strftime('%H%M%S')
    now280 = mem_get(0x2D000280)[0]
    out = {'label': label, 'time': time.strftime('%Y-%m-%d %H:%M:%S'),
           'this_boot_pmu_280': hex(now280) if now280 is not None else None,
           'this_boot_instant': bool(now280 & 1) if now280 is not None else None, 'record': None}
    raw = read_file()
    prev = last_seq()
    if not raw or len(raw) < 4 * WORDS:
        out['verdict'] = 'no PWROFF.LOG: not a --pwroff-file build, or the power-off routine never ran'
    else:
        w = struct.unpack(f'<{WORDS}I', raw[:4 * WORDS])
        if w[0] != MAGIC or w[-1] != (~MAGIC & 0xFFFFFFFF):
            out['verdict'] = 'PWROFF.LOG present but not a valid record'
        else:
            r = dict(zip(F, w))
            out['record'] = r
            m69 = (r['mgr_68'] >> 8) & 0xFF
            cond1 = m69 != 0 and r['mgr_60'] != 5
            wake = any(r[k] for k in ('pmu_300', 'pmu_304', 'pmu_308', 'pmu_30C'))
            wrapped = r['cb'] != CB_STOCK and r['cb'] == r['fusb_wrapper'] and r['fusb_wrapper'] != 0
            ran = prev is None or r['seq'] != prev
            out['analysis'] = {
                'routine ran this power-off': ran if prev is not None else 'unknown (first read)',
                'reason': r['reason'],
                'cond1 mgr+0x69!=0 && mgr+0x60!=5': cond1,
                'external power byte': r['ext_power'],
                'busy [0xC3075748]': hex(r['busy']),
                'raw inputs 0x2D000314 (VBUS = id2, mapping via table 0xC07D1308)': hex(r['pmu_314']),
                'wake factors 0x2D000300..30C non-zero': wake,
                'veto callback': 'our FUSB wrapper' if wrapped else ('stock C0023B60' if r['cb'] == CB_STOCK else hex(r['cb'])),
                'FUSB switch / times armed': ('removed (2026-10-20)' if r['fusb_switch'] == 0xFFFFFFFE
                                              else (r['fusb_switch'], r['fusb_armed'])),
            }
            if not ran:
                out['verdict'] = f'sequence {r["seq"]} did not advance: the power-off routine did not run (or failed to write)'
            elif out['this_boot_instant']:
                out['verdict'] = 'routine ran; this boot was instant (0x10)'
            else:
                why = []
                if wake:
                    why.append('wake factors were set (C0122F90 then sends 0x40)')
                if cond1 and r['ext_power'] and not r['busy']:
                    why.append('veto inputs present (cond1, external power, not busy)')
                if r['reason'] in (3, 4, 6):
                    why.append(f'reason {r["reason"]} takes mode 2 (0x20)')
                out['verdict'] = 'routine ran; this boot was cold. Candidates: ' + ('; '.join(why) or 'none of the recorded inputs -- the cause is after this record')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open('a') as f:
        f.write(json.dumps(out) + '\n')
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main()
