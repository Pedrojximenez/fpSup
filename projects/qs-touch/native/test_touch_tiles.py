import unittest
import build_touch_tiles as T
import test_tiles

B = T.B


class TouchResourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = (B.ROOT / 'out/MAIN_c0000000.bin').read_bytes()
        cls.page, cls.pool, cls.report = T.build(cls.image)
        cls.records = [bytearray(r.to_bytes()) for r in B.Q.N.split(cls.page)]
        cls.tree = B.Q.Tree(cls.records, cls.pool)
        cls.schemas = B.Q.P.load_schemas(cls.image)

    field = test_tiles.TilesTests.field
    assert_private_routes = test_tiles.TilesTests.assert_private_routes

    def test_touch_actions_still_target_only_private_holders(self):
        self.assert_private_routes(self.records)

    def test_shape_budget_and_local_ids(self):
        shape = B.Q.P.page_shape(self.page, self.pool)
        old = B.Q.P.page_shape(B.Q.stock_page(self.image), B.Q.P.Pool(B.Q.stock_pool(self.image)))
        self.assertEqual(shape['header_minus_actual'], old['header_minus_actual'])
        self.assertEqual(shape['orphans'], [])
        self.assertEqual(shape['bad_child_counts'], [])
        self.assertEqual(len(shape['objects']), len(old['objects']) + 44)
        self.assertEqual(B.Q.SL.duplicate_local_ids(self.page), [])

    def test_no_new_or_modified_animation_clips(self):
        old = [r.to_bytes() for r in B.Q.N.split(B.Q.stock_page(self.image)) if r.tag == 0x1000A]
        new = [bytes(r) for r in self.records if B.u32(r, 0) == 0x1000A]
        self.assertEqual(old, new)
        self.assertFalse(self.report['touch']['animation'])
        new_ids = {oid for oid in self.tree.at if oid > 11686}
        self.assertTrue(all(B.u32(r, 20) not in new_ids for r in self.records if B.u32(r, 0) == 0x1000A))

    def test_touch_geometry_matches_the_native_cells(self):
        geometry = self.report['touch']['native_geometry']
        for n, root, _, _ in B.Q.cells(self.tree):
            rec = self.records[self.tree.comps(root, name='objectBase')[0]]
            import struct
            fields = B.Q.fields(rec, self.pool, self.schemas)
            pos = struct.unpack_from('>ff', rec, fields['position'][0])
            size = struct.unpack_from('>ff', rec, fields['size'][0])
            self.assertEqual(pos, ((n - 1) % 4 * 256, geometry['row_y'][(n - 1) // 4]))
            self.assertEqual(size, tuple(geometry['cell']))

    def test_touch_bindings_are_read_only_and_have_exact_targets(self):
        expected = {
            'FPQS_PanelOn': 'is-visible', 'FPQS_TouchLegacyCursor': 'opacity',
            'FPQS_TouchFocusOn': 'is-visible', 'FPQS_TouchFocusX': 'position',
            'FPQS_TouchFocusY': 'position', 'FPQS_TouchFooterOn': 'is-visible',
            'FPQS_TouchLegacyFooter': 'opacity', 'FPQS_TouchFooterText': 'text',
            'FPQS_TouchPageText': 'text'}
        found = {}
        for rec in self.records:
            if B.u32(rec, 0) != 0x10006 or self.pool.text(B.u32(rec, 8)) != 'appVariableEvent':
                continue
            fields = B.Q.fields(rec, self.pool, self.schemas)
            if 'variable-name' not in fields:
                continue
            name = self.pool.text(self.field(rec, 'variable-name'))
            if name not in expected:
                continue
            self.assertEqual(self.field(rec, 'type'), 0)
            found[name] = self.pool.text(self.field(rec, 'property-name'))
        self.assertEqual(found, expected)
        self.assertEqual(len(self.report['variables']), 73)

    def test_original_parser_reads_touch_page(self):
        import qs_probe
        probe = qs_probe.native_parse(self.page, bytes(self.pool.data), self.image)
        self.assertEqual(len(probe.traces), len(self.records))

    def test_mutation_private_dial_route_is_detected(self):
        recs = [bytearray(r) for r in self.records]
        _, actions = B.blocks(B.Q.Tree(recs, self.pool), 253, '19')
        rec = recs[actions[0]]
        B.put(rec, B.Q.fields(rec, self.pool, self.schemas)['object-id'][0], 341)
        with self.assertRaises(AssertionError):
            self.assert_private_routes(recs)


if __name__ == '__main__':
    unittest.main(verbosity=2)
