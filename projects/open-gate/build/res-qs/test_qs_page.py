"""res-custom's QS_CINE copy (qs_page.py): stock plus exactly the RES edits.

Offline: the page's bytes against the stock set, its allocation header and object
graph the way stock keeps them, every reference, the local-number rule that froze
the camera once (fp-native-ui §8b), and the original NBU interpreter (FUN_c05e6400)
over the whole page.  Each check is shown able to fail (the mutation tests)."""
from __future__ import annotations

import struct
import unittest

import qs_page as Q
import qs_probe as QP

P, N, A, SL = Q.P, Q.N, Q.A, Q.SL
u32 = Q.u32
IMG = (Q.ROOT / "out/MAIN_c0000000.bin").read_bytes()
SCHEMAS = P.load_schemas(IMG)


def shape(page, pool):
    s = P.page_shape(page, pool)
    return s["header_minus_actual"], s["orphans"], s["bad_child_counts"], s["objects"]


class QsPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = Q.build(IMG)
        cls.pool = cls.res["pool"]
        cls.stock = Q.stock_page(IMG)
        cls.new = [bytearray(r.to_bytes()) for r in N.split(cls.res["page"])]
        cls.old = [bytearray(r.to_bytes()) for r in N.split(cls.stock)]
        cls.tree = Q.Tree(cls.new, cls.pool)
        cls.stock_tree = Q.Tree(cls.old, P.Pool(Q.stock_pool(IMG)))

    def text(self, rec, off):
        return self.pool.text(u32(rec, off))

    # ---- the bytes ---------------------------------------------------------------------
    def test_the_page_is_stock_plus_exactly_the_res_edits(self):
        """Walk both: every stock record is there, in order, byte for byte, but the
        header, the holder (its binding's variable, its component count), each
        Icon02's child count and each RES group's one clip word; 41 records added."""
        cells = Q.cells(self.stock_tree)
        icon02 = {c[2] for c in cells}
        groups = {c[2]: c[3] for c in cells}
        changed, added, i = [], [], 0
        for k, old in enumerate(self.old):
            while bytes(self.new[i]) != bytes(old) and not self.same_but(old, self.new[i], groups, icon02):
                added.append(self.new[i])
                i += 1
                if i == len(self.new):
                    self.fail(f"stock record {k} ({u32(old, 0):#x}) is not in the copy")
            if bytes(self.new[i]) != bytes(old):
                changed.append(k)
            i += 1
        added += self.new[i:]
        self.assertEqual(len(added), 1 + 5 * Q.CELLS)
        kinds = sorted({self.text(r, 8) if u32(r, 0) != 0x10003 else "object" for r in added})
        self.assertEqual(kinds, ["appVariableEvent", "drawText", "object", "objectBase"])
        self.assertEqual(len(changed), 1 + 2 + Q.CELLS + Q.CELLS, "header, holder x2, Icon02 x8, groups x8")

    def ncomp(self, tree, oid):
        """an object's +8: its components, events and clips -- not the actions
        (0x10009) the events run, nor the groups (0x1000B)"""
        return sum(1 for k in tree.block(oid)[1:] if u32(tree.recs[k], 0) not in (0x10009, 0x1000B, 0xFFFFFFFF))

    def exceptions(self, tree):
        return {oid: u32(tree.obj(oid), 8) - self.ncomp(tree, oid) for oid in tree.at
                if u32(tree.obj(oid), 8) != self.ncomp(tree, oid)}

    def test_component_counts_follow_the_stock_rule(self):
        """stock holds it for 935 of 955 objects; the 20 others (each cell's root and
        the like) count one more -- the copy keeps exactly those, and the objects it
        touched or added hold the rule"""
        old = self.exceptions(self.stock_tree)
        self.assertEqual((len(old), set(old.values())), (20, {1}))
        self.assertEqual(self.exceptions(self.tree), old)
        for oid in [Q.HOLDER] + [c["text"] for c in self.res["report"]["cells"]]:
            self.assertNotIn(oid, old)

    def same_but(self, old, new, groups, icon02):
        """`new` is `old` with one of the intended edits (same tag, length, identity)"""
        if len(old) != len(new) or u32(old, 0) != u32(new, 0):
            return False
        tag = u32(old, 0)
        if u32(old, 0) == 0x10002:
            return True
        diff = [o for o in range(len(old)) if old[o] != new[o]]
        if tag == 0x10003:
            oid = u32(old, 20)
            return u32(new, 20) == oid and (oid == Q.HOLDER or oid in icon02) and all(8 <= o < 20 for o in diff)
        if tag == 0x10006:
            return u32(old, 24) == Q.HOLDER and all(40 <= o < 44 for o in diff)
        if tag == 0x1000B:
            return u32(old, 24) in groups and len(diff) == 1
        return False

    def test_the_header_and_the_graph_are_as_stock_keeps_them(self):
        old = shape(self.stock, P.Pool(Q.stock_pool(IMG)))
        new = shape(self.res["page"], self.pool)
        self.assertEqual(new[0], old[0], "header minus actual: the same residue as stock")
        self.assertEqual((new[1], new[2]), ([], []))
        self.assertEqual(len(new[3]), len(old[3]) + Q.CELLS)
        self.assertEqual(max(new[3]), max(old[3]) + Q.CELLS)

    def dangling(self, recs, tree, pool):
        out = set()
        for r in recs:
            for off, kind in P.typed_fields(bytes(r), pool, SCHEMAS):
                v = u32(r, off)
                if kind == "obj" and v not in (0, 0xFFFFFFFF) and v not in tree.at:
                    out.add(v)
        return out

    def test_every_object_reference_names_an_object_as_in_stock(self):
        """stock QS_CINE itself names 11 objects it does not have (all in
        changePropertyByControl); the copy names exactly those, and nothing new"""
        old = self.dangling(self.old, self.stock_tree, P.Pool(Q.stock_pool(IMG)))
        self.assertEqual(len(old), 11)
        self.assertEqual(self.dangling(self.new, self.tree, self.pool), old)

    def test_no_object_shares_a_local_number_between_events_and_clips(self):
        self.assertEqual(SL.duplicate_local_ids(self.res["page"]), [])
        self.assertEqual(SL.duplicate_local_ids(self.stock), [])

    # ---- what the edits are ------------------------------------------------------------
    def test_the_holder_is_ours_two_way_and_capped(self):
        t = self.tree
        ev = {self.text(self.new[k], Q.fields(self.new[k], self.pool, SCHEMAS)["variable-name"][0]): self.new[k]
              for k in t.comps(Q.HOLDER, 0x10006, "appVariableEvent")}
        self.assertEqual(set(ev), {Q.VAR_VALUE, Q.VAR_MAX}, "MV_Resolution no longer bound")
        value, cap = ev[Q.VAR_VALUE], ev[Q.VAR_MAX]
        f = Q.fields(value, self.pool, SCHEMAS)
        self.assertEqual((self.text(value, f["variable-name"][0]), u32(value, f["type"][0])), (Q.VAR_VALUE, 1))
        f = Q.fields(cap, self.pool, SCHEMAS)
        ctl = self.new[t.comps(Q.HOLDER, 0x1000E, "controlValue")[0]]
        self.assertEqual((self.text(cap, f["variable-name"][0]), self.text(cap, f["property-name"][0]),
                          u32(cap, f["component-id"][0]), u32(cap, f["type"][0])),
                         (Q.VAR_MAX, "max-value", u32(ctl, 24), 1))
        self.assertEqual(u32(t.obj(Q.HOLDER), 8), u32(self.stock_tree.obj(Q.HOLDER), 8) + 1)

    def test_each_cell_hides_the_stock_value_and_shows_ours(self):
        t = self.tree
        for n, root, icon02, big in Q.cells(t):
            with self.subTest(cell=n):
                g = [r for r in self.new if u32(r, 0) == 0x1000B and self.text(r, 20) == "20_MV_Resolution"
                     and u32(r, 24) == icon02]
                self.assertEqual(len(g), 1)
                entries = self.group_entries(g[0])
                self.assertIn((big, Q.BIG_HIDE), entries)
                self.assertNotIn((big, Q.BIG_SHOW), entries)
                mine = [c for c in t.children(icon02) if c not in self.stock_tree.at]
                self.assertEqual(len(mine), 1)
                oid = mine[0]
                self.assertEqual((t.name(oid), u32(t.obj(icon02), 16)), ("Text", len(t.children(icon02))))
                k = t.block(oid)
                self.assertEqual(u32(t.obj(oid), 8), 4)
                base, text, on, txt = (self.new[x] for x in k[1:])
                fb = Q.fields(base, self.pool, SCHEMAS)
                self.assertEqual(struct.unpack_from(">ffff", base, fb["position"][0]), Q.VALUE_AT)
                self.assertEqual(u32(base, fb["is-visible"][0]), 1)
                ft = Q.fields(text, self.pool, SCHEMAS)
                self.assertEqual((self.text(text, ft["text"][0]), text[ft["text"][0] + 4]), (" ", 0))
                self.assertEqual(u32(text, ft["color"][0]), Q.WHITE)
                self.assertEqual(struct.unpack_from(">ffff", text, ft["rect"][0]), (0.0, 0.0) + Q.VALUE_AT[2:])
                for ev, var, comp, prop in ((on, Q.VAR_ON % n, u32(base, 24), "opacity"),
                                            (txt, Q.VAR_TEXT, u32(text, 24), "text")):
                    f = Q.fields(ev, self.pool, SCHEMAS)
                    self.assertEqual((u32(ev, 24), self.text(ev, f["variable-name"][0]),
                                      u32(ev, f["component-id"][0]), self.text(ev, f["property-name"][0])),
                                     (oid, var, comp, prop))
                # drawn like the stock value: right after its block, under the same parent
                self.assertEqual(k[0], t.block(big)[-1] + 1)

    def group_entries(self, rec):
        na, nb, nc = u32(rec, 8), u32(rec, 12), u32(rec, 16)
        cur = 28 + 21 * na
        for _ in range(nb):
            cur += 13 if rec[cur + 8] else 9
        return [(u32(rec, cur + 8 * i), u32(rec, cur + 8 * i + 4)) for i in range(nc)]

    def test_the_private_strings_are_marked_where_they_land(self):
        page = self.res["page"]
        names = {s for _, s in self.res["marks"]}
        self.assertEqual(names, {Q.VAR_VALUE, Q.VAR_MAX, Q.VAR_TEXT} | {Q.VAR_ON % n for n in range(1, 9)})
        self.assertEqual(len(self.res["marks"]), 2 + 2 * Q.CELLS)
        for off, s in self.res["marks"]:
            self.assertEqual(struct.unpack_from(">I", page, off)[0], self.pool.added[s], s)
        self.assertEqual(set(self.res["vars"]), names)

    # ---- the original interpreter --------------------------------------------------------
    def test_the_original_interpreter_parses_every_record(self):
        probe = QP.native_parse(self.res["page"], self.pool.data, IMG)
        self.assertEqual(len(probe.traces), len(self.new))

    # ---- the checks can fail ------------------------------------------------------------------
    def test_mutation_a_header_short_of_one_object_is_seen(self):
        recs = [bytearray(r.to_bytes()) for r in N.split(self.res["page"])]
        Q.put(recs[0], 8, u32(recs[0], 8) - 1)
        bad = b"".join(bytes(r) for r in recs)
        self.assertNotEqual(shape(bad, self.pool)[0], shape(self.stock, P.Pool(Q.stock_pool(IMG)))[0])

    def test_mutation_a_shared_local_number_is_seen(self):
        recs = [bytearray(r.to_bytes()) for r in N.split(self.res["page"])]
        oid = self.res["report"]["cells"][0]["text"]
        evs = [r for r in recs if u32(r, 0) == 0x10006 and u32(r, 24) == oid]
        Q.put(evs[1], 28, u32(evs[0], 28))
        self.assertEqual(SL.duplicate_local_ids(b"".join(bytes(r) for r in recs)), [(oid, u32(evs[0], 28))])

    def test_mutation_a_stray_byte_is_seen_by_the_walk(self):
        page = bytearray(self.res["page"])
        k = self.tree.at[self.res["report"]["cells"][3]["root"]]
        off = sum(len(r) for r in self.new[:k]) + 12
        page[off] ^= 1
        new = [bytearray(r.to_bytes()) for r in N.split(bytes(page))]
        saved = self.new
        try:
            self.new = new
            with self.assertRaises(AssertionError):
                self.test_the_page_is_stock_plus_exactly_the_res_edits()
        finally:
            self.new = saved


if __name__ == "__main__":
    unittest.main(verbosity=2)
