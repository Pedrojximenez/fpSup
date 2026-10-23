"""Print the engine registers LOSS saved when each lane's last job ended (diag build)."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / 'fpSup/fp_usb_shell'), str(ROOT / 'fpSup/lossless')]
import putfile as pf, card_status as cs
f = json.loads((Path(__file__).parent / 'candidate/layout.json').read_text())['fields']
_, st, _ = cs.find_record(pf.mem_get)
out = {}
for lane in ('hold', 'hold_b'):
    base = st + f[lane + '.job.diag_regs']
    regs = [pf.mem_get(base + 4 * n)[0] for n in range(64)]
    ended = pf.mem_get(st + f[lane + '.job.diag_ended'])[0]
    # struct fpl_codec_job: diag_regs follows stall_regs at +200
    jb = base - 200
    names = {'width': 16, 'height': 20, 'tiles': 32, 'tile_width': 40, 'tile_height': 44,
             'source': 68, 'destination': 72, 'source_bytes': 84, 'destination_bytes': 88,
             'flag': 100, 'pattern': 104}
    job = {k: pf.mem_get(jb + o)[0] for k, o in names.items()}
    assert pf.mem_get(jb)[0] == 0x424f4a43, 'job magic'
    out[lane] = {'ended': ended, 'job': job, 'regs': regs}
(Path(__file__).parent / (sys.argv[1] + '.json')).write_text(json.dumps(out, indent=1))
for lane, v in out.items():
    print(lane, 'ended', v['ended'], {k: hex(x) for k, x in v['job'].items()})
    for n in range(0, 64, 8):
        print('  %02x: ' % (4 * n) + ' '.join('%08x' % x for x in v['regs'][n:n + 8]))
