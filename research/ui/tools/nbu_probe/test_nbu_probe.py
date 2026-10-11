#!/usr/bin/env python3
"""Offline tests for the NBU interpreter harness.

Every assertion is either (a) a value an independent source already derived by
hand from the image, or (b) agreement between the firmware's own parse and a
pure-Python decode of the same bytes.  Nothing here touches a camera.

    cd research/ui/tools/nbu_probe && python3 -B -m unittest
"""
import unittest

import nbu_format as F
import nbu_probe as N


class Harness(unittest.TestCase):
    def test_image_hash_is_pinned(self):
        with self.assertRaises(N.ProbeError):
            N.load_firmware(__file__)

    def test_a_synthetic_container_parses_its_own_tokens(self):
        probe = N.build()
        # tag 1 is the string pool: size then that many bytes.
        pool = b"Hello\0World\0"
        blob = N.nbu(1, len(pool) + 8) + pool
        probe.open(blob=blob)
        trace = probe.record()
        self.assertEqual(trace.token, 1)
        self.assertEqual(trace.result, 0)
        size, base = probe.pool()
        self.assertEqual(size, len(pool))
        self.assertEqual(probe.pool_string(0), "Hello")
        self.assertEqual(probe.pool_string(6), "World")

    def test_the_end_tag_stops_the_loop(self):
        probe = N.build()
        probe.open(blob=N.nbu(1, 8, 0xFFFFFFFF))
        traces = probe.records(limit=8)
        self.assertEqual([t.token for t in traces], [1, 0xFFFFFFFF])
        self.assertEqual(traces[-1].result, 1)

    def test_an_unstubbed_call_is_named_not_silently_zero(self):
        probe = N.NbuProbe(N.load_firmware(N._default_image()))   # no arena stub
        probe.open(base=probe.NBU_BASE, size=probe.NBU_SIZE)
        probe.record()                                             # the pool: no calls
        with self.assertRaises(N.UnstubbedCall) as caught:
            probe.record()
        self.assertEqual(caught.exception.address, 0xC05E8EF8)

    def test_the_source_must_carry_the_magic(self):
        probe = N.build()
        with self.assertRaises(N.ProbeError):
            probe.open(blob=b"NBX\0" + b"\0" * 32)


class TopLevelContainer(unittest.TestCase):
    """The real container at 0xC18C0460, parsed by the camera's own interpreter."""

    @classmethod
    def setUpClass(cls):
        cls.probe = N.build(survey=True)
        cls.rows = cls.probe.index()
        cls.by_name = {r["name"]: r for r in cls.rows}

    def test_it_holds_the_pool_and_the_set_table_and_nothing_else(self):
        tokens = [t.token for t in self.probe.traces]
        self.assertEqual(tokens, [1, 0x10001])

    def test_the_pool_base_is_the_documented_one(self):
        size, base = self.probe.pool()
        self.assertEqual(base, 0xC18C0474)      # research/ui/README.md §1
        self.assertEqual(size, 0x2B018)

    def test_there_are_221_named_resource_sets(self):
        self.assertEqual(len(self.rows), 221)
        self.assertTrue(all(row["name"] for row in self.rows))

    def test_mainb2_matches_the_hand_derived_triple(self):
        # MAINB2_ROW_EXTENSION.md derived all three from the image by hand.
        row = self.by_name["MainB2"]
        self.assertEqual(row["hash"], 0xBDD26684)
        self.assertEqual(row["pool_offset"], 0x1A3B8)
        self.assertEqual(row["offset"], 0x76FF04)
        self.assertEqual(row["address"], 0xC2030364)

    def test_mainb3_starts_where_mainb2_ends(self):
        # The note pins MainB2 as C2030364..C2055DB0.
        self.assertEqual(self.by_name["MainB3"]["address"], 0xC2055DB0)

    def test_mainy4_is_where_the_lossless_donor_lives(self):
        # NATIVE_ROW_DONOR.md: MainY4 page [C214A0C0, C217CDEE)
        self.assertEqual(self.by_name["MainY4"]["address"], 0xC214A0C0)
        self.assertEqual(self.by_name["MainY5"]["address"], 0xC217CDEE)

    def test_the_table_is_sorted_by_hash(self):
        hashes = [row["hash"] for row in self.rows]
        self.assertEqual(hashes, sorted(hashes))


