"""One take with FCAP loaded: does a compressed LOSS take run past the 94-frame stop?

Usage: python3 -B fcap_take.py LABEL [--secs 8] [--expect-cap 1|0]
Before: idle, CINE; reads 0xC063F824 (the FCAP word; 0x2A282002 loaded, 0x2A802002 stock).
Take:   MOVON pulse, NO USB traffic for --secs, stop pulse, 10 s quiet.
After:  is_recording; if it is 1 the take had already stopped by itself and the
        stop pulse started a new one -> one more pulse, flagged early_stop.
        rec log-out (batches: reqcnt column), LOSS counters, saved to take-LABEL.json.
Writes nothing but the two key pulses.
"""
import argparse, json, re, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(ROOT / 'fpSup/fp_usb_shell'), str(ROOT / 'fpSup/lossless')]
import putfile as pf
import card_status as cs

SITE = 0xC063F824
WORD = {1: 0x2A282002, 0: 0x2A802002}
LAYOUT = ROOT / 'projects/lossless-sup/validation/20261014-observer-tag/build-plain/layout.json'

ap = argparse.ArgumentParser(); ap.add_argument('label')
ap.add_argument('--secs', type=float, default=8.0)
ap.add_argument('--expect-cap', type=int, default=1, choices=(0, 1))
a = ap.parse_args()
out = HERE / f'take-{a.label}.json'; assert not out.exists(), out
sh = lambda c, t=15000: pf.sh(c, retries=0, timeout_ms=t)
fields = json.loads(LAYOUT.read_text())['fields']

assert sh('status get is_recording').strip() == 'is_recording -> 0'
assert sh('status get app_current').strip() == 'app_current -> 2'
w = pf.mem_get(SITE)[0]
assert w == WORD[a.expect_cap], f'0xC063F824 = 0x{w:08X}, expected 0x{WORD[a.expect_cap]:08X}'
_, st, _ = cs.find_record(pf.mem_get)
names = [k for k in fields if k in ('rec_admitted', 'stops', 'finishes', 'flush.applied', 'flush.tag_failed')
         or (k.startswith(('hold.', 'hold_b.')) and k.split('.')[-1] in ('compressed', 'passed', 'refused', 'lanes_full'))]
snap = lambda: {k: pf.mem_get(st + fields[k])[0] for k in names}
r = {'label': a.label, 'secs': a.secs, 'site_word': f'0x{w:08X}',
     'settings': {c: sh(c).strip() for c in ('menu SetMovRecSize', 'gui geti MV_FrameRate',
                                             'gui geti MV_fpLossless', 'sdcard sdmode')},
     'before': snap()}

def pulse():
    try: sh('key MOVON')
    finally: time.sleep(.12); sh('key MOVOFF')

t0 = time.time(); pulse()
time.sleep(max(0, a.secs - (time.time() - t0)))
pulse(); r['stop_at'] = round(time.time() - t0, 2)
time.sleep(10)
r['early_stop'] = sh('status get is_recording').strip().endswith('1')
if r['early_stop']:                       # our stop pulse started a second take
    pulse(); time.sleep(10)
    assert sh('status get is_recording').strip().endswith('0')
r['after'] = snap()
log = sh('rec log-out'); r['record_log'] = log[log.find('file-size'):]
rows = [list(map(int, re.findall(r'-?\d+', ln))) for ln in r['record_log'].splitlines()[3:]]
cnt = [row[4] for row in rows if len(row) >= 9]
r['batch_frames'] = [b - a_ for a_, b in zip([0] + cnt, cnt)]
out.write_text(json.dumps(r, indent=1))
print(json.dumps({k: r[k] for k in ('site_word', 'settings', 'stop_at', 'early_stop', 'batch_frames')}, indent=1))
print({k: r['after'][k] - r['before'][k] for k in names})
print(r['record_log'])
