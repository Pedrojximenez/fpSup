#!/usr/bin/env python3
"""Sensor Lab: private UI pages, as a pack the stock firmware registers itself.

Design §8.12 "通用新增私有頁".  A page is shown when two things exist: a screen
object of that name (app+7C, FUN_c05e04e8) and, in that screen's reader, a
runtime entry of the same name (C05E82F0).  The stock container 0xC18C0460 gets
both from its top level -- the string pool (tag 1) and the resource-set index
(tag 0x10001, case 0 of FUN_c05e6400), which creates one screen and one entry
per row.  So a private pack in the same shape, registered through the stock
loader C05E84D8 (already used for the private lists), adds pages with no hook:

    "NBR\\0" | version 0x01090000 | 0          (the loader wants NBR\\0; the
                                              version is read, 1.9 = NBU's, so
                                              page records parse as NBU's do)
    tag 1        the pack's pool: the index name and the page names
    tag 0x10001  {name, n, n x {fnv1a(name), name, 1, offset, 0, 0, 1024, 682}}
                 offsets from the pack's first byte, rows by hash (as stock)
    end          FFFFFFFF 00000008
    pages        each its own record stream, ending FFFFFFFF/8

The four trailing words are stock's on every one of its 221 rows.  The page
records use pool offsets of the SHARED pool (stock + private strings, fpSup/
uishare): after registration the new reader's +0x10/+0x14 are pointed at it
(the index names were already resolved from the pack's own pool by then).

Stage 1 (2026-10-02) carries one page, SL_TEST = the stock B2_5 set unchanged:
no private strings, and under CUSTOM it lacks MODE / SIZE, so it is told apart
from the private B2_5 at a glance.  Offline only.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / "research/ui/tools"), str(ROOT / "research/ui/tools/nbu_probe")]
import nbr as NBR             # noqa: E402
import nbu_format as N        # noqa: E402

B = 0xC0000000
VERSION = 0x01090000
ROW_TAIL = (0, 0, 1024, 682)                # every stock index row
INDEX_NAME = "sl_pages"
END = struct.pack(">II", 0xFFFFFFFF, 8)
B25_SET = (0xC1A5C590, 0xC1A792FB)          # imx410_rate_ui.SET_START / SET_END (stock bytes)


def stock_b25(img: bytes) -> bytes:
    """The stock B2_5 set, exactly as the image holds it (ends with its end record)."""
    page = img[B25_SET[0] - B:B25_SET[1] - B]
    if not page.endswith(END) or N.join(N.split(page)) != page:
        raise ValueError("stock B2_5 set is not a closed record stream")
    return page


def set_bytes(name: str) -> bytes:
    """A stock set, by name, from the image's index (research/ui/nbu_sets.json)."""
    img, base, rows, _ = N.load_sets()
    rows = sorted(rows, key=lambda r: r["address"])
    i = next(k for k, r in enumerate(rows) if r["name"] == name)
    return img[rows[i]["address"] - base:rows[i + 1]["address"] - base]


