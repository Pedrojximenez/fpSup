import json, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3] / 'fpSup/fp_usb_shell'), str(HERE.parents[3] / 'fpSup/lossless')]
import putfile as pf, card_status as cs
mode, label = int(sys.argv[1]), sys.argv[2]
extra = sys.argv[3:] or ['--mon-at', '1.0', '--mon', '2.0', '--stop-at', '4.0']
L = HERE / 'build-snap/layout.json'
f = json.loads(L.read_text())['fields']; _, st, _ = cs.find_record(pf.mem_get)
pf.sh(f'mem set 0x{st + f["engine_mode"]:08X} 0x{mode:X}', retries=0, timeout_ms=8000)
assert pf.mem_get(st + f['engine_mode'])[0] == mode
r = subprocess.run([sys.executable, '-B', str(HERE / 'cpu_short.py'), label, str(L), *extra], capture_output=True, text=True)
print('\n'.join(l for l in r.stdout.splitlines() if 'CPU =' in l or 'MRecMgr' in l or 'FPLCODE' in l))
g = lambda k, n=1: pf.mem_get(st + f[k], n)
n = g('hold.job.diag_n')[0] or 1
rep = {'mode': mode, 'compressed': g('hold.compressed')[0], 'refused': g('hold.refused')[0],
       'held': g('hold.held')[0], 'faults': g('hold.faults')[0], 'tag_failed': g('flush.tag_failed')[0],
       'snap': {k: g('engine_snap.' + k)[0] for k in ('on', 'valid', 'opens', 'reuses', 'closes')},
       'engine_release': g('engine_release')[0], 'enable_now': pf.mem_get(0x300D0074)[0] & 1,
       'submit_us': [round(x / n, 1) for x in g('hold.job.diag_submit_us', 5)],
       'finish_us': [round(x / n, 1) for x in g('hold.job.diag_finish_us', 5)], 'jobs': n}
(HERE / f'snap-{label}.json').write_text(json.dumps(rep, indent=1)); print(rep)
