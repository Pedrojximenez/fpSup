"""Bounded live-test adapter: one AF lease, no replay of shell mutations.

Uses the maintained file tools and preserves every native response. This is
an experiment runner, not a deployment interface for users.
"""
import datetime
import fcntl
import json
import importlib
import pathlib
import sys
import socket
import time
import subprocess
import re

ROOT = pathlib.Path(__file__).resolve().parents[4]
SHELL = ROOT / 'fpSup/fp_usb_shell'
LOG = pathlib.Path(__file__).with_name('commands.jsonl')
sys.path.insert(0, str(SHELL))
import putfile

native_sh = putfile.sh


def checked_sh(line, retries=0, **kwargs):
    # Native file I/O and first private-page registration can exceed the
    # daemon's short default timeout. Bound them without replaying the action.
    kwargs.setdefault('timeout_ms', 20000)
    reply = native_sh(line, retries=0, **kwargs)
    with LOG.open('a') as log:
        log.write(json.dumps({'time': datetime.datetime.now().isoformat(),
                              'command': line, 'reply': reply},
                             ensure_ascii=True) + '\n')
    if reply.lstrip().startswith('ERR'):
        raise RuntimeError(f'Uncertain outcome; command will not be replayed: {line}: {reply}')
    return reply


putfile.sh = checked_sh


def screen():
    app = putfile.mem_get(0xC37B7048)[0]
    scr = putfile.mem_get(app + 0x84c)[0]
    ptr = putfile.mem_get(scr + 8)[0]
    name = b''.join(w.to_bytes(4, 'little') for w in putfile.mem_get(ptr, 8)).split(b'\0')[0].decode('ascii')
    print('screen:', name, flush=True)
    return name


def listing():
    out = checked_sh(r'dir \DCIM\100SIGMA')
    return {int(m.group(2)): int(m.group(1)) for m in
            re.finditer(r'(\d+)\s+SS__(\d{4})\.JPG', out)}


def shot(tag):
    before = listing()
    checked_sh('key CAPTUREON')
    time.sleep(.3)
    checked_sh('key CAPTUREOFF')
    for _ in range(8):
        time.sleep(2.5)
        now = listing()
        new = now.keys() - before.keys()
        if new:
            break
    else:
        raise RuntimeError('No new screenshot, capture will not be replayed')
    n = max(new)
    time.sleep(.5)
    size = listing()[n]
    local = pathlib.Path(__file__).with_name('screenshots') / f'{n:04d}-{tag}.jpg'
    local.parent.mkdir(exist_ok=True)
    if local.exists():
        raise RuntimeError('Refusing to overwrite screenshot evidence')
    sys.argv = ['getfile.py', f'\\DCIM\\100SIGMA\\SS__{n:04d}.JPG', str(local), '--size', str(size)]
    rc = importlib.import_module('getfile').main()
    assert not rc and local.stat().st_size == size
    print('Screenshot:', local, flush=True)


def main():
    with open('/tmp/fp-af-fusion.lock', 'r') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if sys.argv[1] == 'shell':
            for cmd in sys.argv[2:]:
                print(cmd + '\n' + checked_sh(cmd), flush=True)
        elif sys.argv[1] == 'tool':
            name = sys.argv[2]
            if name not in {'getfile.py', 'putfile.py'}:
                raise ValueError('Only reviewed file tools are allowed')
            sys.argv = [str(SHELL / name), *sys.argv[3:]]
            # Invoke the imported module so its helper really is checked_sh.
            # run_path would define a second, unpatched sh in putfile.py.
            module = importlib.import_module(name[:-3])
            raise SystemExit(module.main())
        elif sys.argv[1] == 'reboot':
            # Reboot is sent exactly once; a disconnect is an expected uncertain
            # reply. Never use the legacy helper's blanket pkill loop.
            try:
                print('Single reboot reply:', repr(checked_sh('reboot')), flush=True)
            except RuntimeError as exc:
                print(str(exc), flush=True)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect('/tmp/fpshd.sock')
                s.sendall(b'QUIT\n')
                print('Owned daemon shutdown:', s.recv(1024).decode().strip(), flush=True)
            time.sleep(25)
            log = pathlib.Path(__file__).with_name('daemon-after-reboot.log').open('ab')
            proc = subprocess.Popen([str(SHELL / 'fpshd')], cwd=SHELL,
                                    stdout=log, stderr=log, start_new_session=True)
            print('Replacement daemon PID:', proc.pid, flush=True)
            time.sleep(2)
            if proc.poll() is not None:
                raise RuntimeError('Replacement daemon exited; inspect its log')
            # A getter proves that a freshly booted worker is actually serving.
            print('Boot standby:', checked_sh('status get is_recording'), flush=True)
        elif sys.argv[1] == 'state':
            screen()
            for var in sys.argv[2:]:
                print(checked_sh('gui geti ' + var), flush=True)
        elif sys.argv[1] == 'key':
            for name in sys.argv[2:]:
                if name not in {'MENU', 'OK', 'UP', 'DOWN', 'LEFT', 'RIGHT', 'DISP', 'AEL', 'QS', 'Fn'}:
                    raise ValueError('Not a navigation key')
                print(name, repr(checked_sh('key ' + name + 'ON')), flush=True)
                time.sleep(.12)
                checked_sh('key ' + name + 'OFF')
                time.sleep(.8)
                screen()
        elif sys.argv[1] == 'shot':
            shot(sys.argv[2])
        else:
            raise ValueError('Expected shell, tool, reboot, state, key or shot')


if __name__ == '__main__':
    main()