def return_page(img: bytes | None = None) -> bytes:
    """The stage-1 test page: stock "Test" (one white fill under Root, 276 B)
    plus, on Root, B2_6_2's own way out -- FooterSelect's MENU keyEvent (the
    0xB, screen-level form) with one controlAppState sync-request 'Return'.
    Nothing else; no private string.  Small on purpose (the user: keep files small)."""
    page = set_bytes("Test")
    recs = N.split(page)
    if [r.tag for r in recs] != [0x10002, 0x10003, 0x10004, 0x10005, 0xFFFFFFFF] or recs[1].words(7)[3] != 1:
        raise ValueError("stock Test set changed")
    src = N.split(set_bytes("B2_6_2"))
    owner, ev, act = None, None, None
    for k, r in enumerate(src):
        if r.tag == 0x10003:
            owner = r.words(7)[3]
            continue
        d = r.to_bytes()
        if owner == 31 and r.tag == 0x10006 and d[20:24] == bytes.fromhex("0001a784"):
            ev = bytearray(d)
            n_act = struct.unpack_from(">I", d, 16)[0]
            act = next((bytearray(a.to_bytes()) for a in src[k + 1:k + 1 + n_act]
                        if a.to_bytes()[36:40] == bytes.fromhex("0002010c")), None)
    if ev is None or act is None or len(ev) != 48 or len(act) != 41:
        raise ValueError("B2_6_2 FooterSelect MENU -> Return changed")
    struct.pack_into(">I", ev, 16, 1)               # one action (stock: four)
    struct.pack_into(">I", ev, 24, 1)               # owner: Root (object 1)
    struct.pack_into(">I", act, 20, 1)
    struct.pack_into(">I", act, 28, 1)              # its first (only) action
    root = bytearray(recs[1].to_bytes())
    struct.pack_into(">I", root, 8, struct.unpack_from(">I", root, 8)[0] + 1)   # + one event
    # Allocation header: Test lists two classes (fill, objectBase) and four empty
    # arena vectors; the two new component classes are appended, one instance each
    # (FUN_c05e6400 case 1 sums the pairs into one arena; order does not matter).
    h = recs[0].body
    objects, objects2, classes = struct.unpack_from(">III", h, 0)
    pairs = h[12:12 + 8 * classes]
    tail = h[12 + 8 * classes:]
    if (objects, objects2, classes, tail) != (1, 0, 2, bytes(16)):
        raise ValueError("stock Test allocation header changed")
    name_of = lambda rec: struct.unpack_from(">I", rec, 8)[0]
    pairs += struct.pack(">II", name_of(ev), 1) + struct.pack(">II", name_of(act), 1)
    body = struct.pack(">III", objects, objects2, classes + 2) + pairs + tail
    new_header = struct.pack(">II", 0x10002, 8 + len(body)) + body
    return b"".join([bytes(new_header), bytes(root), recs[2].to_bytes(), recs[3].to_bytes(),
                     bytes(ev), bytes(act), END])


# The test page's content.  "white": the small Return page (Test + MENU -> Return);
# "b2_6_2": a whole stock sub page (headphone volume, ~81 KB), the control for the
# camera differential (r15: every key died on SL_TEST -- the GUI page table had no
# entry, so a NullGuiInterface forwarded nothing; is it that, or the page?).
TEST_CONTENT = "white"


def test_pages(img: bytes) -> list[tuple[str, bytes, str]]:
    """(name, page, parent): the stage-1 test pages (SL_TEST)."""
    page = return_page(img) if TEST_CONTENT == "white" else set_bytes("B2_6_2")
    return [("SL_TEST", page, "B2_5")]


def size_pages(img: bytes, pool) -> tuple[list[tuple[str, bytes, str]], list]:
    """The SIZE sub page (sl_size_page.py) that SIZE's Right key on B2_5 opens,
    built into `pool` (the private B2_5's, so one strings section serves both).
    Returns the pages and the page's private-string fields (page offset, text)."""
    import sl_size_page as SZ
    refs = []
    seq = SZ.build_size_page(img, pool, refs)
    page, abs_refs = SZ.assemble(seq, refs)
    return [(SZ.PAGE_NAME, page, "B2_5")], abs_refs


def lab_pages(img: bytes, pool) -> tuple[list[tuple[str, bytes, str]], dict]:
    """The Sensor Lab tabbed page (sl_lab_page.py), opened from B2_5.  Returns
    the pages and {page name: [(page offset, private text)]}."""
    import sl_lab_page as LAB
    import sl_size_page as SZ
    pages, refs_by = [], {}
    # (sl_wh_page.py, the Width / Height digit page, is not packed: the panel is
    #  edited in place since 2026-10-03, the date / time page's way)
    for name, parent, build in ((LAB.PAGE_NAME, "B2_5", LAB.build_lab_page),):
        refs = []
        page, abs_refs = SZ.assemble(build(img, pool, refs), refs)
        pages.append((name, page, parent))
        refs_by[name] = abs_refs
    return pages, refs_by


