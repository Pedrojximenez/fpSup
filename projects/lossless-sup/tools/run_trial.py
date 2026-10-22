#!/usr/bin/env python3
"""Fail-closed host-only regression for the existing slimRAW DNG builder.

Never changes the builder, source DNGs, camera, firmware, or transport. A fresh
run directory is required even when a metadata guard rejects every source.
All paths are explicit arguments; nothing depends on the caller's cwd.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

sys.dont_write_bytecode = True

from tiff_guard import (ClassicTIFF, Rejected, require, sha, overlap,
                        integers, scalar, validate_fhd, MAX_FILE)

LAYOUT = {259, 273, 278, 279, 322, 323, 324, 325}
TILE = (512, 368)


def preflight(data, builder):
    tree, width, height, start, bytecount, packed_bytes = validate_fhd(data)
    t = tree.root["tags"]
    # Predict the existing builder's *actual* allocator, then reject if its
    # write overlaps anything found by the independent recursive protector.
    # We deliberately do NOT pass expanded ranges to the builder or patch it.
    occupied = [(0, 8), (tree.root_at, tree.root_at + tree.root['length'])]
    occupied += [(entry['value_at'], entry['value_at'] + entry['size'])
                 for entry in t.values() if entry['size'] > 4]
    tiles = ((width + TILE[0] - 1) // TILE[0]) * ((height + TILE[1] - 1) // TILE[1])
    new_tags = len(t) - 3 + 4
    allocation = 2 + new_tags * 12 + 4 + 8 * tiles
    append = getattr(builder, 'HOST_ONLY_APPEND', False) is True
    if append:
        # Independent arithmetic: the new host-only builder may extend the
        # header but must not consume any old header bytes.
        free_at, free_len = start, allocation
        compressed_start = (start + allocation + 511) & ~511
    else:
        free_at, free_len = builder.largest_zero_run(data[:start], 0, start, occupied)
        compressed_start = start
    require(free_len >= allocation, 'builder found insufficient header space')
    write_range = (free_at, free_at + allocation)
    require(8 <= free_at and write_range[1] <= compressed_start, 'new IFD outside header')
    collisions = [r for r in tree.protected
                  if overlap(write_range, (r['start'], r['end']))]
    plan = {'width': width, 'height': height, 'frame_pixels': width * height,
            'raw_offset': start, 'raw_bytes': bytecount, 'packed_pixel_bytes': packed_bytes,
            'strip_nonpixel_tail_bytes': bytecount - packed_bytes,
            'strip_nonpixel_tail_sha256': sha(data[start + packed_bytes:start + bytecount]),
            'tile': list(TILE),
            'tile_count': tiles, 'predictor': 1, 'file_align': 512,
            'new_ifd_range': list(write_range), 'builder_zero_run_bytes': free_len,
            'layout_strategy': 'append_host_header' if append else 'existing_header_hole',
            'compressed_data_offset': compressed_start,
            'protected_ranges': tree.protected,
            'ifd_paths': [n['path'] for n in tree.nodes],
            'metadata_collisions': collisions}
    return tree, plan


def verify_result(source, output, before, source_tree, plan, build_result):
    import numpy as np
    import rawpy

    after = output.read_bytes()
    require(source.read_bytes() == before, 'SOURCE CHANGED during host trial')
    require(build_result['ifd_at'] == plan['new_ifd_range'][0] and
            build_result['need'] == plan['new_ifd_range'][1] - plan['new_ifd_range'][0],
            'builder allocation changed after preflight')
    root = ClassicTIFF(after)
    require(root.root_at == plan['new_ifd_range'][0], 'output IFD at unexpected offset')
    old_tags, new_tags = source_tree.root['tags'], root.root['tags']
    require(old_tags.keys() - LAYOUT == new_tags.keys() - LAYOUT,
            'non-layout root tag inventory changed')
    for tag in old_tags.keys() - LAYOUT:
        require(old_tags[tag]['entry'] == new_tags[tag]['entry'] and
                old_tags[tag]['raw'] == new_tags[tag]['raw'],
                f'non-layout root tag {tag} changed')
    for region in source_tree.protected:
        start, end = region['start'], region['end']
        require(before[start:end] == after[start:end], region['label'] + ' changed')
    old_nested = {(n['path'], n['offset'], n['length']) for n in source_tree.nodes
                  if n['path'] != 'IFD0'}
    new_nested = {(n['path'], n['offset'], n['length']) for n in root.nodes
                  if n['path'] != 'IFD0'}
    require(old_nested == new_nested, 'nested IFD graph changed')
    # Stronger than tag comparison: every retained header byte outside the
    # root-pointer and approved new allocation must remain exactly unchanged.
    a, b = plan['new_ifd_range']
    limit = plan['raw_offset']
    if plan['layout_strategy'] == 'append_host_header':
        require(a == limit and before[:4] == after[:4] and before[8:limit] == after[8:limit],
                'original header changed beyond root pointer')
        require(not any(after[b:plan['compressed_data_offset']]), 'new header padding is not zero')
    else:
        require(before[:4] == after[:4] and before[8:a] == after[8:a] and
                before[b:limit] == after[b:limit], 'unapproved header byte changed')
    require(scalar(new_tags, 259) == 7 and scalar(new_tags, 322) == TILE[0] and
            scalar(new_tags, 323) == TILE[1], 'output tile layout not requested layout')
    offsets, counts = integers(new_tags, 324), integers(new_tags, 325)
    require(len(offsets) == len(counts) == plan['tile_count'], 'wrong tile count')
    end = plan['compressed_data_offset']
    for offset, count in zip(offsets, counts):
        require(offset == end and count > 0, 'tile stream not contiguous/nonempty')
        end += count
        require(end <= len(after), 'tile stream beyond file')
    require(len(after) == (end + 511) & ~511 and not any(after[end:]),
            'output file alignment/padding mismatch')
    with rawpy.imread(str(source)) as raw:
        original = raw.raw_image.copy()
    with rawpy.imread(str(output)) as raw:
        decoded = raw.raw_image.copy()
    require(original.shape == decoded.shape == (plan['height'], plan['width']),
            'LibRaw raster shape changed')
    require(np.array_equal(original, decoded), 'LibRaw decoded samples differ')
    return {'status': 'PASS', 'output': str(output), 'output_bytes': len(after),
            'ratio_source_over_output': len(before) / len(after),
            'output_sha256': sha(after), 'frame_pixels': int(original.size),
            'raw_sample_sha256_le_u16': sha(original.astype('<u2').tobytes()),
            'raw_samples_equal': True, 'source_root_ifd_bytes_equal': True,
            'non_layout_tags_equal': True, 'nested_metadata_bytes_equal': True,
            'header_only_approved_ranges_changed': True,
            'rawpy_version': rawpy.__version__, 'libraw_version': list(rawpy.libraw_version)}


def load_builder(path, encoder_dir=None):
    require(path.name in ('mkcompressed.py', 'mkcompressed_safe.py'),
            'explicit original or host-safe builder path required')
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location('trial_existing_mkcompressed', path)
    require(spec is not None and spec.loader is not None, 'cannot load existing builder')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if path.name == 'mkcompressed_safe.py':
        require(encoder_dir is not None, 'safe builder requires explicit --encoder-dir')
        module.configure_encoder(encoder_dir)
    return module


def trial(source, output, builder):
    require(source.is_file(), f'source is not a file: {source}')
    require(source.stat().st_size <= MAX_FILE, 'source too large for bounded FHD trial')
    before = source.read_bytes()
    result = {'source': str(source), 'source_bytes': len(before),
              'source_sha256_before': sha(before), 'output': None, 'output_bytes': None,
              'ratio_source_over_output': None, 'output_sha256': None}
    try:
        tree, plan = preflight(before, builder)
        result['preflight'] = plan
        result['frame_pixels'] = plan['frame_pixels']
        require(not plan['metadata_collisions'],
                'existing builder would overwrite recursively referenced metadata')
        require(not output.exists() and output.resolve() != source.resolve(),
                'output already exists or aliases source')
        built = builder.build(str(source), str(output), *TILE, predictor=1, file_align=512)
        result.update(verify_result(source, output, before, tree, plan, built))
        result['builder_result'] = built
    except Exception as exc:
        result['status'] = 'REJECTED' if isinstance(exc, Rejected) else 'ERROR'
        result['reason'] = str(exc)
        if output.exists():
            result['unverified_output'] = str(output)
    finally:
        result['source_sha256_after'] = sha(source.read_bytes())
        result['source_unchanged'] = result['source_sha256_after'] == result['source_sha256_before']
        if not result['source_unchanged']:
            result['status'] = 'ERROR'
            result['reason'] = 'SOURCE CHANGED'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--builder', type=Path, required=True)
    parser.add_argument('--encoder-dir', type=Path)
    parser.add_argument('--run-parent', type=Path, required=True)
    parser.add_argument('--source', type=Path, action='append', required=True)
    args = parser.parse_args()
    builder_path = args.builder.resolve(strict=True)
    parent = args.run_parent.resolve(strict=True)
    require(parent.is_dir(), '--run-parent must already be a directory')
    sources = [p.resolve(strict=True) for p in args.source]
    require(1 <= len(sources) <= 4 and len(sources) == len(set(sources)),
            'provide 1..4 distinct source files')
    encoder_dir = args.encoder_dir.resolve(strict=True) if args.encoder_dir else builder_path.parent
    dependencies = [builder_path, Path(__file__).with_name('tiff_guard.py')]
    dependencies += [encoder_dir / name for name in ('tiff.py', 'tilegeom.py', 'ljenc.py', 'ljcost.py', 'ljpeg.py')]
    # Include the original builder in the attestation even for the separate
    # safe path, to demonstrate that its camera-oriented assumptions did not change.
    dependencies += [encoder_dir / 'mkcompressed.py']
    source_hashes = {str(p): sha(p.read_bytes()) for p in dependencies}
    builder = load_builder(builder_path, encoder_dir)
    directory = Path(tempfile.mkdtemp(prefix='run-', dir=parent))
    records = [trial(source, directory / f'{index:02d}_{source.stem}_512x368_p1.DNG', builder)
               for index, source in enumerate(sources, 1)]
    unchanged = all(sha(Path(p).read_bytes()) == digest for p, digest in source_hashes.items())
    report = {'scope': 'host TIFF/RAW-format verification only; no camera, playback or hardware timing claim',
              'run_directory': str(directory), 'builder': str(builder_path),
              'builder_source_hashes_before': source_hashes, 'builder_sources_unchanged': unchanged,
              'tile': list(TILE), 'predictor': 1, 'file_align': 512, 'files': records,
              'pass_count': sum(r['status'] == 'PASS' for r in records),
              'all_passed': unchanged and all(r['status'] == 'PASS' for r in records)}
    report_path = directory / 'report.json'
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'report': str(report_path), 'all_passed': report['all_passed'],
                      'pass_count': report['pass_count'],
                      'files': [{'source': r['source'], 'status': r['status'],
                                 'reason': r.get('reason'), 'source_unchanged': r['source_unchanged'],
                                 'metadata_collisions': r.get('preflight', {}).get('metadata_collisions', [])}
                                for r in records]}, indent=2))
    return 0 if report['all_passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
