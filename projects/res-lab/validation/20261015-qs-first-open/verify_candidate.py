"""Verify the saved QS-only candidate offline, using the existing ARM harness.

The original record interpreter, resource cache, GUI and hardware calls are
the harness's declared stubs. This checks bytes and restoration, not latency.
"""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'legacy-fps-root/projects/open-gate/build/res-custom'
sys.path.insert(0, str(SOURCE))
import test_v3_rescustom as R
import vr_ui

meta = json.loads((HERE / 'qs-only/build.json').read_text())['files']
t = R.CoreTests()
t.core = (HERE / 'qs-only/32RESCUS.BIN').read_bytes()
t.f = meta['32RESCUS.BIN']['facts']
t.img = R.T.IMAGE.read_bytes()
t.rcds = {Path(name).name: (HERE / 'qs-only' / name).read_bytes()
          for name in meta if name.startswith('RESCUS/')}
for name, info in meta.items():
    data = (HERE / 'qs-only' / name).read_bytes()
    assert len(data) == info['bytes'], name
    assert hashlib.sha256(data).hexdigest() == info['sha256'], name
assert 'LV_RECORDS' not in R.L.S, 'candidate must retain the pre-style FPS layout'

cam = t.boot(vr=True)
t.assertEqual(t.outcome(cam, '32RESCUS.BIN'), 'LOADED')
t.assertEqual((t.S(cam, R.L.S['VR_WHY']), t.S(cam, R.L.S['VR_UI'])), (1, 1))
ids = t.qs_ids(cam)
t.assertEqual(sorted(ids), list(range(2, 8)), 'virtual row plus five file rows')
got = t.run_recipe(cam, 8)
for row in R.QS.recipe()['records']:
    stock = R.QS.stock(row)
    want = R.rcd.qs_target(row, stock, 8, ids)
    t.assertEqual(got[row['address']], stock if want is None else want,
                  (row['address'], row['rule']))

runs, _ = vr_ui.lv(t.img)
cam.power_off()
t.hooks_stock(cam)
for address, stock, _ in runs:
    t.assertEqual(bytes(cam.mu.mem_read(address, len(stock))), stock,
                  f'LV restore {address:#x}')

result = dict(
    artifact='qs-only/32RESCUS.BIN',
    sha256=hashlib.sha256(t.core).hexdigest(), bytes=len(t.core),
    loaded=True, custom_qs_rows=6, recipe_records=len(got),
    reference_bytes_equal=True, reader_base_and_cursor_restored=True,
    hooks_restored=True, legacy_lv_journal_restored=True,
    fps_style='pre-20261015-text-style', camera_latency_measured=False,
)
(HERE / 'candidate-verification.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
