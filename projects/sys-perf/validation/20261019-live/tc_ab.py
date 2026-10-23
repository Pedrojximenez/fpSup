"""Timecode-only A/B: neonblit (incl. span idx 7) off vs on, alternating, 3 rounds.
CINE standby, not recording. Restores the user's display values afterwards."""
import re, subprocess, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'fpSup/fp_usb_shell'))
from putfile import sh, mem_get

PROF = ROOT / 'projects/sys-perf/profiler'
CTL = hex(mem_get(0xC2E38E7C)[0] - 96)
ELEMS = ['TimeCode', 'GridLines', 'FrameGuide', 'CenterMark', 'ElectronicLevel',
         'BrightnessLevel', 'ZebraPattern', 'AudioMeter', 'LensInfo', 'DateTime']
USER = {'SetDisplayMode': '1', 'SetDisplayCustomSupport': '1', 'SetDisplayBrightnessLevel': '1',
        'SetDisplayTimeCode': '0', 'SetDisplayAudioMeter': '1', 'SetDisplayZebraPattern': '0'}
TAG = time.strftime('%H%M%S')


def menu(n, v=None):
    r = sh(f'menu {n}' + ('' if v is None else f' {v}'), retries=0).strip().splitlines()
    return r[-1].strip() if r else ''


def run(*a, cwd=None):
    return subprocess.run(['python3', '-B', *a], cwd=cwd, check=True, capture_output=True, text=True).stdout


def sample(label):
    time.sleep(3)
    p = str(PROF / 'pcsample.py')
    run(p, 'start'); time.sleep(2); run(p, 'stop'); run(p, 'read', label)
    out = run(str(PROF / 'analyze.py'), f'captures/{label}', '--top', '1', cwd=PROF)
    pct = {m.group(2): float(m.group(1)) for m in re.finditer(r'^\s+([\d.]+)%\s+\d+\s+(\S+)$', out, re.M)}
    return pct.get('DrawMgr', 0.0), pct.get('inittsk', 0.0)


assert sh('status get is_recording', retries=0).strip() == 'is_recording -> 0'
res = {0: [], 1: []}
try:
    run(str(PROF / 'pcsample.py'), 'install', '--via', 'B', '--ch', '3')
    menu('SetDisplayMode', 1)
    for e in ELEMS:
        menu(f'SetDisplay{e}', 1 if e == 'TimeCode' else 0)
    for rnd in range(3):
        for nb in (0, 1):
            run(str(ROOT / 'projects/sys-perf/sup/perfctl.py'), '--ctl', CTL, 'set', f'nb={nb}')
            d, idle = sample(f'tc-{TAG}-{rnd}-nb{nb}')
            res[nb].append(d)
            print(f'round {rnd} nb={nb}: DrawMgr {d:.1f}%  idle {idle:.1f}%', flush=True)
    for nb in (0, 1):
        print(f'nb={nb} mean DrawMgr {sum(res[nb]) / 3:.2f}%')
finally:
    try:
        run(str(PROF / 'pcsample.py'), 'uninstall')
    finally:
        for e in ELEMS:
            menu(f'SetDisplay{e}', 0)
        for k, v in USER.items():
            menu(k, v)
        print('restored', {k: menu(k) for k in USER})