class ResourceSet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.probe = N.build(survey=True)
        cls.probe.index()
        cls.probe.open_set("MainB2")
        cls.trace = cls.probe.record()
        cls.header = cls.probe.allocation_header()

    def test_the_first_record_is_the_allocation_header(self):
        self.assertEqual(self.trace.token, 0x00010002)
        self.assertEqual(self.trace.result, 0)

    def test_it_is_3028_bytes_as_the_note_says(self):
        # MAINB2_ROW_EXTENSION.md: "Allocation header C2030364 / 3028"
        self.assertEqual(self.trace.consumed, 3028)
        self.assertEqual(self.header["size"], 3028)

    def test_the_python_decode_agrees_with_the_firmware_parse(self):
        self.assertEqual([name for name, _n in self.header["classes"]],
                         self.trace.strings)

    def test_the_object_count_is_the_objectbase_count(self):
        classes = dict(self.header["classes"])
        self.assertEqual(self.header["objects"], classes["objectBase"])
        self.assertEqual(self.header["objects"], 193)

    def test_the_classes_include_the_ones_the_donor_work_needs(self):
        classes = dict(self.header["classes"])
        for name in ("drawText", "drawImage", "controlValue", "animationClip",
                     "controlAppVariable", "keyEvent"):
            self.assertIn(name, classes)

    def test_every_token_of_the_record_was_read(self):
        # 757 big-endian words is exactly 3028 bytes: the interpreter consumed
        # the whole header through its own reader, nothing was skipped.
        self.assertEqual(len(self.trace.tokens) * 4, self.trace.consumed)


class PureFormat(unittest.TestCase):
    """The Python codec, checked against the firmware's own record boundaries."""

    @classmethod
    def setUpClass(cls):
        cls.probe = N.build(survey=True)
        cls.probe.allow(*cls.probe.OBJECT_FACTORY, "object factory")
        cls.emulated = cls.probe.map_set("MainB2")
        row = [r for r in cls.probe.index() if r["name"] == "MainB2"][0]
        last = cls.emulated[-1]
        cls.start, end = row["address"], last["address"] + last["size"]
        cls.raw = bytes(cls.probe.uc.mem_read(cls.start, end - cls.start))
        cls.parsed = F.split(cls.raw)
        size, base = cls.probe.pool()
        cls.pool = bytes(cls.probe.uc.mem_read(base, size))

    def test_python_finds_the_same_records_as_the_firmware(self):
        self.assertEqual([(r["tag"], r["offset"], r["size"]) for r in self.emulated],
                         [(r.tag, r.offset, r.size) for r in self.parsed])

    def test_re_emitting_is_byte_exact(self):
        self.assertEqual(F.join(self.parsed), self.raw)

    def test_every_record_is_length_prefixed(self):
        import struct
        for record in self.parsed:
            tag, size = struct.unpack_from(">II", self.raw, record.offset)
            self.assertEqual((tag, size), (record.tag, record.size))

    def test_the_terminator_is_eight_bytes(self):
        self.assertEqual(self.parsed[-1].tag, F.TERMINATOR)
        self.assertEqual(self.parsed[-1].size, 8)

    def test_the_allocation_header_agrees_with_the_emulated_decode(self):
        mine = F.allocation_header(self.parsed[0], self.pool)
        theirs = self.probe.allocation_header(self.start)
        self.assertEqual(mine["objects"], theirs["objects"])
        self.assertEqual(mine["classes"], theirs["classes"])

    def test_editing_a_body_keeps_the_stream_consistent(self):
        records = F.split(self.raw)
        records[5].body += b"\x00\x00\x00\x07"
        rebuilt = F.join(records)
        self.assertEqual(len(rebuilt), len(self.raw) + 4)
        again = F.split(rebuilt)
        self.assertEqual([r.tag for r in again], [r.tag for r in records])
        self.assertEqual(again[5].size, self.parsed[5].size + 4)

    def test_a_broken_size_is_refused_by_name_not_by_running_out(self):
        # Asserting only "it raises" would also pass if the size check were gone
        # and the walk merely spun until the record limit -- so check the reason.
        import struct
        for bad_size in (0, len(self.raw) + 16):
            broken = bytearray(self.raw)
            struct.pack_into(">I", broken, 4, bad_size)
            with self.assertRaises(F.FormatError) as caught:
                F.split(bytes(broken))
            self.assertIn("impossible size", str(caught.exception))

    def test_the_whole_ui_parses_and_the_sets_tile_exactly(self):
        image, base, rows, _pool = F.load_sets()
        self.assertEqual(len(rows), 221)
        total = closed = 0
        for index, row in enumerate(rows):
            parsed = F.split(image[row["address"] - base:])
            total += len(parsed)
            end = row["address"] + sum(r.size for r in parsed)
            if index + 1 < len(rows):
                self.assertEqual(end, rows[index + 1]["address"], row["name"])
                closed += 1
        self.assertEqual(closed, 220)
        self.assertEqual(total, 303_597)

    def test_the_image_array_tag_is_the_one_that_builds_containers(self):
        # Established by execution: 0x1000B is the only tag whose trace calls
        # FUN_c05e2988 (image_container_new).
        counts = F.tally(self.parsed)
        self.assertEqual(counts[0x0001000B], 52)
        self.assertIn("IMAGE ARRAY", F.TAGS[0x0001000B][0])


