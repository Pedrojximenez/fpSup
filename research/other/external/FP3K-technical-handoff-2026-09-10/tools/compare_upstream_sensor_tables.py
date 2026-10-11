"""Compare our decoded stock tables with fpSup's published CSVs. Read-only inputs."""
import csv
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / 'research/fpSup'
DATA = UPSTREAM / 'gyro/analysis_imx410'
OUT = ROOT / 'analysis/firmware'

def rows(name):
    with (DATA / name).open(newline='') as f:
        result = list(csv.DictReader(f))
    assert len(result) == 70
    return result

registers = json.loads((OUT / 'sensor-registers.json').read_text())
geometry = json.loads((OUT / 'sensor-modes.json').read_text())
assert len(registers['rows']) == len(geometry) == 70
checks = {'register_values': 0, 'geometry_words': 0, 'timing_parameters': 0}
for ours, theirs in zip(registers['rows'], rows('imx410_modes.csv')):
    assert ours['mode_id'] == int(theirs['mode_id'])
    assert ours['index'] == int(theirs['index'])
    for entry in registers['mapping']:
        assert ours['words'][entry['word_index']] == int(theirs[f"reg_0x{entry['register']:04x}"])
        checks['register_values'] += 1
for ours, theirs in zip(geometry, rows('imx410_mode_geometry.csv')):
    assert ours['mode_id'] == int(theirs['mode_id'])
    for i in range(1, 25):
        assert ours['geometry_words'][i] == int(theirs[f'field_0x{i*4:02x}'])
        checks['geometry_words'] += 1
for ours, theirs in zip(geometry, rows('imx410_timing.csv')):
    assert ours['mode_id'] == int(theirs['mode_id'])
    for i, field in enumerate(('hmax_cycles', 'tail_cycles', 'vmax_lines'), 1):
        assert ours['timing_record'][i] == int(theirs[field])
        checks['timing_parameters'] += 1
result = {
    'upstream': 'https://github.com/ijigen/fpSup',
    'commit': subprocess.check_output(['git', '-C', str(UPSTREAM), 'rev-parse', 'HEAD'], text=True).strip(),
    'modes': 70, 'matching_values': checks,
    'scope': 'Exact extracted values only; does not validate register meanings, measured frame rates, or recording feasibility.'
}
(OUT / 'upstream-table-verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
