"""One recorded take with a whole-system PC-sampling window. Not touching USB while recording.

Usage: python3 -B rec_profile.py LABEL [seconds=8]
Profiler starts with --skip 2000 (window opens ~2 s after the start pulse, after the
record-start transient), 16384 records (~16 s). rec_take.sh does: MOV pulse, SECONDS
with no USB, MOV pulse, 5 s, ping. Then wait 10 s, stop, read, rec log, LOSS card_status.
"""
import json, subprocess, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SH = ROOT / 'fpSup/fp_usb_shell'
sys.path[:0] = [str(SH), str(ROOT / 'fpSup/lossless')]
from putfile import sh, mem_get

P = str(ROOT / 'projects/sys-perf/profiler/pcsample.py')
label = sys.argv[1]
secs = sys.argv[2] if len(sys.argv) > 2 else '8'


def run(*a):
    r = subprocess.run(['python3', '-B', *a], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f'{a}: {r.stderr[-300:]}')
    return r.stdout


assert sh('status get is_recording', retries=0).strip() == 'is_recording -> 0'
out = {'label': label, 'settings': {c: sh(c, retries=0).strip().splitlines()[-1] for c in
       ('menu SetMovRecSize', 'menu SetMovFramerate', 'gui geti MV_fpLossless', 'sdcard sdmode')}}
print(out['settings'], flush=True)
try:
    run(P, 'install', '--via', 'B', '--ch', '3')
    run(P, 'start', '--skip', '2000')
    t0 = time.time()
    subprocess.run(['zsh', str(SH / 'rec_take.sh'), secs], cwd=SH, capture_output=True, text=True)
    out['take_wall_s'] = round(time.time() - t0, 1)
    time.sleep(10)
    for _ in range(10):
        if sh('status get is_recording', retries=0).strip() == 'is_recording -> 0':
            break
        time.sleep(2)
    out['is_recording_after'] = sh('status get is_recording', retries=0).strip()
    run(P, 'stop')
    out['mode_after'] = mem_get(0xC343B590)[0]
    run(P, 'read', label)
    log = sh('rec log-out', retries=0)
    out['rec_log'] = log[log.find('file-size'):][:1500]
    try:
        import card_status as cs
        fields = json.loads((ROOT / 'projects/lossless-sup/validation/20261015-clear/build-plain/layout.json').read_text())['fields']
        _, st, _ = cs.find_record(mem_get)
        out['loss_status'] = {k: mem_get(st + v)[0] for k, v in fields.items()}
    except Exception as e:
        out['loss_status_error'] = repr(e)
finally:
    subprocess.run(['python3', '-B', P, 'uninstall'], capture_output=True)
    (HERE / f'rec-{label}.json').write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != 'loss_status'}, indent=1)[:1500])