def pack_refs(pack: bytes, pages, page_refs: dict) -> list:
    """{page name: [(page offset, text)]} -> [(pack offset, text)]."""
    rows = {n: o for n, o, _ in native_rows(pack)}
    return sorted((rows[n] + a, t) for n, refs in page_refs.items() for a, t in refs)


def native_rows(pack: bytes):
    """(name, pack offset, hash) rows of the pack's index, read in Python."""
    recs = N.split(pack[12:])
    pool = recs[0].body
    s = lambda o: pool[o:pool.index(b"\0", o)].decode()
    _name, n = struct.unpack_from(">II", recs[1].body, 0)
    out = []
    for i in range(n):
        h, nm, _one, off = struct.unpack_from(">4I", recs[1].body, 8 + 32 * i)
        out.append((s(nm), off, h))
    return out


# GUI page tables (FUN_c0564638 picks by the name's first letter): 0-terminated
# {char *name, u32 id}.  B2_5 = 36 (UicGuiMenuMovieRecord).
GUI_TABLES = {"B": 0xC0D0DFC8, "M": 0xC0D0DB68}
PRIVATE_PREFIX = "SL_"


def gui_id(img: bytes, name: str) -> int:
    table = GUI_TABLES[name[0]]
    for i in range(512):
        ptr, gid = struct.unpack_from("<II", img, table - B + 8 * i)
        if ptr == 0:
            break
        o = ptr - B
        if img[o:img.index(b"\0", o)].decode("ascii", "replace") == name:
            return gid
    raise ValueError(f"{name} not in the GUI page table")


def gui_parent_id(img: bytes, pages) -> int:
    """The GUI id private pages borrow (sl_excl.S ROLE 15): their stock parent's,
    so the parent's GUI handler keeps forwarding keys on them.  One for all
    pages for now; a page under a private page inherits its parent's."""
    parents = {}
    names = {n for n, _, _ in pages}
    for name, _page, parent in pages:
        while parent in names:
            parent = next(p for n, _, p in pages if n == parent)
        parents[name] = parent
    if not all(n.startswith(PRIVATE_PREFIX) for n in names):
        raise ValueError(f"private page names must start with {PRIVATE_PREFIX}")
    ids = {gui_id(img, p) for p in parents.values()}
    if len(ids) != 1:
        raise ValueError(f"pages under several stock parents ({parents}) need a table, not one id")
    return ids.pop()


MACHINE = "TransSensorLab"


def transitions(pages) -> tuple[list[str], list[tuple[str, str, str]]]:
    """States and transitions of the private state machine (NBM-style, tags
    0x50001..0x50004): per page, parent -name-> page and page -Return-> page's
    parent.  Stock has no wildcard Return (every page names its parent), and the
    UI switches a screen only when some machine on app+0xF4 matches (current
    screen, request) -- FUN_c05dd448 / FUN_c05ed028 / FUN_c05ece48."""
    states, trans = [], []
    for name, _page, parent in pages:
        for st in (parent, name):
            if st not in states:
                states.append(st)
        trans += [(parent, name, name), (name, parent, "Return")]
    return states, trans