class ImageArrays(unittest.TestCase):
    """Tag 0x1000B decoded field by field, across the whole UI."""

    @classmethod
    def setUpClass(cls):
        cls.image, cls.base, cls.rows, (pool_base, pool_size) = F.load_sets()
        cls.pool = cls.image[pool_base - cls.base:pool_base - cls.base + pool_size]
        cls.arrays = []
        for row in cls.rows:
            for record in F.split(cls.image[row["address"] - cls.base:]):
                if record.tag == 0x0001000B:
                    cls.arrays.append((row["name"], record))

    def test_every_image_array_in_the_ui_decodes_with_nothing_left_over(self):
        # decode_image_array raises if a single byte is unaccounted for, so a
        # wrong field width anywhere would fail here rather than pass quietly.
        self.assertEqual(len(self.arrays), 11_383)
        for _set_name, record in self.arrays:
            F.decode_image_array(record, self.pool)

    def test_a_spare_byte_is_refused_not_ignored(self):
        # Without this the "nothing left over" check could be deleted and the
        # suite would still pass -- the other assertions only read fields.
        _name, record = self.arrays[0]
        padded = F.Record(record.tag, record.offset, record.body + b"\x00")
        with self.assertRaises(F.FormatError) as caught:
            F.decode_image_array(padded, self.pool)
        self.assertIn("left over", str(caught.exception))

    def test_object_records_are_a_fixed_36_bytes_everywhere(self):
        # 8-byte header + 7 u32 = 36.  All 36,379 of them, which is what makes
        # the case-2 token list arithmetically forced rather than just read.
        total = 0
        for row in self.rows:
            for record in F.split(self.image[row["address"] - self.base:]):
                if record.tag == 0x00010003:
                    self.assertEqual(record.size, 36)
                    total += 1
        self.assertEqual(total, 36_379)

    def test_no_ui_record_names_a_file(self):
        # Every 0x1000A names the CLASS animationClip -- not a resource file.
        # Paths live only in the NBR name pool, which is why a resource repoint
        # applied late still takes effect.
        names = set()
        total = 0
        for row in self.rows:
            for record in F.split(self.image[row["address"] - self.base:]):
                if record.tag == 0x0001000A:
                    names.add(F.string_at(self.pool, record.words(1)[0]))
                    total += 1
        self.assertEqual(total, 46_528)
        self.assertEqual(names, {"animationClip"})

    def test_the_resolution_groups_live_in_the_quick_set_sets(self):
        found = {}
        for set_name, record in self.arrays:
            decoded = F.decode_image_array(record, self.pool)
            if decoded["group"] in ("20_MV_Resolution", "21_MV_Resolution"):
                found.setdefault(decoded["group"], []).append(set_name)
        for group in ("20_MV_Resolution", "21_MV_Resolution"):
            counts = {name: found[group].count(name) for name in set(found[group])}
            self.assertEqual(counts, {"QS_Common": 2, "QS_CINE": 8, "QS_STILLlike": 8})

    def test_their_endpoint_is_the_two_state_time_33(self):
        # research/ui/README.md 3: stock two-state curves end at 33, a third
        # state needs 66.  Here that endpoint is the entry's `b`.
        for set_name, record in self.arrays:
            decoded = F.decode_image_array(record, self.pool)
            if decoded["group"] in ("20_MV_Resolution", "21_MV_Resolution"):
                self.assertEqual(len(decoded["entries"]), 1)
                self.assertEqual(decoded["entries"][0]["b"], 33)

    def test_how_many_records_a_third_resolution_state_has_to_touch(self):
        import struct as _s
        keys = []
        for name in ("20_MV_Resolution", "21_MV_Resolution", "MV_Resolution"):
            at = self.pool.find(b"\0" + name.encode() + b"\0")
            self.assertGreater(at, 0, name)
            keys.append(_s.pack(">I", at + 1))
        per = {}
        for row in self.rows:
            hits = sum(1 for r in F.split(self.image[row["address"] - self.base:])
                       if any(k in r.body for k in keys))
            if hits:
                per[row["name"]] = hits
        self.assertEqual(sum(per.values()), 218)
        # the Quick Set is the bulk of it
        self.assertEqual(per["QS_CINE"], 68)
        self.assertEqual(per["QS_STILLlike"], 68)
        self.assertEqual(per["B2_5"], 6)


