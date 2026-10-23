"""One bounded take with a native task-CPU window, for step-by-step comparison.

Usage: python3 -B cpu_take.py LABEL LAYOUT_JSON [--seconds 4]
Idle checks; MOVON; after 1 s, tskmon over 2 s; stop pulse at --seconds if
still recording; wait for the writer; save task top, LOSS hold counters and
the stock record log to cpu-LABEL.json. No LOSS state is written.
"""
import argparse, json, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT / 'fpSup/fp_usb_shell'), str(ROOT / 'fpSup/lossless')]
import putfile as pf
import card_status as cs

ap = argparse.ArgumentParser(); ap.add_argument('label'); ap.add_argument('layout', type=Path)
ap.add_argument('--seconds', type=float, default=4.0)
a = ap.parse_args()
out = HERE / f'cpu-{a.label}.json'; assert not out.exists()
fields = json.loads(a.layout.read_text())['fields']
sh = lambda c, t=15000: pf.sh(c, retries=0, timeout_ms=t)
assert sh('status get is_recording').strip() == 'is_recording -> 0'
assert sh('status get app_current').strip() == 'app_current -> 2'
assert pf.mem_get(0xC358E140)[0] == 0
_, st, _ = cs.find_record(pf.mem_get)
names = [k for k in fields if k.startswith(('hold.', 'hold_b.')) and k.split('.')[-1] in
         ('held', 'compressed', 'refused', 'no_benefit', 'passed', 'lanes_full', 'job_count', 'job_sum_us')]
snap = lambda: {k: pf.mem_get(st + fields[k])[0] for k in names}
r = {'label': a.label, 'settings': {c: sh(c).strip() for c in ('menu SetMovRecSize', 'menu SetMovFramerate',
     'gui geti MV_FrameRate', 'gui geti MV_fpLossless', 'sdcard sdmode')}, 'before': snap()}
def pulse():
    try: sh('key MOVON')
    finally: time.sleep(.12); sh('key MOVOFF')
t0 = time.time(); pulse()
time.sleep(max(0, 1.0 - (time.time() - t0)))
sh('analyzer tskmon_start 32768 64 1000000 52'); r['mon_start'] = round(time.time() - t0, 2)
time.sleep(2.0)
r['task_top'] = sh('analyzer tskmon_top 0 12'); r['mon_end'] = round(time.time() - t0, 2)
sh('analyzer tskmon_stop')
time.sleep(max(0, a.seconds - (time.time() - t0)))
if sh('status get is_recording').strip().endswith('1'):
    pulse(); r['stop_at'] = round(time.time() - t0, 2)
for _ in range(60):
    time.sleep(1)
    if pf.mem_get(0xC358E140)[0] == 0 and sh('status get is_recording').strip().endswith('0'): break
r['after'] = snap()
log = sh('rec log-out'); r['record_log'] = log[log.find('file-size'):]
out.write_text(json.dumps(r, indent=1))
print(r['task_top'].split('# Total')[0])
print({k: r['after'][k] - r['before'][k] for k in names})
print('mon', r['mon_start'], r['mon_end'], 'stop', r.get('stop_at')); print(r['record_log'])
