"""One take that measures how long the shell takes to answer while recording.

Usage: python3 -B responsive_take.py LABEL [--seconds 2]
Idle checks, one MOVON pulse, then a light command every 0.3 s with its
round-trip time; the stop pulse at --seconds (only if still recording);
then waits for the writer to go idle and saves the stock record log.
"""
import argparse, json, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3] / 'fpSup/fp_usb_shell'))
import putfile as pf

ap = argparse.ArgumentParser(); ap.add_argument('label'); ap.add_argument('--seconds', type=float, default=2.0)
a = ap.parse_args()
out = HERE / f'resp-{a.label}.json'; assert not out.exists()
sh = lambda c, t=15000: pf.sh(c, retries=0, timeout_ms=t)
assert sh('status get is_recording').strip() == 'is_recording -> 0'
assert sh('status get app_current').strip() == 'app_current -> 2'
assert pf.mem_get(0xC358E140)[0] == 0
def pulse():
    try: sh('key MOVON')
    finally: time.sleep(.12); sh('key MOVOFF')
r = {'label': a.label, 'polls': []}
t0 = time.time(); pulse(); stopped = False
while time.time() - t0 < a.seconds + 20:
    s = time.time()
    rec = sh('status get is_recording').strip()
    r['polls'].append([round(s - t0, 2), round(time.time() - s, 3), rec[-1]])
    if not stopped and time.time() - t0 >= a.seconds:
        if rec.endswith('1'): pulse(); r['stop_at'] = round(time.time() - t0, 2)
        stopped = True
    if stopped and rec.endswith('0') and pf.mem_get(0xC358E140)[0] == 0: break
    time.sleep(.3)
log = sh('rec log-out'); r['record_log'] = log[log.find('file-size'):]
out.write_text(json.dumps(r, indent=1))
print('worst reply', max(p[1] for p in r['polls']), 's; stop at', r.get('stop_at'))
print([p for p in r['polls'] if p[1] > 0.5])
print(r['record_log'])
