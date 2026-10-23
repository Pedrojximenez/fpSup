"""Private objects, full input replacement and the actual native record parser."""
import unittest
import struct
import build_tiles as B


class TilesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = (B.ROOT / 'out/MAIN_c0000000.bin').read_bytes()
        cls.page, cls.pool, cls.report = B.build(cls.image)
        cls.records = [bytearray(r.to_bytes()) for r in B.Q.N.split(cls.page)]
        cls.tree = B.Q.Tree(cls.records, cls.pool)
        cls.schemas = B.Q.P.load_schemas(cls.image)

    def field(self, rec, name):
        return B.u32(rec, B.Q.fields(rec, self.pool, self.schemas)[name][0])

    def assert_private_routes(self, recs):
        tree = B.Q.Tree(recs, self.pool)
        for owner in B.DIALS:
            for event, key in B.EVENT_ROLES.items():
                _, actions = B.blocks(tree, owner, event)
                self.assertEqual(len(actions), 1)
                action = recs[actions[0]]
                self.assertEqual(self.pool.text(B.u32(action, 8)), 'changePropertyByControl')
                self.assertEqual(self.field(action, 'object-id'), self.report['holders'][key])
        for row in self.report['more']:
            _, actions = B.blocks(tree, row['owner'], row['event'])
            self.assertEqual(len(actions), 1)
            action = recs[actions[0]]
            self.assertEqual(self.pool.text(B.u32(action, 8)), 'changePropertyByControl')
            self.assertEqual(self.field(action, 'object-id'), row['target'])

    def test_all_four_are_independent_objects_in_every_slot(self):
        self.assertEqual(len(self.report['tiles']), 32)
        self.assertEqual({(x['cell'], x['key']) for x in self.report['tiles']},
                         {(n, key) for n in range(1, 9) for key, _, _ in B.TILES})
        for row in self.report['tiles']:
            self.assertGreater(row['object'], 11686)
            self.assertEqual(self.tree.parent(row['object']), row['parent'])
            kinds = [self.pool.text(B.u32(self.records[k], 8))
                     for k in self.tree.block(row['object'])[1:]]
            self.assertEqual(kinds.count('drawText'), 3)
            self.assertNotIn('drawImage', kinds)
            for k in self.tree.comps(row['object'], name='appVariableEvent'):
                rec = self.records[k]
                self.assertEqual(self.field(rec, 'type'), 0)
                var = self.pool.text(self.field(rec, 'variable-name'))
                self.assertTrue(var.startswith('FPQS_' + row['key']))

    def test_graph_allocations_and_local_numbers(self):
        actual = B.Q.P.page_shape(self.page, self.pool)
        old_pool = B.Q.P.Pool(B.Q.stock_pool(self.image))
        old = B.Q.P.page_shape(B.Q.stock_page(self.image), old_pool)
        self.assertEqual(actual['header_minus_actual'], old['header_minus_actual'])
        self.assertEqual(actual['orphans'], [])
        self.assertEqual(actual['bad_child_counts'], [])
        self.assertEqual(len(actual['objects']), len(old['objects']) + 41)
        self.assertEqual(B.Q.SL.duplicate_local_ids(self.page), [])

    def test_replaced_inputs_never_use_the_stock_setter_or_menu_jump(self):
        self.assert_private_routes(self.records)

    def test_private_holders_have_one_own_value_and_read_only_cap_binding(self):
        for key, holder in self.report['holders'].items():
            evs = [self.records[k] for k in self.tree.comps(holder, name='appVariableEvent')]
            self.assertEqual(len(evs), 2)
            for rec in evs:
                var = self.pool.text(self.field(rec, 'variable-name'))
                reverse = self.field(rec, 'type')
                self.assertEqual((var, reverse), (f'FPQS_{key}Index', 1) if var.endswith('Index')
                                 else (f'FPQS_{key}Max', 0))

    def test_private_refs_and_declared_variables(self):
        self.assertEqual(len(self.report['variables']), 64)
        for off, text in self.report['marks']:
            self.assertEqual(self.pool.text(struct.unpack_from('>I', self.page, off)[0]), text)
        bound = set()
        for rec in self.records:
            if B.u32(rec, 0) != 0x10006 or self.pool.text(B.u32(rec, 8)) != 'appVariableEvent':
                continue
            fields = B.Q.fields(rec, self.pool, self.schemas)
            if 'variable-name' in fields:
                var = self.pool.text(B.u32(rec, fields['variable-name'][0]))
                if var and var.startswith('FPQS_'):
                    bound.add(var)
        self.assertEqual(bound, set(self.report['variables']))

    def test_other_native_records_are_unchanged(self):
        old = [bytearray(r.to_bytes()) for r in B.Q.N.split(B.Q.stock_page(self.image))]
        old_tree = B.Q.Tree(old, self.pool)
        replaced, removed = set(), set()
        for dial in B.DIALS:
            for event in B.EVENT_ROLES:
                replaced.update(B.blocks(old_tree, dial, event)[1])
        for event in ('19', '20', '21'):
            actions = B.blocks(old_tree, B.AEL, event)[1]
            replaced.add(actions[0]); removed.update(actions[1:])
        objects = {299, 339, B.AEL}
        for _, root, icon, _ in B.Q.cells(old_tree):
            objects.update((root, icon, old_tree.child(root, 'Icon01')))
        # Remove only newly added object blocks, bindings and DC's added event.
        filtered = self.records[1:min(self.tree.at.values())]
        for oid in self.tree.at:
            if oid not in old_tree.at:
                continue
            dc_indices = set()
            if oid == B.AEL:
                event, actions = B.blocks(self.tree, oid, 'FPQS_DC_MoreKey')
                dc_indices = {event, *actions}
            for k in self.tree.block(oid):
                rec = self.records[k]
                if k in dc_indices:
                    continue
                if B.u32(rec, 0) == 0x10006 and self.pool.text(B.u32(rec, 8)) == 'appVariableEvent':
                    fields = B.Q.fields(rec, self.pool, self.schemas)
                    if 'variable-name' in fields:
                        var = self.pool.text(B.u32(rec, fields['variable-name'][0]))
                        if var and var.startswith('FPQS_'):
                            continue
                filtered.append(rec)
        expected = [(k, rec) for k, rec in enumerate(old[1:], 1) if k not in removed]
        # Last native block also contains the terminator, included by Tree.block.
        self.assertEqual(len(filtered), len(expected))
        for (k, before), after in zip(expected, filtered):
            if k in replaced:
                continue
            if B.u32(before, 0) == 0x10003 and B.u32(before, 20) in objects:
                self.assertEqual(before[:8] + before[20:], after[:8] + after[20:])
            else:
                self.assertEqual(before, after, f'Unexpected native record change at {k}')

    def test_original_parser_reads_every_record(self):
        import qs_probe
        probe = qs_probe.native_parse(self.page, bytes(self.pool.data), self.image)
        self.assertEqual(len(probe.traces), len(self.records))

    def test_mutation_native_action_leak_is_detected(self):
        recs = [bytearray(r) for r in self.records]
        _, actions = B.blocks(B.Q.Tree(recs, self.pool), 253, '19')
        rec = recs[actions[0]]
        B.put(rec, B.Q.fields(rec, self.pool, self.schemas)['object-id'][0], 341)
        with self.assertRaises(AssertionError):
            self.assert_private_routes(recs)

    def test_mutation_object_budget_is_detected(self):
        recs = [bytearray(r) for r in self.records]
        B.put(recs[0], 8, B.u32(recs[0], 8) - 1)
        bad = B.Q.P.page_shape(b''.join(recs), self.pool)
        self.assertNotEqual(bad['header_minus_actual'], B.Q.P.page_shape(self.page, self.pool)['header_minus_actual'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
