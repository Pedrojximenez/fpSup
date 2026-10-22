#!/usr/bin/env python3
"""Offline audit of fp private color matrices; never connects to a camera."""

from pathlib import Path
import hashlib
import json
import struct
import subprocess
import numpy as np

OUT = Path(__file__).resolve().parent
PROJECT = OUT.parent.parent
ROM = PROJECT / 'out/MAIN_c0000000.bin'
DATA_SEGMENT = PROJECT / 'out/seg1_c2ef6e00.bin'
CAPTURES = PROJECT / 'research/imaging-hw/color-characterisation/captures'
FILES = [OUT.parent / 'fp-colormatrix-ab-20260923/A_original.DNG'] + [
    CAPTURES / name for name in ('_SDI0010.DNG', '_SDI0011.DNG', '_SDI0012.DNG', '_SDI0013.DNG')
]
MODES = [0x23, 1, 0, 3, 5, 6, 7, 0xe, 0xb, 0xc, 0xf, 8, 10, 0x24, 0xd, 0x24]


def numbers(value):
    return np.array([float(x) for x in str(value).split()])


def main():
    records = json.loads(subprocess.check_output([
        'exiftool', '-j', '-n', '-u', '-u', '-Software', '-PictureMode',
        '-Sigma_0x0033', '-Sigma_0x0034', '-Sigma_0x0124', '-Sigma_0x0129',
        '-CameraCalibration', *map(str, FILES),
    ], text=True))
    report = {'scope': 'Offline source/metadata audit; no sensor characterization or rendering claim.',
              'private_matrix_mode_order_from_writer': [hex(x) for x in MODES], 'captures': []}
    tables124, tables129 = [], []
    for record in records:
        a = numbers(record['Sigma_0x0124']).reshape(16, 3, 3)
        b = numbers(record['Sigma_0x0129']).reshape(16, 3, 3)
        tables124.append(a)
        tables129.append(b)
        report['captures'].append({
            'path': record['SourceFile'], 'software': record['Software'],
            'mode': record['PictureMode'],
            'body_calibration': numbers(record['CameraCalibration']).reshape(3, 3).tolist(),
            'private_wb_0x33': numbers(record['Sigma_0x0033']).tolist(),
            'private_current_matrix_0x34': numbers(record['Sigma_0x0034']).reshape(3, 3).tolist(),
            'tag_0x124_matrices': a.tolist(), 'tag_0x129_matrices': b.tolist(),
            'tag_0x124_OFF_identity': bool(np.array_equal(a[13], np.eye(3))),
        })
    report['all_selected_captures_tag_0x124_equal'] = all(np.array_equal(x, tables124[0]) for x in tables124)
    report['all_selected_captures_tag_0x129_equal'] = all(np.array_equal(x, tables129[0]) for x in tables129)
    rom = ROM.read_bytes()
    report['rom_sha256'] = hashlib.sha256(rom).hexdigest()
    report['rom_size'] = len(rom)
    data_segment = DATA_SEGMENT.read_bytes()
    report['initialized_data_segment_sha256'] = hashlib.sha256(data_segment).hexdigest()
    # The container is not a flat mapping for this address range; use seg1.
    # These are initialized-image values, not a live RAM snapshot.
    report['initialized_image_matrices_not_runtime_proof'] = {
        hex(addr): np.array(struct.unpack_from('<9d', data_segment, addr - 0xc2ef6e00)).reshape(3, 3).tolist()
        for addr in (0xc2f19ca4, 0xc2f19cec)
    }
    report['builder_scale_constants'] = {
        hex(addr): struct.unpack_from('<d', rom, addr - 0xc0000000)[0]
        for addr in (0xc02c5934, 0xc02c593c, 0xc02cc400)
    }
    s50 = np.array(report['initialized_image_matrices_not_runtime_proof']['0xc2f19cec'])
    adobe_to_srgb = np.array(report['initialized_image_matrices_not_runtime_proof']['0xc2f19ca4'])
    for index, capture in enumerate(report['captures']):
        # Sigma MakerNote ColorSpace checked independently: A is sRGB, selected
        # stills are AdobeRGB(1998). Do not generalize this assumption to new files.
        adobe = index != 0
        basis = s50 @ adobe_to_srgb if adobe else s50
        recovered = np.linalg.inv(basis) @ np.linalg.inv(
            np.array(capture['private_current_matrix_0x34'])
        ) @ np.diag(1 / np.array(capture['private_wb_0x33']))
        q = np.rint(recovered * 512)
        signed = np.where(q >= 1024, q - 2048, q) / 512
        capture['current_matrix_inverse_recovery'] = {
            'selected_output_basis': 'AdobeRGB(1998)' if adobe else 'sRGB',
            'matrix_as_encoded_before_inverse': recovered.tolist(),
            'distance_from_nearest_Q9_integer': float(np.max(np.abs(recovered * 512 - q))),
            'candidate_signed_11bit_interpretation': signed.tolist(),
            'note': 'Assembly resolves an inverse omitted by decompiler. Non-OFF captured values include masked 11-bit coeffs; this is not a ready IDT or proof of wrong pixel rendering.',
        }
    report['A_OFF_runtime_matrix_max_error_from_identity'] = float(np.max(np.abs(
        np.array(report['captures'][0]['current_matrix_inverse_recovery']['matrix_as_encoded_before_inverse']) - np.eye(3)
    )))
    target = OUT / 'fp-private-matrix-audit.json'
    target.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({
        'report': str(target),
        'all_private_tables_equal': [report['all_selected_captures_tag_0x124_equal'], report['all_selected_captures_tag_0x129_equal']],
        'Standard_tag_0x124': tables124[0][2].tolist(),
        'OFF_tag_0x124': tables124[0][13].tolist(),
        'OFF_tag_0x129': tables129[0][13].tolist(),
        'constants': report['builder_scale_constants'],
        'initial_matrices': report['initialized_image_matrices_not_runtime_proof'],
    }, indent=2))


if __name__ == '__main__':
    main()
