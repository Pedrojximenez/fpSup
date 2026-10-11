#!/usr/bin/env python3
"""Numerical audit of existing A/C Resolve TIFF exports, without modifying media."""

from pathlib import Path
import json
import sys
import numpy as np

ROOT = Path(__file__).resolve().parent
MEDIA = ROOT.parent / 'fp-colormatrix-ab-20260923'
sys.path.insert(0, str(MEDIA))
from analyze_tiff_pair import read_tiff, transfer_decode, transfer_encode, residual_stats


def stats(img):
    return {
        'min_RGB': img.min(axis=(0, 1)).tolist(),
        'max_RGB': img.max(axis=(0, 1)).tolist(),
        'mean_RGB': img.mean(axis=(0, 1)).tolist(),
        'zero_fraction_RGB': (img == 0).mean(axis=(0, 1)).tolist(),
        'max65535_fraction_RGB': (img == 65535).mean(axis=(0, 1)).tolist(),
        'gcd_of_stored_codes': int(np.gcd.reduce(img.reshape(-1))),
        'unique_values_per_channel': [len(np.unique(img[..., c])) for c in range(3)],
    }


def local_range(img):
    lo, hi = img.copy(), img.copy()
    for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        shifted = np.roll(img, (dy, dx), (0, 1))
        lo = np.minimum(lo, shifted)
        hi = np.maximum(hi, shifted)
    return np.max(hi - lo, axis=2)


def fit_models(a, c, valid):
    yy, xx = np.indices(valid.shape)
    train = valid & (((yy // 64 + xx // 64) % 2) == 0)
    test = valid & (((yy // 64 + xx // 64) % 2) == 1)
    xa, yc = a[train][::5], c[train][::5]
    ta, tc = a[test][::5], c[test][::5]
    results = {'training_samples': len(xa), 'spatial_holdout_samples': len(ta)}
    for kind in ['linear', 'sRGB', '2.2', '2.4']:
        x, y = transfer_decode(xa, kind), transfer_decode(yc, kind)
        tx, ty = transfer_decode(ta, kind), transfer_decode(tc, kind)
        coef, _, rank, singular = np.linalg.lstsq(x, y, rcond=None)
        affine, _, _, _ = np.linalg.lstsq(np.column_stack([x, np.ones(len(x))]), y, rcond=None)
        scale = float(np.sum(x*y) / np.sum(x*x))
        pred = transfer_encode(tx @ coef, kind)
        matrix = coef.T
        results[kind] = {
            'C_from_A_column_matrix': matrix.tolist(),
            'eigenvalues_real_imag': [[float(z.real), float(z.imag)] for z in np.linalg.eigvals(matrix)],
            'neutral_111_output': matrix.sum(axis=1).tolist(),
            'determinant': float(np.linalg.det(matrix)),
            'rank': int(rank), 'condition': float(singular[0]/singular[-1]),
            'holdout_matrix': residual_stats(pred-tc),
            'holdout_identity': residual_stats(ta-tc),
            'holdout_exposure_only': residual_stats(transfer_encode(tx*scale, kind)-tc),
            'exposure_only_scale': scale,
            'holdout_affine': residual_stats(transfer_encode(np.column_stack([tx,np.ones(len(tx))]) @ affine,kind)-tc),
            'affine_offset_decoded': affine[-1].tolist(),
            'holdout_decoded_relative_L2': float(np.linalg.norm(tx @ coef-ty)/np.linalg.norm(ty)),
        }
    return results


def main():
    paths = [MEDIA/'Timeline 1_01_00_02_24.tif', MEDIA/'Timeline 1_01_00_07_15.tif']
    (a16, ai), (c16, ci) = [read_tiff(p) for p in paths]
    assert a16.shape == c16.shape
    old_a, old_ai = read_tiff(MEDIA/'Timeline 1_01_00_02_04.tif')
    old_b, _ = read_tiff(MEDIA/'Timeline 1_01_00_06_27.tif')
    active = np.flatnonzero(np.any((a16 > 256) | (c16 > 256), axis=(1,2)))
    y0, y1 = int(active[0]), int(active[-1])+1
    a, c = [v[y0:y1].astype(float)/65535 for v in (a16,c16)]
    valid = np.all((a > .005)&(a < .98)&(c > .005)&(c < .98),axis=2)
    flat = np.all((a > .04)&(a < .90)&(c > .04)&(c < .90),axis=2)
    flat &= (local_range(a) < .006)&(local_range(c) < .006)
    flat[[0,-1],:] = False
    flat[:,[0,-1]] = False
    report = {
        'purpose':'A/C Resolve export behavior; not absolute color accuracy validation',
        'files':{'A':ai,'C':ci},
        'mapping_evidence':'User confirmed the second/latest-timecode file is C; earlier export is byte-identical to previous A.',
        'new_A_pixels_exactly_equal_previous_A':bool(np.array_equal(a16,old_a)),
        'new_A_file_hash_equals_previous_A':ai['sha256']==old_ai['sha256'],
        'C_pixels_equal_old_B_probe':bool(np.array_equal(c16,old_b)),
        'active_rows_half_open':[y0,y1],
        'A':stats(a16[y0:y1]),'C':stats(c16[y0:y1]),
        'difference_stored_values':residual_stats(c-a),
        'changed_pixels_fraction_active':float(np.any(a16[y0:y1]!=c16[y0:y1],axis=2).mean()),
        'fits_all_unclipped':fit_models(a,c,valid),
        'flat_selection':'Every channel in both files between .04 and .90; each image 4-neighbour RGB range < .006; exclude borders.',
        'fits_flat_unclipped':fit_models(a,c,flat),
        'limits':[
            'TIFF has no profile/transfer/primaries declaration; fitting a transfer is not measuring the actual export configuration.',
            'Matrix is fitted to this single limited-gamut scene, not a calibration, IDT, or LUT to reuse.',
            'Identical A baseline supports stability but does not prove identical per-clip settings for C.',
            'AsShotNeutral metadata identical does not guarantee identical inferred CCT or interpolation weights after changing ColorMatrix.',
            'Integer outputs cannot retain negative values or values above full scale; scaling/quantization can limit precision.',
        ],
    }
    destination=ROOT/'resolve-ac-analysis.json'
    with destination.open('x',encoding='utf-8') as f:
        json.dump(report,f,ensure_ascii=False,indent=2)
        f.write('\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
