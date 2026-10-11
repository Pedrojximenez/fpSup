"""Decode offline SIGMA fp 5.02 native subject byte slices without camera I/O.

This is a representation decoder, not a native-to-FgSample adapter. Input bytes
do not establish capture provenance, freshness, coherent publication, physical
scale, identity continuity, lens state, or optical focus confirmation.

Evidence: fpSup/focus/geometry/NATIVE_INPUT_AUDIT.md and
out/decomp/full/blk_c05.c:131621 (parsed face), :132704 (AAT publication),
:139675/:139713 (tracker model), and :139893 (tracker quality fields).
All offsets are relative to the supplied slice and all integers little endian.
"""

from __future__ import annotations

import struct


SCHEMA = "sigma-fp-subject-observation/v1"
FACE_GROUP_BYTES = 0x9C
AAT_PUBLICATION_BYTES = 0x28
AAT_MODEL_BYTES = 0x2C

# name -> (offset, primitive type, count, static source description)
# Keep the two face coordinate tuples distinct: only +00/+04 pass through the
# mode-dependent C05A9AF0 transform; copied size is not proven size/320.
_FACE_FIELDS = {
    "primary_xy": (0x00, "i32", 2, "C05A9AF0/C05BAC90 signed coordinate path; conversion may be bypassed"),
    "primary_size": (0x08, "u32", 2, "C05AAFF8 copies P+10 to G+08/+0C"),
    "detector_xy": (0x10, "i32", 2, "C05AAFF8: P center minus half P+10 size; can be negative"),
    "detector_size": (0x18, "u32", 2, "C05AAFF8 copies P+10 to G+18/+1C"),
    "native_angle": (0x20, "u16", 1, "C05AAFF8 copies P+18 u16; not a verified yaw angle"),
    "native_tracking_id": (0x24, "u32", 1, "C05AAFF8 copies P+1C to G+24, not G+34"),
    "native_score": (0x28, "u32", 1, "C05AAFF8 copies P+14; not geometry confidence"),
    "size": (0x2C, "u32", 1, "C05AAFF8 copies raw square P+10 size"),
    "parsed_valid": (0x30, "byte", 1, "C05AAFF8 parsed-result flag, not physical-scale validity"),
}

_AAT_PUBLICATION_FIELDS = {
    "path_count": (0x00, "u32", 1, "M+3DC path counter conditionally copied to M+340; not frame ID"),
    "result_xywh": (0x04, "i32", 4, "M+344..350 from GetResult; backend can provide a fixed box"),
    "af_input_xywh": (0x14, "i32", 4, "M+354..360; C02763C0 consumes this before AF reshape"),
    "valid": (0x24, "byte", 1, "M+364; C02761C8 checks published S+5D8"),
    "ever_found": (0x25, "byte", 1, "M+365 from AAT found-history flag"),
    "quality": (0x26, "byte", 1, "M+366; one C02761C8 gate is >19, not the complete adoption decision"),
    "additional_result": (0x27, "byte", 1, "M+367 from GetResult+11; preserve without added interpretation"),
}

_AAT_MODEL_FIELDS = {
    "center_xy": (0x00, "u16", 2, "C05B7880 writes center; C05B7968 reads unsigned coordinates"),
    "semi_axes": (0x04, "u16", 2, "C05B7880/C05B2DC0 model semi-axes; not physical object depth"),
    "native_angle": (0x08, "i32", 1, "C05B7968 reads signed 32-bit model angle, not pose/yaw"),
    "hits_mapped_quality": (0x0C, "byte", 1, "C05B7D98 maps global hits to a byte; not raw hits or scale reliability"),
    "semi_axes_area_ratio": (0x0D, "byte", 1, "C05B7D98: semi_axis_0*semi_axis_1*100/maxAxis^2; not hit density"),
}

_FORMATS = {"u32": "I", "i32": "i", "u16": "H", "byte": "B"}


def _validate_blob(name: str, blob: bytes | None, length: int) -> None:
    if blob is None:
        return
    if type(blob) is not bytes:
        raise TypeError(f"{name} must be immutable bytes or None")
    if len(blob) != length:
        raise ValueError(f"{name} must contain exactly {length:#x} bytes, got {len(blob):#x}")


def _block(blob: bytes, fields: dict, source: dict, limitations: list[str]) -> dict:
    raw = {}
    layout = {}
    for name, (offset, kind, count, evidence) in fields.items():
        values = struct.unpack_from("<" + _FORMATS[kind] * count, blob, offset)
        raw[name] = values[0] if count == 1 else list(values)
        layout[name] = {
            "offset": offset,
            "type": kind,
            "count": count,
            "source": evidence,
        }
    return {
        "source": source,
        "raw": raw,
        "field_layout": layout,
        "bytes_hex": blob.hex(),
        "coordinate_reference": None,
        "source_completion_epoch": None,
        "geometry_eligible": False,
        "limitations": limitations,
    }


