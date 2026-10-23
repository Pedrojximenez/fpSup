"""Per-UI-element CPU cost, CINE standby, not recording.

DispMode custom (SetDisplayMode 1); all elements 0, then one at a time = 1,
then all = 1 with 70PERF off / on. Each point: 3 s settle, 2 s PC sample.
Restores the pre-reboot user values at the end (display_user.json).
"""
import json, re, subprocess, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'fpSup/fp_usb_shell'))
from putfile import sh, mem_get

PROF = ROOT / 'projects/sys-perf/profiler'
PERFCTL = ROOT / 'projects/sys-perf/sup/perfctl.py'
CTL = hex(mem_get(0xC2E38E7C)[0] - 96)
ELEMS = ['TimeCode', 'GridLines', 'FrameGuide', 'CenterMark', 'ElectronicLevel',
         'BrightnessLevel', 'ZebraPattern', 'AudioMeter', 'LensInfo', 'DateTime']
USER = {'SetDisplayMode': '1', 'SetDisplayCustomSupport': '1', 'SetDisplayBrightnessLevel': '1',
        'SetDisplayTimeCode': '0', 'SetDisplayAudioMeter': '1', 'SetDisplayZebraPattern': '0'}


def menu(name, val=None):
    r = sh(f'menu {name}' + ('' if val is None else f' {val}'), retries=0).strip().splitlines()
    return r[-1].strip() if r else ''


def perf(**kw):
    subprocess.run(['python3', '-B', str(PERFCTL), '--ctl', CTL, 'set'] +
                   [f'{k}={v}' for k, v in kw.items()], check=True, capture_output=True)


def prof(*a):
    return subprocess.run(['python3', '-B', str(PROF / 'pcsample.py'), *a],
                          check=True, capture_output=True, text=True).stdout


def sample(label):
    time.sleep(3)
    prof('start'); time.sleep(2); prof('stop'); prof('read', label)
    out = subprocess.run(['python3', '-B', str(PROF / 'analyze.py'), f'captures/{label}', '--top', '1'],
                         cwd=PROF, check=True, capture_output=True, text=True).stdout
    pct = {m.group(2): float(m.group(1)) for m in re.finditer(r'^\s+([\d.]+)%\s+\d+\s+(\S+)$', out, re.M)}
    return {'idle': pct.get('inittsk', 0.0), 'DrawMgr': pct.get('DrawMgr', 0.0), 'CamSch': pct.get('CamSch', 0.0)}


assert sh('status get is_recording', retries=0).strip() == 'is_recording -> 0'
res = {}
try:
    prof('install', '--via', 'B', '--ch', '3')
    perf(dc=0, nb=0, fd=0, lz=0, ir=0, ic=0, pl=0)
    menu('SetDisplayMode', 1)
    for e in ELEMS:
        menu(f'SetDisplay{e}', 0)
    res['none'] = sample('v2-none'); print('none', res['none'], flush=True)
    for e in ELEMS:
        menu(f'SetDisplay{e}', 1)
        got = menu(f'SetDisplay{e}')
        res[e] = sample(f'v2-{e}'); res[e]['set'] = got
        print(e, res[e], flush=True)
        menu(f'SetDisplay{e}', 0)
    for e in ELEMS:
        menu(f'SetDisplay{e}', 1)
    res['all_perf_off'] = sample('v2-all-off'); print('all perf off', res['all_perf_off'], flush=True)
    perf(dc=1, nb=1, fd=1, lz=1, ir=1, ic=1, pl=1)
    res['all_perf_on'] = sample('v2-all-on'); print('all perf on', res['all_perf_on'], flush=True)
    subprocess.run(['python3', '-B', '/private/tmp/claude-501/-Users-dido-Developer-localized-SIGMAfp-re/d8b52e05-f45d-4908-9eb1-c2708f2ac578/scratchpad/shot.py', str(HERE / 'ss_all_ui_perf_on.jpg')], check=False)
finally:
    try:
        prof('uninstall')
    finally:
        for e in ELEMS:
            menu(f'SetDisplay{e}', 0)
        for k, v in USER.items():
            menu(k, v)
        res['restored'] = {k: menu(k) for k in USER}
        (HERE / 'ui_cost.json').write_text(json.dumps(res, indent=1))
        print('restored', res['restored'])
