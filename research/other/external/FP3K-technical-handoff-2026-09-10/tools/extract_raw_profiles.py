"""Extract stock RAW processing profiles from the validated ARM table loader."""
import hashlib
import json
import struct
from pathlib import Path
from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'analysis/firmware'
b = (OUT / 'MAIN_c0000000.bin').read_bytes()
assert hashlib.sha256(b).hexdigest() == 'aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'
md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
columns = []
for offset in range(0, 0x104, 4):
    address = 0xc0439d28 + offset * 4
    ins = list(md.disasm(b[address-0xc0000000:address-0xc0000000+16], address))
    assert len(ins) == 4
    assert [i.mnemonic for i in ins] == ['movw', 'movt', 'ldr', 'str']
    assert all(i.op_str.startswith('r6, #') for i in ins[:2])
    assert ins[2].op_str == 'r3, [r6, r4, lsl #2]'
    assert ins[3].op_str == ('r3, [ip]' if not offset else f'r3, [ip, #{hex(offset) if offset >= 10 else offset}]')
    lo, hi = [int(i.op_str.split('#')[1], 0) for i in ins[:2]]
    columns.append({'offset': offset, 'table': lo | hi << 16, 'instruction': address})
bases = sorted(c['table'] for c in columns)
assert len(set(bases)) == 65
assert {y-x for x, y in zip(bases, bases[1:])} == {0x4c8}
count = 0x4c8 // 4  # Inferred from all 64 adjacent column spacings.
mapping_base = 0xc0bd05d4
assert bases[0] - mapping_base == 500 * 4
mapping = struct.unpack_from('<500I', b, mapping_base-0xc0000000)
assert all(x == 0xffffffff or x < count for x in mapping)
assert set(mapping) - {0xffffffff} == set(range(count))
rows = []
for index in range(count):
    words = [struct.unpack_from('<I', b, c['table']-0xc0000000+index*4)[0] for c in columns]
    rows.append({'index': index, 'profile_ids': [i for i, value in enumerate(mapping) if value == index],
                 'words': words, 'raw_dimensions': [words[0xdc//4] or words[0], words[0xe4//4] or words[1]],
                 'crop_dimensions': [words[0x24//4], words[0x2c//4]],
                 'reduction_enums': [words[0x5c//4], words[0xc8//4]],
                 'zoom': [words[0x64//4], words[0xd4//4]]})
result = {'scope': 'Static RAW profile loader; profile IDs are not sensor mode IDs. Live selection and hardware filter semantics remain unverified.',
          'columns': columns, 'mapping_base': mapping_base, 'mapping': list(mapping), 'rows': rows}
sensor_modes = {r['mode_id']: r for r in json.loads((OUT / 'sensor-modes.json').read_text())}
by_id = {pid: r for r in rows for pid in r['profile_ids']}
routes = []
# C043B828 selects these three tables; C043CCF8 scans 0x1A0 bytes in 16-byte records.
assert struct.unpack_from('<I', b, 0x43cd10)[0] == 0xe283be1a
for table in (0xc0be5810, 0xc0be59b0, 0xc0be5b50):
    for index in range(26):
        address = table + index * 16
        kind, profile_id, sensor_id, name_ptr = struct.unpack_from('<4I', b, address-0xc0000000)
        assert kind == 5 and profile_id in by_id and sensor_id in sensor_modes
        assert 0xc0be6000 <= name_ptr < 0xc0be6400
        name = b[name_ptr-0xc0000000:name_ptr-0xc0000000+32].split(b'\0',1)[0].decode('ascii')
        assert name.startswith(('UHD', 'FHD'))
        profile = by_id[profile_id]
        routes.append({'address': address, 'table': table, 'name': name, 'profile_id': profile_id,
                       'profile_row': profile['index'], 'sensor_mode': sensor_id,
                       'sensor_raster': sensor_modes[sensor_id]['raster'],
                       'raw_dimensions': profile['raw_dimensions'], 'crop': profile['crop_dimensions'],
                       'format_enum': profile['words'][0x84//4], 'zoom': profile['zoom']})
result['movie_routes'] = routes
(OUT / 'raw-profiles.json').write_text(json.dumps(result, indent=2)+'\n')
lines = ['# Stock RAW processing profiles', '', result['scope'], '',
         '65 column-load instruction blocks checked; 306 rows inferred from uniform column spacing. All 500 mapping entries are either invalid (FFFFFFFF) or in range; all 306 rows are referenced. Width/height include the nonzero override fields used by the stock getters.', '',
         '| Row | Profile IDs | RAW dimensions | Crop | Reduction enums H/V | Zoom H/V |', '|---:|---|---|---|---|---|']
for row in rows:
    if row['raw_dimensions'][0] in (3856, 3032, 6064, 1936):
        fmt = lambda values: ' × '.join(map(str, values))
        lines.append(f"| {row['index']} | {','.join(map(str,row['profile_ids']))} | {fmt(row['raw_dimensions'])} | {fmt(row['crop_dimensions'])} | {row['reduction_enums']} | {row['zoom']} |")
(OUT / 'raw-profiles.md').write_text('\n'.join(lines)+'\n')
route_lines = ['# Stock movie RAW routing', '',
               'Extracted from tables selected by C043B828. Format enum is the processing field at +0x84, not a bit count. The live camera has confirmed sensor mode 151 for UHD24 and 218 for FHD24, but not yet the selected processing profile.', '',
               '| Table | Name | Profile / row | Sensor mode | Sensor raster | RAW raster | Crop | Format enum | Zoom |',
               '|---|---|---|---:|---|---|---|---:|---|']
for r in routes:
    route_lines.append(f"| {r['table']:08X} | {r['name']} | {r['profile_id']} / {r['profile_row']} | {r['sensor_mode']} | {r['sensor_raster']} | {r['raw_dimensions']} | {r['crop']} | {r['format_enum']} | {r['zoom']} |")
(OUT / 'movie-raw-routing.md').write_text('\n'.join(route_lines)+'\n')
print(f'Extracted {len(rows)} rows, {len(columns)} fields, {len(mapping)} profile mappings.')
print('\n'.join(lines[:22]))
