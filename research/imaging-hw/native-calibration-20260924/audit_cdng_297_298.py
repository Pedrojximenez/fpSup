#!/usr/bin/env python3
"""Read-only audit of the user's OFF/Standard CinemaDNG sequences.

Original DNGs are opened only for reading. This writes a derived JSON report,
not media, camera settings, firmware, or Resolve settings.
"""
from pathlib import Path
from hashlib import sha256
import importlib.util
import json
import struct
import subprocess
import numpy as np

OUT = Path(__file__).resolve().parent
BASE = Path('/Users/dido/Movies/fpSup/color area')
spec = importlib.util.spec_from_file_location(
    'candidates', OUT.parent / 'fp-colormatrix-ab-20260923/generate_candidates.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
TAGS = {
    50721: 'ColorMatrix1', 50722: 'ColorMatrix2',
    50728: 'AsShotNeutral', 50778: 'CalibrationIlluminant1',
    50779: 'CalibrationIlluminant2', 50937: 'ProfileHueSatMapDims',
    50938: 'ProfileHueSatMapData1', 50939: 'ProfileHueSatMapData2',
    50940: 'ProfileToneCurve', 50714: 'BlackLevel',
    50717: 'WhiteLevel', 51022: 'OpcodeList3', 50730: 'BaselineExposure',
}
META_TAGS = '''Software PictureMode ISO ExposureTime FNumber FocalLength
LensModel AsShotNeutral CameraCalibration SerialNumber FrameRate
BaselineExposure BlackLevel WhiteLevel BitsPerSample ImageWidth ImageHeight
DefaultCropSize DateTimeOriginal'''.split()


def header(path):
    with path.open('rb') as stream:
        data = stream.read(131072)
    return helper.RootIFD(data)


def float_table(parsed, tag):
    typ, count, _, _ = parsed.entries[tag]
    assert typ == 11
    return np.array(struct.unpack(parsed.endian + 'f' * count, parsed.payload(tag)))


def main():
    rom = helper.ROM_PATH.read_bytes()
    references = {name: header(helper.OUT / filename) for name, filename in (
        ('A', 'A_original.DNG'), ('C', 'C_firmware_normal.DNG'))}
    result = {
        'purpose': 'Verify actual OFF/Standard CinemaDNG profile selection',
        'originals_modified': False,
        'rom_sha256': sha256(rom).hexdigest(),
        'scope': 'FHD 12-bit files with Software SIGMA fp Ver.5.02.0.V91; not every camera mode or firmware',
        'sequences': {},
        'not_tested': ['Resolve rendering of these new sequences',
                       'absolute color accuracy', 'full RAW pixel processing invariance'],
    }
    parsed_first = {}
    for sequence, branch in [('A001_297', 'OFF'), ('A001_298', 'normal')]:
        paths = sorted((BASE / sequence).glob('*.DNG'))
        assert paths
        metadata = json.loads(subprocess.check_output(
            ['exiftool', '-j', '-G1', '-a', '-s', '-n'] +
            ['-' + tag for tag in META_TAGS] + [str(paths[0])], text=True))[0]
        body = helper.body_calibration(paths[0]).astype(np.float32).astype(np.float64)
        first = header(paths[0])
        parsed_first[sequence] = first
        checks = {}
        for tag in (50721, 50722):
            checks[TAGS[tag]] = {'stored': first.matrix(tag).tolist()}
            for candidate, addresses in [('OFF', helper.OFF_ADDRESSES),
                                         ('normal', helper.NORMAL_ADDRESSES)]:
                matrix = np.array(struct.unpack_from(
                    '<9d', rom, addresses[tag] - helper.ROM_BASE)).reshape(3, 3)
                expected, _ = helper.firmware_payload(matrix, np.linalg.inv(body), first.endian)
                checks[TAGS[tag]][candidate + '_writer_payload_exact'] = expected == first.payload(tag)
            for name, reference in references.items():
                checks[TAGS[tag]][name + '_payload_exact'] = first.payload(tag) == reference.payload(tag)
            assert checks[TAGS[tag]][branch + '_writer_payload_exact']
        variants = {tag: {} for tag in TAGS}
        for path in paths:
            parsed = header(path)
            for tag in TAGS:
                digest = sha256(parsed.payload(tag)).hexdigest() if tag in parsed.entries else 'ABSENT'
                variants[tag][digest] = variants[tag].get(digest, 0) + 1
        profile = {}
        for tag in (50938, 50939):
            table = float_table(first, tag).reshape(-1, 3)
            profile[TAGS[tag]] = {
                'entries': len(table),
                'nonidentity_entries': int(np.any(table != [0, 1, 1], axis=1).sum()),
                'min_HSV': table.min(axis=0).tolist(),
                'max_HSV': table.max(axis=0).tolist(),
            }
        curve = float_table(first, 50940).reshape(-1, 2)
        profile['ProfileToneCurve'] = {
            'points': len(curve), 'identity': bool(np.array_equal(curve[:, 0], curve[:, 1])),
            'sample_near_input_0_3': curve[np.argmin(abs(curve[:, 0] - .3))].tolist(),
        }
        # Source identity is recorded for the representative frame, not conflated
        # with a RAW-pixel equivalence test of two separately recorded clips.
        file_hash = sha256(paths[0].read_bytes()).hexdigest()
        result['sequences'][sequence] = {
            'directory': str(BASE / sequence), 'frame_count': len(paths),
            'first_frame': str(paths[0]), 'last_frame': str(paths[-1]),
            'first_frame_sha256': file_hash, 'metadata_first_frame': metadata,
            'body_calibration_float32': body.tolist(), 'matrix_checks': checks,
            'tag_variants_all_frames': {TAGS[t]: values for t, values in variants.items()},
            'profile_first_frame': profile,
        }
    a, b = (parsed_first[key] for key in ('A001_297', 'A001_298'))
    result['first_frame_root_ifd_tag_differences'] = [
        {'tag': tag, 'name': TAGS.get(tag),
         'in_off': tag in a.entries, 'in_standard': tag in b.entries}
        for tag in sorted(a.entries.keys() | b.entries.keys())
        if tag not in a.entries or tag not in b.entries or
        a.entries[tag][:2] != b.entries[tag][:2] or a.payload(tag) != b.payload(tag)
    ]
    destination = OUT / 'cdng-297-298-audit.json'
    destination.write_text(json.dumps(result, indent=2) + '\n')
    for key, item in result['sequences'].items():
        print(key, item['frame_count'], 'frames')
        print(json.dumps(item['matrix_checks'], indent=2))
        print('Unique tag payloads:', {k: len(v) for k, v in item['tag_variants_all_frames'].items()})
        print('Profile:', item['profile_first_frame'])
    print('Derived report:', destination)


if __name__ == '__main__':
    main()
