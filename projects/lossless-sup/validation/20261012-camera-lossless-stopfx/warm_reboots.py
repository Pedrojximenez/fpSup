"""Ten explicitly invoked normal software warm reboots, no recordings.

This verifies software reboot/reload, not battery removal or a physical switch.
No daemon is replaced; each reboot command is sent once and never retried.
"""
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'fpSup/fp_usb_shell'))
import putfile as pf

if __name__ == '__main__':
    for i in range(1, 11):
        label = f'warm-reboot-{i:02d}'
        out = HERE / (label + '-command.json')
        assert not out.exists()
        with open('/tmp/fp-af-fusion.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            assert pf.sh('status get is_recording', retries=0).strip() == 'is_recording -> 0'
            assert pf.mem_get(0xC358E140)[0] == 0
            assert pf.mem_get(0xC35A952C)[0] & 255 == 0
            before = pf.mem_get(0xC072F6F8)[0]
            report = {'boot_before': before, 'sent_at': time.time(), 'command': 'reboot'}
            out.write_text(json.dumps(report, indent=2))
            report['reply'] = pf.sh('reboot', retries=0, timeout_ms=5000)
            out.write_text(json.dumps(report, indent=2))
            time.sleep(12)
        r = subprocess.run([sys.executable, '-B', str(HERE / 'live_trial.py'), label])
        assert r.returncode == 0, 'stop on failed restart; no reboot replay'
        data = json.loads((HERE / (label + '.json')).read_text())
        state = data['after']
        assert state['boot'] != before
        assert state['descriptors_free'] == 96 and state['registry_occupied'] == 0
        assert state['values']['rec_admitted'] == 0 and state['values']['take_frames'] == 0
        print(label, 'PASS both modules reloaded, no REC, descriptors=96', flush=True)
