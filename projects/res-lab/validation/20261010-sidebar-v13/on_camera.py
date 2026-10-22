"""Bounded sidebar hardware trials using the existing, non-replaying adapter."""
import fcntl
import importlib
import json
import os
import pathlib
import plistlib
import re
import signal
import socket
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE.parent / '20261009-oncamera'))
import live_camera as live
live.LOG = HERE / 'commands.jsonl'


def shot(tag):
    assert 'is_recording -> 0' in live.checked_sh('status get is_recording')
    before = live.listing()
    live.checked_sh('key CAPTUREON')
    time.sleep(.3)
    live.checked_sh('key CAPTUREOFF')
    for _ in range(8):
        time.sleep(2.5)
        now = live.listing()
        new = now.keys() - before.keys()
        if new:
            break
    else:
        raise RuntimeError('No new screenshot; capture will not be replayed')
    n = max(new)
    time.sleep(.5)
    size = live.listing()[n]
    dest = HERE / 'screenshots' / f'{n:04d}-{tag}.jpg'
    dest.parent.mkdir(exist_ok=True)
    assert not dest.exists()
    sys.argv = ['getfile.py', f'\\DCIM\\100SIGMA\\SS__{n:04d}.JPG', str(dest), '--size', str(size)]
    assert not importlib.import_module('getfile').main()
    assert dest.stat().st_size == size
    print('Screenshot:', dest, flush=True)


def main():
    command = sys.argv[1]
    if command in ('shell', 'key', 'state', 'tool'):
        return live.main()
    with open('/tmp/fp-af-fusion.lock', 'r') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if command == 'shot':
            shot(sys.argv[2])
        elif command == 'runtime':
            assert 'is_recording -> 0' in live.checked_sh('status get is_recording')
            data = importlib.import_module('inspect_runtime').snapshot()
            dest = HERE / (sys.argv[2] + '.json')
            assert not dest.exists()
            dest.write_text(json.dumps(data, indent=2) + '\n')
            print(json.dumps(data, indent=2))
        elif command == 'reboot':
            # Caller supplies the already identified daemon PID. Verify again,
            # send one reboot only, then cleanly release the owned host service.
            owned = int(sys.argv[2])
            exe = str(live.SHELL/'fpshd')
            assert subprocess.check_output(['ps','-p',str(owned),'-o','command='], text=True).strip() == exe
            assert 'is_recording -> 0' in live.checked_sh('status get is_recording')
            try:
                print('Single reboot:', repr(live.checked_sh('reboot')), flush=True)
            except RuntimeError as exc:
                print(str(exc), flush=True)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(5); s.connect('/tmp/fpshd.sock'); s.sendall(b'QUIT\n')
                reply = s.recv(1024).decode().strip()
                assert reply == 'OK bye', reply
                print('Owned daemon released:', owned, flush=True)
            time.sleep(25)
            log = (HERE/'daemon.log').open('ab')
            p = subprocess.Popen([exe], cwd=live.SHELL, stdout=log, stderr=log, start_new_session=True)
            print('Replacement daemon PID:', p.pid, flush=True)
            time.sleep(2)
            assert p.poll() is None
            print('Standby:', live.checked_sh('status get is_recording'), flush=True)
        elif command == 'reclaim':
            raw = subprocess.check_output(['ioreg','-a','-l','-p','IOService'])
            evidence = HERE/(sys.argv[2]+'.plist')
            assert not evidence.exists(); evidence.write_bytes(raw)
            owners = []
            def scan(node, camera=False):
                if isinstance(node, dict):
                    camera = camera or (node.get('USB Product Name') == 'SIGMA fp' and node.get('IOObjectClass') == 'IOUSBHostDevice')
                    if camera and node.get('bInterfaceNumber') == 0 and node.get('UsbExclusiveOwner'):
                        owners.append(node['UsbExclusiveOwner'])
                    for child in node.get('IORegistryEntryChildren', []): scan(child, camera)
                elif isinstance(node, list):
                    for child in node: scan(child, camera)
            scan(plistlib.loads(raw))
            assert len(owners) == 1, owners
            match = re.fullmatch(r'pid (\d+), ptpcamerad', owners[0])
            assert match, owners
            pid = int(match[1])
            assert subprocess.check_output(['ps','-p',str(pid),'-o','comm='], text=True).strip() == '/usr/libexec/ptpcamerad'
            os.kill(pid, signal.SIGTERM)
            time.sleep(.025)
            current = subprocess.run(['ps','-p',str(pid),'-o','comm='], capture_output=True, text=True).stdout.strip()
            if current == '/usr/libexec/ptpcamerad':
                # Match the existing recovery helper's TERM -> exact-PID KILL
                # fallback, without its one-second re-claim race window.
                os.kill(pid, signal.SIGKILL)
                time.sleep(.025)
            print('Released verified SIGMA PTP claimant:', pid, flush=True)
            print(live.checked_sh('status get is_recording'), flush=True)
        else:
            raise ValueError('Expected shell, key, state, tool, shot, runtime, reboot or reclaim')


if __name__ == '__main__':
    main()
