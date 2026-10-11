#!/usr/bin/env python3
"""List an NBU page's objects and their components, with typed properties.

Reads a page either from the pinned firmware image (by address range) or
from a private page file plus its string pool (as menu/build_menu_candidate.py
writes them), and prints, for one object subtree, every component with its
decoded properties: event types, key args, controlFocus targets, animation
sets and intervals, app-variable names, sync requests, drawText text.

Property schemas are the native descriptors, read through the builder's own
load_property_schemas (fpSup/lossless/menu/build_menu_candidate.py), so a
field is only named when the firmware names it. Strings resolve against the
pool; an enum field that is not a pool offset shows as garbage -- treat
'operation' and 'type' values as opaque.

  nbu_components.py --page 0xC2030364:0xC2055DB0 --root 122        # stock MainB2, Audio row
  nbu_components.py --page-file X.page --pool-file X.strings --root-name fpLossless_Row_GATED
  nbu_components.py ... --only keyEvent,controlFocus,controlAnimation
  nbu_components.py ... --clips                                      # animation clip keys too
"""
import argparse
import pathlib
import struct
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
SEG0 = ROOT / 'out/seg0_c0000000.bin'
POOL, POOL_LEN = 0xC18C0474, 176152
sys.path.insert(0, str(ROOT / 'fpSup/lossless/menu'))
import build_menu_candidate as BM  # noqa: E402

WIDTH = {0: 4, 1: 4, 2: 4, 3: 4, 4: 16, 5: 16, 6: 8, 7: 12, 8: 16, 9: 4, 10: 4, 11: 5,
         12: 4, 13: 4, 14: 4}


def u32(d, o):
    return struct.unpack_from('>I', d, o)[0]


def text(pool, off):
    if off == 0xFFFFFFFF or off >= len(pool):
        return None
    return pool[off:pool.find(b'\0', off)].decode('utf-8', 'replace')


def walk(page, pool, schemas):
    objects, components, clips = {}, [], []
    off = 0
    while off + 8 <= len(page):
        tag, size = u32(page, off), u32(page, off + 4)
        if size < 8:
            break
        rec = page[off:off + size]
        if tag == 0x10003:
            objects[u32(rec, 20)] = (text(pool, u32(rec, 28)), u32(rec, 24))
        elif tag == 0x1000A:
            cur, props = 28, []
            for _ in range(u32(rec, 12)):
                count, kind, _c, name, dim = struct.unpack_from('>5I', rec, cur)
                keys = [(u32(rec, cur + 20 + 10 * i + 2),
                         text(pool, u32(rec, cur + 24 + 10 * i + 2)) if kind == 2 else
                         struct.unpack_from('>f', rec, cur + 26 + 10 * i)[0] if kind == 1 else
                         u32(rec, cur + 26 + 10 * i)) for i in range(count)]
                props.append((text(pool, name), dim, keys))
                cur += 20 + count * 10
            clips.append((off, u32(rec, 20), u32(rec, 24), props))
        elif tag in BM.OWNER_OFFSETS:
            comp = text(pool, u32(rec, 8))
            inst = text(pool, u32(rec, 20 if tag == 0x10006 else 16))
            fields = {}
            if comp in schemas:
                cur, mask = BM.MASK_OFFSETS[tag], 0
                for i, p in enumerate(schemas[comp]):
                    if i % 32 == 0:
                        mask, cur = u32(rec, cur), cur + 4
                    if not (mask >> (i % 32)) & 1:
                        continue
                    k, v = p['kind'], rec[cur:cur + WIDTH[p['kind']]]
                    fields[p['name']] = (text(pool, u32(v, 0)) if k in (9, 10, 11, 12, 13) else
                                         ('obj', u32(v, 0)) if k == 14 else
                                         struct.unpack('>f', v)[0] if k == 1 else v.hex())
                    cur += WIDTH[k]
            components.append((off, u32(rec, BM.OWNER_OFFSETS[tag]), tag, comp, inst, fields))
        off += size
    return objects, components, clips


def subtree(objects, root):
    ids, grew = {root}, True
    while grew:
        grew = False
        for i, (_, parent) in objects.items():
            if parent in ids and i not in ids:
                ids.add(i)
                grew = True
    return ids


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--page', help='firmware address range START:END')
    ap.add_argument('--page-file', type=pathlib.Path)
    ap.add_argument('--pool-file', type=pathlib.Path)
    ap.add_argument('--root', type=int)
    ap.add_argument('--root-name')
    ap.add_argument('--only', help='comma-separated component kinds')
    ap.add_argument('--clips', action='store_true')
    a = ap.parse_args()
    seg0 = SEG0.read_bytes()
    schemas = BM.load_property_schemas(seg0)
    if a.page:
        lo, hi = (int(x, 16) - 0xC0000000 for x in a.page.split(':'))
        page, base = seg0[lo:hi], lo + 0xC0000000
        pool = a.pool_file.read_bytes() if a.pool_file else seg0[POOL - 0xC0000000:][:POOL_LEN]
    else:
        page, base = a.page_file.read_bytes(), 0
        pool = a.pool_file.read_bytes()
    objects, components, clips = walk(page, pool, schemas)
    root = a.root if a.root is not None else next(
        i for i, (n, _) in objects.items() if n == a.root_name)
    ids = subtree(objects, root)
    only = set(a.only.split(',')) if a.only else None
    for i in sorted(ids):
        print(f'object {i} {objects[i][0]!r} parent {objects[i][1]}')
    for off, owner, tag, comp, inst, fields in components:
        if owner in ids and (not only or comp in only):
            shown = {k: v for k, v in fields.items() if v not in (None, '')}
            print(f'{base + off:#x} {owner} {objects[owner][0]} {comp} {inst or ""} {shown}')
    if a.clips:
        for off, owner, cid, props in clips:
            if owner in ids:
                for name, dim, keys in props:
                    print(f'{base + off:#x} clip {owner}/{cid} {name}[{dim}] {keys[:8]}')


if __name__ == '__main__':
    main()
