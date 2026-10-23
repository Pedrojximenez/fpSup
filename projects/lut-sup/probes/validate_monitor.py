#!/usr/bin/env python3
"""Reproducible offline monitor validation against the archived ARRI reference.

Creates a new directory only. No camera IO, firmware/card build, or Resolve
project changes. The synthetic HDR chart demonstrates the numerical pipeline;
it is not a camera-calibration or LCD-fidelity measurement. ARRI remains a
generic numerical regression, not a CinemaDNG Camera RAW menu option.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageCms

ROOT = Path(__file__).resolve().parents[3]
LIB = ROOT/'fpSup/lut'
sys.path.insert(0, str(LIB))
from color import REFERENCE_SPACES
from cube import Cube
from monitor import Monitor, png_bytes, prepare, presets


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def chart(cube, output):
    width, height = 960, 180
    stops = np.linspace(-8, 8, width)
    scene = np.empty((height, width, 3))
    scene[:100] = (.18*2**stops)[None, :, None]
    # Six RGB/CMY scene-linear gradients below the neutral HDR ramp.
    colours = np.array([[1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 1, 1], [0, 0, 1], [1, 0, 1]])
    for i, colour in enumerate(colours):
        part = slice(i*160, (i+1)*160)
        scene[100:, part] = colour[None, None, :]*np.linspace(0, 4, 160)[None, :, None]
    canvas = Image.new('RGB', (width, 3*(height+56)+76), '#17191d')
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Unicode.ttf', 22)
    draw.text((18, 12), 'ARRI Classic LUT · 合成 HDR 輸入 · 輸出 Rec.709', font=font, fill='white')
    draw.text((18, 42), '灰階 −8 至 +8 EV；下排為 RGB／CMY 漸層。不是相機實拍或校準結果。', font=font, fill='#bec4ce')
    for index, strength in enumerate((0., .5, 1.)):
        image, _ = Monitor(cube, 'arri-logc3-ei800', strength).evaluate(scene, 'linear-709')
        y = 76 + index*(height+56)
        label = '基準監看（線性裁切＋Gamma 2.4）' if strength == 0 else f'LUT 強度 {strength:.0%}'
        draw.text((18, y+12), label, font=font, fill='white')
        canvas.paste(Image.open(io.BytesIO(png_bytes(image))), (0, y+50))
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    canvas.save(output, icc_profile=icc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='new validation directory')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    run = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'test_cinemadng', 'test_monitor', 'test_lut',
                          'test_preview', 'test_residual'], cwd=LIB, capture_output=True, text=True)
    (args.output/'tests.txt').write_text(run.stdout+run.stderr)
    if run.returncode:
        raise RuntimeError('monitor regression tests failed; see tests.txt')
    original = ROOT/'projects/lut-sup/assets/arri/official-20261009/ARRI_LogC3-to-Gamma24_Rec709_D65-Classic_33.cube'
    cube = Cube.read(original)
    if cube.sha256 != '29212a71808ab22f2819b904b3730fa4231b5841d883e43ec17610096dc38879':
        raise RuntimeError('official ARRI fixture hash mismatch')
    old = ROOT/'projects/lut-sup/validation/20261009-arri-classic-known-inputs-01'
    manifest = json.loads((old/'manifest.json').read_text())
    if manifest['source_sha256'] != cube.sha256:
        raise RuntimeError('archived ARRI reference uses a different LUT')
    encoded = np.load(old/'input_rgb_f64.npy', allow_pickle=False)
    expected = np.load(old/'target_rgb_f64.npy', allow_pickle=False)
    # These are archived LogC3/AWG3 samples and outputs. Reconstruct XYZ first,
    # exercising the NEW gamut/encoding path before comparing with the old data.
    xyz = REFERENCE_SPACES['arri-logc3-ei800'].to_xyz(encoded)
    actual, diagnostics = Monitor(cube, 'arri-logc3-ei800').evaluate(xyz, 'xyz-d65')
    delta = np.abs(actual-expected)
    if float(delta.max()) > 1e-9:
        raise RuntimeError('new monitor pipeline differs from archived reference')
    compiled = prepare(Monitor(cube, 'arri-logc3-ei800'), args.output/'arri-classic-33', 33)
    if compiled['compiled']['error']['max_channel'] > 1e-6:
        raise RuntimeError('same-domain ARRI table exceeded float32 reference error')
    chart(cube, args.output/'preview.png')
    (args.output/'presets.json').write_text(json.dumps(presets(), indent=2, ensure_ascii=False)+'\n')
    menu = presets()
    report = dict(schema='fpSup-monitor-validation-2', test_exit=run.returncode,
                  fixed_output=compiled['output'], cinemadng_color_spaces=len(menu['color_spaces']),
                  common_gammas=len(menu['common_gammas']), blackmagic_gammas=len(menu['blackmagic_gammas']),
                  standard_numerical_pairs=sum(len(c['numerical_gamma_ids']) for c in menu['color_spaces']),
                  menu_evidence=menu['menu_evidence'], menu_evidence_sha256=digest(ROOT/menu['menu_evidence']),
                  resolve_cinemadng_pixel_match_verified=False,
                  arri_regression_scope='generic numerical reference; not a CinemaDNG menu option',
                  original_cube_sha256=cube.sha256, archived_reference_samples=len(encoded),
                  archived_reference_max_channel_error=float(delta.max()),
                  archived_reference_mean_error=float(delta.mean()),
                  compiled_error=compiled['compiled']['error'],
                  scene_pipeline_diagnostics=diagnostics,
                  source_hashes={p.name: digest(p) for p in
                      [LIB/'color.py', LIB/'cinemadng.py', LIB/'monitor.py', LIB/'cube.py', LIB/'fplut.py',
                       LIB/'test_monitor.py', LIB/'test_cinemadng.py', Path(__file__).resolve()]},
                  archived_input_sha256=digest(old/'input_rgb_f64.npy'),
                  archived_target_sha256=digest(old/'target_rgb_f64.npy'),
                  camera_operations=False, fp_input_calibration_verified=False,
                  native_preview_runtime_verified=False, lcd_fidelity_verified=False)
    (args.output/'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)+'\n')
    print(json.dumps({k: report[k] for k in ['cinemadng_color_spaces', 'standard_numerical_pairs', 'archived_reference_samples',
          'archived_reference_max_channel_error', 'compiled_error']}, indent=2))


if __name__ == '__main__':
    main()
