"""Task-local adapter to reviewed UI keys and native LCD capture; idle only."""
import fcntl
from pathlib import Path
import subprocess
import re
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
        elif action == 'fps':
            # Native Settings picker only; no resident consumer-layout assumptions.
            def value(name):
                reply = c.checked_sh('gui geti ' + name)
                match = re.fullmatch(r'\s*OK:' + name + r' -> (-?\d+)\s*', reply)
                assert match, reply
                return int(match[1])
            def press(name):
                try:
                    c.checked_sh('key ' + name + 'ON')
                finally:
                    time.sleep(.12)
                    c.checked_sh('key ' + name + 'OFF')
                time.sleep(.8)
            target = int(sys.argv[2])
            assert target in (3, 6, 8, 9)
            assert c.screen() == 'B2_5' and value('MENU_Level2') == 4434
            press('RIGHT')
            current = value('B2_n5_ListFocus4')
            assert 0 <= current <= 9
            for _ in range(10):
                if current == target:
                    break
                wanted = current + (1 if current < target else -1)
                press('DOWN' if current < target else 'UP')
                current = value('B2_n5_ListFocus4')
                assert current == wanted
            assert current == target
            press('OK')
            assert value('MV_FrameRate') == target
            print('Committed native FPS row', target, flush=True)
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
            r = subprocess.run([sys.executable, '-B', str(HERE / 'read_file_once.py'),
                f'\\DCIM\\100SIGMA\\SS__{n:04d}.JPG', str(dest), '--size', str(after[n])],
                capture_output=True, text=True)
            dest.with_suffix('.fetch.log').write_text(r.stdout + r.stderr)
            assert r.returncode == 0
            print(dest)
        else:
            raise ValueError(action)
