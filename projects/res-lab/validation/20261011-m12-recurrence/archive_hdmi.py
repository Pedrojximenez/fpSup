"""Preserve HDMI evidence losslessly; remove RGB only after full decode hash.

Only task-owned temporary captures are affected. Camera files are never touched.
"""
import hashlib
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
for label in sys.argv[1:]:
    assert re.fullmatch(r'v(?:39|40)-[a-z0-9-]+', label)
    dest = HERE / label
    raw, movie, report = (dest / name for name in ('hdmi.rgb', 'hdmi.mkv', 'hdmi-archive.json'))
    assert raw.is_file() and not movie.exists() and not report.exists()
    size = raw.stat().st_size
    assert size == 240 * 1024 * 576 * 3
    digest = hashlib.sha256()
    with raw.open('rb') as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    original_hash = digest.hexdigest()
    with (dest / 'ffv1-encode.log').open('w') as log:
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'warning', '-f', 'rawvideo',
                        '-pixel_format', 'rgb24', '-video_size', '1024x576', '-framerate', '30',
                        '-i', str(raw), '-frames:v', '240', '-c:v', 'ffv1', '-level', '3',
                        '-g', '1', '-threads', '4', str(movie)], check=True, stderr=log)
    digest, decoded = hashlib.sha256(), 0
    with (dest / 'ffv1-decode.log').open('w') as log:
        proc = subprocess.Popen(['ffmpeg', '-hide_banner', '-loglevel', 'warning', '-i', str(movie),
                                 '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-fps_mode', 'passthrough',
                                 'pipe:1'], stdout=subprocess.PIPE, stderr=log)
        try:
            while chunk := proc.stdout.read(1024 * 1024):
                digest.update(chunk)
                decoded += len(chunk)
        finally:
            proc.stdout.close()
        assert proc.wait() == 0
    assert decoded == size and digest.hexdigest() == original_hash
    assert raw.stat().st_size == size
    proof = {'codec': 'FFV1', 'frames': 240, 'raster': [1024, 576],
             'original_rgb_bytes': size, 'decoded_rgb_bytes': decoded,
             'original_rgb_sha256': original_hash, 'decoded_rgb_sha256': digest.hexdigest(),
             'archive_bytes': movie.stat().st_size, 'archive_sha256': hashlib.sha256(movie.read_bytes()).hexdigest(),
             'full_decode_verified': True, 'temporary_rgb_removed': False}
    report.write_text(json.dumps(proof, indent=2) + '\n')
    raw.unlink()
    proof['temporary_rgb_removed'] = True
    report.write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps({'label': label, 'archive_bytes': proof['archive_bytes'], 'verified': True}), flush=True)
