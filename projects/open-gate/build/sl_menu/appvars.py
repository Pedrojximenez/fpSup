#!/usr/bin/env python3
"""Read-only: UI app variables by name (mem get only). Usage: appvars.py NAME..."""
import re, subprocess, sys, json, pathlib
SH = '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell'
CACHE = pathlib.Path('/tmp') / 'fp_appvars_cache.json'   # keyed by the table's address and size
def get(a, n):
    out = subprocess.run([sys.executable, '-B', 'shcmd.py', f'mem get {a:#x},,{n:#x}'], cwd=SH,
                         capture_output=True, text=True).stdout
    w = {}
    for m in re.finditer(r'A:0x([0-9a-f]+), D:0x([0-9A-F]+)', out):
        w[int(m.group(1), 16)] = int(m.group(2), 16)
    return w
def words(a, n):
    w = {}
    for o in range(0, n, 0x400):
        for _ in range(3):
            part = get(a + o, min(0x400, n - o))
            if len(part) == min(0x400, n - o) // 4: break
        w.update(part)
    return w
def fnv(s):
    h = 0x811c9dc5
    for b in s.encode(): h = ((h ^ b) * 0x1000193) & 0xFFFFFFFF
    return h
app = get(0xC37B7048, 4)[0xC37B7048]
reg = get(app + 0x888, 4)[app + 0x888] + 0x60
t = words(reg + 0x14, 0x18)
count, ents = t[reg + 0x14 + 8], t[reg + 0x14 + 0xC]
key = f'{ents:#x}:{count}'
cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
if key not in cache:
    w = words(ents, count * 12)
    cache = {key: {str(w[ents + 12 * i]): w[ents + 12 * i + 8] for i in range(count)}}
    CACHE.write_text(json.dumps(cache))
table = cache[key]
for name in sys.argv[1:]:
    d = table.get(str(fnv(name)))
    if d is None:
        print(f'{name:28s} not registered'); continue
    v = words(d, 12)
    print(f'{name:28s} desc {d:#x} type {v[d]} value {v[d+8]}')
