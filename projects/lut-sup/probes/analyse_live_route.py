#!/usr/bin/env python3
"""Reconcile live metadata with exact native display/descriptor source facts."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from native_live_route import ROOT, ROM_PATH, ROM_SHA256


def native_function(file, name):
    path = ROOT / 'out/decomp/full' / file
    text = path.read_text()
    marker = re.search(r'/\* ==== ' + re.escape(name) + r' @ [0-9a-f]+ ==== \*/', text)
    if not marker:
        raise ValueError('missing native function ' + name)
    end = text.find('/* ==== ', marker.end())
    body = text[marker.start():end if end >= 0 else len(text)]
    return {'file': str(path.relative_to(ROOT)), 'line': text[:marker.start()].count('\n') + 1,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'body': body}


def analyse(path):
    report = json.loads(path.read_text())
    if (report['status'] != 'read-only-live-route-complete' or not report['unchanged']
            or report['camera_writes'] or report['pixel_data_read']
            or report['original_state'] != report['final_state']
            or report['original_controls'] != report['final_controls']):
        raise ValueError('route report is incomplete or not a read-only unchanged-state audit')
    for name, digest in report['source_sha256'].items():
        if hashlib.sha256((path.parent / name).read_bytes()).hexdigest() != digest:
            raise ValueError('archived probe hash mismatch: ' + name)
    rom = ROM_PATH.read_bytes()
    if hashlib.sha256(rom).hexdigest() != ROM_SHA256 or report['source_rom_sha256'] != ROM_SHA256:
        raise ValueError('firmware provenance mismatch')
    names = [('blk_c00.c', name) for name in
             ('FUN_c00dd520', 'FUN_c00dd6c8', 'FUN_c00e3948', 'FUN_c00e4830',
              'FUN_c00e4858', 'FUN_c00e4648', 'FUN_c00fa858', 'FUN_c00fa8f0')]
    names += [('blk_c01.c', name) for name in
              ('FUN_c01d7638', 'FUN_c0182228', 'FUN_c01822b8', 'FUN_c01d7708')]
    names += [('blk_c04.c', 'FUN_c0429560'), ('blk_c04.c', 'FUN_c04321a0'),
              ('blk_c04.c', 'XC_SigproRawMakePreview__v0'), ('blk_c06.c', 'FUN_c0625f68')]
    sources = {name: native_function(file, name) for file, name in names}
    assert 'FUN_c00dd508(1)' in sources['FUN_c00dd520']['body']
    assert 'FUN_c00fa858(param_2)' in sources['FUN_c00dd520']['body']
    assert '_DAT_c3025630 = FUN_c01822b8' in sources['FUN_c01d7638']['body']
    assert '_DAT_c30256b0 = FUN_c01822b8' in sources['FUN_c01d7638']['body']
    assert 'FUN_c001349c(param_1,4)' in sources['XC_SigproRawMakePreview__v0']['body']
    assert 'param_3[0xf] = uVar3' in sources['FUN_c04321a0']['body']
    samples = []
    for sample in report['samples']:
        region = sample['regions']
        get = lambda name: region[name]['words']
        selector_key = ('DISPLAY_PARAMETER_SELECTORS' if 'DISPLAY_PARAMETER_SELECTORS' in region
                        else 'DISPLAY_RANGE_SELECTORS')
        selectors = get(selector_key)
        a, b = get('LCD_MATRIX_CACHE_A'), get('LCD_MATRIX_CACHE_B')
        cache_a = a[:5] + get('LCD_MATRIX_CACHE_A_6') + [a[5]] + get('LCD_MATRIX_CACHE_A_8') + [a[6]]
        cache_b = [b[6], b[5], b[4], b[3], b[2]] + get('LCD_MATRIX_CACHE_B_6') + [b[1]] + get('LCD_MATRIX_CACHE_B_8') + [b[0]]
        banks = {}
        for bank in range(3):
            words = get('DISPLAY_CSC_' + str(bank))
            coefficients = [words[i] for i in (4, 5, 6, 8, 9, 10, 12, 13, 14)]
            if any(v > 0x7ff for v in coefficients):
                raise ValueError('coefficient outside native signed-11 candidate domain')
            signed = [v - 0x800 if v & 0x400 else v for v in coefficients]
            banks[bank] = {'coefficient_words': coefficients,
                           'cache_A_exact_match': coefficients == cache_a,
                           'cache_B_exact_match': coefficients == cache_b,
                           'signed11_div256_candidate_GBR_rows': [signed[i:i + 3] for i in (0, 3, 6)],
                           'offset_word': words[1], 'hardware_pixel_formula_verified': False}
            banks[bank]['signed11_div256_candidate_GBR_rows'] = [
                [v / 256 for v in row] for row in banks[bank]['signed11_div256_candidate_GBR_rows']]
        packed = get('DISPLAY_ROUTE_IDS')[0] & 0xffff
        first, second = packed & 255, packed >> 8 or packed & 255
        flags_first = rom[0xC07BFA8C - 0xC0000000 + first * 16:][:16]
        flags_second = rom[0xC07BFA8C - 0xC0000000 + second * 16:][:16]
        if len(flags_first) != 16 or len(flags_second) != 16:
            raise ValueError('invalid display route flags')
        class_a = first in (0x1e, 0x1f, 0x20)
        class_b = first in (0x29, 0x2a, 0x2b)
        dual = bool(flags_first[6] and (flags_second[0] or flags_second[3]) and (class_a or class_b))
        matrix_class = first in (0x1e, 0x1f, 0x20, 0x21, 0x22, 0x29, 0x2a, 0x2b)
        update_bank = 2 if dual else (None if matrix_class else 0)
        raw0, raw1 = get('DISPLAY_SCANOUT_INDICES')
        fmt = get('DISPLAY_COMPOSITE_KIND')[0]
        scan_indices = [((raw0 >> 24) if fmt & 15 in (12, 13, 14) else raw0) & 31,
                        ((raw1 >> 24) if (fmt >> 16) & 15 in (12, 13, 14) else raw1) & 31]
        descriptor = get('SIGSEQ_OUTPUT_0')
        count, width, height = descriptor[8], descriptor[3], descriptor[4]
        if not 0 < count <= 22 or not 0 < width <= 4096 or not 0 < height <= 4096:
            raise ValueError('unexpected output descriptor geometry/count')
        handles = descriptor[9:9 + count]
        bases = [h * 4 + 0x40000000 for h in handles]
        if any(not 0x40000000 <= p < 0x60000000 for p in bases):
            raise ValueError('unexpected native output handle')
        samples.append({'geometry': [width, height], 'output_handles': [hex(h) for h in handles],
                        'output_bases': [hex(p) for p in bases], 'descriptor_index': descriptor[31],
                        'second_develop_base': hex(get('SECOND_DEVELOP_DESCRIPTOR')[7]),
                        'display_route_ids': [first, second], 'raw_parameter_selectors': selectors,
                        'native_pending_matrix_update_bank': update_bank,
                        'native_lcd_cache_selected_by_C00DD520': 'B' if selectors[1] == 2 else 'A',
                        'display_scanout_indices': scan_indices,
                        'producer_engine2_index': get('WRITER_INDEX_2')[0] & 31,
                        'producer_engine8_index': get('WRITER_INDEX_8')[0] & 7,
                        'matrices': banks, 'atomic': False})
    old = ROOT / 'projects/lut-sup/validation/20261009-native-preview-bytes-01/analysis.json'
    prior = json.loads(old.read_text())
    result = {'status': 'metadata-and-native-route-reconciled', 'camera_operations': False,
              'measured_state': report['final_state'], 'samples': samples,
              'csc_configuration_stable': all(s['matrices'] == samples[0]['matrices'] for s in samples),
              'all_three_csc_banks_match_native_cache_B': all(
                  all(b['cache_B_exact_match'] for b in s['matrices'].values()) for s in samples),
              'prior_pixel_capture_geometry': [prior['width'], prior['height']],
              'current_metadata_geometry': samples[0]['geometry'],
              'current_geometry_pixel_packing_verified': False,
              'current_metadata_boot_matches_prior_pixel_capture': report['final_state']['boot_id'] == json.loads(
                  (old.parent / 'report.json').read_text())['final_state']['boot_id'],
              'frame_lease_owned': False, 'rgb_colourimetry_verified': False,
              'transfer_function_verified': False, 'cube_fidelity_verified': False,
              'facts': [
                  'Current hardware CSC words exactly match native cache B on all three banks and all three reads.',
                  'C00DD520 selects LCD cache B when the raw second selector equals 2; this does not label full/legal range.',
                  'C01D7638 updates output indices for contexts 1/2 before copying a descriptor; it is not a buffer lease.',
                  'Producer and scanout indices are live and were read sequentially; no free-buffer or coherent-frame claim follows.',
                  'The current geometry and boot differ from the one earlier authorized pixel capture; its packing must not be generalized.',
                  'XC_SigproRawMakePreview::v0 is a destructor, not a callable preview-processing entry.',
                  'C04321A0 allocates an output handle and issues native jobs; its context, cleanup and isolation still need audit.'
              ],
              'next_pixel_trial': {
                  'same_input': 'replay one owned, preserved input through stock, native fit, and native fit plus CPU correction',
                  'input_patterns': ['neutral ramp', 'R/G/B and C/M/Y ramps', 'RGB lattice and separate holdout samples'],
                  'first_backend': 'matrix and native tone only, then add CEQ/CUV after their pixel formula is identified',
                  'reference': 'full source cube with explicit input/output colour encoding',
                  'measurements': ['per-channel numerical error', 'holdout colour error after verified RGB decoding',
                                   'clipping/collisions', 'frame time and dropped frames'],
                  'requires_before_execution': ['owned input and output allocations', 'native job completion and cleanup',
                                                'explicit format/stride/bit depth', 'verified input calibration',
                                                'original-setting restoration'],
                  'executed': False},
              'sources': sources,
              'sha256': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest(),
                         str(old.relative_to(ROOT)): hashlib.sha256(old.read_bytes()).hexdigest(),
                         str(Path(__file__).relative_to(ROOT)): hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = analyse(args.report.resolve())
    with args.output.open('x') as f:
        f.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('status', 'current_metadata_geometry',
          'all_three_csc_banks_match_native_cache_B', 'frame_lease_owned', 'rgb_colourimetry_verified')}, indent=2))
