#!/usr/bin/env python3
"""Inspect the pinned upstream QS patches as data; never execute camera code."""
import csv
import hashlib
import io
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'research/ui/tools'))
from nbr_stock import StockNbr, SEG0_SIZE

PIN = 'f4cddac261c47021ce666449cdab3deb6c12f1467b019113b6d70909b854fd98'
HOOKS = (0xC05E5B58, 0xC05E6400, 0xC05EC4B4, 0xC05FCE58,
         0xC05FD360, 0xC05FD4D0, 0xC05FD4E8, 0xC05FD8E0)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def inspect():
    source = ROOT / 'projects/julien-acquaviva/upstream/release/R168/FPOG.BIN'
    data = source.read_bytes()
    require(hashlib.sha256(data).hexdigest() == PIN, 'R168 source hash changed')
    header = struct.unpack_from('<12I', data)
    require(header[0] == 0x314D5246 and header[1] == 1 and
            header[2] == len(data) and header[5] == 1013, 'Unexpected FRM1 header')
    stock = (ROOT / 'out/MAIN_c0000000.bin').read_bytes()
    patched = bytearray(stock)
    patches = []
    for index in range(header[5]):
        address, size, old, new, kind, reserved = struct.unpack_from(
            '<6I', data, header[6] + index * 24)
        offset = address - 0xC0000000
        require(size > 0 and max(old, new) + size <= len(data) and
                0 <= offset < offset + size <= len(stock) and reserved == 0,
                f'Invalid patch {index}')
        require(stock[offset:offset + size] == data[old:old + size],
                f'Before-image mismatch at 0x{address:08X}')
        patched[offset:offset + size] = data[new:new + size]
        patches.append((address, size, kind))

    # Use directory lengths: the CSV files are adjacent, not NUL terminated.
    require(len(stock) >= SEG0_SIZE, 'Firmware image lacks the complete NBR segment')
    before_nbr = StockNbr(stock[:SEG0_SIZE])
    after_nbr = StockNbr(bytes(patched[:SEG0_SIZE]))
    tables = []
    for entry in before_nbr.entries:
        if '/Y2_3_' not in entry.path or not entry.path.endswith('.cvm'):
            continue
        before = before_nbr.read(entry.path)
        after = after_nbr.read(entry.path)
        if before == after:
            continue
        parse = lambda body: {int(row['ID']): row for row in
                              csv.DictReader(io.StringIO(body.decode('utf-8-sig')))}
        old_rows, new_rows = parse(before), parse(after)
        require(old_rows.keys() == new_rows.keys(), 'Editor IDs changed')
        changes = []
        for tile_id, row in new_rows.items():
            old_row = old_rows[tile_id]
            require(row['ID'] == old_row['ID'] and row['KEY'] == old_row['KEY'],
                    'Editor ID or localisation key changed')
            if row['IMAGE'] != old_row['IMAGE']:
                changes.append({'ui_id': tile_id, 'key': row['KEY'],
                                'before_image': old_row['IMAGE'],
                                'after_image': row['IMAGE']})
        tables.append({'path': entry.path, 'row_count': len(new_rows), 'changes': changes})
    require({row['ui_id'] for table in tables for row in table['changes']} ==
            {15, 17, 20, 21, 39, 48}, 'Unexpected changed editor slots')
    return {
        'scope': 'Static data inspection; no camera or firmware execution',
        'upstream': 'https://github.com/julienacquaviva/sigma-fp-supmod',
        'snapshot_commit': '3d60d0f7d3ecbc09843d87a80e35e6adf735abe2',
        'release': 'R168', 'source_sha256': PIN,
        'stock_sha256': hashlib.sha256(stock).hexdigest(),
        'patch_count': len(patches), 'all_before_images_match': True,
        'qs_cine_patch_count': sum(0xC2278C02 <= a < 0xC239C5FB for a, _, _ in patches),
        'editor_csv_changes': tables,
        'ui_hook_sites': [f'0x{a:08X}' for a, _, _ in patches if a in HOOKS],
        'limits': ['CSV data confirms retained IDs, not runtime setter behaviour',
                   'Patch counts do not measure rendering performance',
                   'No touchscreen or paging behaviour is established by this inspection']
    }


if __name__ == '__main__':
    result = inspect()
    output = ROOT / 'projects/qs-touch/validation/julien-qs-r168-static.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(f'PASS: {result["patch_count"]} before-images match; '
          f'{len(result["editor_csv_changes"])} editor tables retain IDs and keys; '
          f'evidence: {output.relative_to(ROOT)}')
