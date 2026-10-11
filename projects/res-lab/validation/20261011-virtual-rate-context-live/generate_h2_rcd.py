"""Reconstruct the September 29 H2 parameter family as a named RCD.

No camera/USB operations. Archived live pairs and independent p13 defaults are
the geometry oracle. The exact A001_193 binary and its full FPS latch snapshot
are unavailable; the capture-engine value follows the preserved predecessor's
recipe/FPS-latch implementation, not an invented assertion of live readback.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT/'projects/open-gate/build'),
               str(ROOT/'projects/open-gate/build/res-custom')]
import rcd
import ogc_layout as L
import build_v3_rescustom as C
import build_og3k_ui_candidate as UI


def main():
    destination = HERE/'h2-success-rcd'
    destination.mkdir()
    source = HERE/'success-version-audit/historical-h2-profile-difference.json'
    reference = json.loads(source.read_text())
    pairs = sorted((int(k, 0), v) for k, v in reference['runtime_pairs'].items())
    assert len(pairs) == 25
    profiles = json.loads(Path(reference['profiles_source']).read_text())
    base = next(r['words'] for r in profiles['rows'] if 13 in r['profile_ids'])
    assert base[0x1c//4] == 2 and base[0x88//4] == 0
    canvas = base.copy()
    for offset, value in pairs:
        canvas[offset//4] = value
    engine = struct.unpack('<I', struct.pack('<f', 240000/1001))[0]
    canvas[0x30//4] = engine
    label = 'H2S240'
    UI.PLAN_TARGET = {'label': label, 'act': (992, 662)}
    pack, assets = UI.assets(destination, names={
        'OG3K_QS': label+'_QS', 'OG3K_SET': label+'_SET',
        'OG3K_FONT': label+'_FONT'})
    row = dict(label=label, profile=13, enum=7, stock_value=2, aspect=2,
               flags=0, prev_h=1334, act=(992, 662),
               modes=[(12, 2997, 330, 0, 6)],
               canvas_rec=pairs,
               canvas_pb=[(0,1008),(4,672),(0xc,1008),(0x10,672),
                          (0x24,992),(0x2c,662),(0xdc,1008),(0xe4,672)],
               row_text='H2S240 992x662', summary=label,
               capture_timing=[(2997, 0, 330|(330<<16), 910|(6<<16), engine, 240)])
    data = rcd.encode(row, pack, mincore=3)
    image = C.img()
    stock_ids = {C.word(C.TT + 0x20*i, image) for i in range(70)}
    decoded = rcd.decode(data, image, stock_ids)
    entry = next(e for e in decoded['entries'] if e['key'] == label+'30')
    assert (entry['w0'], entry['w1'], entry['engfps'], entry['nominal'], entry['vrate']) == \
           (330|(330<<16),910|(6<<16),engine,240,0)
    path = destination/(label+'.RCD')
    path.write_bytes(data)
    report = dict(file=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                  fnv1a=hex(struct.unpack_from('<I',data,L.RCD['SUM'])[0]),
                  required_consumer_product_version=16, rcd_wire_version=3,
                  parameters=row, expected_canvas=canvas, assets=assets,
                  source=str(source), source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  tested_entry=entry, sensor_fps=72000000/(330*910),
                  native_menu_fps='30000/1001', raw=[1008,672], crop=[992,662],
                  inference='Engine FPS derives from the preserved predecessor recipe-to-FPSLATCH path. '
                            'The exact live FPSLATCH at A001_193 start was not saved.',
                  limitations=['Reconstructed parameter family, not the exact old installed binary.',
                               'Only the native30 entry selects the historical240 capture timing.',
                               'Other generated carrier entries retain their ordinary timing.',
                               'Playback UI/assets and the maintained loader are current integrations.',
                               'No hardware recording test has passed for this reconstructed RCD.'],
                  camera_changed=False)
    (destination/'manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    (destination/'README.md').write_text(
        '# September29 H2 recording comparison\n\n'
        'H2S240.RCD reconstructs the archived M12/p13 parameter family: '
        'RAW1008x672, crop992x662,12-bit, RWZM2048/1024,25 archived live canvas pairs. '
        'Select H2S240 and native29.97p (30). That carrier alone requests sensor239.76p '
        'and capture-engine239.76p; the menu/container retains29.97p, like A001_193.\n\n'
        'Requires the development32RESCUS.BIN productv16. A required section makesv15 '
        'and earlier reject this file instead of silently ignoring its capture timing. '
        'The file belongs at `\\fpSup\\RESCUS\\H2S240.RCD`. '
        'Do not select280p for this historical comparison.\n\n'
        'The exact old binary and full FPS-latch snapshot are unavailable. Geometry '
        'matches the archived live25 pairs and independent nativep13 defaults. Engine '
        'cadence follows the preserved predecessor code and is explicitly an inference. '
        'This is a hardware test artifact, not a confirmed repair.\n')
    print(json.dumps({k:report[k] for k in ('file','bytes','sha256','sensor_fps',
          'native_menu_fps','camera_changed')},indent=2),flush=True)


if __name__ == '__main__':
    main()
