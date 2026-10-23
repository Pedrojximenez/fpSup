"""Read-only native task-CPU window in the camera's current state.
Usage: python3 -B cpu_state.py LABEL [--mon 1.0] [--n 3]
Runs `analyzer tskmon_start/top/stop` N times; writes cpu-LABEL.json. No writes besides the profiler's own allocation."""
import argparse, json, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT / 'fpSup/fp_usb_shell')]
import putfile as pf
ap = argparse.ArgumentParser(); ap.add_argument('label')
ap.add_argument('--mon', type=float, default=1.0); ap.add_argument('--n', type=int, default=3)
a = ap.parse_args()
out = HERE / f'cpu-{a.label}.json'; assert not out.exists()
sh = lambda c, t=15000: pf.sh(c, retries=0, timeout_ms=t)
assert sh('status get is_recording').strip() == 'is_recording -> 0'
r = {'label': a.label, 'app_current': sh('status get app_current').strip(), 'runs': []}
for i in range(a.n):
    sh('analyzer tskmon_start 32768 64 1000000 52'); time.sleep(a.mon)
    top = sh('analyzer tskmon_top 0 15'); sh('analyzer tskmon_stop')
    r['runs'].append(top); print(top.split('# Total')[0]); time.sleep(.5)
out.write_text(json.dumps(r, indent=1))
