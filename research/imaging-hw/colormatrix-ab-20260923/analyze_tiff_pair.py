#!/usr/bin/env python3
"""Analyze the supplied unsigned 16-bit TIFF exports without reducing precision."""

from pathlib import Path
from hashlib import sha256
import json
import struct
import numpy as np


ROOT = Path(__file__).resolve().parent
FILES = [ROOT / 'Timeline 1_01_00_02_04.tif', ROOT / 'Timeline 1_01_00_06_27.tif']


def read_tiff(path):
    raw = path.read_bytes()
    endian = {b'II': '<', b'MM': '>'}[raw[:2]]
    assert struct.unpack_from(endian + 'H', raw, 2)[0] == 42
    offset = struct.unpack_from(endian + 'I', raw, 4)[0]
    count = struct.unpack_from(endian + 'H', raw, offset)[0]
    tags = {}
    sizes = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8, 11: 4, 12: 8}
    for i in range(count):
        p = offset + 2 + i * 12
        tag, typ, n = struct.unpack_from(endian + 'HHI', raw, p)
        length = sizes[typ] * n
        start = p + 8 if length <= 4 else struct.unpack_from(endian + 'I', raw, p + 8)[0]
        value = raw[start:start + length]
        if typ in (3, 4):
            tags[tag] = struct.unpack(endian + {3: 'H', 4: 'I'}[typ] * n, value)
        else:
            tags[tag] = value
    width, height = tags[256][0], tags[257][0]
    assert tags[258] == (16, 16, 16)
    assert tags[259] == (1,) and tags[262] == (2,)
    assert tags.get(284, (1,)) == (1,)
    assert tags.get(339, (1, 1, 1)) == (1, 1, 1)
    assert len(tags[273]) == len(tags[279])
    pixels = b''.join(raw[o:o + n] for o, n in zip(tags[273], tags[279]))
    assert len(pixels) == width * height * 3 * 2
    a = np.frombuffer(pixels, dtype=endian + 'u2').reshape(height, width, 3)
    return a, {'path': str(path), 'sha256': sha256(raw).hexdigest(),
               'width': width, 'height': height, 'dtype': 'uint16',
               'has_ICC_profile': 34675 in tags,
               'has_TransferFunction': 301 in tags,
               'has_WhitePoint': 318 in tags,
               'has_PrimaryChromaticities': 319 in tags}


def transfer_decode(x, kind):
    if kind == 'linear':
        return x
    if kind == 'sRGB':
        return np.where(x <= .04045, x / 12.92, ((x + .055) / 1.055) ** 2.4)
    return x ** float(kind)


def transfer_encode(x, kind):
    if kind == 'linear':
        return x
    if kind == 'sRGB':
        return np.where(x <= .0031308, 12.92 * x,
                        1.055 * np.maximum(x, 0) ** (1 / 2.4) - .055)
    return np.sign(x) * np.abs(x) ** (1 / float(kind))


def residual_stats(error):
    return {'MAE_codes16': float(np.mean(np.abs(error)) * 65535),
            'RMSE_codes16': float(np.sqrt(np.mean(error ** 2)) * 65535),
            'P95_abs_codes16': float(np.quantile(np.abs(error), .95) * 65535),
            'P99_abs_codes16': float(np.quantile(np.abs(error), .99) * 65535),
            'max_abs_codes16': float(np.max(np.abs(error)) * 65535)}


def main():
    (a16, ai), (b16, bi) = [read_tiff(p) for p in FILES]
    assert a16.shape == b16.shape
    active_rows = np.flatnonzero(np.any((a16 > 256) | (b16 > 256), axis=(1, 2)))
    y0, y1 = int(active_rows[0]), int(active_rows[-1]) + 1
    a = a16[y0:y1].astype(np.float64) / 65535
    b = b16[y0:y1].astype(np.float64) / 65535
    report = {'files': [ai, bi], 'mapping_assumption': 'earlier timeline = A; later = B',
              'active_rows': [y0, y1], 'pixel_difference': residual_stats(b - a),
              'caveat': 'Stored TIFF values; output gamut/transfer not verified by file tags.'}
    for name, img in [('earlier', a16[y0:y1]), ('later', b16[y0:y1])]:
        report[name] = {'min_RGB': img.min(axis=(0, 1)).tolist(),
                        'max_RGB': img.max(axis=(0, 1)).tolist(),
                        'mean_RGB': img.mean(axis=(0, 1)).tolist(),
                        'zero_fraction_RGB': (img == 0).mean(axis=(0, 1)).tolist(),
                        'max_code_fraction_RGB': (img == 65535).mean(axis=(0, 1)).tolist()}
    # Exclude integer-endpoint clipping and extremely dark pixels from the fit.
    valid = np.all((a > .005) & (a < .98) & (b > .005) & (b < .98), axis=2)
    yy, xx = np.indices(valid.shape)
    train_mask = valid & (((yy // 64 + xx // 64) % 2) == 0)
    test_mask = valid & (((yy // 64 + xx // 64) % 2) == 1)
    train_a, train_b = a[train_mask][::5], b[train_mask][::5]
    test_a, test_b = a[test_mask][::5], b[test_mask][::5]
    report['training_samples'] = len(train_a)
    report['spatial_holdout_samples'] = len(test_a)
    report['fits'] = {}
    for kind in ['linear', 'sRGB', '2.2', '2.4']:
        x, y = transfer_decode(train_a, kind), transfer_decode(train_b, kind)
        tx = transfer_decode(test_a, kind)
        coef, _, rank, singular = np.linalg.lstsq(x, y, rcond=None)
        pred = transfer_encode(tx @ coef, kind)
        affine, _, _, _ = np.linalg.lstsq(np.column_stack([x, np.ones(len(x))]), y, rcond=None)
        pred_affine = transfer_encode(np.column_stack([tx, np.ones(len(tx))]) @ affine, kind)
        matrix = coef.T
        eig = np.linalg.eigvals(matrix)
        report['fits'][kind] = {
            'B_from_A_column_vector_matrix': matrix.tolist(),
            'eigenvalues_real_imag': [[float(v.real), float(v.imag)] for v in eig],
            'neutral_111_output': matrix.sum(axis=1).tolist(),
            'matrix_determinant': float(np.linalg.det(matrix)),
            'training_design_rank': int(rank),
            'training_design_condition': float(singular[0] / singular[-1]),
            'spatial_holdout': residual_stats(pred - test_b),
            'affine_spatial_holdout': residual_stats(pred_affine - test_b),
            'affine_offset_in_decoded_domain': affine[-1].tolist(),
        }
    out = ROOT / 'resolve-tiff-analysis.json'
    with out.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
