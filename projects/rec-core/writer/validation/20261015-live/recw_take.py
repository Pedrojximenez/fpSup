"""One take with RECW loaded.

Usage: python3 -B recw_take.py LABEL [--secs 8]
Before: idle, CINE, both hooks armed (0xC063F140 / 0xC063F220 = F000F8DF + shim).
Take:   MOVON pulse, NO USB traffic for --secs, stop pulse, 10 s quiet.
After:  is_recording (1 = had stopped by itself, one more pulse, early_stop),
        rec log-out, RECW wr_t counters, LOSS card_status, \\CINEMA listing.
Writes nothing but the key pulses.
"""
import argparse, json, re, subprocess, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(ROOT / 'fpSup/fp_usb_shell'), str(HERE)]
import putfile as pf
import recw_state

LAYOUT = ROOT / 'projects/lossless-sup/validation/20261015-clear/build-plain/layout.json'
ap = argparse.ArgumentParser(); ap.add_argument('label'); ap.add_argument('--secs', type=float, default=8.0)
a = ap.parse_args()
out = HERE / f'take-{a.label}.json'; assert not out.exists(), out
sh = lambda c, t=15000: pf.sh(c, retries=0, timeout_ms=t)
loss = lambda: subprocess.run([sys.executable, '-B', str(ROOT / 'fpSup/lossless/card_status.py'), '--layout', str(LAYOUT)],
                              capture_output=True, text=True).stdout

assert sh('status get is_recording').strip() == 'is_recording -> 0'
assert sh('status get app_current').strip() == 'app_current -> 2'
for site in (0xC063F140, 0xC063F220):
    assert pf.mem_get(site)[0] == 0xF000F8DF, hex(site)
r = {'label': a.label, 'secs': a.secs,
     'settings': {c: sh(c).strip() for c in ('menu SetMovRecSize', 'gui geti MV_FrameRate',
                                             'gui geti MV_fpLossless', 'sdcard sdmode')},
     'cinema_before': sh(r'dir \CINEMA'), 'recw_before': recw_state.read(), 'loss_before': loss()}

def pulse():
    try: sh('key MOVON')
    finally: time.sleep(.12); sh('key MOVOFF')

t0 = time.time(); pulse()
time.sleep(max(0, a.secs - (time.time() - t0)))
pulse(); r['stop_at'] = round(time.time() - t0, 2)
time.sleep(10)
r['early_stop'] = sh('status get is_recording').strip().endswith('1')
if r['early_stop']:
    pulse(); time.sleep(10)
    assert sh('status get is_recording').strip().endswith('0')
log = sh('rec log-out'); r['record_log'] = log[log.find('file-size'):]
r['recw_after'] = recw_state.read()
r['loss_after'] = loss()
r['cinema_after'] = sh(r'dir \CINEMA')
r['hooks_after'] = [hex(pf.mem_get(s)[0]) for s in (0xC063F140, 0xC063F220)]
out.write_text(json.dumps(r, indent=1))
print('settings', r['settings'], 'stop_at', r['stop_at'], 'early_stop', r['early_stop'])
print({k: r['recw_after'][k] - r['recw_before'][k] for k in r['recw_after']
       if k not in ('magic', 'flag', 'task_id', 'block_bytes', 'vol', 'wvol', 'sector_shift', 'last_status')},
      'vol', hex(r['recw_after']['vol']), 'wvol', hex(r['recw_after']['wvol']), 'last_status', r['recw_after']['last_status'])
print(r['record_log'])
print(r['loss_after'])
