"""cpu_short.py with the diagnostic build's hook counters read before and
after, and each hook's last stack pointer mapped to its task through the
firmware's TCB table (C301EACC, 0x34 a task: +0x1C/+0x20 stack, +0x2C name).

Usage: python3 -B hook_take.py LABEL LAYOUT [cpu_short options]
Writes hooks-LABEL.json beside cpu-LABEL.json.
"""
import json, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT / 'fpSup/fp_usb_shell'), str(ROOT / 'fpSup/lossless')]
import putfile as pf
import card_status as cs

label, layout = sys.argv[1], Path(sys.argv[2])
fields = json.loads(layout.read_text())['fields']
_, st, _ = cs.find_record(pf.mem_get)
NAMES = ['rec', 'arrive', 'stop', 'flush', 'observe', 'written', 'event', 'discard']
SCALARS = ['enq_n', 'enq_us', 'hold.diag_enq_n', 'hold.diag_enq_us', 'hold.diag_enq_max_us',
           'hold_b.diag_enq_n', 'hold_b.diag_enq_us']

def snap():
    w = pf.mem_get(st + fields['hook_time'], 32)
    s = {k: pf.mem_get(st + fields[k])[0] for k in SCALARS}
    return {'hooks': {n: w[4 * i:4 * i + 4] for i, n in enumerate(NAMES)}, **s}

def tasks():
    out = []
    for i in range(50):
        t = pf.mem_get(0xC301EACC + 0x34 * i, 13)
        lo, hi = t[7], t[8]
        name = b''.join(x.to_bytes(4, 'little') for x in t[11:13]).split(b'\0')[0].decode('latin1')
        if lo and hi: out.append((i + 1, lo, hi, name))
    return out

before = snap()
r = subprocess.run([sys.executable, '-B', str(HERE / 'cpu_short.py'), label, str(layout), *sys.argv[3:]],
                   capture_output=True, text=True)
print(r.stdout[-1800:], r.stderr[-800:])
after = snap()
tl = tasks()
# istk / stksz from the shell's task list (research/autofocus/captures/
# native-preflight/20260927-121028/native-stack-check.json): the stack grows down
STACKS = {'RecPMgr': (0xc3a3ae3c, 0x4000), 'CamSch': (0xc3a3ee44, 0x4000),
          'MRecMgr': (0xc3a42e4c, 0x4000), 'SRecFile': (0xc3a6f6cc, 0x4000),
          'DrawMgr': (0xc3a32e1c, 0x4000), 'EventMgr': (0xc3a36e34, 0x2800),
          'PlyMgr': (0xc3b19994, 0x4000), 'shell': (0xc3ab2704, 0x4000)}
def task_of(sp):
    for name, (top, size) in STACKS.items():
        if top - size <= sp < top: return name
    return '?'
rep = {'label': label, 'hooks': {}}
for n in NAMES:
    b, a = before['hooks'][n], after['hooks'][n]
    calls, us = a[0] - b[0], a[1] - b[1]
    rep['hooks'][n] = {'calls': calls, 'us': us, 'per_call_us': round(us / calls, 1) if calls else 0,
                       'max_us': a[2], 'task': task_of(a[3]), 'sp': hex(a[3])}
for k in SCALARS: rep[k] = after[k] - before[k]
(HERE / f'hooks-{label}.json').write_text(json.dumps(rep, indent=1))
for n, v in rep['hooks'].items(): print(f"{n:8s} {v['calls']:5d} calls {v['us']:8d} us  {v['per_call_us']:7.1f} us/call  max {v['max_us']:6d}  {v['task']}")
print({k: rep[k] for k in SCALARS})
