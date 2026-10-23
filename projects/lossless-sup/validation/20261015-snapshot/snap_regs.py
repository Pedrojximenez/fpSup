import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3] / 'fpSup/fp_usb_shell'), str(HERE.parents[3] / 'fpSup/lossless')]
import putfile as pf, card_status as cs
f = json.loads((HERE / 'build-snap/layout.json').read_text())['fields']; _, st, _ = cs.find_record(pf.mem_get)
regs = pf.mem_get(st + f['engine_snap.on'] + 20, 21)
live = pf.mem_get(0x300D0040, 21)
out = {'label': sys.argv[1], 'snapshot': [hex(x) for x in regs], 'registers_now': [hex(x) for x in live]}
(HERE / f'regs-{sys.argv[1]}.json').write_text(json.dumps(out, indent=1))
print(sys.argv[1], ' '.join(f'{0x40+4*i:02X}:{x:08X}' for i, x in enumerate(regs) if x) or 'all zero')
