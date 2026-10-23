"""UI latency per action from the stock GUI log (uicMgr+0x198 bit0 = 0xC37B71E0, log GUI).

Usage: python3 -B ui_latency.py ACTION... (each ACTION = key name like MENU, RIGHT, QS, PLAY;
       'wait' sleeps 2 s without measuring). For each key: log clear, read current_time,
       send ON/OFF, wait 1.5 s, parse Gui:Update/Render lines (value = ms) and Load Start/End.
Prints: key, first-update delay after the key (ms, includes the USB send),
        work = sum of Update+Render ms in the burst, number of non-zero rounds.
"""
import json, re, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3] / 'fpSup/fp_usb_shell'))
from putfile import sh, mem_get, mem_set

LINE = re.compile(r'^\s*(\d+),\s*\d+,\s*\d+,\w+,0x[0-9a-f]+,(?:(\d+),)?(Gui:Update|Gui:Render|Load Start|Load End)')


def now_ms():
    for _ in range(5):
        v = mem_get(0xC301EAE4)[0]
        if v is not None:
            return v
    raise RuntimeError('current_time unreadable')


assert sh('status get is_recording', retries=0).strip() == 'is_recording -> 0'
mem_set(0xC37B71E0, 1)
assert mem_get(0xC37B71E0)[0] == 1
sh('log act GUI', retries=0)
results = []
try:
    for act in sys.argv[1:]:
        if act == 'wait':
            time.sleep(2); continue
        key = 'QS' if act == 'QS' else act
        sh('log clear', retries=0)
        t = now_ms()
        sh(f'key {key}ON', retries=0)
        if key != 'QS':
            sh(f'key {key}OFF', retries=0)
        time.sleep(1.5)
        ev = []
        for l in sh('log out GUI', retries=0).splitlines():
            m = LINE.match(l)
            if m:
                ev.append((int(m.group(1)) / 1000.0, int(m.group(2) or 0), m.group(3)))
        ev = [e for e in ev if e[0] >= t - 20]           # log clear is not reliable: keep only after the key
        work = [(ts, v, k) for ts, v, k in ev if k.startswith('Gui') and v > 0]
        loads = [ts for ts, v, k in ev if k.startswith('Load')]
        first = (work[0][0] - work[0][1] - t) if work else None   # start of first busy update
        done = (work[-1][0] - t) if work else None
        r = {'key': act, 'start_after_key_ms': round(first, 1) if first is not None else None,
             'done_after_key_ms': round(done, 1) if done is not None else None,
             'update_ms': sum(v for ts, v, k in work if k == 'Gui:Update'),
             'render_ms': sum(v for ts, v, k in work if k == 'Gui:Render'),
             'busy_rounds': sum(1 for ts, v, k in work if k == 'Gui:Update'),
             'loads': len(loads) // 2}
        results.append(r)
        print(r, flush=True)
finally:
    mem_set(0xC37B71E0, 0)
    sh('log inact GUI', retries=0)
    out = HERE / f'ui_latency_{time.strftime("%H%M%S")}.json'
    out.write_text(json.dumps(results, indent=1))
    print('saved', out.name)
