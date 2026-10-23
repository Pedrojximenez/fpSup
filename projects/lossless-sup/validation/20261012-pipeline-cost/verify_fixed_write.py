"""Verify an already-issued file write; never replay it."""
import fcntl
import hashlib
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
    out = HERE / 'fixed-restoration-readback-recovery.json'
    assert not out.exists()
    report = {'commands': [], 'write_replayed': False}
    def sh(cmd):
        r = pf.sh(cmd, retries=0, timeout_ms=5000)
        report['commands'].append({'command': cmd, 'reply': r})
        assert r.strip() and not r.startswith('ERR'), r
        return r.strip()
    with open('/tmp/fp-af-fusion.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            # A fresh synchronous command proves the previous handler returned.
            assert sh('status get is_recording') == 'is_recording -> 0'
            assert pf.mem_get(0xC358E140)[0] == 0
            assert pf.mem_get(0xC35A952C)[0] & 255 == 0
            assert pf.mem_get(0xC0BAC2F8)[0] == 0xC03D99A0
            report['parameter_address'] = hex(pf.P)
            report['parameters'] = pf.mem_get(pf.P, 6)
            assert report['parameters'][2:5] == [2, 1, 1]
            data = (HERE / 'fixed-profile/10LOSS.BIN').read_bytes()
            listing = sh('dir ' + chr(92) + 'fpSup')
            rows = [x.split() for x in listing.splitlines()]
            assert [int(p[-2]) for p in rows if p and p[-1] == '10LOSS.BIN'] == [len(data)]
            back = HERE / 'fixed-restoration-readback-verified.BIN'
            r = subprocess.run([sys.executable, '-B', str(HERE / 'read_file_once.py'),
                r'\fpSup\10LOSS.BIN', str(back), '--size', str(len(data))], capture_output=True, text=True)
            (HERE / 'recovery-readback.log').write_text(r.stdout + r.stderr)
            assert r.returncode == 0
            assert back.read_bytes() == data
            assert sh('status get is_recording') == 'is_recording -> 0'
            report.update(readback_verified=True, sha256=hashlib.sha256(data).hexdigest(),
                          bytes=len(data), completed_at=time.time())
        finally:
            out.write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps({k:v for k,v in report.items() if k != 'commands'}))
