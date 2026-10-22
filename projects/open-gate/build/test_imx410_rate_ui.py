#!/usr/bin/env python3
"""Offline structural and original-interpreter checks for the 240 summary.

The native interpreter's allocation service and UI constructors are stubs.
Passing this suite does not assert that a camera has drawn the new label.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import struct
import sys
import unittest

import imx410_rate_ui as U
sys.path.insert(0, str(U.ROOT / "research/ui/tools"))
import native_ui_audit as A

IMAGE = (U.ROOT / "out/MAIN_c0000000.bin").read_bytes()
POOL = IMAGE[U.POOL_START-U.BASE:U.POOL_START-U.BASE+U.POOL_SIZE]


def patched_image():
    im = bytearray(IMAGE)
    for address, value, _ in U.patches(IMAGE):
        struct.pack_into("<I", im, address-U.BASE, value)
    return bytes(im)


def records(image):
    return U.N.split(image[U.SET_START-U.BASE:U.SET_END-U.BASE])


def objects(rows):
    return {r.words(7)[3]: r for r in rows if r.tag == 0x10003}


def check_summary(image):
    rows = records(image)
    objs = objects(rows)
    children = [r for r in rows if r.tag == 0x10003
                and r.words(7)[4] == U.TEXT_PARENT]
    assert len(children) == objs[U.TEXT_PARENT].words(7)[2] == 10
    assert [r.words(7)[3] for r in children] == list(range(4449, 4457)) + [29946, 4458]
    assert objs[U.ICON_PARENT].words(7)[2] == 6
    assert len([r for r in objs.values() if r.words(7)[4] == U.ICON_PARENT]) == 6
    assert U.DROP_ID not in objs
    text = [r for r in rows if r.tag == 0x10005
            and r.words(4)[3] == U.BORROWED_ID]
    assert len(text) == 1
    raw = text[0].body
    assert struct.unpack_from(">I", raw, 0)[0] == 0x2541C
    assert struct.unpack_from(">I", raw, 20)[0] == 0x40002001
    assert U.N.string_at(POOL, struct.unpack_from(">I", raw, 24)[0]) == "240"
    assert raw[28] == 0, "literal label must not enter the nloc resolver"
    assert struct.unpack_from(">I", raw, 29)[0] == 0xFFFFFFFF
    assert struct.unpack_from(">4f", raw, 33) == (0, 0, 532, 54)


class SummaryStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patched = patched_image()
        cls.old, cls.new = records(IMAGE), records(cls.patched)

    def test_tenth_native_text_child_is_literal_240(self):
        check_summary(self.patched)

    def test_only_set_bytes_change_and_next_set_stays_in_place(self):
        lo, hi = U.SET_START-U.BASE, U.SET_END-U.BASE
        self.assertEqual(self.patched[:lo], IMAGE[:lo])
        self.assertEqual(self.patched[hi:], IMAGE[hi:])
        self.assertEqual(self.patched[hi-3:hi], bytes(3))
        self.assertEqual(sum(r.size for r in self.new), hi-lo-3)
        self.assertEqual(self.new[-1].tag, 0xFFFFFFFF)

    def test_first_nine_labels_and_all_other_object_ids_remain(self):
        old, new = objects(self.old), objects(self.new)
        self.assertEqual(set(old) - {U.DROP_ID}, set(new))
        changed = {U.TEXT_PARENT, U.ICON_PARENT, U.BORROWED_ID, U.LIST_ID, U.DROP_ID}
        for oid in set(old)-changed:
            self.assertEqual(old[oid].body, new[oid].body, oid)
        for oid in list(range(4449, 4457)) + [29946]:
            a = [r.body for r in self.old if r.tag == 0x10005 and r.words(4)[3] == oid]
            b = [r.body for r in self.new if r.tag == 0x10005 and r.words(4)[3] == oid]
            self.assertEqual(a, b, oid)

    def test_native_layout_and_rgb_animation_are_preserved(self):
        old_base = next(r for r in self.old if r.tag == 0x10004 and r.words(4)[3] == 29946)
        new_base = next(r for r in self.new if r.tag == 0x10004 and r.words(4)[3] == 4458)
        self.assertEqual(old_base.body[:12] + old_base.body[16:],
                         new_base.body[:12] + new_base.body[16:])
        clips = []
        for rows in (self.old, self.new):
            r = next(r for r in rows if r.tag == 0x1000A and r.words(4)[3] == 4458)
            clips.append(A.parse_clip(A.Record(0, r.to_bytes()), lambda x: U.N.string_at(POOL, x)))
        self.assertEqual(clips[0]['properties'][:3], clips[1]['properties'])
        self.assertEqual([k['value'] for k in clips[0]['properties'][3]['keys']], [1.0, 1.0])
        expected = Counter(r.tag for r in self.old)
        expected.subtract({0x10003: 1, 0x10004: 1, 0x10005: 1, 0x1000A: 1})   # Icon08
        expected.update({0x10006: 1, 0x10009: 1})                           # row-ten pair
        self.assertEqual(+expected, Counter(r.tag for r in self.new))

    def test_drawable_capacity_transfer_and_conservative_animation_budgets(self):
        old = A.parse_header(A.Record(0, self.old[0].to_bytes()), lambda x: U.N.string_at(POOL, x))
        new = A.parse_header(A.Record(0, self.new[0].to_bytes()), lambda x: U.N.string_at(POOL, x))
        expected = dict(old['component_counts'])
        expected['drawImage'] -= 2
        expected['drawText'] += 1
        expected['animationClip'] -= 1
        expected['controlValueEvent'] += 1
        expected['controlFocus'] += 1
        self.assertEqual(new['component_counts'], expected)
        for key in ('objects', 'special_objects', 'groups', 'clip_property_counts',
                    'property_key_counts', 'trailing_budget'):
            self.assertEqual(old[key], new[key], key)

    def test_popup_controller_and_bit_depth_records_do_not_move(self):
        for start, length in ((0xC1A74B24, 64), (0xC1A690B7, 64)):
            a = start-U.BASE
            self.assertEqual(IMAGE[a:a+length], self.patched[a:a+length])

    def test_installed_word_helper_accepts_the_real_controller_edit(self):
        words = {a: w for a, w, _ in U.patches(IMAGE)}
        words[0xC1A74B44] = 0x00001041  # PL's BE float 9.0, same exact slot
        result = U.verify_installed(words, base_image=IMAGE)
        self.assertEqual(result['literal_text'], '240')
        self.assertEqual(len(result['summary_children']), 10)
        self.assertFalse(result['native_interpreter_executed'])

    def _controller(self, owner, prop):
        oid = None
        for r in self.new:
            if r.tag == 0x10003:
                oid = r.words(7)[3]
            elif oid == owner and r.tag == 0x1000E and r.words(6)[3:6:2] == (owner, prop):
                return r
        raise AssertionError((owner, prop))

    def test_popup_row_instances_and_summary_range_cover_ten(self):
        """r2 grew the rows/children but not these two ranges (camera: no row 10)."""
        item = struct.unpack_from(">f", self._controller(4440, 3).body, 28)[0]
        summary = struct.unpack_from(">f", self._controller(4434, 0x12).body, 24)[0]
        self.assertEqual((item, summary), (10.0, 9.0))
        icon = struct.unpack_from(">f", self._controller(4438, 0x12).body, 24)[0]
        self.assertEqual(icon, 9.0)   # camera 2026-10-01: 8.0 clamped row 9 to 8

    def test_the_two_ranges_follow_the_stock_law(self):
        """Every stock popup: ListItem count = max(8, rows); summary max = max(7, children-1)."""
        children = objects(self.new)[U.TEXT_PARENT].words(7)[2]
        item = struct.unpack_from(">f", self._controller(4440, 3).body, 28)[0]
        summary = struct.unpack_from(">f", self._controller(4434, 0x12).body, 24)[0]
        self.assertEqual(item, max(8, 10))
        self.assertEqual(summary, max(7, children - 1))

    def test_popup_has_a_cursor_pair_for_every_row(self):
        """Stock v=0..8 each focus instance "v"; r4 on camera had none for row ten."""
        self.assertEqual(U.popup_cursor_pairs(self.old, POOL), {v: str(v) for v in range(9)})
        self.assertEqual(U.popup_cursor_pairs(self.new, POOL), {v: str(v) for v in range(10)})
        self.assertEqual(objects(self.new)[U.LIST_ID].words(1)[0], 17)

    def test_zero_tail_is_only_on_the_new_focus_record(self):
        focus = [r for r in self.new if r.tag == 0x10009 and len(r.body) > 41]
        pair = [r for r in focus if r.words(5)[3:5] == (U.LIST_ID, U.PAIR_KEY)]
        self.assertEqual(len(pair), 1)
        self.assertFalse(any(pair[0].body[41:]))

    def test_changed_firmware_is_rejected(self):
        mutant = bytearray(IMAGE)
        mutant[U.BORROW_START-U.BASE] ^= 1
        with self.assertRaises(ValueError):
            U.patches(bytes(mutant))

    def test_missing_tenth_parent_count_and_wrong_literal_flag_are_detected(self):
        parent = objects(self.new)[U.TEXT_PARENT]      # moved by the row-ten pair
        mutant = bytearray(self.patched)
        struct.pack_into('>I', mutant, U.SET_START-U.BASE+parent.offset+8+8, 9)
        with self.assertRaises(AssertionError):
            check_summary(bytes(mutant))
        r = next(r for r in self.new if r.tag == 0x10005 and r.words(4)[3] == 4458)
        mutant = bytearray(self.patched)
        mutant[U.SET_START-U.BASE+r.offset+8+28] = 1
        with self.assertRaises(AssertionError):
            check_summary(bytes(mutant))


class NativeInterpreter(unittest.TestCase):
    def test_original_interpreter_consumes_the_changed_set(self):
        image = bytearray(patched_image())
        struct.pack_into('<I', image, 0xC1A74B44-U.BASE, 0x00001041)
        result = U.verify_installed(image, native=True)
        self.assertTrue(result['native_interpreter_executed'])
        self.assertEqual(result['native_selected_summary_child'], 4458)
        self.assertFalse(result['gui_rendered'])

    def test_popup_only_mode_parses_natively_without_the_summary(self):
        """Freeze bisection card M: row-ten cursor pair, stock nine-label summary."""
        U.WITH_SUMMARY = False
        try:
            im = bytearray(IMAGE)
            for address, value, _ in U.patches(IMAGE):
                struct.pack_into("<I", im, address-U.BASE, value)
        finally:
            U.WITH_SUMMARY = True
        rows = records(bytes(im))
        objs = objects(rows)
        self.assertEqual(objs[U.TEXT_PARENT].words(7)[2], 9)
        self.assertEqual(objs[U.BORROWED_ID].words(7)[4], U.ICON_PARENT)
        self.assertEqual(U.popup_cursor_pairs(rows, POOL), {v: str(v) for v in range(10)})
        self.assertEqual(sum(r.size for r in rows), U.SET_END-U.SET_START)
        U.native_parse(bytes(im))

    def test_native_selector_detects_a_missing_tenth_child(self):
        import nbu_probe as P
        probe = P.NbuProbe(IMAGE[:P.SEG0_SIZE])
        with self.assertRaisesRegex(ValueError, 'clamped'):
            U._verify_summary_selector(probe, list(range(4449, 4457)) + [29946])


if __name__ == '__main__':
    unittest.main(verbosity=2)
