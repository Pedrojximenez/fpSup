#!/usr/bin/env python3
"""Offline analysis of the one authorized diagnostic image; no camera access."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'fpSup/lut'))
from preview import YUYVFrame


def analyse(directory):
    report = json.loads((directory / 'report.json').read_text())
    raw = (directory / 'native-ring.bin').read_bytes()
    if (report['status'] != 'diagnostic-native-ring-read-complete'
            or not report['read_window_revoked'] or not report['state_unchanged']
            or report['original_state'] != report['final_state']
            or hashlib.sha256(raw).hexdigest() != report['raw_sha256']):
        raise ValueError('diagnostic provenance/state/transfer mismatch')
    width, height = report['descriptor']['width'], report['descriptor']['height']
    extent = width * height * 2
    frame = YUYVFrame.unpack(raw[:extent], width, height)
    ystream = np.frombuffer(raw, np.uint8)[::2][:1200000].astype(np.int16)
    rows = []
    for stride_pixels in (16, 32, 64, 128, 256, 512, 960, 1024, 1620, 1632, 1648, 1664, 1920, 2048):
        score = float(np.mean(np.abs(ystream[stride_pixels:] - ystream[:-stride_pixels])))
        rows.append({'stride_pixels': stride_pixels, 'mean_absolute_y_step': score})
    candidates = []
    canvas = Image.new('RGB', (1080, 660), '#111')
    draw = ImageDraw.Draw(canvas)
    for index, (matrix, value_range) in enumerate((('601', 'full'), ('709', 'full'),
                                                  ('601', 'limited'), ('709', 'limited'))):
        rgb = frame.rgb(matrix, value_range)
        name = f'{matrix}-{value_range}'
        # Clamp only the presentation PNG. Scientific statistics use original RGB.
        image = Image.fromarray(np.rint(np.clip(rgb, 0, 1) * 255).astype(np.uint8))
        image.save(directory / f'preview-{name}-hypothesis.png')
        image.thumbnail((530, 298))
        x, y = index % 2 * 540, index // 2 * 330
        canvas.paste(image, (x, y + 25))
        draw.text((x + 5, y + 5), name + ' hypothesis', fill='white')
        candidates.append({'matrix': matrix, 'range': value_range,
                           'rgb_min': float(rgb.min()), 'rgb_max': float(rgb.max()),
                           'fraction_pixels_outside_0_1': float(np.mean(np.any((rgb < 0) | (rgb > 1), axis=-1))),
                           'rgb_encoding_verified': False, 'gamma_conversion': False})
    canvas.save(directory / 'colour-decode-candidates.png')
    analysis = {**frame.summary(), 'raw_ring_sha256': report['raw_sha256'],
                'row_stride_bytes': width * 2, 'ring_bytes': len(raw),
                'excluded_tail_bytes': len(raw) - extent,
                'packing_evidence': 'complete recognizable scene at descriptor geometry, Y-first chroma-neutral byte lanes, and row-stride comparison',
                'packing_confirmed_for_this_capture': True,
                'applies_to_all_camera_modes': False,
                'linear_stride_candidates': rows, 'rgb_decode_hypotheses': candidates,
                'planes': {name: {'min': int(plane.min()), 'max': int(plane.max()),
                                   'p05_p50_p95': np.percentile(plane, [5, 50, 95]).tolist()}
                           for name, plane in (('y', frame.y), ('cb', frame.cb), ('cr', frame.cr))},
                'atomic_frame': False, 'frame_lease_owned': False,
                'cube_deployed': False, 'cube_pixel_fidelity_measured': False,
                'camera_cpu_runtime_verified': False,
                'sample_has_native_hardware_input_output_pairs': False,
                'conclusions': [
                    'This CINE MONIT1 sample is linear YUYV8 at 1620x911; old blanket tiled-ring interpretation is disproved for this mode.',
                    'Do not read the unused ring capacity as image pixels or count its 255 tail as highlight clipping.',
                    'A readable output is available, but RGB matrix/range, transfer function and primaries remain uncalibrated.',
                    'Eight-bit quantization and shared 4:2:2 chroma limit output-only recovery; seek pre-quantization/chroma-reduction correction placement.',
                    'A running producer was not leased or frozen; diagnostic bytes are not a coherent calibration frame.',
                    'Native setters/CPU kernel, frame ownership and full-cube error comparison remain required before live LUT fidelity claims.',
                ],
                'references': [
                    'https://www.itu.int/rec/R-REC-BT.601-7-201103-I/en',
                    'https://www.itu.int/rec/R-REC-BT.709-6-201506-I/en',
                    'https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/libavutil/csp.c'],
                'sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                           (Path(__file__), ROOT / 'fpSup/lut/preview.py', directory / 'report.json')}}
    (directory / 'analysis.json').write_text(json.dumps(analysis, ensure_ascii=False, indent=2) + '\n')
    return analysis


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    result = analyse(args.directory.resolve())
    print(f"{result['width']}x{result['height']} YUYV8, {result['row_stride_bytes']} byte stride; RGB encoding uncalibrated")
