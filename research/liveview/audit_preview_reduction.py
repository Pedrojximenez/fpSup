#!/usr/bin/env python3
"""Read-only ROM audit of fp preview reduction; no camera access or script execution."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--repo', type=Path, default=Path('/Users/dido/Developer.localized/SIGMAfp_re'))
    ap.add_argument('--output', type=Path, default=Path(__file__).with_name('preview-reduction-audit.json'))
    args = ap.parse_args()
    segments = []
    sources = []
    for name, base in [('seg0_c0000000.bin', 0xC0000000), ('seg1_c2ef6e00.bin', 0xC2EF6E00)]:
        path = args.repo / 'out' / name
        data = path.read_bytes()
        segments.append((base, data))
        sources.append({'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})

    def read(addr, size):
        for base, data in segments:
            if base <= addr and addr + size <= base + len(data):
                return data[addr-base:addr-base+size]
        raise ValueError(f'unmapped ROM read {addr:#x}+{size:#x}')

    def u32(addr):
        return struct.unpack('<I', read(addr, 4))[0]

    profile_path = args.repo / 'research/other/external/FP3K-technical-handoff-2026-09-10/analysis/firmware/raw-profiles.json'
    data = profile_path.read_bytes()
    profiles = json.loads(data)
    sources.append({'path': str(profile_path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    checked = 0
    for row in profiles['rows']:
        for col in profiles['columns']:
            actual = u32(col['table'] + 4 * row['index'])
            assert actual == row['words'][col['offset']//4], (row['index'], col['offset'])
            checked += 1
    mapping_base = profiles['mapping_base']
    if isinstance(mapping_base, str):
        mapping_base = int(mapping_base, 0)
    for i, expected in enumerate(profiles['mapping']):
        assert u32(mapping_base + i*4) == expected, i

    records_base = u32(0xC2F1E654 + 0x114)
    assert records_base == 0xC0B5F770
    assert u32(0xC0B5FCC0 + 0x9C) == 0xC0325228
    records = []
    for idx in range(2):
        addr = records_base + idx * 0x38
        raw = read(addr, 0x38)
        v = list(struct.unpack_from('<9H', raw, 8))
        h = list(raw[0x1C:0x28])
        h2 = list(raw[0x29:0x2C])
        vs = [sum(v[i:i+3]) for i in range(0, 9, 3)]
        hs = [sum(h[i:i+3]) for i in range(0, 12, 3)]
        assert vs == [4096]*3 and hs == [64]*4 and sum(h2) == 64
        records.append({'index': idx, 'address': f'0x{addr:08X}', 'hex': raw.hex(),
                        'v_variant': raw[6], 'v_control': raw[7], 'h_variant': raw[0x1B],
                        'vertical': v, 'vertical_triplet_sums': vs,
                        'horizontal': h, 'horizontal_triplet_sums': hs,
                        'horizontal2': h2, 'horizontal2_sum': sum(h2),
                        'main_v_control_if_vbin3': f'0x{(1 | (0 if raw[6] in (2,3) else 4)<<4 | int(raw[6] in (0,2))<<16 | int(raw[7] not in (0,1))<<29):08X}',
                        'sub_v_control_if_vbin3': f'0x{(1 | 4<<4 | int(raw[6] == 0)<<16 | int(raw[7] not in (0,1))<<29):08X}'})

    hmap, vmap = {0: 1, 1: 3, 2: 5}, {0: 1, 1: 3}
    counts = Counter()
    selected = []
    binned_profiles = []
    for row in profiles['rows']:
        w = row['words']
        get = lambda off: w[off//4]
        prev = [hmap[get(0x58)], vmap[get(0xC4)]]
        rec = [hmap[get(0x5C)], vmap[get(0xC8)]]
        counts[f'preview_{prev[0]}x{prev[1]}_record_{rec[0]}x{rec[1]}'] += 1
        if prev != [1, 1]:
            binned_profiles.extend(row['profile_ids'])
        if set(row['profile_ids']) & {1, 5, 429, 431, 432}:
            selected.append({'row': row['index'], 'profile_ids': row['profile_ids'],
                             'preview_hvbin': prev, 'record_hvbin': rec,
                             'preview_zoom_clamped': [max(1024,get(0x60)), max(1024,get(0xD0))],
                             'record_zoom_clamped': [max(1024,get(0x64)), max(1024,get(0xD4))],
                             'preview_base_dimensions': [get(0x0C), get(0x10)],
                             'record_base_dimensions': [get(0x00), get(0x04)],
                             'format_words_at_80_84': [get(0x80), get(0x84)]})
    accum = []
    for bits in [12, 13, 14]:
        mx = (1 << bits)-1
        accum.append({'input_bits': bits, 'max_input': mx,
                      'vertical_max_unsigned_weighted_sum': mx*4096,
                      'vertical_min_unsigned_accumulator_bits': (mx*4096).bit_length(),
                      'horizontal_max_unsigned_weighted_sum': mx*64,
                      'horizontal_min_unsigned_accumulator_bits': (mx*64).bit_length()})
    report = {'scope': 'Static ROM/table verification, not an active-state capture or pixel simulation of the ASIC.',
              'sources': sources, 'profile_cells_verified': checked, 'mapping_cells_verified': len(profiles['mapping']),
              'profile_row_counts': dict(counts), 'preview_binned_profile_ids': binned_profiles,
              'selected_profile_templates': selected, 'reduction_records': records,
              'conditional_accumulator_requirements': accum,
              'assumptions_and_limits': [
                  'Under the unsigned u16/u8 ROM interpretation, positive weights sum to 4096 vertically and 64 horizontally. ASIC coefficient signedness and division by these sums are not independently verified hardware specifications.',
                  'Under that coefficient interpretation, normalization and adequate intermediate precision, a weighted average lies between its input minimum and maximum.',
                  'Control fields are written exactly as modeled; their arithmetic semantics and actual ASIC accumulator width remain unknown.',
                  'Static profile templates can be selected/combined at runtime; profile IDs are not sensor-mode enum IDs.',
                  'A record DMA mux that does not select Vbin is not evidence that the preview pipeline bypasses Vbin.',
                  'Sensor saturation and gain/clamp stages before or after binning are not excluded by this audit.'
              ]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps({'verified_cells': checked, 'mapping_cells': len(profiles['mapping']), 'counts': dict(counts), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
