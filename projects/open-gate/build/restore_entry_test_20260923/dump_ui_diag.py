#!/usr/bin/env python3
"""Read the UI_DIAG caller-capture slots (0xC0732748..0xC07327C7, 128 bytes,
read-only) and name every word that falls inside a firmware function.

    python3 dump_ui_diag.py LABEL
"""
import bisect, json, re, signal, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DECOMP = Path('/Users/dido/Developer.localized/SIGMAfp_re/out/decomp/full')
sys.path.insert(0, '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
signal.alarm(90)
from putfile import mem_get  # noqa: E402

starts, names = [], []
for f in sorted(DECOMP.glob('blk_c0*.c')):
    for m in re.finditer(r'/\* ==== (\S+) @ ([0-9a-f]{8}) ==== \*/', f.read_text(errors='replace')):
        starts.append(int(m.group(2), 16)); names.append(m.group(1))
order = sorted(range(len(starts)), key=starts.__getitem__)
starts = [starts[i] for i in order]; names = [names[i] for i in order]


def where(v):
    if not 0xC0000000 <= v < 0xC0C00000:
        return ''
    i = bisect.bisect_right(starts, v & ~1) - 1
    return f'{names[i]}+0x{(v & ~1) - starts[i]:X}' if i >= 0 else ''


w = mem_get(0xC0732748, 32)
if any(x is None for x in w):
    sys.exit(f'incomplete read: {w}')
out = {}
for slot, base in (('A_first_target', 0), ('B_first_qs_resolution', 16)):
    s = w[base:base + 16]
    rows = dict(filled=s[0], record=hex(s[1]), parse_obj=hex(s[2]),
                caller_lr=[hex(s[3]), where(s[3])],
                stack=[[hex(v), where(v)] for v in s[4:16]])
    out[slot] = rows
    print(f'{slot}: filled={s[0]} record=0x{s[1]:08X} parse_obj=0x{s[2]:08X}')
    print(f'   LR     0x{s[3]:08X}  {where(s[3])}')
    for k, v in enumerate(s[4:16]):
        print(f'   sp+{k*4:02X}  0x{v:08X}  {where(v)}')
(HERE / f'ui_diag_{sys.argv[1]}.json').write_text(json.dumps(out, indent=1))