def build_pack(pages: list[tuple[str, bytes, str]], extra_transitions=(), return_targets=None) -> bytes:
    names = [n for n, _, _ in pages]
    if len(set(names)) != len(names) or not all(n.isascii() and n for n in names):
        raise ValueError("page names must be unique ASCII")
    pool = bytearray(4)
    offs = {}

    def intern(s):
        if s not in offs:
            offs[s] = len(pool)
            pool.extend(s.encode() + b"\0")
            pool.extend(bytes(-len(pool) % 4))
        return offs[s]

    intern(INDEX_NAME)
    for n in names:
        intern(n)
    states, trans = transitions(pages)
    # The GUI parent supplies the native controller type. A tool launched
    # from SupManager must return to its caller, whose focus is still valid.
    for page, target in (return_targets or {}).items():
        if page not in names or not target or not target.isascii():
            raise ValueError('return target must name an ASCII state for a declared page')
        trans = [(src, target if src == page and ev == 'Return' else dst, ev)
                 for src, dst, ev in trans]
        if target not in states:
            states.append(target)
    for src, dst, ev in extra_transitions:
        if dst not in names or not src or not ev or not src.isascii() or not ev.isascii():
            raise ValueError('extra transition must target a declared private page')
        if src not in states:
            states.append(src)
        trans.append((src,dst,ev))
    for _,_,ev in trans:
        intern(ev)
    for t in [MACHINE, "Return"] + states:
        intern(t)
    # the state machine: one table, one machine {states, 0 x 6, transitions, name},
    # its states {name, type 0 (screen), 0}, its transitions {from, to, event, ""}
    # (offset 0 of the pool is the empty string, as stock's conditions)
    sm = struct.pack(">III", 0x50001, 12, 1)
    sm += struct.pack(">II9I", 0x50002, 44, len(states), 0, 0, 0, 0, 0, 0, len(trans), offs[MACHINE])
    for st in states:
        sm += struct.pack(">II3I", 0x50003, 20, offs[st], 0, 0)
    for src, dst, ev in trans:
        sm += struct.pack(">II4I", 0x50004, 24, offs[src], offs[dst], offs[ev], 0)
    head = b"NBR\0" + struct.pack(">II", VERSION, 0)
    pool_rec = struct.pack(">II", 1, 8 + len(pool)) + pool
    index_len = 8 + 8 + 32 * len(pages)
    at = len(head) + len(pool_rec) + index_len + len(sm) + len(END)
    rows, body = [], b""
    for name, page, _parent in pages:
        if not page.endswith(END):
            raise ValueError(f"page {name} does not end with an end record")
        rows.append((NBR.fnv1a(name), offs[name], 1, at + len(body)) + ROW_TAIL)
        body += page
    rows.sort()
    index = struct.pack(">IIII", 0x10001, index_len, offs[INDEX_NAME], len(rows))
    index += b"".join(struct.pack(">8I", *r) for r in rows)
    out = head + pool_rec + index + sm + END + body
    assert len(head + pool_rec + index + sm + END) == at
    return out


def inspect_pack(pack: bytes) -> dict:
    """Pure-Python reading of a pack: {name: page bytes}, every bound checked."""
    if pack[:4] != b"NBR\0" or struct.unpack_from(">I", pack, 4)[0] != VERSION:
        raise ValueError("not a version 1.9 NBR pack")
    recs = N.split(pack[12:])
    if [r.tag for r in recs[:2]] != [1, 0x10001]:
        raise ValueError("top level is not pool, index, ...")
    pool = recs[0].body
    s = lambda o: pool[o:pool.index(b"\0", o)].decode()
    _name, n = struct.unpack_from(">II", recs[1].body, 0)
    out, keys = {}, []
    for i in range(n):
        h, nm, one, off, *tail = struct.unpack_from(">8I", recs[1].body, 8 + 32 * i)
        name = s(nm)
        if h != NBR.fnv1a(name) or one != 1 or tuple(tail) != ROW_TAIL:
            raise ValueError(f"row {i} malformed")
        page_recs = N.split(pack[off:])
        page = N.join(page_recs)
        if not page.endswith(END) or off + len(page) > len(pack):
            raise ValueError(f"page {name} runs past the pack")
        out[name] = page
        keys.append(h)
    if keys != sorted(keys):
        raise ValueError("index rows not sorted by hash")
    return out


SM_CODE = ((0xC05D9B00, 0xC05D9E80, "UI helpers"), (0xC05ECC00, 0xC05ED600, "state machine"),
           (0xC0013000, 0xC0016000, "libc"), (0xC05E8F00, 0xC05EA000, "strings / dictionary"))


