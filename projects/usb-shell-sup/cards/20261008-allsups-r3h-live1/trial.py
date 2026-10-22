#!/usr/bin/env python3
"""Bounded UI trial. Single-send keys; retain native replies and exact screenshots."""
import argparse
import pathlib
import re
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SHELL = ROOT / 'fpSup/fp_usb_shell'
sys.path.insert(0, str(SHELL))
import putfile as pf


def say(s):
    print(s, flush=True)
    with (HERE / 'transcript.txt').open('a') as f:
        f.write(time.strftime('%H:%M:%S ') + str(s) + '\n')


def command(s, retries=3):
    r = pf.sh(s, retries=retries, timeout_ms=2000)
    if s.startswith('dir '):
        with (HERE / 'transcript.txt').open('a') as f:
            f.write(time.strftime('%H:%M:%S ') + s + ' => ' + repr(r) + '\n')
        print(s + ' => listing retained', flush=True)
    else:
        say(s + ' => ' + repr(r))
    if r.lstrip().startswith('ERR'):
        raise RuntimeError(r)
    return r


def key(s):
    assert s in ('MENU', 'OK', 'UP', 'DOWN', 'LEFT', 'RIGHT')
    command('key ' + s + 'ON', retries=0)
    time.sleep(.8)


def screen():
    app = pf.mem_get(0xC37B7048)[0]
    scr = pf.mem_get(app + 0x84c)[0]
    ptr = pf.mem_get(scr + 8)[0]
    w = pf.mem_get(ptr, 8)
    name = b''.join(x.to_bytes(4, 'little') for x in w).split(b'\0')[0].decode('ascii')
    say('screen ' + name)
    return name


def state():
    screen()
    for s in ('MENU_Level1', 'FT_Focus', 'FT_HomeFocus', 'FT_Key',
              'FT_Default1', 'FT_Default2', 'FT_Choice1', 'FT_Choice2'):
        command('gui geti ' + s)
    command('gui gets FT_PageText')


def listing():
    return {int(m.group(2)): int(m.group(1)) for m in
            re.finditer(r'(\d+)\s+SS__(\d{4})\.JPG', command('dir \\DCIM\\100SIGMA'))}


def shot(tag):
    before = listing()
    command('key CAPTUREON', retries=0)
    time.sleep(.3)
    command('key CAPTUREOFF', retries=0)
    for _ in range(8):
        time.sleep(2.5)
        now = listing()
        new = now.keys() - before.keys()
        if new:
            break
    else:
        raise RuntimeError('No new screenshot; do not accept an old file')
    n = max(new)
    time.sleep(.5)
    size = listing()[n]
    local = HERE / 'screenshots' / f'{n:04d}-{tag}.jpg'
    local.parent.mkdir(exist_ok=True)
    p = subprocess.run([sys.executable, '-B', str(SHELL / 'getfile.py'),
                        f'\\DCIM\\100SIGMA\\SS__{n:04d}.JPG', str(local), '--size', str(size)],
                       cwd=SHELL, capture_output=True, text=True)
    (HERE / f'getfile-{n:04d}.txt').write_text(p.stdout + p.stderr)
    assert p.returncode == 0 and local.stat().st_size == size, p.stdout + p.stderr
    say('shot ' + str(local))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--key', action='append', default=[])
    ap.add_argument('--shot')
    ap.add_argument('--state', action='store_true')
    ap.add_argument('--to-home', action='store_true')
    a = ap.parse_args()
    for k in a.key:
        key(k)
    if a.to_home:
        for _ in range(16):
            if screen() == 'FT_Y6':
                break
            key('RIGHT')
        else:
            raise RuntimeError('Did not reach management home')
    if a.state:
        state()
    if a.shot:
        shot(a.shot)
