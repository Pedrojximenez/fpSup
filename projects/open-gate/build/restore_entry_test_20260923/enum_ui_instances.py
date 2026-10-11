#!/usr/bin/env python3
"""READ-ONLY: list every NB resource instance in the live GUI resource context
and find the ones whose record variants hold the Quick Set resolution groups.

    python3 enum_ui_instances.py LABEL

Layout (blk_c05.c, checked 2026-09-24):
  ctx          = word 0 of our UI state block 0xC0732700
  sub          = [ctx+0x888]
  count        = [sub+0x30]      instance pointers at [sub+0x3C] (FUN_c05dfe08/48, c05d7528)
  inst+0x08    name ptr          inst+0x18 parsed child (0 = acquire will re-parse, c05d8910)
  inst+0x1C/20 lang/region the child was built for      inst+0x28 cache flags
  inst+0x30    variant elem size inst+0x34 variant count  inst+0x40 variant data (c05d9ce0)
  variant      {lang, region, reader, offset}; record address = [reader+0x24] + offset
  child+0x0C   refcount (c05d5d18)

Writes nothing.  Saves everything to ui_instances_<LABEL>.json for offline analysis.
"""
import json
import signal
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
signal.alarm(1800)
from putfile import mem_get  # noqa: E402

QS_GROUPS = [0xC228C346, 0xC228CD3E, 0xC22A3433, 0xC22A3E2B, 0xC22BA520, 0xC22BAF18,
             0xC22D160D, 0xC22D2005, 0xC22E86FA, 0xC22E90F2, 0xC22FF7E7, 0xC23001DF,
             0xC23168D4, 0xC23172CC, 0xC232D9C1, 0xC232E3B9]


def words(addr, n):
    out = []
    while n > 0:
        k = min(n, 16)
        for attempt in range(6):
            got = mem_get(addr, k)
            if not any(w is None for w in got):
                break
        else:
            raise SystemExit(f'incomplete read at 0x{addr:08X} after retries')
        out += got
        addr += 4 * k
        n -= k
    return out


def cstr(addr, limit=48):
    if not addr:
        return None
    raw = b''.join(w.to_bytes(4, 'little') for w in words(addr & ~3, (limit + 7) // 4))
    raw = raw[addr & 3:]
    return raw.split(b'\0', 1)[0].decode('latin-1')


label = sys.argv[1]
ctx = words(0xC0732700, 1)[0]
sub = words(ctx + 0x888, 1)[0]
count, = words(sub + 0x30, 1)
data, = words(sub + 0x3C, 1)
print(f'ctx 0x{ctx:08X}  sub 0x{sub:08X}  instances {count}  data 0x{data:08X}')
if not 0 < count < 20000:
    raise SystemExit('implausible instance count; stopping')

ptrs = words(data, count)
insts = []
reader_base = {}
for i, inst in enumerate(ptrs):
    f = words(inst, 0x44 // 4)                       # inst+0x00 .. +0x40
    esz, vcount, vdata = f[0x30 // 4], f[0x34 // 4], f[0x40 // 4]
    variants = []
    if 0 < vcount < 64 and esz >= 16:
        raw = words(vdata, vcount * esz // 4)
        for v in range(vcount):
            lang, region, reader, off = raw[v * esz // 4:v * esz // 4 + 4]
            if reader and reader not in reader_base:
                reader_base[reader] = words(reader + 0x24, 1)[0]
            variants.append([lang, region, reader, off,
                             (reader_base.get(reader, 0) + off) & 0xFFFFFFFF])
    insts.append(dict(index=i, inst=inst, name_ptr=f[2], child=f[6], lang=f[7],
                      region=f[8], flags=f[10], variants=variants))
    if i % 200 == 0:
        print(f'  {i}/{count}', flush=True)

hits = []
for rec in insts:
    for v in rec['variants']:
        if v[4] in QS_GROUPS:
            hits.append(rec)
            break
for rec in hits:
    rec['name'] = cstr(rec['name_ptr'])
    rec['child_refcount'] = words(rec['child'] + 0xC, 1)[0] if rec['child'] else None

out = HERE / f'ui_instances_{label}.json'
out.write_text(json.dumps(dict(ctx=ctx, sub=sub, count=count, reader_base=reader_base,
                               instances=insts, qs_hits=[h['index'] for h in hits]),
                          indent=1))
print(f'saved {out.name}; exact QS-group matches: {len(hits)}')
for rec in hits:
    print(f"  #{rec['index']} inst 0x{rec['inst']:08X} name {rec['name']!r} child 0x{rec['child']:08X} "
          f"ref {rec['child_refcount']} flags 0x{rec['flags']:X} variants {len(rec['variants'])}")
