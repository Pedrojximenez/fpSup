"""Native parser and route checks for the r3h management design."""
import struct
import unittest
from unittest.mock import patch

import build_ft6 as B
import ft6_page as F
import manage_page as M


class ManagementPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.img, cls.pool = F.stock_pool()
        cls.pages = {'FT_Y6': M.build_home(cls.img, cls.pool),
                     'FT_LIST': M.build_manage(cls.img, cls.pool)}
        cls.pages.update({name: M.build_info(name, cls.img, cls.pool) for name in M.INFO})

    def test_all_pages_through_the_native_interpreter(self):
        for name, (page, _refs) in self.pages.items():
            with self.subTest(page=name):
                shape = F.check_page(page, self.img, self.pool)
                self.assertFalse(F.Lab.duplicate_local_ids(page))
                self.assertEqual(shape['objects'][F.ROWS_PARENT]['child_count'],
                                 6 if name == 'FT_LIST' else 4 if name == 'FT_Y6' else len(M.INFO[name]))

    def test_home_and_child_routes_use_the_stock_matcher(self):
        pack = B.build_pack([(n, p[0]) for n, p in self.pages.items()],
                            trans=B.TRANSITIONS + B.LIST_TRANSITIONS)
        pairs = [(B.PAGE, request) for _label, request in M.HOME]
        pairs += [(request, 'Return') for _label, request in M.HOME]
        pairs += [(B.PAGE, 'Menu01'), (B.PAGE, 'Menu12')]
        old, B.SL.MACHINE = B.SL.MACHINE, B.MACHINE
        try:
            import nbu_probe
            self.assertLess(nbu_probe.NbuProbe.BLOB + 0x70000, nbu_probe.NbuProbe.HEAP)
            with patch.object(nbu_probe.NbuProbe, 'BLOB_MAX', 0x70000):
                got = B.SL.native_switch(pack, pairs)
        finally:
            B.SL.MACHINE = old
        for _label, request in M.HOME:
            self.assertEqual(got[(B.PAGE, request)][0], request)
            self.assertEqual(got[(request, 'Return')][0], B.PAGE)
        self.assertEqual(got[(B.PAGE, 'Menu01')][0], 'MainB1')
        self.assertEqual(got[(B.PAGE, 'Menu12')][0], 'MainY5')

    def test_only_title_keys_page_and_popup_choices_write_private_values(self):
        page, refs = self.pages['FT_LIST']
        objects = F.SZ.objects(F.N.split(page), self.pool)
        named = set()
        writes = []
        key, owner, at = None, None, 0
        for rec in F.N.split(page):
            r = rec.to_bytes()
            if rec.tag == 0x10003:
                owner, key = F.u32(r, 20), None
            elif rec.tag == 0x10006:
                key = self.pool.text(F.u32(r, 20)) if F.pool_name(type('P', (), {'pool': self.pool}), r) == 'keyEvent' else None
            for off, kind in F.P.typed_fields(r, self.pool, F.P.load_schemas(self.img)):
                if kind in ('str', 'text'): named.add(self.pool.text(F.u32(r, off)))
            if rec.tag == 0x10009 and len(r) > 36 and self.pool.text(F.u32(r, 8)) == 'controlAppVariable':
                destination = self.pool.text(F.u32(r, 36))
                if key and destination and destination.startswith('FT_'):
                    writes.append((owner, key, destination, r))
            at += len(r)
        page_keys = [(o, k, self.pool.text(F.u32(r, 41))) for o, k, v, r in writes if v == 'FT_Key']
        self.assertCountEqual(page_keys, [(3451, 'Left', '10'), (3451, 'Right', '11')])
        for k in range(1, 6):
            choices = [(o, key, r) for o, key, v, r in writes if v == M.var('Choice', k)]
            self.assertEqual([key for _o, key, _r in choices], ['Right', 'OK'])
            for _o, key, r in choices:
                if key == 'OK':
                    self.assertEqual(objects[F.u32(r, 45)]['name'], 'List')
                    self.assertEqual(self.pool.text(F.u32(r, 49)), 'controlValue')
                else:
                    self.assertEqual(self.pool.text(F.u32(r, 41)), '2')
        self.assertFalse(named & {'CM_TargetVersionUpgrade', 'CM_SaveReadSettings',
                                 'SoftKeyboard_MenuName', 'SoftKeyboard_InputID', 'MainY5_ListFocus5', 'MENU_Level1'})
        self.assertTrue({'Enable', 'Disable'} <= named)
        self.assertNotIn('More Settings', named)
        self.assertIn(M.var('TabActive', 1), named)
        self.assertIn('SupManager', named)

    def test_paging_title_has_no_submenu_dots_or_arrow(self):
        recs = F.N.split(self.pages['FT_LIST'][0])
        by = F.by_object([r.to_bytes() for r in recs])
        for owner in (10062, 3457):
            draw = next(recs[i].to_bytes() for i in by[owner]
                        if self.pool.text(F.u32(recs[i].to_bytes(), 8)) == 'drawImage')
            self.assertEqual(self.pool.text(F.u32(draw, 32)), 'blank')

    def test_unfinished_features_cannot_dispatch_a_request(self):
        for page_name, (page, _refs) in self.pages.items():
            if page_name == 'FT_LIST':
                continue
            records = [r.to_bytes() for r in F.N.split(page)]
            objects = F.SZ.objects(F.N.split(page), self.pool)
            rows = [o for o, v in objects.items() if v['parent'] == F.ROWS_PARENT]
            blocked = {'FT_Y6': {1, 2, 3}, 'FT_UPDATES': {1, 2},
                       'FT_CARD': {1}, 'FT_ABOUT': {2}}[page_name]
            for k in blocked:
                with self.subTest(page=page_name, row=k):
                    subtree = F.SZ.subtree(objects, rows[k])
                    events = [r for r in records if F.u32(r, 0) == 0x10006
                              and F.u32(r, 24) in subtree
                              and self.pool.text(F.u32(r, 8)) == 'keyEvent'
                              and self.pool.text(F.u32(r, 20)) in ('Right', 'OK')]
                    self.assertEqual(len(events), 2)
                    self.assertTrue(all(F.u32(r, 16) == 0 for r in events))
                    menu = [r for r in records if F.u32(r, 0) == 0x10006
                            and F.u32(r, 24) in subtree
                            and self.pool.text(F.u32(r, 8)) == 'keyEvent'
                            and self.pool.text(F.u32(r, 20)) == 'Menu']
                    self.assertTrue(menu)
                    self.assertTrue(all(F.u32(r, 16) for r in menu))
        self.assertIn('SD Card Format (Keep fpSup)', self.pool.added)
        self.assertNotIn('SD Card Tools', self.pool.added)

    def test_current_state_initializes_the_popup_list_itself(self):
        page = self.pages['FT_LIST'][0]
        records = F.N.split(page)
        objects = F.SZ.objects(records, self.pool)
        lists = []
        for rec in records:
            r = rec.to_bytes()
            if rec.tag == 0x10006 and self.pool.text(F.u32(r, 8)) == 'appVariableEvent' and len(r) == 58:
                name = self.pool.text(F.u32(r, 40))
                if name and name.startswith('FT_Default') and objects[F.u32(r, 24)]['name'] == 'List':
                    self.assertEqual(self.pool.text(F.u32(r, 49)), 'value')
                    lists.append(name)
        self.assertCountEqual(lists, [f'FT_Default{k}' for k in range(1, 6)])

    def test_logo_colour_preserves_stock_cursor_without_an_outline(self):
        for name, (page, _refs) in self.pages.items():
            self.assertIn(struct.pack('>I', 0xE03858FF), page, name)
            self.assertNotIn(struct.pack('>I', 0xFFDD44FF), page, name)
            self.assertIn('FT_Version', self.pool.added)
            self.assertNotIn(struct.pack('>IIf', 0xE03858FF, 0, 2.0), page, name)


if __name__ == '__main__':
    unittest.main()
