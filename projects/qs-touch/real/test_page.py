"""The genuine QS resource keeps its native settings owners and entry."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import page as P


class PageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patches, cls.pool, cls.report, cls.builder = P.resources()
        cls.stock = P.B.Q.N.split(cls.builder.stock)
        cls.by_addr = {p['address']:p for p in cls.patches}
        cls.raw = b''.join(cls.by_addr.get(P.B.Q.SET_START+r.offset, {'data':r.to_bytes()})['data']
                           for r in cls.stock)
        cls.records = [bytearray(r.to_bytes()) for r in P.B.Q.N.split(cls.raw)]
        cls.tree = P.B.Q.Tree(cls.records, cls.pool)

    def test_actual_native_variables_are_two_way_and_keep_native_subscribers(self):
        self.assertEqual(self.report['page'], 'QS_CINE')
        self.assertEqual(self.report['gui_id'], 159)
        self.assertFalse(self.report['separate_test_page'])
        for (key, _, _), name in zip(P.B.TILES, P.NATIVE[:4]):
            holder = self.report['holders'][key]
            bindings = [self.records[k] for k in self.tree.comps(holder, name='appVariableEvent')]
            found = []
            for r in bindings:
                f = P.B.Q.fields(r, self.pool, self.builder.schemas)
                found.append((self.pool.text(P.B.u32(r, f['variable-name'][0])),
                              P.B.u32(r, f['type'][0])))
            self.assertIn((name, 1), found)
            self.assertNotIn((f'FPQS_{key}Index', 1), found)
            # A second two-way owner can initialise the native mirror to 0
            # even while the actual setting is FHD. Keep exactly the original.
            owners=[]
            for r in self.records:
                if P.B.u32(r,0)!=0x10006 or self.pool.text(P.B.u32(r,8))!='appVariableEvent':continue
                f=P.B.Q.fields(r,self.pool,self.builder.schemas)
                at=f.get('variable-name')
                if at and self.pool.text(P.B.u32(r,at[0]))==name:
                    owners.append(P.B.u32(r,24))
            self.assertEqual(owners,[holder])

    def test_res_custom_edits_and_other_native_tiles_are_preserved(self):
        self.assertFalse(self.report['res_custom_record_overlap'])
        self.assertEqual(P.B.Q.SL.duplicate_local_ids(self.raw), [])
        shape = P.B.Q.P.page_shape(self.raw, self.pool)
        self.assertEqual(shape['orphans'], [])
        self.assertEqual(shape['bad_child_counts'], [])
        # In particular, native AEL / More dispatch was not repurposed as a
        # diagnostic counter, as it was in the independent prototype.
        for event in ('19', '20', '21'):
            _, new = P.B.blocks(self.tree, P.B.AEL, event)
            _, old = P.B.blocks(self.builder.tree, P.B.AEL, event)
            self.assertEqual([bytes(self.records[k]) for k in new],
                             [self.stock[k].to_bytes() for k in old])
        for dial in P.B.DIALS:
            for event in P.B.EVENT_ROLES:
                _, new=P.B.blocks(self.tree,dial,event)
                _, old=P.B.blocks(self.builder.tree,dial,event)
                self.assertEqual([bytes(self.records[k]) for k in new],
                                 [self.stock[k].to_bytes() for k in old])

    def test_original_parser_reads_complete_reconstructed_native_qs(self):
        import qs_probe
        parsed = qs_probe.native_parse(self.raw, bytes(self.pool.data), self.builder.image)
        self.assertEqual(len(parsed.traces), len(self.records))


if __name__ == '__main__':unittest.main(verbosity=2)
