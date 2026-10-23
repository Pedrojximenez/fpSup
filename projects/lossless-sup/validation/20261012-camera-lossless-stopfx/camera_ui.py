"""Task-local adapter to reviewed UI keys and native LCD capture; idle only."""
import fcntl
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'projects/res-lab/validation/20261009-oncamera'))
import live_camera as c
c.LOG = HERE / 'ui-commands.jsonl'

if __name__ == '__main__':
    with open('/tmp/fp-af-fusion.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert c.checked_sh('status get is_recording').strip() == 'is_recording -> 0'
        assert c.putfile.mem_get(0xC358E140)[0] == 0
        assert c.putfile.mem_get(0xC35A952C)[0] & 255 == 0
        action = sys.argv[1]
        if action == 'key':
            for k in sys.argv[2:]:
                assert k in ('MENU', 'RIGHT', 'LEFT', 'UP', 'DOWN', 'OK', 'DISP')
                try:
                    c.checked_sh('key ' + k + 'ON')
                finally:
                    time.sleep(.12)
                    c.checked_sh('key ' + k + 'OFF')
                time.sleep(.8)
                c.screen()
        elif action == 'read':
            c.screen()
            for name in sys.argv[2:]:
                print(c.checked_sh('gui geti ' + name), flush=True)
        elif action == 'dial':
            assert sys.argv[2] in ('-1', '1')
            c.checked_sh('key CMDDIAL1 ' + sys.argv[2])
            time.sleep(1)
            c.screen()
        elif action == 'page':
            assert sys.argv[2] == 'MainB2'
            c.checked_sh('gui scr set MainB2')
            time.sleep(1)
            c.screen()
        elif action == 'shot':
            dest = HERE / (sys.argv[2] + '.jpg')
            assert not dest.exists()
            old = c.listing()
            try:
                c.checked_sh('key CAPTUREON')
            finally:
                time.sleep(.15)
                c.checked_sh('key CAPTUREOFF')
            time.sleep(2.5)
            after = c.listing()
            new = set(after) - set(old)
            assert len(new) == 1
            n = new.pop()
            r = subprocess.run([sys.executable, '-B', str(ROOT / 'fpSup/fp_usb_shell/getfile.py'),
                f'\\DCIM\\100SIGMA\\SS__{n:04d}.JPG', str(dest), '--size', str(after[n])],
                capture_output=True, text=True)
            dest.with_suffix('.fetch.log').write_text(r.stdout + r.stderr)
            assert r.returncode == 0
            print(dest)
        else:
            raise ValueError(action)
