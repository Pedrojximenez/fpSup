#!/usr/bin/env python3
"""res-custom's Quick Set: QS_CINE as it is, with the RES tile's value ours.

research/ui/CUSTOM_QS.md §12 (2026-10-20).  The user places RES / FPS / FMT with
the stock custom-QS editor (the settings hold stock function ids only); this page
is QS_CINE byte for byte except, for RES (UI id 21):

  1. the Footer holder 343 -- the one value object the dials step for RES, in
     every cell -- is bound to the private integer RC_QsRes instead of
     MV_Resolution (still two-way, type 1), its cap to RC_QsResMax;
  2. in each of the 8 cells the stock value image is hidden: the cell's
     20_MV_Resolution group shows its big value (Icon, clip 12) -> clip 13 (its
     hidden clip), the same 4 bytes;
  3. each cell gets one text object under its Icon02, where clip 12 puts the
     stock image (53,108 150x38): a copy of this page's Footer drawText (11484),
     white, its text bound to RC_QsResText, its opacity to RC_QsResOn<n> (1 while
     cell n shows RES -- the native side follows MV_QSMENU_QS<n>).

The native side (not here) registers the variables, follows RC_QsRes and calls
res-custom's service; only stock values ever reach MV_Resolution.  The page goes
in by the runtime entry's offset (§10 Q1), like B2_5 -> B2_6 on the camera.

Offline only: no camera, no card.
"""
from __future__ import annotations

from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
BUILD = HERE.parent
ROOT = BUILD.parents[2]
sys.path[:0] = [str(BUILD), str(ROOT / "research/ui/tools/nbu_probe"), str(ROOT / "research/ui/tools"),
                str(ROOT / "fpSup/lossless/menu")]
import nbu_format as N                      # noqa: E402
import native_ui_audit as A                 # noqa: E402
import sl_b25_page as P                     # noqa: E402
import sl_lab_page as SL                    # noqa: E402
import imx410_rate_ui as U                  # noqa: E402

BM = P.BM
B = 0xC0000000
NBU_BASE = 0xC18C0460
SET_START, SET_END = 0xC2278C02, 0xC239C5FB          # QS_CINE (uinav.py sets)
ENTRY_OFFSET = SET_START - NBU_BASE                    # the runtime entry's +08 for QS_CINE
CELLS = 8
RES = 21                                               # UI id (= MV_QSMENU_QSn frame / 33.3)
HOLDER = 343                                           # Footer > QSMode > '20': RES's value object
TEXT_DONOR = 11484                                     # Footer > ... > Text: this page's drawText
BIG_SHOW, BIG_HIDE = 12, 13                            # the big value Icon's clips (20_MV_Resolution)
VALUE_AT = (53.0, 108.0, 150.0, 38.0)                  # where clip 12 puts the stock value image
WHITE = 0xFFFFFFFF
VAR_VALUE, VAR_MAX, VAR_TEXT = "RC_QsRes", "RC_QsResMax", "RC_QsResText"
VAR_ON = "RC_QsResOn%d"                                # cell 1..8
SIZE = {0: 4, 1: 4, 2: 4, 3: 4, 4: 16, 5: 16, 6: 8, 7: 12, 8: 16, 9: 4, 10: 4, 11: 5, 12: 4, 13: 4, 14: 4}

check, u32, put = P.check, P.u32, P.put


def fields(rec, pool, schemas):
    """{property name: (offset, kind)} of a component record (its mask decides)."""
    tag = u32(rec, 0)
    comp = pool.text(u32(rec, 8))
    check(comp in schemas, f"no schema for {comp}")
    cur, out = BM.MASK_OFFSETS[tag], {}
    for i, p in enumerate(schemas[comp]):
        if i % 32 == 0:
            mask, cur = u32(rec, cur), cur + 4
        if (mask >> (i % 32)) & 1:
            out[p["name"]] = (cur, p["kind"])
            cur += SIZE[p["kind"]]
    check(cur == len(rec), f"{comp}: fields end at {cur}, record is {len(rec)}")
    return out


def stock_page(img):
    return img[SET_START - B:SET_END - B]


def stock_pool(img):
    return img[U.POOL_START - B:U.POOL_START - B + U.POOL_SIZE]


