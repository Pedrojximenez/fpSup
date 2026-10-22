#!/usr/bin/env python3
"""Read-only existing-capture comparison, no rendering/profile/rawpy postprocess.

Writes a derived JSON analysis only. Bayer measurements use raw_image samples,
metadata black subtraction, same-channel spatial averaging, and an explicitly
limited translation model. This is not a camera calibration or causal mode test.
"""
from pathlib import Path
from hashlib import sha256
from itertools import combinations
import json
import subprocess
import numpy as np
import rawpy

OUT = Path(__file__).resolve().parent
PROJECT = OUT.parent.parent
CAP = PROJECT / 'research/imaging-hw/color-characterisation/captures'
PATHS = [CAP / f'_SDI{i:04d}.DNG' for i in (10, 11, 12, 13, 5625, 5626)]
PATHS += [OUT.parent / 'fp-colormatrix-ab-20260923/A_original.DNG']
TAGS = '''ISO ExposureTime FNumber ExposureCompensation ExposureMode ExposureProgram
MeteringMode WhiteBalance WhiteBalanceMode ColorTemperature ColorTemp PictureMode
BlackLevel WhiteLevel BitsPerSample Compression PhotometricInterpretation
ImageWidth ImageHeight ActiveArea DefaultCropOrigin DefaultCropSize
CFARepeatPatternDim CFAPattern AsShotNeutral AnalogBalance CameraCalibration
ColorMatrix1 ColorMatrix2 DateTimeOriginal CreateDate SubSecTimeOriginal
LensModel FocalLength FocusMode ShutterType SerialNumber'''.split()
ORDER = [(0, 0), (0, 1), (1, 0), (1, 1)]


def block(a, size):
    h, w = a.shape[:2]
    return a[:h//size*size, :w//size*size].reshape(
        h//size, size, w//size, size, *a.shape[2:]
    ).mean(axis=(1, 3))


