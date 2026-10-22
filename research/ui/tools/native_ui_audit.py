#!/usr/bin/env python3
"""Read-only, pinned-firmware audit of the stock MainB2 CINE menu.

This is an evidence extractor, not a firmware builder or runtime adapter.
Only the explicitly supplied input file is opened; JSON is written to stdout.
"""

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
import sys


SEG0_SHA256 = "aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622"
SEG0_SIZE = 49_245_696
BASE = 0xC0000000
NBU = 0x18C0460
POOL = 0x18C0474
POOL_END = 0x18EB48C
PAGE_START = 0x2030364
PAGE_END = 0x2055DB0
PAGE_SHA256 = "10ed690e589bf7899ca022a3f108116d6a25ff9579081cd637e6ba8bcc99bc41"
DONOR_START = 0x204DACA
DONOR_END = 0x205460A
DONOR_SHA256 = "006113cce5bb460973e5934e02e1fe8d3d32c7fb325160cd8bbd46abd3cf3fb3"
HEADER_SHA256 = "4ffde39e76ffc7ee23933b0b84416e688a1f10866ba4889544894e0f1a82bf8c"
MODE_CHANGE = 0x20318F7
B2_OBJECT = 0x2037C1B
INDEX_ENTRY = 0x18EC77C
COMPONENT_TAGS = frozenset((0x10004, 0x10005, 0x10006, 0x10007,
                            0x10008, 0x10009, 0x1000A, 0x1000D, 0x1000E))


class AuditError(ValueError):
    """Input does not satisfy the pinned, known-format audit contract."""


def require(condition, message):
    if not condition:
        raise AuditError(message)


def u32(data, offset):
    require(0 <= offset <= len(data) - 4, "u32 read outside buffer")
    return struct.unpack_from(">I", data, offset)[0]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def address(offset):
    return "0x%08X" % (BASE + offset)


def fingerprint(data, start, end):
    require(0 <= start <= end <= len(data), "fingerprint range outside input")
    return {"address": address(start), "end_exclusive": address(end),
            "file_offset": start, "length": end - start,
            "sha256": sha256(data[start:end])}


@dataclass(frozen=True)
class Record:
    offset: int
    data: bytes

    @property
    def tag(self):
        return u32(self.data, 0)

    def word(self, offset):
        return u32(self.data, offset)


def records(data, start, end):
    require(0 <= start <= end <= len(data), "record region outside input")
    result = []
    offset = start
    while offset < end:
        require(end - offset >= 8, "truncated record header")
        size = u32(data, offset + 4)
        require(8 <= size <= end - offset, "invalid or truncated record size")
        result.append(Record(offset, data[offset:offset + size]))
        offset += size
    return result


def pool_string(data, offset):
    start = POOL + offset
    require(POOL <= start < POOL_END <= len(data), "string reference outside pool")
    end = data.find(b"\0", start, POOL_END)
    require(end >= start, "unterminated pool string")
    try:
        return data[start:end].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AuditError("invalid pool UTF-8") from exc


def parse_header(record, resolve):
    require(record.tag == 0x10002, "expected page allocation header")
    data = record.data
    require(len(data) >= 20, "truncated allocation header")
    cursor = 20

    def vector(count, width=1):
        nonlocal cursor
        require(count * width <= (len(data) - cursor) // 4,
                "allocation vector exceeds header")
        rows = [[u32(data, cursor + 4 * (i * width + j)) for j in range(width)]
                for i in range(count)]
        cursor += count * width * 4
        return rows if width != 1 else [row[0] for row in rows]

    def counted(width=1):
        nonlocal cursor
        count = u32(data, cursor)
        cursor += 4
        return vector(count, width)

    components = {}
    for name, count in vector(u32(data, 16), 2):
        name = resolve(name)
        require(name not in components, "duplicate component budget kind")
        components[name] = count
    result = {"objects": u32(data, 8), "special_objects": u32(data, 12),
              "component_counts": components, "groups": counted(3),
              "clip_property_counts": counted(), "property_key_counts": counted(),
              "trailing_budget": counted()}
    require(cursor == len(data), "unconsumed allocation header bytes")
    return result


def parse_objects(items, resolve):
    result = {}
    for record in items:
        if record.tag != 0x10003:
            continue
        require(len(record.data) == 36, "unexpected object record size")
        object_id = record.word(20)
        require(object_id not in result, "duplicate object ID")
        result[object_id] = {"id": object_id, "parent_id": record.word(24),
                             "name": resolve(record.word(28)),
                             "child_count": record.word(16),
                             "address": address(record.offset)}
    return result