class ControllerMaxima(unittest.TestCase):
    """The float that decides how many rows a list will let you select."""

    @classmethod
    def setUpClass(cls):
        image, base, rows, _pool = F.load_sets()
        row = next(r for r in rows if r["name"] == "B2_5")
        cls.found = F.controller_maxima(F.split(image[row["address"] - base:]),
                                        row["address"])
        cls.by_address = {f["address"]: f for f in cls.found}

    def test_the_two_addresses_two_sessions_used_are_both_in_here(self):
        # 0xC1A709BC: the Resolution list, 2 rows, confirmed on a camera by
        # fpSup-Formats writing 5.0 for six rows.
        self.assertEqual(self.by_address[0xC1A709BC]["rows"], 2)
        # 0xC1A690D7: the bit-depth list, 3 rows, used on the camera 2026-09-29.
        self.assertEqual(self.by_address[0xC1A690D7]["rows"], 3)

    def test_the_frame_rate_list_has_nine_rows_and_three_copies(self):
        nine = [f for f in self.found if f["rows"] == 9]
        self.assertEqual(len(nine), 3)

    def test_each_row_count_repeats_so_one_write_may_not_be_enough(self):
        counts = {}
        for f in self.found:
            counts[f["rows"]] = counts.get(f["rows"], 0) + 1
        self.assertGreater(counts[2], 1)
        self.assertGreater(counts[3], 1)

    def test_only_tag_1000e_records_are_reported(self):
        image, base, rows, _pool = F.load_sets()
        row = next(r for r in rows if r["name"] == "B2_5")
        parsed = split_ = F.split(image[row["address"] - base:])
        by_offset = {row["address"] + r.offset: r for r in parsed}
        for f in self.found:
            self.assertEqual(by_offset[f["record"]].tag, 0x0001000E)


class MutationGuard(unittest.TestCase):
    """The checks above have to be able to fail (RE verification discipline)."""

    def test_a_little_endian_reader_would_disagree(self):
        probe = N.build(survey=True)
        probe.index()
        probe.open_set("MainB2")
        address = probe.words(probe.CTX + 0x24)[0]
        self.assertEqual(probe.be_words(address, 1)[0], 0x00010002)
        self.assertNotEqual(probe.words(address, 1)[0], 0x00010002)

    def test_a_wrong_pool_base_breaks_the_names(self):
        probe = N.build(survey=True)
        probe.index()
        probe.open_set("MainB2")
        probe.record()
        good = probe.allocation_header()["classes"][0][0]
        probe.write_words(probe.CTX + 0x14, 0xC18C0470)      # four bytes early
        bad = probe.allocation_header()["classes"][0][0]
        self.assertEqual(good, "animationClip")
        self.assertNotEqual(bad, good)

    def test_a_little_endian_split_would_not_close(self):
        import struct
        image, base, rows, _pool = F.load_sets()
        data = image[rows[0]["address"] - base:]
        tag_be, size_be = struct.unpack_from(">II", data, 0)
        tag_le, size_le = struct.unpack_from("<II", data, 0)
        self.assertEqual(tag_be, 0x00010002)
        self.assertNotEqual(tag_le, 0x00010002)
        self.assertNotEqual(size_le, size_be)

    def test_splitting_one_byte_late_desynchronises(self):
        image, base, rows, _pool = F.load_sets()
        data = image[rows[0]["address"] - base:]
        with self.assertRaises(F.FormatError):
            F.split(data, offset=1, limit=4000)

    def test_a_set_that_does_not_exist_is_refused(self):
        probe = N.build(survey=True)
        with self.assertRaises(N.ProbeError):
            probe.open_set("MainB99")


if __name__ == "__main__":
    unittest.main()
