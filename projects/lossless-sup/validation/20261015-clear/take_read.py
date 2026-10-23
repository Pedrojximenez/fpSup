import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3] / 'fpSup/fp_usb_shell'), str(HERE.parents[3] / 'fpSup/lossless')]
import putfile as pf, card_status as cs
f = json.loads((HERE / 'build-plain/layout.json').read_text())['fields']; _, st, _ = cs.find_record(pf.mem_get)
g = lambda k: pf.mem_get(st + f[k])[0]
rep = {k: g(k) for k in ('take_frames', 'hold.held', 'hold.compressed', 'hold.refused', 'hold.faults', 'hold.stalls',
                         'hold_b.compressed', 'hold.job.reused', 'hold_b.job.reused', 'flush.applied', 'flush.tag_failed',
                         'engine_release', 'finishes', 'finish_busy', 'hold_live')}
rep['enable_now'] = pf.mem_get(0x300D0074)[0] & 1
(HERE / f'take-{sys.argv[1]}.json').write_text(json.dumps(rep, indent=1)); print(sys.argv[1], rep)
