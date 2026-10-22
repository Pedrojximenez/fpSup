#!/usr/bin/env python3
"""Offline ROM audit only. Never imports or accesses camera transport.

The table's input index is NOT established as normalized sensor exposure.
Uses only the standard library.
"""
import argparse
import csv
import hashlib
import json
import math
import re
import struct
from pathlib import Path

BASE = 0xC0000000
INDEX = 0xC0971118
TABLE = 0xC0971F34
COUNT = 88
N = 2048


def audit(firmware):
    data = firmware.read_bytes()
    rows, curves = [], []
    for zero in range(COUNT):
        address, rom_id = struct.unpack_from('<II', data, INDEX - BASE + zero * 8)
        if (address, rom_id) != (TABLE + zero * 4096, zero + 1):
            raise ValueError(f'Unexpected ROM index entry {zero}: {address:#x}, {rom_id}')
        curve = struct.unpack_from('<2048H', data, address - BASE)
        if max(curve) > 8191 or any(a > b for a, b in zip(curve, curve[1:])):
            raise ValueError(f'Unexpected curve representation at {address:#x}')
        tail = N - 1
        while tail and curve[tail - 1] == curve[-1]:
            tail -= 1
        # An isolated final 8191 can hide a long near-top 8190 plateau.
        runs = []
        start = 0
        for end in range(1, N + 1):
            if end == N or curve[end] != curve[start]:
                if curve[start] >= 8189:
                    runs.append((start, end - 1, curve[start]))
                start = end
        longest = max(runs, key=lambda t: t[1] - t[0])
        row = dict(rom_id=rom_id, zero_index=zero, address=f'0x{address:08X}',
                   minimum=min(curve), maximum=max(curve), terminal_plateau_start=tail,
                   terminal_plateau_length=N-tail,
                   terminal_plateau_input_fraction=tail/(N-1),
                   table_domain_ev_to_full_scale=-math.log2(tail/(N-1)),
                   longest_near_top_run_start=longest[0],
                   longest_near_top_run_end=longest[1],
                   longest_near_top_run_value=longest[2],
                   unique_output_values=len(set(curve)))
        rows.append(row)
        curves.append(curve)
    return data, rows, curves


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--firmware', type=Path, default=Path(__file__).resolve().parents[2] / 'out/MAIN_c0000000.bin')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--historical-dir', type=Path, default=Path('/Users/dido/Documents/Codex/2026-08-16/4/outputs'))
    args = parser.parse_args()
    data, rows, curves = audit(args.firmware)
    args.output.mkdir(parents=True, exist_ok=True)
    payload = dict(source=str(args.firmware.resolve()), sha256=hashlib.sha256(data).hexdigest(),
                   table_sha256=hashlib.sha256(data[TABLE-BASE:TABLE-BASE+COUNT*4096]).hexdigest(),
                   caveat='Curve presence is proven; active LCD selection, pixel domain, scale, and clipping order are not.',
                   curves=rows)
    (args.output / 'tone-audit.json').write_text(json.dumps(payload, indent=2) + '\n')
    with (args.output / 'tone-audit.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    old = args.historical_dir / 'AutoRun_Stretched_ID83_Test.txt'
    if old.is_file():
        # Parse data; NEVER execute the historic AutoRun or its generator.
        written = {}
        for addr, value in re.findall(r'^mem set (0x[0-9A-Fa-f]+) (0x[0-9A-Fa-f]+)$', old.read_text(), re.M):
            address = int(addr, 16)
            if 0xC3414DA8 <= address < 0xC3414DA8 + 4096:
                if address in written:
                    raise ValueError('Duplicate curve write')
                written[address] = struct.pack('<I', int(value, 16))
        actual_bytes = b''.join(written[a] for a in range(0xC3414DA8, 0xC3414DA8+4096, 4))
        actual = struct.unpack('<2048H', actual_bytes)
        source = curves[82]
        expected = []
        for x in range(N):
            pos = x * 1918 / 2047
            lo, hi = int(pos), min(int(pos)+1, 1918)
            f = pos-lo
            expected.append(round(source[lo]*(1-f)+source[hi]*f))
        assert tuple(expected) == actual, 'Historical script differs from stretched ID83 calculation'
        historic = dict(script=str(old), script_sha256=hashlib.sha256(old.read_bytes()).hexdigest(),
                        payload_sha256=hashlib.sha256(actual_bytes).hexdigest(),
                        all_2048_samples_match_stretched_id83=True,
                        is_identity=False, formula='T83(x * 1918 / 2047), linearly interpolated and rounded',
                        max_input_headroom_gain_stops=-math.log2(1918/2047),
                        samples={str(x):dict(stretched=actual[x],identity=round(x*8190/2047)) for x in (0,128,256,512,1024,1536,1918,2047)},
                        no_clip_family5_rom_id50=rows[49],
                        caveat='Script content verified, not camera execution, readback, or observed LCD result.')
        (args.output / 'historical-curve-audit.json').write_text(json.dumps(historic, indent=2)+'\n')
    print(json.dumps(dict(curves_verified=len(rows), source_sha256=payload['sha256'],
                          selected=[rows[i] for i in (0,76,82)]), indent=2))


if __name__ == '__main__':
    main()
