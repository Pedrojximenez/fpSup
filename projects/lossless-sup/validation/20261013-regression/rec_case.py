"""One bounded regression take on the current LOSS build.

Usage: python3 -B rec_case.py LABEL LAYOUT_JSON [--size N] [--rate N] [--seconds S]

Idle checks; optional `menu SetMovRecSize/SetMovFramerate` (RAM menu values,
nothing saved); MOVON; stop pulse at --seconds if still recording; then waits
up to 60 s for the writer to finish (XMP object 0xC358E140 back to 0 and
is_recording 0). A writer that does not finish is reported as HANG and the
script stops there -- nothing else is sent. Saves rec-LABEL.json: settings,
the LOSS per-take counters, the stock record log. Writes no LOSS state.
"""
import argparse, json, re, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT / 'fpSup/fp_usb_shell'), str(ROOT / 'fpSup/lossless')]
import putfile as pf
import card_status as cs

ap = argparse.ArgumentParser(); ap.add_argument('label'); ap.add_argument('layout', type=Path)
ap.add_argument('--size', type=int); ap.add_argument('--rate', type=int)
ap.add_argument('--seconds', type=float, default=2.0)
a = ap.parse_args()
out = HERE / f'rec-{a.label}.json'; assert not out.exists()
fields = json.loads(a.layout.read_text())['fields']
sh = lambda c, t=15000: pf.sh(c, retries=0, timeout_ms=t)
assert sh('status get is_recording').strip() == 'is_recording -> 0'
assert sh('status get app_current').strip() == 'app_current -> 2'
assert pf.mem_get(0xC358E140)[0] == 0
if a.size is not None: sh(f'menu SetMovRecSize {a.size}')
if a.rate is not None: sh(f'menu SetMovFramerate {a.rate}')
if a.size is not None or a.rate is not None: time.sleep(3)
_, st, _ = cs.find_record(pf.mem_get)
names = [k for k in fields if k.startswith(('hold.', 'hold_b.', 'flush.', 'rec.facts.seen.')) and
         k.split('.')[-1] in ('held', 'compressed', 'refused', 'no_benefit', 'passed', 'lanes_full',
                              'applied', 'trailer_failed', 'length_mismatch', 'built', 'reused',
                              'fallback', 'width', 'height', 'bits', 'stalls', 'faults')]
names += [k for k in ('rec_events', 'rec_admitted', 'rec_raw', 'rec_menu_off', 'hold_live') if k in fields]
snap = lambda: {k: pf.mem_get(st + fields[k])[0] for k in names}
r = {'label': a.label, 'settings': {c: sh(c).strip() for c in (
    'menu SetMovRecSize', 'menu SetMovFramerate', 'gui geti MV_FrameRate',
    'gui geti MV_fpLossless', 'sdcard sdmode')}, 'before': snap()}
def pulse():
    try: sh('key MOVON')
    finally: time.sleep(.12); sh('key MOVOFF')
t0 = time.time(); pulse()
time.sleep(1.0)
r['recording_at_1s'] = sh('status get is_recording').strip()
time.sleep(max(0, a.seconds - (time.time() - t0)))
if sh('status get is_recording').strip().endswith('1'):
    pulse(); r['stop_at'] = round(time.time() - t0, 2)
else:
    r['stopped_by_itself_before'] = round(time.time() - t0, 2)
r['finished'] = False
for i in range(60):
    time.sleep(1)
    if pf.mem_get(0xC358E140)[0] == 0 and sh('status get is_recording').strip().endswith('0'):
        r['finished'] = True; r['finish_wait_s'] = i + 1; break
r['after'] = snap()
log = sh('rec log-out'); r['record_log'] = log[log.find('file-size'):]
m = re.search(r'req_cnt=(\d+), fin_cnt=(\d+)', r['record_log'])
r['req_fin'] = [int(m[1]), int(m[2])] if m else None
out.write_text(json.dumps(r, indent=1))
print('HANG' if not r['finished'] else 'finished', r.get('stop_at') or r.get('stopped_by_itself_before'),
      'req/fin', r['req_fin'], r['settings']['gui geti MV_FrameRate'])
print({k: v for k, v in r['after'].items() if v})
