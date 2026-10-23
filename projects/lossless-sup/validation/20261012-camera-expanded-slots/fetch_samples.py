"""Fetch bounded known DNG names after a completed trial; no clip dir listing.

The read buffer exceeds the maximum file for the tested FHD12/3K12 modes.
The native actual length must be below that bound and equal the saved length.
These are samples, not proof that every frame in the clip decodes.
"""
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT / 'fpSup/fp_usb_shell'),
               str(ROOT / 'projects/open-gate/build'),
               str(ROOT / 'projects/lossless-sup/tools')]
import putfile as pf
from fpcam import parse_dng
from check_take import frame

if __name__ == '__main__':
    label = sys.argv[1]
    trial = json.loads((HERE / (label + '.json')).read_text())
    assert 'completed_at' in trial and len(trial['new_clips']) == 1
    clip = trial['new_clips'][0]
    line = next(l for l in trial['folders_after'].splitlines() if l.split()[-1] == clip)
    date = line.split()[0].replace('/', '')
    req, fin = map(int, re.search(r'req_cnt=(\d+), fin_cnt=(\d+),', trial['record_log']).groups())
    assert req == fin and 0 < fin <= 999999, 'sample plan requires a drained writer queue and six-digit file numbers'
    dest = HERE / (label + '-frames')
    dest.mkdir()
    report = {'clip': clip, 'requested': req, 'finished': fin, 'sample_only': True, 'frames': []}
    with open('/tmp/fp-af-fusion.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert pf.sh('status get is_recording', retries=0).strip() == 'is_recording -> 0'
        assert pf.mem_get(0xC358E140)[0] == 0
        assert pf.mem_get(0xC35A952C)[0] & 255 == 0
        numbers = set(map(int, sys.argv[2].split(','))) if len(sys.argv) > 2 else {1, (fin + 1) // 2, fin}
        assert 1 <= len(numbers) <= 3 and all(1 <= n <= fin for n in numbers)
        for n in sorted(numbers):
            remote = f'\\CINEMA\\{clip}\\{clip}_{date}_{n:06d}.DNG'
            local = dest / f'{n:06d}.DNG'
            bound = 12 * 1024 * 1024
            r = subprocess.run([sys.executable, '-B', str(ROOT / 'fpSup/fp_usb_shell/getfile.py'),
                remote, str(local), '--size', str(bound), '--partial'], capture_output=True, text=True)
            local.with_suffix('.read.log').write_text(r.stdout + r.stderr)
            assert r.returncode == 0, r.stdout + r.stderr
            actual = int(re.search(r'actual (\d+) of', r.stdout)[1])
            assert 0 < actual < bound and local.stat().st_size == actual
            tags, _ = parse_dng(local)
            check, _ = frame(str(local))
            check.update(number=n, main_ifd=tags, sha256=hashlib.sha256(local.read_bytes()).hexdigest())
            report['frames'].append(check)
            (dest / 'validation.json').write_text(json.dumps(report, indent=2))
            print(json.dumps(check), flush=True)