def parse_clip(record, resolve):
    require(record.tag == 0x1000A and len(record.data) >= 28,
            "expected animation clip")
    cursor = 28
    properties = []
    for _ in range(record.word(12)):
        require(cursor + 20 <= len(record.data), "truncated clip property")
        count, kind, component, name, dimension = struct.unpack_from(">5I", record.data, cursor)
        require(kind in (0, 1, 2), "unsupported clip property type")
        require(0 < count <= (len(record.data) - cursor - 20) // 10,
                "truncated clip keys")
        keys = []
        for index in range(count):
            offset = cursor + 20 + index * 10
            a, b = record.data[offset:offset + 2]
            require(a <= 1 and b <= 1, "unsupported tangent-bearing clip key")
            raw = record.word(offset + 6)
            value = struct.unpack_from(">f", record.data, offset + 6)[0] if kind == 1 else raw
            keys.append({"time": record.word(offset + 2), "value": value})
        properties.append({"name": resolve(name), "component_ref": component,
                           "kind": kind, "dimension": dimension, "keys": keys})
        cursor += 20 + count * 10
    require(cursor == len(record.data), "unconsumed animation clip bytes")
    return {"owner_id": record.word(20), "clip_id": record.word(24),
            "address": address(record.offset), "properties": properties}


def parse_mode_change(record):
    require(record.tag == 0x1000B, "expected animation group")
    states, transitions, count = (record.word(8), record.word(12), record.word(16))
    require(states == 2 and transitions == 0, "unexpected ModeChange state layout")
    cursor = 28 + states * 21
    require(cursor + count * 8 + 8 == len(record.data), "unexpected ModeChange size")
    return [[record.word(cursor + i * 8), record.word(cursor + i * 8 + 4)]
            for i in range(count)]


def component_counts(items, resolve):
    return dict(sorted(Counter(resolve(item.word(8)) for item in items
                               if item.tag in COMPONENT_TAGS).items()))


