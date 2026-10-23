"""Exact plain consumers with the saved on-card loader; hardware services stubbed."""
import hashlib
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'legacy-fps-root/projects/open-gate/build/res-custom'
sys.path.insert(0, str(SOURCE))
import test_v3_rescustom as R
import vr_ui

results = []
rcds = None
existing_hooks = {int(a, 16) for a in re.findall(r'^12 ([0-9A-F]+)',
                  (HERE / 'backup/fpSup__LOAD.LOG').read_text(), re.M)}
for name in ('baseline', 'optimized'):
    folder = HERE / name
    meta = json.loads((folder / 'build.json').read_text())['files']
    t = R.CoreTests()
    t.core = (folder / '32RESCUS.BIN').read_bytes()
    t.f = meta['32RESCUS.BIN']['facts']
    t.img = R.T.IMAGE.read_bytes()
    t.rcds = {Path(n).name: (folder / n).read_bytes() for n in meta if n.startswith('RESCUS/')}
    if rcds is not None:
        t.assertEqual(t.rcds, rcds, 'A/B format data must match')
    rcds = t.rcds
    for n, info in meta.items():
        data = (folder / n).read_bytes()
        assert len(data) == info['bytes']
        assert hashlib.sha256(data).hexdigest() == info['sha256']
    files, dirs = R.rcd_card('32RESCUS.BIN', t.core, t.rcds)
    loader = (HERE / 'backup/fpSup__LOADER.BIN').read_bytes()
    files['\\fpSup\\LOADER.BIN'] = loader
    dirs['\\fpSup'] = [(n, a, len(loader) if n == 'LOADER.BIN' else size)
                        for n, a, size in dirs['\\fpSup']]
    cam = R.Cam(files, dirs, t.f, vr=True,
                autorun=(HERE / 'backup/AutoRun.txt').read_bytes())
    cam.boot()
    t.assertEqual(cam.misaligned, [])
    cam.S = t.s_addr(cam, '32RESCUS.BIN')
    t.assertEqual(t.outcome(cam, '32RESCUS.BIN'), 'LOADED')
    ids = t.qs_ids(cam)
    t.assertEqual(sorted(ids), list(range(2, 7)))
    got = t.run_recipe(cam, 7)
    for row in R.QS.recipe()['records']:
        stock = R.QS.stock(row)
        want = R.rcd.qs_target(row, stock, 7, ids)
        t.assertEqual(got[row['address']], stock if want is None else want)
    cam.power_off()
    t.hooks_stock(cam)
    for address, stock, _ in vr_ui.lv(t.img)[0]:
        t.assertEqual(bytes(cam.mu.mem_read(address, len(stock))), stock)
    sites = {int(h['site'], 16) for h in t.f['hooks']}
    overlaps = sites & existing_hooks
    assert not overlaps, [hex(s) for s in overlaps]
    results.append({'variant': name, 'sha256': hashlib.sha256(t.core).hexdigest(),
                    'bytes': len(t.core), 'custom_qs_rows': len(ids),
                    'recipe_records_equal': len(got), 'journal_restored': True,
                    'exact_card_loader': hashlib.sha256(loader).hexdigest(),
                    'existing_hook_site_overlap': [],
                    'other_sup_entries_emulated': False})
(HERE / 'pair-verification.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results, indent=2))
