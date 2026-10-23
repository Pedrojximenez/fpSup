"""Fetch known DNG names of one clip (no clip-dir listing) and decode them.
Usage: python3 -B fetch_frames.py CLIP DATE N,N,...  -> frames-CLIP/ + validation.json"""
import hashlib, json, re, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(ROOT / 'projects/lossless-sup/tools')]
from check_take import frame
clip, date, nums = sys.argv[1], sys.argv[2], sorted(map(int, sys.argv[3].split(',')))
dest = HERE / f'frames-{clip}'; dest.mkdir(exist_ok=True)
rep = []
for n in nums:
    remote = f'\\CINEMA\\{clip}\\{clip}_{date}_{n:06d}.DNG'
    local = dest / f'{n:06d}.DNG'
    bound = 12 << 20
    r = subprocess.run([sys.executable, '-B', str(ROOT / 'fpSup/fp_usb_shell/getfile.py'), remote, str(local),
                        '--size', str(bound), '--partial'], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    actual = int(re.search(r'actual (\d+) of', r.stdout)[1])
    assert 0 < actual < bound and local.stat().st_size == actual
    try:
        info, _ = frame(str(local))
    except Exception as e:
        info = {'error': str(e)}
    info.update(number=n, sha256=hashlib.sha256(local.read_bytes()).hexdigest())
    rep.append(info); print(json.dumps(info), flush=True)
(dest / 'validation.json').write_text(json.dumps(rep, indent=1))