def audit_bytes(data):
    require(len(data) == SEG0_SIZE, "input is not the pinned seg0 size")
    require(sha256(data) == SEG0_SHA256, "input SHA-256 does not match pinned seg0")
    resolve = lambda offset: pool_string(data, offset)
    require(resolve(u32(data, INDEX_ENTRY + 4)) == "MainB2", "index name mismatch")
    require(NBU + u32(data, INDEX_ENTRY + 12) == PAGE_START, "index page offset mismatch")
    page = records(data, PAGE_START, PAGE_END)
    by_offset = {item.offset: item for item in page}
    page_fp = fingerprint(data, PAGE_START, PAGE_END)
    donor_fp = fingerprint(data, DONOR_START, DONOR_END)
    header_fp = fingerprint(data, PAGE_START, PAGE_START + len(page[0].data))
    require(page_fp["sha256"] == PAGE_SHA256, "MainB2 page hash mismatch")
    require(donor_fp["sha256"] == DONOR_SHA256, "Audio donor hash mismatch")
    require(header_fp["sha256"] == HEADER_SHA256, "allocation header hash mismatch")
    require(DONOR_START in by_offset and DONOR_END in by_offset, "donor boundary not a record")
    header = parse_header(page[0], resolve)
    objects = parse_objects(page, resolve)
    root = objects[by_offset[B2_OBJECT].word(20)]
    require((root["id"], root["parent_id"], root["name"], root["child_count"]) ==
            (116, 130, "B2", 6), "B2 object identity mismatch")
    children = [obj for obj in objects.values() if obj["parent_id"] == 116]
    require(len(children) == root["child_count"], "B2 child count mismatch")
    require(len(objects) == header["objects"], "object allocation count mismatch")
    groups = [item for item in page if item.tag == 0x1000B]
    require(len(groups) == len(header["groups"]), "group allocation count mismatch")
    group_index = next(i for i, item in enumerate(groups) if item.offset == MODE_CHANGE)
    mode = by_offset[MODE_CHANGE]
    require(resolve(mode.word(20)) == "ModeChange", "ModeChange name mismatch")
    references = parse_mode_change(mode)
    clips = [parse_clip(item, resolve) for item in page if item.tag == 0x1000A]
    clip_lookup = {(clip["owner_id"], clip["clip_id"]): clip for clip in clips}
    require(len(clip_lookup) == len(clips), "duplicate owner/clip IDs")
    cine_rows = []
    for object_id, clip_id in references:
        require((object_id, clip_id) in clip_lookup, "unresolved ModeChange clip")
        clip = clip_lookup[object_id, clip_id]
        visibility = next((p for p in clip["properties"] if p["name"] == "is-visible"), None)
        require(visibility is not None, "ModeChange row lacks visibility property")
        visibility_keys = {key["time"]: key["value"] for key in visibility["keys"]}
        if visibility_keys.get(0) == 0 and visibility_keys.get(66) == 1:
            y = next((p for p in clip["properties"]
                      if p["name"] == "position" and p["dimension"] == 1), None)
            cine_rows.append({**objects[object_id], "mode_clip_id": clip_id,
                              "mode_clip_address": clip["address"],
                              "visibility_keys": visibility["keys"],
                              "modechange_y_keys": y["keys"] if y else None})
    require([row["id"] for row in cine_rows] == [21878, 121, 122], "CINE row mapping mismatch")
    donor = [item for item in page if DONOR_START <= item.offset < DONOR_END]
    donor_objects = parse_objects(donor, resolve)
    donor_clips = [parse_clip(item, resolve) for item in donor if item.tag == 0x1000A]
    group_indexes = [i for i, item in enumerate(groups) if DONOR_START <= item.offset < DONOR_END]
    property_counts = [len(clip["properties"]) for clip in donor_clips]
    key_counts = [len(prop["keys"]) for clip in donor_clips for prop in clip["properties"]]
    delta = {"objects": len(donor_objects), "component_counts": component_counts(donor, resolve),
             "source_group_budget_indexes": group_indexes,
             "group_budgets": [header["groups"][i] for i in group_indexes],
             "clip_property_counts": property_counts, "property_key_counts": key_counts}
    added_header_bytes = 12 * len(group_indexes) + 4 * len(property_counts) + 4 * len(key_counts)
    return {
        "schema_version": 1, "kind": "read_only_native_menu_evidence",
        "input": {"sha256": SEG0_SHA256, "length": len(data)},
        "readiness": {"fourth_row_connected": False, "deployable_firmware": False,
                      "free_ids_determined": False, "private_binding_ready": False,
                      "runtime_hook_ready": False, "navigation_verified": False},
        "page": {**page_fp, "name": "MainB2", "record_count": len(page),
                 "record_tag_counts": {"0x%08X" % tag: count for tag, count in
                                       sorted(Counter(item.tag for item in page).items())},
                 "object_count": len(objects), "serialized_clip_count": len(clips),
                 "serialized_property_count": sum(len(c["properties"]) for c in clips)},
        "b2_root": {**root, "direct_children": children}, "cine_rows": cine_rows,
        "mode_change": {**fingerprint(data, mode.offset, mode.offset + len(mode.data)),
                        "group_budget_index": group_index, "references": references,
                        "actual_clip_references": len(references),
                        "allocation_budget": header["groups"][group_index],
                        "unused_clip_reference_capacity": header["groups"][group_index][2] - len(references)},
        "allocation_header": {**header_fp, **header},
        "audio_donor": {**donor_fp, "record_count": len(donor),
                        "objects": list(donor_objects.values()),
                        "widget_kind": "MenuItem_SelectJump", "is_pure_toggle": False,
                        "allocation_delta_for_unmodified_full_clone": delta},
        "hypothetical_full_clone_budget_only": {
            "not_a_transform_or_deployment_plan": True,
            "preserve_all_original_budgets": True,
            "header_length": len(page[0].data) + added_header_bytes,
            "objects": header["objects"] + len(donor_objects),
            "groups": len(header["groups"]) + len(group_indexes),
            "clip_budget_entries": len(header["clip_property_counts"]) + len(property_counts),
            "property_budget_entries": len(header["property_key_counts"]) + len(key_counts)},
        "hard_gates": [
            "Audio donor still targets MV_AudioRecord, B2_6, and SUB_MV_AudioRecord; it cannot be installed as-is.",
            "Schema-aware object/reference remapping and private variable creation remain unimplemented.",
            "A copied row does not establish native focus navigation or attach/detach lifetime safety.",
            "The existing 512-byte record-copy path does not implement page expansion or header rebuilding.",
            "No camera, USB, runtime hooks, allocator calls, or firmware writes are performed by this audit."
        ]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seg0", required=True, type=Path,
                        help="explicit local seg0 input; exact SHA-256 is required")
    args = parser.parse_args(argv)
    try:
        with args.seg0.open("rb") as source:
            data = source.read(SEG0_SIZE + 1)
        result = audit_bytes(data)
        result["input"]["path"] = str(args.seg0.resolve())
    except (OSError, AuditError) as exc:
        print("audit failed: %s" % exc, file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