class Tree:
    """The objects of a record list: id -> {record index, parent, name, children}."""

    def __init__(self, recs, pool):
        self.recs, self.pool, self.at = recs, pool, {}
        for i, r in enumerate(recs):
            if u32(r, 0) == 0x10003:
                self.at[u32(r, 20)] = i

    def obj(self, oid):
        return self.recs[self.at[oid]]

    def name(self, oid):
        return self.pool.text(u32(self.obj(oid), 28))

    def parent(self, oid):
        return u32(self.obj(oid), 24)

    def children(self, oid):
        return [c for c in self.at if self.parent(c) == oid]

    def child(self, oid, name):
        hit = [c for c in self.children(oid) if self.name(c) == name]
        check(len(hit) == 1, f"{oid}: {len(hit)} children named {name}")
        return hit[0]

    def block(self, oid):
        """[record indices] of the object and its own components (stream order)."""
        i = self.at[oid]
        out = [i]
        for k in range(i + 1, len(self.recs)):
            if u32(self.recs[k], 0) == 0x10003:
                break
            out.append(k)
        return out

    def comps(self, oid, tag=None, name=None):
        out = []
        for k in self.block(oid)[1:]:
            r = self.recs[k]
            if (tag is None or u32(r, 0) == tag) and (name is None or self.pool.text(u32(r, 8)) == name):
                out.append(k)
        return out


def cells(tree):
    """[(n, cell root, Icon02, big value Icon)] for the 8 cells."""
    out = []
    for n in range(1, CELLS + 1):
        root = [o for o in tree.children(1) if tree.name(o) == f"QS_CINE{n}"]
        check(len(root) == 1, f"cell {n}")
        icon02 = tree.child(root[0], "Icon02")
        out.append((n, root[0], icon02, tree.child(icon02, "Icon")))
    return out


def local_ids(tree, oid):
    """the object's local numbers in use: components (+24 / +28) and clips (+24)"""
    ids = set()
    for k in tree.block(oid)[1:]:
        r = tree.recs[k]
        ids.add(u32(r, BM.OWNER_OFFSETS.get(u32(r, 0), 20) + 4))
    return ids


def group_show(rec, pool, obj, old, new):
    """In one 0x1000B group, the (obj, old) entry of its C list -> (obj, new); exactly one."""
    na, nb, nc = u32(rec, 8), u32(rec, 12), u32(rec, 16)
    cur = 28 + 21 * na
    for _ in range(nb):
        cur += 13 if rec[cur + 8] else 9
    hits = [cur + 8 * i for i in range(nc) if u32(rec, cur + 8 * i) == obj and u32(rec, cur + 8 * i + 4) == old]
    check(len(hits) == 1, f"group {pool.text(u32(rec, 20))}: {len(hits)} entries ({obj}, {old})")
    put(rec, hits[0] + 4, new)


