"""Rapid key burst: does the menu drop fast keys?  (2026-10-25)

    python3 -B ui_burst.py TAG KEY N GAP      # e.g. home DOWN 4 0.15

Sends N presses of KEY GAP seconds apart, then reads the GUI time log once:
the Gui:Render values and every Gui:Update round (ms, busy count).  Renders
are not moves -- take a screenshot (ui_shot.sh) and count where the cursor is.
The time log is the GUI's own clock (memory gui-key-cost-measurement)."""
import re, sys, time
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parent))
from putfile import sh, mem_set
LINE = re.compile(r'^\s*(\d+),\s*(-?\d+),\s*\d+,\w+,0x[0-9a-f]+,(\d+),(Gui:Update|Gui:Render)')
tag, key, n, gap = sys.argv[1], sys.argv[2], int(sys.argv[3]), float(sys.argv[4])
mem_set(0xC37B71E0, 1); sh('log act GUI', retries=0)
ev0 = [int(m.group(1)) for l in sh('log out GUI', retries=0).splitlines() for m in [LINE.match(l)] if m]
seen = max(ev0 or [0])
t0 = time.time(); sent = []
try:
    for i in range(n):
        sh(f'key {key}ON', retries=0); sh(f'key {key}OFF', retries=0); sent.append(time.time() - t0)
        time.sleep(gap)
    time.sleep(1.5)
    ev = [(int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)) for l in sh('log out GUI', retries=0).splitlines() for m in [LINE.match(l)] if m]
finally:
    mem_set(0xC37B71E0, 0); sh('log inact GUI', retries=0)
new = [e for e in ev if e[0] > seen]
rend = [v for ts, d, v, nm in new if nm == 'Gui:Render' and v > 0]
upd = [d for ts, d, v, nm in new if nm == 'Gui:Update' and v > 0]
span = (new[-1][0] - new[0][0]) / 1000 if new else 0
print(tag, 'renders', rend, 'all-upd', [(round(d/1000),v) for ts,d,v,nm in new if nm=='Gui:Update'])
