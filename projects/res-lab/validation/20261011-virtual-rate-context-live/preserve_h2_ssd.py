"""Read/hash host-mounted SSD takes; never modify the source volume or camera."""
from pathlib import Path
import hashlib
import json
import shutil
import sys
import tempfile
import wave
from collections import Counter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT/'projects/open-gate/build'))
from fpcam import parse_dng

source = Path('/Volumes/Untitled/CINEMA')
dest = HERE/'h2-ssd-host-evidence'
dest.mkdir(exist_ok=True)
reports = []
for clip in ('A001_277', 'A001_278', 'A001_279'):
    folder = source/clip
    files = sorted(folder.glob('*'))
    assert files and all(p.is_file() for p in files)
    dngs = [p for p in files if p.suffix.upper() == '.DNG']
    numbers = [int(p.stem.rsplit('_',1)[1]) for p in dngs]
    assert numbers == list(range(1,len(dngs)+1))
    local = dest/clip
    local.mkdir(exist_ok=True)
    hashes = []
    for p in files:
        data = p.read_bytes()
        row = dict(name=p.name, bytes=p.stat().st_size,
                   mtime=p.stat().st_mtime, sha256=hashlib.sha256(data).hexdigest())
        if p.suffix.upper() == '.DNG':
            at = data.find(b'II*\0')
            row.update(tiff_offset=at, prefix_all_zero=not any(data[:max(at,0)]))
            assert at in (0,19456,65536)
        hashes.append(row)
    samples = []
    for i in sorted({0,(len(dngs)-1)//2,len(dngs)-1}):
        p = dngs[i]; q = local/p.name
        if q.exists(): assert q.read_bytes() == p.read_bytes()
        else: shutil.copyfile(p,q)
        data = q.read_bytes(); at = data.find(b'II*\0')
        if not at:
            main,ifds = parse_dng(q)
        else:
            # Parse tags relative to the displaced TIFF only. This temporary
            # byte slice is neither a repaired image nor a usable full frame.
            with tempfile.NamedTemporaryFile(suffix='.DNG') as temporary:
                temporary.write(data[at:]); temporary.flush()
                main,ifds = parse_dng(temporary.name)
        assert main['ImageWidth'] == 1008 and main['ImageLength'] == 672
        assert main['BitsPerSample'] == 12 and main['Compression'] == 1
        assert main['FrameRate'] == '30000/1001'
        samples.append(dict(file=q.name, number=numbers[i], tiff_offset=at,
                            parsed_relative_to_tiff=True, main_ifd=main, ifds=ifds,
                            declared_strip_end_from_tiff=main['StripOffsets']+main['StripByteCounts'],
                            tiff_base_plus_declared_strip_end=at+main['StripOffsets']+main['StripByteCounts'],
                            file_bytes=len(data)))
    extras = []
    for p in files:
        if p.suffix.upper() not in ('.WAV','.XMP','.TXT'): continue
        q = local/p.name
        if q.exists(): assert q.read_bytes() == p.read_bytes()
        else: shutil.copyfile(p,q)
        meta = dict(file=q.name)
        if p.suffix.upper() == '.WAV':
            with wave.open(str(q),'rb') as w:
                meta.update(rate=w.getframerate(), audio_frames=w.getnframes(),
                            seconds=w.getnframes()/w.getframerate(), channels=w.getnchannels())
        extras.append(meta)
    reports.append(dict(clip=clip, source=str(folder), count=len(dngs),
                        numbers_contiguous=True, files=hashes, samples=samples, extras=extras,
                        tiff_offset_counts=dict(Counter(x['tiff_offset'] for x in hashes
                                                        if 'tiff_offset' in x))))
(dest/'manifest.json').write_text(json.dumps(dict(takes=reports,
    limitations='User reports automatic early stop. Exact per-take actions and native stop '
                'logs are unavailable; the frame counts and tags do not independently prove '
                'vbuf, sensor cadence, durable writes or absence of mosaic. No full HDMI '
                'recording was captured for these manual SSD takes.'),indent=2)+'\n')
for r in reports: print(r['clip'], r['count'], r['tiff_offset_counts'],
                        r['samples'][0]['main_ifd']['FrameRate'])
