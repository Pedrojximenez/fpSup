"""Diagnostic consumer: compare the historical native-30 high-rate carrier.

Use the maintained builder with process-local table overrides; production
sources, the producer and the shared loader stay byte-for-byte unchanged.
This is a camera experiment, not an accepted fix or a release.
"""
import hashlib
import json
import pathlib
import shutil
import struct
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BUILD = ROOT / 'projects/open-gate/build'
sys.path[:0] = [str(BUILD / 'res-custom'), str(BUILD)]
import build_v3_rescustom as RC
import ogc_layout as L
import vr_ui

out = ROOT / 'projects/res-lab/cards/20261011-m12-native30-v40/debug'
prior = ROOT / 'projects/res-lab/cards/20261011-m12-engine60-v39/debug'
assert not out.exists()
old_rates, old_times, old_ui = L.VRATES, L.VR_TIME, vr_ui.VRATES
assert old_rates[:2] == ((23976, 7, 10), (27972, 7, 10))
assert old_times[:2] == ((300300, 60.0, 240, 8, 1), (257400, 60.0, 280, 8, 1))
L.VRATES = tuple((rank, 3 if index < 2 else base, export)
                  for index, (rank, base, export) in enumerate(old_rates))
L.VR_TIME = tuple((cycles, engine, nominal, 3 if index < 2 else base, enabled)
                  for index, (cycles, engine, nominal, base, enabled) in enumerate(old_times))
vr_ui.VRATES = tuple((rank, 3 if index < 2 else base, export, text, label)
                     for index, (rank, base, export, text, label) in enumerate(old_ui))
with tempfile.TemporaryDirectory(prefix='reslab-native30-') as temp:
    data, facts, _ = RC.build_core(pathlib.Path(temp), virtual=True)
shutil.copytree(prior, out)
(out / 'fpSup/32RESCUS.BIN').write_bytes(data)
info = json.loads((out / 'build.json').read_text())
info['facts']['rescustom'] = facts
info['diagnostic_only'] = True
info['diagnostic_overrides'] = {'VRATES': L.VRATES, 'VR_TIME': L.VR_TIME, 'vr_ui.VRATES': vr_ui.VRATES}
(out / 'build.json').write_text(json.dumps(info, indent=2) + '\n')
(out / 'diagnostic-header.h').write_text(L.header())
before = (prior / 'fpSup/32RESCUS.BIN').read_bytes()
unchanged = {}
for path in prior.rglob('*'):
    if not path.is_file() or path.name in ('32RESCUS.BIN', 'build.json', 'MANIFEST.sha256'):
        continue
    relative = path.relative_to(prior)
    assert (out / relative).read_bytes() == path.read_bytes()
    unchanged[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
sources = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
           for path in (BUILD / 'res-custom').glob('*') if path.is_file()}
differences = [offset for offset, (a, b) in enumerate(zip(before, data)) if a != b]
header, old_header = struct.unpack_from('<8I', data), struct.unpack_from('<8I', before)
assert all(header[index] == old_header[index] for index in (0, 1, 2, 3, 5, 6, 7)), 'header ABI changed'
assert data[32:128] == before[32:128], 'CFG changed'
assert header[4] == facts['entry'] and 32 <= (header[4] & ~1) < len(data)
proof = {'diagnostic_only': True, 'candidate_sha256': hashlib.sha256(data).hexdigest(),
         'prior_sha256': hashlib.sha256(before).hexdigest(), 'bytes': len(data),
         'prior_bytes': len(before), 'different_bytes': len(differences),
         'difference_offsets': differences, 'unchanged': unchanged, 'source_sha256': sources,
         'build_script_sha256': hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
         'overrides': info['diagnostic_overrides']}
(out / 'PROVENANCE.json').write_text(json.dumps(proof, indent=2) + '\n')
(out / 'MANIFEST.sha256').write_text(''.join(
    f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(out)}\n'
    for path in sorted(out.rglob('*')) if path.is_file() and path.name != 'MANIFEST.sha256'))
print(json.dumps({key: proof[key] for key in ('candidate_sha256', 'bytes', 'prior_bytes', 'different_bytes')}, indent=2))
