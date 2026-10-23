"""Offline: task CPU in the 1.1-2.1 s window of each stopped native task ring.

Same timing/attribution rules as 20261012-early-dng-handoff/analyze_task_rings.py;
cross-checks the full-ring CPU against the camera's own tskmon_top summary.
"""
import collections, json, re, struct, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
NAMES = {1: 'idle', 44: 'CamSch', 45: 'MRecMgr', 39: 'DrawMgr', 61: 'SRecFile', 54: 'SRecRaw', 125: 'FPLCODE'}

def analyze(label):
    d = json.loads((HERE / f'{label}.json').read_text())
    m = json.loads((HERE / f'{label}-ring.json').read_text())
    rows = list(struct.iter_unpack('<7I', (HERE / f'{label}-ring.bin').read_bytes()))
    assert not m['monitor'][6] & 15
    t = [r[2] * 1000000 + (r[3] * 100) // m['clock'][2] for r in rows]
    t = [x - t[0] for x in t]
    def window(lo, hi):
        c = collections.Counter()
        for i, r in enumerate(rows[:-1]):
            c[r[0]] += max(0, min(t[i + 1], hi) - max(t[i], lo))
        total = sum(c.values()); assert total == hi - lo
        return {'cpu': round(100 * (total - c[1]) / total, 2),
                **{NAMES[k]: round(100 * c[k] / total, 2) for k in NAMES if k != 1}}
    top = d['task_top_recording']
    n = int(re.search(r'Cnt = (\d+)', top).group(1)); total = int(re.search(r'Total\(Sum\)\s+(\d+)', top).group(1))
    # The ring's first record precedes the summary's origin by ~2 ms in these
    # captures, so compare the CPU share rather than the exact end time.
    full = window(0, t[n - 1])
    full['camera_summary_cpu'] = float(re.search(r'CPU = ([\d.]+)', top).group(1))
    assert abs(full['cpu'] - full['camera_summary_cpu']) < 0.5, full
    return {'full': full, 'window_1.1_2.1s': window(1100000, 2100000)}

out = {label: analyze(label) for label in sys.argv[1:]}
(HERE / 'window-cpu.json').write_text(json.dumps(out, indent=2) + '\n')
for k, v in out.items(): print(k, v['window_1.1_2.1s'])
