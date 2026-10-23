"""Verify the saved plain FPS-style + QS candidate offline; no camera I/O."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import argparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT / 'projects/open-gate/build/res-custom'))
import test_v3_rescustom as R
import vr_ui

parser = argparse.ArgumentParser()
parser.add_argument('--variant', default='combined')
parser.add_argument('--card-backup', default='backup')
parser.add_argument('--loader')
parser.add_argument('--proof')
args = parser.parse_args()
folder = HERE / args.variant
assert folder.resolve().parent == HERE
meta = json.loads((folder / 'build.json').read_text())['files']
t = R.CoreTests()
t.core = (folder / '32RESCUS.BIN').read_bytes()
t.f = meta['32RESCUS.BIN']['facts']
t.img = R.T.IMAGE.read_bytes()
t.rcds = {Path(n).name: (folder / n).read_bytes() for n in meta if n.startswith('RESCUS/')}
files, dirs = R.rcd_card('32RESCUS.BIN', t.core, t.rcds)
backup = HERE / args.card_backup
loader = (HERE / args.loader if args.loader else backup / 'fpSup__LOADER.BIN').read_bytes()
files['\\fpSup\\LOADER.BIN'] = loader
dirs['\\fpSup'] = [(n, a, len(loader) if n == 'LOADER.BIN' else length) for n, a, length in dirs['\\fpSup']]
cam = R.Cam(files, dirs, t.f, vr=True, autorun=(backup / 'AutoRun.txt').read_bytes())
cam.boot()
cam.S = t.s_addr(cam, '32RESCUS.BIN')
t.assertEqual(t.outcome(cam, '32RESCUS.BIN'), 'LOADED')
t.assertEqual((t.S(cam, R.L.S['VR_WHY']), t.S(cam, R.L.S['VR_UI'])), (1, 1))
t.assertEqual(len(cam.lv_ids), 29)
ids = t.qs_ids(cam)
t.assertEqual(sorted(ids), list(range(2, 7)))
got = t.run_recipe(cam, 7)
for row in R.QS.recipe()['records']:
    stock = R.QS.stock(row)
    want = R.rcd.qs_target(row, stock, 7, ids)
    t.assertEqual(got[row['address']], stock if want is None else want)
lv_rows = vr_ui.lv_records(t.img)
for row in lv_rows:
    data = bytearray(row['data'])
    for offset, label in row['marks']:
        struct.pack_into('>I', data, offset, cam.lv_ids[label])
    cam.qs_seen = []
    rd = t.reader(cam, row['address'])
    # A real booted reader may have registered resources before this LV set.
    cam.put(rd + 0x1c, 1)
    ret, _ = cam.call(R.QS_REC, r0=rd, thumb=True)
    t.assertEqual(ret, 0x55)
    t.assertEqual(b''.join(cam.qs_seen), bytes(data))
    t.assertEqual(len(cam.qs_seen), row['records'])
    t.assertEqual(cam.w(rd + 0x1c), 1)
    t.assertEqual(cam.w(rd + 36), R.NBU_BASE)
    t.assertEqual(cam.w(rd + 4), row['address'] - R.NBU_BASE + len(row['stock']))
cam.power_off()
t.hooks_stock(cam)
for address, stock, _ in vr_ui.lv(t.img)[0]:
    t.assertEqual(bytes(cam.mu.mem_read(address, len(stock))), stock)
result = {'sha256': hashlib.sha256(t.core).hexdigest(), 'bytes': len(t.core),
          'actual_card_loader': hashlib.sha256(loader).hexdigest(), 'custom_qs_rows': 5,
          'qs_reference_records_equal': len(got), 'lv_reference_records_equal': len(lv_rows),
          'LV_reader_resource_registration_flag': 1,
          'journal_restored': True, 'written_to_card': False, 'GUI_rendered': False}
(HERE / (args.proof or args.variant + '-verification.json')).write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