def phase_shift(a, b):
    """Return b displacement vs a, in array pixels; same image should give zero."""
    # Fixed textured central/right room region; no channel mixing with R/B.
    a, b = a[80:-80, 230:-80], b[80:-80, 230:-80]
    window = np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1]))
    fa = np.fft.rfft2((a-a.mean())*window)
    fb = np.fft.rfft2((b-b.mean())*window)
    cross = fb * np.conj(fa)
    cross /= np.maximum(abs(cross), 1e-12)
    corr = np.fft.irfft2(cross, s=a.shape)
    peak = np.unravel_index(np.argmax(corr), corr.shape)
    shifts = []
    for dim, p in enumerate(peak):
        c = corr[peak]
        ix1, ix2 = list(peak), list(peak)
        ix1[dim], ix2[dim] = (p-1)%corr.shape[dim], (p+1)%corr.shape[dim]
        lo, hi = corr[tuple(ix1)], corr[tuple(ix2)]
        offset = 0.5*(lo-hi)/(lo-2*c+hi)
        shifts.append((p if p <= corr.shape[dim]//2 else p-corr.shape[dim]) + offset)
    return np.array(shifts), float(corr[peak])


def translated_samples(a, dy, dx):
    # Output at reference coordinate y,x samples target at y+dy,x+dx.
    h, w = a.shape[:2]
    ys, xs = np.arange(h)+dy, np.arange(w)+dx
    yi, xi = np.floor(ys).astype(int), np.floor(xs).astype(int)
    fy, fx = ys-yi, xs-xi
    yi, xi = np.clip(yi, 0, h-2), np.clip(xi, 0, w-2)
    return ((1-fy)[:,None,None]*((1-fx)[None,:,None]*a[yi[:,None],xi[None,:]] +
             fx[None,:,None]*a[yi[:,None],xi[None,:]+1]) +
            fy[:,None,None]*((1-fx)[None,:,None]*a[yi[:,None]+1,xi[None,:]] +
             fx[None,:,None]*a[yi[:,None]+1,xi[None,:]+1]))


def measure(a, b):
    # Blocks are 32x32 Bayer pixels (16x16 samples from each individual plane).
    a, b = block(a, 8), block(b, 8)
    core = np.zeros(a.shape[:2], dtype=bool)
    core[2:-2, 2:-2] = True
    valid = core & np.all((a > 300) & (b > 300) & (a < 13000) & (b < 13000), axis=2)
    x, y = a[valid], b[valid]
    ratios = y/x
    slopes = (x*y).sum(axis=0)/(x*x).sum(axis=0)
    median = np.median(ratios, axis=0)
    # Exact change in chromatic ratio, not an unweighted average of G gains.
    # (target_R / mean(target_G1,target_G2)) /
    # (reference_R / mean(reference_G1,reference_G2)); likewise for B.
    chroma = ((y[:, [0, 3]] / y[:, [1, 2]].mean(axis=1)[:,None]) /
              (x[:, [0, 3]] / x[:, [1, 2]].mean(axis=1)[:,None]))
    # Smoothing/low-texture subset to reduce residual alignment confounding.
    green = a[..., [1,2]].mean(axis=2)
    gy, gx = np.gradient(green)
    smooth = valid & ((abs(gy)+abs(gx))/np.maximum(green, 1) < 0.04)
    smooth_ratios = b[smooth]/a[smooth]
    return {
        'valid_blocks': int(valid.sum()),
        'median_ratio_RG1G2B': median.tolist(),
        'ratio_percentiles_05_95_RG1G2B': np.quantile(ratios,[.05,.95],axis=0).tolist(),
        'zero_intercept_least_squares_slope_RG1G2B': slopes.tolist(),
        'median_R_over_G_and_B_over_G_ratio': np.median(chroma,axis=0).tolist(),
        'rms_residual_after_per_channel_gain_ADU': np.sqrt(np.mean((y-x*slopes)**2,axis=0)).tolist(),
        'pearson_RG1G2B': [float(np.corrcoef(x[:,i],y[:,i])[0,1]) for i in range(4)],
        'low_texture_blocks': int(smooth.sum()),
        'low_texture_median_ratio_RG1G2B': np.median(smooth_ratios,axis=0).tolist(),
    }


def main():
    metadata = json.loads(subprocess.check_output(
        ['exiftool','-j','-G1','-a','-s','-n'] + ['-'+t for t in TAGS] +
        [str(p) for p in PATHS], text=True))
    result = {
        'purpose': 'Existing sequential captures: test consistency, not prove RAW mode invariance',
        'method': {
            'rawpy': rawpy.__version__,
            'processing': 'raw_image only, no demosaic, color matrix, profile, white balance or tone processing',
            'channels': ['R','G1','G2','B'],
            'registration_image': '2x2 same-channel mean in CFA planes = 4x4 original Bayer sampling grid; average green for translation only',
            'comparison': 'black subtraction then 32x32 original Bayer block means, exclude edge/dark/clipped blocks; no absolute exposure normalization because settings identical',
            'chromatic_ratio_change': '(target_R_or_B / mean(target_G1,target_G2)) / (reference_R_or_B / mean(reference_G1,reference_G2)), computed per block before median',
            'WB': '0010–13 have exactly equal AsShotNeutral; multiplying all by its reciprocal would cancel in reported ratios, so no WB was applied',
            'registration_model_limit': 'global translation only, not rotation/parallax/local object motion',
            'source_files_modified': False,
        },
        'files': {}, 'registered_pairs': [],
    }
    images = {}
    for p, meta in zip(PATHS, metadata):
        entry = {'path':str(p),'file_sha256':sha256(p.read_bytes()).hexdigest(),'metadata':meta}
        with rawpy.imread(str(p)) as raw:
            a = raw.raw_image
            entry['raw'] = {
                'shape': list(a.shape), 'dtype':str(a.dtype), 'bayer_sha256':sha256(a.tobytes()).hexdigest(),
                'raw_pattern':raw.raw_pattern.tolist(), 'color_desc':raw.color_desc.decode(),
                'black_levels_by_color_index':raw.black_level_per_channel,
                'white_level':raw.white_level, 'rawpy_sizes':raw.sizes._asdict(),
                'camera_whitebalance':list(raw.camera_whitebalance),
            }
            plane_means = []
            planes = []
            for yy,xx in ORDER:
                index = int(raw.raw_pattern[yy,xx])
                plane = a[yy::2,xx::2].astype(np.float32) - raw.black_level_per_channel[index]
                plane_means.append(float(plane.mean(dtype=np.float64)))
                if p.name in [f'_SDI{i:04d}.DNG' for i in range(10,14)]:
                    planes.append(block(plane,2))
            entry['raw']['whole_image_mean_black_subtracted_RG1G2B'] = plane_means
            if planes:
                images[p.name] = np.stack(planes,axis=2)
        result['files'][p.name] = entry
        print('Read',p.name,flush=True)
    for na, nb in combinations(images,2):
        a,b = images[na],images[nb]
        shift,peak = phase_shift(a[...,1:3].mean(axis=2),b[...,1:3].mean(axis=2))
        aligned = translated_samples(b,*shift)
        result['registered_pairs'].append({
            'reference':na, 'target':nb, 'target_displacement_original_Bayer_yx':(shift*4).tolist(),
            'phase_correlation_peak':peak,
            'unregistered':measure(a,b),'registered':measure(a,aligned),
            'Bayer_samples_identical':result['files'][na]['raw']['bayer_sha256']==result['files'][nb]['raw']['bayer_sha256'],
        })
    target=OUT/'existing-raw-capture-comparison.json'
    target.write_text(json.dumps(result,indent=2)+'\n')
    print('Wrote derived analysis',target)
    for pair in result['registered_pairs']:
        print(pair['reference'],pair['target'],'shift yx',pair['target_displacement_original_Bayer_yx'],
              'ratios',pair['registered']['median_ratio_RG1G2B'],
              'R/G B/G',pair['registered']['median_R_over_G_and_B_over_G_ratio'])


if __name__ == '__main__':
    main()