def native_index(pack: bytes, img: bytes | None = None):
    """Run the original interpreter over the pack's top level (pool, index, end)
    and return [(name, offset)] as case 0 built them (ctx 0x2A / 0x2B rows)."""
    import nbu_probe as P
    img = img if img is not None else (ROOT / "out/MAIN_c0000000.bin").read_bytes()
    probe = P.NbuProbe(img[:P.SEG0_SIZE])
    probe.install_arena()
    probe.survey = True            # every other native call recorded and returned 0, as for stock's index
    for lo, hi, what in SM_CODE:   # the state-machine builders run for real (0x5000x records)
        probe.allow(lo, hi, what)
    probe.open(blob=pack, magic=False, cursor=12, version=VERSION)
    traces = probe.records(64)
    # ctx+0x1C ends 1 after the end record, as for stock's own index; FUN_c05e8508
    # attaches the reader only when it is nonzero
    toks = [t.token for t in traces]
    if toks[:2] != [1, 0x10001] or toks[-1] != 0xFFFFFFFF or traces[-1].result != 1 or probe.error_flag() != 1:
        raise ValueError(f"interpreter walk {[hex(t.token) for t in traces]}")
    count, array = probe.ctx(0x2A)[0], probe.ctx(0x2B)[0]
    rows = []
    for i in range(count):
        h, name, off = probe.words(array + i * 0x2C, 3)
        rows.append((probe.string(name), off, h))
    calls = [c.name for t in traces for c in t.calls if c.name != "pool_string"]
    return rows, calls


def native_switch(pack: bytes, queries, img: bytes | None = None) -> dict:
    """Load the pack with the original interpreter -- the state-machine records
    run the stock builders (FUN_c05ecda8 / c05ecf28 / c05eced8, code in SM_CODE
    really executes) -- then ask the stock matcher what each (current screen,
    request) leads to: {(cur, req): (target state, its type) or None}."""
    import nbu_probe as P
    img = img if img is not None else (ROOT / "out/MAIN_c0000000.bin").read_bytes()
    blob_max = max(P.NbuProbe.BLOB_MAX, (len(pack)+0xFFFF)&~0xFFFF)
    class PackProbe(P.NbuProbe):
        BLOB_MAX = blob_max
        HEAP = max(P.NbuProbe.HEAP, P.NbuProbe.BLOB+blob_max+0x10000)
    if PackProbe.HEAP+0x600C0 >= PackProbe.HEAP_END:
        raise ValueError('page pack leaves no state-machine probe scratch')
    probe = PackProbe(img[:P.SEG0_SIZE])
    probe.install_arena()
    probe.survey = True
    for lo, hi, what in SM_CODE:
        probe.allow(lo, hi, what)
    probe.open(blob=pack, magic=False, cursor=12, version=VERSION)
    traces = probe.records(64)
    if traces[-1].token != 0xFFFFFFFF or probe.error_flag() != 1:
        raise ValueError(f"walk {[hex(t.token) for t in traces]}")
    sm = probe.ctx(0x15)[0]
    if probe.string(probe.words(sm + 8)[0]) != MACHINE:
        raise ValueError("no private state machine built")
    scratch, out = probe.HEAP + 0x60000, {}
    for cur, req in queries:
        probe.write(scratch, cur.encode() + b"\0")
        probe.write(scratch + 0x40, req.encode() + b"\0")
        probe.write_words(scratch + 0x80, 0)
        state = probe._call(0xC05ECF10, sm, scratch)               # state by screen name
        hit = None
        if state:
            probe._call(0xC05ECCE0, state, scratch + 0x40, scratch + 0x80)
            t = probe.words(scratch + 0x80)[0]
            if t:
                to = probe.words(t + 4)[0]
                hit = (probe.string(probe.words(to + 4)[0]), probe.words(to + 0x20)[0])
        out[(cur, req)] = hit
    return out


if __name__ == "__main__":
    img = (ROOT / "out/MAIN_c0000000.bin").read_bytes()
    pack = build_pack(test_pages(img))
    print(len(pack), "bytes", {k: len(v) for k, v in inspect_pack(pack).items()})
    print("native", native_index(pack, img))
    print("switch", native_switch(pack, [("B2_5", "SL_TEST"), ("SL_TEST", "Return"), ("B2_5", "Return"),
                                         ("MainB2", "SL_TEST")], img))
