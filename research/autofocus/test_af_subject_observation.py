"""Offline sentinel regressions for native subject layouts; no camera imports."""

import json
import struct
import unittest

from af_subject_observation import decode_native_subject


class NativeSubjectDecoderTests(unittest.TestCase):
    def test_missing_sources_remain_missing_with_no_geometry_authority(self):
        data = decode_native_subject()
        self.assertEqual(data["schema"], "sigma-fp-subject-observation/v1")
        for name in ("face_group", "aat_publication", "aat_model"):
            self.assertIsNone(data[name])
        self.assert_untrusted(data)

    def assert_untrusted(self, data):
        self.assertIs(data["geometry_eligible"], False)
        geometry = data["geometry"]
        for key, value in geometry.items():
            if key == "flags":
                self.assertTrue(value)
                self.assertTrue(all(flag is False for flag in value.values()))
            elif key == "motion_authorized":
                self.assertIs(value, False)
            else:
                self.assertIsNone(value, key)
        for name in ("face_group", "aat_publication", "aat_model"):
            if data[name] is not None:
                self.assertIs(data[name]["geometry_eligible"], False)
                self.assertIsNone(data[name]["coordinate_reference"])
                self.assertIsNone(data[name]["source_completion_epoch"])

    def test_face_offsets_use_group_relative_id_and_size_with_separate_tuples(self):
        blob = bytearray([0xA5] * 0x9C)
        struct.pack_into("<4I", blob, 0x00, 11, 22, 33, 44)
        struct.pack_into("<4I", blob, 0x10, 101, 202, 303, 404)
        struct.pack_into("<H", blob, 0x20, 0x8001)
        struct.pack_into("<I", blob, 0x24, 0x12345678)
        struct.pack_into("<I", blob, 0x28, 0xFEDCBA98)
        struct.pack_into("<I", blob, 0x2C, 98765)
        blob[0x30] = 0xFE
        struct.pack_into("<I", blob, 0x34, 0xDEADBEEF)  # Historical wrong ID offset.
        data = decode_native_subject(face_group=bytes(blob))
        raw = data["face_group"]["raw"]
        self.assertEqual(raw, {
            "primary_xy": [11, 22], "primary_size": [33, 44],
            "detector_xy": [101, 202], "detector_size": [303, 404],
            "native_angle": 0x8001, "native_tracking_id": 0x12345678,
            "native_score": 0xFEDCBA98, "size": 98765, "parsed_valid": 0xFE,
        })
        self.assertEqual(data["face_group"]["bytes_hex"], bytes(blob).hex())
        self.assert_untrusted(data)

    def test_face_slot_changes_only_source_address_not_bytes_or_identity(self):
        blob = bytes(range(0x9C))
        first = decode_native_subject(face_group=blob)["face_group"]
        last = decode_native_subject(face_group=blob, face_group_index=4)["face_group"]
        self.assertEqual(first["source"]["address"], "0xC37CCAAC")
        self.assertEqual(last["source"]["address"], "0xC37CCD1C")
        self.assertEqual(last["source"]["manager_offset"], 0x280)
        self.assertEqual(last["source"]["group_index"], 4)
        self.assertEqual(first["raw"], last["raw"])
        self.assertEqual(first["bytes_hex"], last["bytes_hex"])

    def test_face_coordinates_preserve_negative_top_left_and_signed_boundaries(self):
        blob = bytearray(0x9C)
        # Native center=5, size=20 produces top-left=-5 before conversion.
        # A bypass keeps that negative coordinate in the primary tuple too.
        struct.pack_into("<ii", blob, 0, -5, -2147483648)
        struct.pack_into("<ii", blob, 0x10, -5, 2147483647)
        struct.pack_into("<I", blob, 0x2C, 20)
        block = decode_native_subject(face_group=bytes(blob))["face_group"]
        self.assertEqual(block["raw"]["primary_xy"], [-5, -2147483648])
        self.assertEqual(block["raw"]["detector_xy"], [-5, 2147483647])
        self.assertEqual(block["raw"]["size"], 20)
        self.assertEqual(block["field_layout"]["primary_xy"]["type"], "i32")
        self.assertEqual(block["field_layout"]["detector_xy"]["type"], "i32")
        self.assertEqual(bytes.fromhex(block["bytes_hex"]), bytes(blob))

    def test_aat_counter_is_u32_and_rectangles_are_two_separate_i32_tuples(self):
        blob = bytearray(0x28)
        struct.pack_into("<I", blob, 0, 0xFEDCBA98)
        struct.pack_into("<4i", blob, 4, -2147483648, -2, 2147483647, -4)
        struct.pack_into("<4i", blob, 0x14, 17, -18, 19, -20)
        blob[0x24:0x28] = bytes([1, 0x80, 0xFE, 0xA7])
        data = decode_native_subject(aat_publication=bytes(blob))
        block = data["aat_publication"]
        self.assertEqual(block["raw"], {
            "path_count": 0xFEDCBA98,
            "result_xywh": [-2147483648, -2, 2147483647, -4],
            "af_input_xywh": [17, -18, 19, -20],
            "valid": 1, "ever_found": 0x80, "quality": 0xFE,
            "additional_result": 0xA7,
        })
        self.assertEqual(block["bytes_hex"], bytes(blob).hex())
        self.assertNotIn("frame_id", block["raw"])
        self.assertNotIn("locked", block["raw"])
        self.assert_untrusted(data)

    def test_model_is_direct_struct_with_u16_axes_i32_angle_and_quality_bytes(self):
        blob = bytearray([0xA5] * 0x2C)
        struct.pack_into("<4H", blob, 0, 65535, 0x8001, 0xFFFF, 0x8000)
        struct.pack_into("<i", blob, 8, -2147483648)
        blob[0xC], blob[0xD] = 255, 254
        data = decode_native_subject(aat_model=bytes(blob))
        block = data["aat_model"]
        self.assertEqual(block["source"]["address"], "0xC37CDFA8")
        self.assertEqual(block["raw"], {
            "center_xy": [65535, 0x8001], "semi_axes": [0xFFFF, 0x8000],
            "native_angle": -2147483648, "hits_mapped_quality": 255,
            "semi_axes_area_ratio": 254,
        })
        self.assertEqual(block["bytes_hex"], bytes(blob).hex())
        self.assertNotIn("depth", block["raw"])
        self.assertNotIn("hits", block["raw"])
        self.assert_untrusted(data)

    def test_field_layout_describes_byte_offsets_and_types(self):
        data = decode_native_subject(face_group=bytes(0x9C),
                                     aat_publication=bytes(0x28), aat_model=bytes(0x2C))
        expected = {
            "face_group": {"native_tracking_id": (0x24, "u32", 1),
                           "size": (0x2C, "u32", 1), "parsed_valid": (0x30, "byte", 1),
                           "native_angle": (0x20, "u16", 1), "native_score": (0x28, "u32", 1)},
            "aat_publication": {"path_count": (0, "u32", 1),
                                "result_xywh": (4, "i32", 4), "af_input_xywh": (0x14, "i32", 4),
                                "valid": (0x24, "byte", 1), "quality": (0x26, "byte", 1)},
            "aat_model": {"semi_axes": (4, "u16", 2), "native_angle": (8, "i32", 1),
                          "hits_mapped_quality": (0xC, "byte", 1),
                          "semi_axes_area_ratio": (0xD, "byte", 1)},
        }
        for source, fields in expected.items():
            for name, wanted in fields.items():
                with self.subTest(source=source, field=name):
                    actual = data[source]["field_layout"][name]
                    self.assertEqual((actual["offset"], actual["type"], actual["count"]), wanted)
                    self.assertTrue(actual["source"])

    def test_exact_length_is_required_for_each_source(self):
        for name, length in (("face_group", 0x9C), ("aat_publication", 0x28), ("aat_model", 0x2C)):
            for invalid in (b"", bytes(length-1), bytes(length+1), bytes(length*2)):
                with self.subTest(source=name, length=len(invalid)), self.assertRaisesRegex(ValueError, name):
                    decode_native_subject(**{name: invalid})

    def test_only_immutable_bytes_or_none_are_accepted(self):
        for name, length in (("face_group", 0x9C), ("aat_publication", 0x28), ("aat_model", 0x2C)):
            for invalid in (bytearray(length), memoryview(bytes(length)), "00"*length,
                            [0]*length, length, True):
                with self.subTest(source=name, value=type(invalid)), self.assertRaises(TypeError):
                    decode_native_subject(**{name: invalid})

    def test_face_slot_range_and_type_are_checked_even_without_face_bytes(self):
        for invalid in (-1, 5, 2**32):
            with self.subTest(index=invalid), self.assertRaises(ValueError):
                decode_native_subject(face_group_index=invalid)
        for invalid in (False, True, 0.0, "0", None):
            with self.subTest(index=invalid), self.assertRaises(TypeError):
                decode_native_subject(face_group_index=invalid)

    def test_positive_sizes_valid_quality_and_three_sources_do_not_enable_geometry(self):
        face = bytearray(0x9C)
        struct.pack_into("<4I", face, 0, 0, 0, 80, 80)
        struct.pack_into("<I", face, 0x24, 1234)
        struct.pack_into("<I", face, 0x2C, 80)
        face[0x30] = 1
        aat = struct.pack("<I8i4B", 0xFFFFFFFF, 1, 2, 80, 80, 3, 4, 80, 80, 1, 1, 100, 0)
        model = bytearray(0x2C)
        struct.pack_into("<4Hi2B", model, 0, 10, 20, 80, 80, 0, 100, 100)
        data = decode_native_subject(face_group=bytes(face), aat_publication=aat, aat_model=bytes(model))
        self.assert_untrusted(data)
        self.assertEqual(json.loads(json.dumps(data)), data)

    def test_u32_face_boundaries_and_i32_model_angle_are_not_clamped(self):
        for value in (0, 0x80000000, 0xFFFFFFFF):
            face = bytearray(0x9C)
            struct.pack_into("<I", face, 0x2C, value)
            data = decode_native_subject(face_group=bytes(face))
            self.assertEqual(data["face_group"]["raw"]["size"], value)
            self.assert_untrusted(data)
        for value in (-2147483648, -1, 0, 2147483647):
            model = bytearray(0x2C)
            struct.pack_into("<i", model, 8, value)
            self.assertEqual(decode_native_subject(aat_model=bytes(model))["aat_model"]["raw"]["native_angle"], value)

    def test_results_are_independent_and_full_unparsed_bytes_are_retained(self):
        face = bytes([0x80] * 0x9C)
        first = decode_native_subject(face_group=face)
        first["geometry"]["flags"]["scale_valid"] = True
        first["face_group"]["raw"]["primary_xy"][0] = 0
        first["face_group"]["field_layout"]["size"]["offset"] = 0
        again = decode_native_subject(face_group=face)
        self.assert_untrusted(again)
        self.assertEqual(again["face_group"]["raw"]["primary_xy"], [-2139062144, -2139062144])
        self.assertEqual(again["face_group"]["field_layout"]["size"]["offset"], 0x2C)
        self.assertEqual(bytes.fromhex(again["face_group"]["bytes_hex"]), face)


if __name__ == "__main__":
    unittest.main()
