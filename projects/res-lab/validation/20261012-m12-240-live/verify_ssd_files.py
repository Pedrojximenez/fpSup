"""Host-only checks of unchanged SSD originals, including malformed DNGs.

No repair, rotation or writer test. Hashes must match the preserved inventory.
Only TIFF-at-zero files are offered to the native DNG parser. Representative
misplaced headers are parsed relative to a temporary copy for diagnosis only.
"""
from collections import Counter
from pathlib import Path
import hashlib
import json
import shutil
import sys
import tempfile

import rawpy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3] / 'projects/open-gate/build'))
from fpcam import parse_dng


def main():
    inventory = json.loads((HERE / 'ssd-host-evidence/manifest.json').read_text())
    output = HERE / 'ssd-host-verification.json'
    assert not output.exists()
    reports = []
    for take in inventory['takes']:
        files = []
        representatives = []
        seen = set()
        for entry in take['files']:
            source = Path(take['source']) / entry['file']
            data = source.read_bytes()
            assert hashlib.sha256(data).hexdigest() == entry['sha256']
            offset = data.find(b'II*\0', 0, 0x20000)
            assert offset == entry['tiff_offset']
            result = {'file': source.name, 'tiff_offset': offset,
                      'prefix_all_zero': not any(data[:offset]) if offset > 0 else None}
            if offset == 0:
                main_ifd, _ = parse_dng(source)
                result['tags'] = {k: main_ifd.get(k) for k in (
                    'ImageWidth', 'ImageLength', 'BitsPerSample', 'Compression',
                    'DefaultCropSize', 'StripOffsets', 'StripByteCounts', 'FrameRate')}
            try:
                with rawpy.imread(str(source)) as raw:
                    result['libraw_shape'] = list(raw.raw_image.shape)
            except Exception as exc:
                result['libraw_error'] = type(exc).__name__ + ': ' + str(exc)
            files.append(result)
            if offset > 0 and offset not in seen:
                seen.add(offset)
                local = HERE / 'ssd-host-evidence' / take['clip'] / source.name
                if not local.exists():
                    shutil.copyfile(source, local)
                assert hashlib.sha256(local.read_bytes()).hexdigest() == entry['sha256']
                with tempfile.NamedTemporaryFile(suffix='.DNG') as tmp:
                    tmp.write(data[offset:])
                    tmp.flush()
                    tags, _ = parse_dng(tmp.name)
                representatives.append({'file': source.name, 'tiff_offset': offset,
                                        'relative_tags_only': tags,
                                        'original_decode_error': result.get('libraw_error')})
        report = {'clip': take['clip'], 'files': files, 'representatives': representatives,
                  'tiff_offsets': dict(Counter(f['tiff_offset'] for f in files)),
                  'libraw_decoded': sum('libraw_shape' in f for f in files),
                  'libraw_rejected': sum('libraw_error' in f for f in files),
                  'misplaced_prefixes_all_zero': all(f['prefix_all_zero'] for f in files if f['tiff_offset'] > 0)}
        reports.append(report)
        print(take['clip'], report['tiff_offsets'], 'decoded', report['libraw_decoded'],
              'rejected', report['libraw_rejected'], flush=True)
    output.write_text(json.dumps({'source_files_modified': False, 'takes': reports,
        'limitations': 'LibRaw decoding checks file structure, not scene quality or exposure cadence. Relative parsing does not repair a file.'}, indent=2) + '\n')


if __name__ == '__main__':
    main()
