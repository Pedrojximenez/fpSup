"""Set LOSS's own tile_force word (card state, not stock data); 0 = default grid.

Usage: python3 -B set_tile_force.py WxH | 0
Refuses while recording or with the writer busy. Reads the word back.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT / 'fpSup/fp_usb_shell'), str(ROOT / 'fpSup/lossless')]
import putfile as pf
import card_status as cs

arg = sys.argv[1]
if arg == '0':
    value = 0
else:
    w, h = map(int, arg.lower().split('x'))
    # tile_grid.h limits: width 32..512 step 32, height 16..512 step 16.
    assert 32 <= w <= 512 and w % 32 == 0 and 16 <= h <= 512 and h % 16 == 0, arg
    value = (w << 16) | h
assert pf.sh('status get is_recording', retries=0, timeout_ms=5000).strip() == 'is_recording -> 0'
assert pf.mem_get(0xC358E140)[0] == 0 and pf.mem_get(0xC35A952C)[0] & 255 == 0
fields = json.loads((HERE / 'candidate/layout.json').read_text())['fields']
record, state, base = cs.find_record(pf.mem_get)
address = state + fields['tile_force']
before = pf.mem_get(address)[0]
pf.mem_set(address, value)
after = pf.mem_get(address)[0]
print(f'tile_force @ {address:#x}: {before:#x} -> {after:#x}')
assert after == value