def build(img=None):
    img = img if img is not None else (ROOT / "out/MAIN_c0000000.bin").read_bytes()
    pool = P.Pool(stock_pool(img))
    schemas = P.load_schemas(img)
    recs = [bytearray(r.to_bytes()) for r in N.split(stock_page(img))]
    tree = Tree(recs, pool)
    refs = []                                   # (record, offset, private string)
    next_id = max(tree.at) + 1
    report = dict(next_id=next_id, cells=[])
    inserts = {}                                # record index -> [records] after it

    # 1. the holder: two-way to RC_QsRes, capped by RC_QsResMax
    check(tree.name(HOLDER) == "20" and tree.name(tree.parent(HOLDER)) == "QSMode", "RES holder")
    ev = tree.comps(HOLDER, 0x10006, "appVariableEvent")
    check(len(ev) == 1, "the holder's one binding")
    bind = recs[ev[0]]
    f = fields(bind, pool, schemas)
    check(pool.text(u32(bind, f["variable-name"][0])) == "MV_Resolution" and u32(bind, f["type"][0]) == 1,
          "the holder binds MV_Resolution two-way")
    SL._intern_at(bind, f["variable-name"][0], VAR_VALUE, pool, refs)
    ctl = tree.comps(HOLDER, 0x1000E, "controlValue")
    check(len(ctl) == 1 and "max-value" not in fields(recs[ctl[0]], pool, schemas), "the holder's controlValue")
    local = max(local_ids(tree, HOLDER)) + 1
    inserts.setdefault(ctl[0], []).append(
        SL._binding(HOLDER, local, VAR_MAX, u32(recs[ctl[0]], 24), "max-value", pool, refs, 1))
    put(tree.obj(HOLDER), 8, u32(tree.obj(HOLDER), 8) + 1)

    # the text template: this page's Footer drawText
    text_donor = tree.comps(TEXT_DONOR, 0x10005, "drawText")
    check(len(text_donor) == 1, "the text donor")
    groups = [k for k, r in enumerate(recs) if u32(r, 0) == 0x1000B and pool.text(u32(r, 20)) == "20_MV_Resolution"]
    check(len(groups) == CELLS, f"{len(groups)} 20_MV_Resolution groups")

    for n, root, icon02, big in cells(tree):
        # 2. the stock value image stays hidden in this cell's RES group
        mine = [k for k in groups if u32(recs[k], 24) == icon02]
        check(len(mine) == 1, f"cell {n}: its 20_MV_Resolution")
        group_show(recs[mine[0]], pool, big, BIG_SHOW, BIG_HIDE)
        # 3. the text object, right after the big value's block (drawn like it)
        src = tree.block(big)
        obj, base = bytearray(recs[src[0]]), bytearray(recs[src[1]])
        check(u32(base, 0) == 0x10004 and set(fields(base, pool, schemas)) == {"position", "size", "is-visible"},
              f"cell {n}: the value's objectBase")
        oid = next_id
        next_id += 1
        put(obj, 8, 4)                          # objectBase, drawText, two bindings
        put(obj, 16, 0)
        put(obj, 20, oid)
        put(obj, 24, icon02)
        put(obj, 28, pool.find("Text"))
        fb = fields(base, pool, schemas)
        put(base, 20, oid)
        struct.pack_into(">ffff", base, fb["position"][0], *VALUE_AT)
        put(base, fb["is-visible"][0], 1)
        text = bytearray(recs[text_donor[0]])
        ft = fields(text, pool, schemas)
        put(text, 20, oid)
        SL._intern_at(text, ft["text"][0], " ", pool, refs)
        text[ft["text"][0] + 4] = 0             # a literal, not an .nloc key
        put(text, ft["color"][0], WHITE)
        check(u32(text, ft["horz-align"][0]) == 2, "centred")
        struct.pack_into(">ffff", text, ft["rect"][0], 0.0, 0.0, VALUE_AT[2], VALUE_AT[3])
        on = SL._binding(oid, u32(text, 24) + 1, VAR_ON % n, u32(base, 24), "opacity", pool, refs, 0)
        txt = SL._binding(oid, u32(text, 24) + 2, VAR_TEXT, u32(text, 24), "text", pool, refs, 0)
        inserts.setdefault(src[-1], []).extend([obj, base, text, on, txt])
        put(tree.obj(icon02), 16, u32(tree.obj(icon02), 16) + 1)
        report["cells"].append(dict(cell=n, root=root, icon02=icon02, big=big, text=oid, group=mine[0]))

    # the allocation header: 8 objects, their components and one more binding
    header = A.parse_header(A.Record(0, bytes(recs[0])), pool.text)
    added = [A.Record(0, bytes(x)) for k in sorted(inserts) for x in inserts[k]]
    counts = A.component_counts(added, pool.text)
    delta = dict(objects=CELLS, component_counts=counts, group_budgets=[], clip_property_counts=[],
                 property_key_counts=[])
    out = [bytearray(BM.extend_header(A.Record(0, bytes(recs[0])), header, delta))]
    for k in range(1, len(recs)):
        out.append(recs[k])
        out.extend(inserts.get(k, []))
    page = b"".join(bytes(r) for r in out)
    marks = []                                  # (page offset, private string)
    at = 0
    where = {}
    for r in out:
        where[id(r)] = at
        at += len(r)
    for rec, off, s in refs:
        marks.append((where[id(rec)] + off, s))
    report.update(objects=CELLS, components=counts, private=sorted(set(s for _, s in marks)))
    return dict(page=page, pool=pool, marks=sorted(marks), report=report,
                vars=[VAR_VALUE, VAR_MAX, VAR_TEXT] + [VAR_ON % n for n in range(1, CELLS + 1)])


def main():
    res = build()
    r = res["report"]
    print(f"QS_CINE copy: {len(res['page'])} B (stock {SET_END - SET_START}), +{r['objects']} objects, "
          f"components {r['components']}, {len(res['marks'])} private string fields: {r['private']}")


if __name__ == "__main__":
    main()