def decode_native_subject(
    *,
    face_group: bytes | None = None,
    aat_publication: bytes | None = None,
    aat_model: bytes | None = None,
    face_group_index: int = 0,
) -> dict:
    """Decode exact byte slices, retaining unknowns and all original bytes.

    ``face_group`` is one selected parsed 0x9c group, not an entire manager or
    raw 0x20 ISP record. ``face_group_index`` is its native slot (0..4), not a
    stable target ID. ``aat_publication`` is the 0x28 status block at C3033E00;
    ``aat_model`` is the 0x2c structure at C37CDFA8 itself, not a pointer cell.

    Incorrect types/lengths/slot ranges raise before any result is produced.
    Integer values are preserved without clamping or interpreting dimensions,
    validity, or quality as trustworthy physical scale. No I/O is performed.
    """
    if type(face_group_index) is not int:
        raise TypeError("face_group_index must be an integer slot, not bool")
    if not 0 <= face_group_index < 5:
        raise ValueError("face_group_index must be in the native slot range 0..4")
    _validate_blob("face_group", face_group, FACE_GROUP_BYTES)
    _validate_blob("aat_publication", aat_publication, AAT_PUBLICATION_BYTES)
    _validate_blob("aat_model", aat_model, AAT_MODEL_BYTES)

    out = {
        "schema": SCHEMA,
        "firmware": "SIGMA fp Ver.5.02",
        "byte_order": "little",
        "geometry_eligible": False,
        "face_group": None,
        "aat_publication": None,
        "aat_model": None,
        "geometry": {
            "scale_q16": None,
            "coordinate_reference": None,
            "target_generation": None,
            "context_generation": None,
            "scale_generation": None,
            "source_sequence": None,
            "source_completion_epoch": None,
            "exposure_sequence": None,
            "projection_stable": None,
            "lens_stationary": None,
            "lens_position": None,
            "optical_anchor": None,
            "focus_event_sequence": None,
            "flags": {
                "scale_valid": False,
                "identity_valid": False,
                "time_valid": False,
                "projection_stable": False,
                "lens_stationary": False,
                "aat_scale_validated": False,
            },
            "motion_authorized": False,
        },
    }
    if face_group is not None:
        manager_offset = 0x10 + face_group_index * FACE_GROUP_BYTES
        out["face_group"] = _block(face_group, _FACE_FIELDS, {
            "kind": "parsed_face_group",
            "address": f"0x{0xC37CCA9C + manager_offset:08X}",
            "manager_address": "0xC37CCA9C",
            "manager_offset": manager_offset,
            "group_index": face_group_index,
            "length_bytes": FACE_GROUP_BYTES,
            "producer": "C05AAFF8",
        }, [
            "Native slot and tracking ID do not establish persistent target identity.",
            "Only primary x/y undergo a mode-dependent transform; reference/crop is unavailable.",
            "Native angle is not verified yaw; native score/valid do not establish geometric reliability.",
            "Eye subrecords and uninterpreted bytes remain preserved only in bytes_hex.",
        ])
    if aat_publication is not None:
        out["aat_publication"] = _block(aat_publication, _AAT_PUBLICATION_FIELDS, {
            "kind": "aat_status_publication",
            "address": "0xC3033E00",
            "status_address": "0xC303384C",
            "status_offset": 0x5B4,
            "manager_address": "0xC37CCA9C",
            "manager_offset": 0x340,
            "length_bytes": AAT_PUBLICATION_BYTES,
            "producer": "C05AC690 -> C05A9900",
        }, [
            "path_count is a conditionally copied AAT path counter, not exposure or frame identity.",
            "The two signed rectangles are distinct; af_input_xywh precedes AF output reshape.",
            "Positive dimensions, valid, ever_found, and quality do not prove physical scale or actual AF adoption.",
        ])
    if aat_model is not None:
        out["aat_model"] = _block(aat_model, _AAT_MODEL_FIELDS, {
            "kind": "aat_color_tracker_model",
            "address": "0xC37CDFA8",
            "length_bytes": AAT_MODEL_BYTES,
            "producer": "C05B6CF8; field writers C05B7880/C05B2DC0/C05B7D98",
        }, [
            "Model semi-axes adapt and can differ from GetResult, search-window, and adopted AF ROI dimensions.",
            "hits_mapped_quality is not raw hits or geometric reliability; semi_axes_area_ratio is not hit density.",
            "Model angle is not subject pose; no depth, normalized size, or AAT scale-validation flag is inferred.",
        ])
    return out
