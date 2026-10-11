#!/usr/bin/env python3
"""Build and validate the small NBR 1.5 resource packs used by the fp GUI.

The pack builder is intentionally project-neutral.  Callers provide named file
payloads and the matching resource plugin; OpenGate, for example, supplies XCI
files and uses the stock ``xcimage`` plugin.

The layout was recovered from SIGMA fp firmware 5.02 and cross-checked by
executing the camera's native NBR parser in the archived FP3K work.  This module
does not write camera memory or modify the stock firmware image.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Iterable


MAGIC = b"NBR\0\x01\x05" + bytes(6)


def fnv1a(value: str) -> int:
    """Return the 32-bit FNV-1a key used by the native resource lookup."""
    out = 0x811C9DC5
    for byte in value.encode("utf-8"):
        out = ((out ^ byte) * 0x01000193) & 0xFFFFFFFF
    return out


@dataclass(frozen=True)
class Resource:
    """One named resource file exposed through an NBR plugin."""

    name: str
    filename: str
    data: bytes
    plugin: str = "xcimage"


def build(resources: Iterable[Resource]) -> bytes:
    """Create a bounded NBR 1.5 pack for ``resources``.

    Names and filenames must be unique.  Empty packs are rejected because the
    camera-side loader has no useful reason to register one.
    """
    resources = tuple(resources)
    if not resources:
        raise ValueError("an NBR pack needs at least one resource")
    names = [resource.name for resource in resources]
    filenames = [resource.filename for resource in resources]
    if len(set(names)) != len(names):
        raise ValueError("duplicate resource name")
    if len(set(filenames)) != len(filenames):
        raise ValueError("duplicate resource filename")
    if any(not resource.data for resource in resources):
        raise ValueError("resource payloads must not be empty")

    pool = bytearray(4)
    offsets: dict[str, int] = {}

    def intern(value: str) -> int:
        if value not in offsets:
            offsets[value] = len(pool)
            pool.extend(value.encode("utf-8") + b"\0")
            pool.extend(bytes((-len(pool)) % 4))
        return offsets[value]

    for resource in resources:
        intern(resource.plugin)
        intern(resource.name)
        intern(resource.filename)

    out = bytearray(MAGIC)
    out.extend(struct.pack(">II", 1, 8 + len(pool)) + pool)

    file_table = len(out)
    out.extend(bytes(12 + 16 * len(resources)))
    file_entries = []
    for resource in resources:
        file_entries.append(
            (fnv1a(resource.filename), intern(resource.filename), len(out), len(resource.data))
        )
        out.extend(resource.data)
        out.extend(bytes((-len(out)) % 4))
    struct.pack_into(">III", out, file_table, 2, len(out) - file_table, len(resources))
    for index, entry in enumerate(sorted(file_entries)):
        struct.pack_into(">4I", out, file_table + 12 + 16 * index, *entry)

    declarations = len(out)
    out.extend(struct.pack(">4I", 0x20001, 16 + 36 * len(resources),
                           len(resources), len(resources)))
    definitions = len(out)
    out.extend(bytes(36 * len(resources)))
    out.extend(struct.pack(">II", 0xFFFFFFFF, 8))

    for index, resource in enumerate(resources):
        property_offset = len(out)
        struct.pack_into(
            ">9I", out, definitions + 36 * index,
            intern(resource.name), intern(resource.plugin), 0, 0xFFFFFFFF, 0, 1,
            0xFFFFFFFF, 0xFFFFFFFF, property_offset,
        )
        out.extend(
            struct.pack(
                ">12I", 0x20002, 48, 5, 0x1F, intern(resource.filename),
                0, 0, 0, 0, 0, 0, 0,
            )
        )
    out.extend(struct.pack(">II", 0xFFFFFFFF, 8))

    # Catch accidental layout drift in the builder itself.
    parsed = inspect(bytes(out))
    if parsed["declarations_offset"] != declarations:
        raise AssertionError("NBR declaration offset changed during construction")
    return bytes(out)


def inspect(pack: bytes) -> dict:
    """Perform structural bounds checks and return a compact pack inventory."""
    if not pack.startswith(MAGIC):
        raise ValueError("not an NBR 1.5 pack")
    if len(pack) < 20:
        raise ValueError("truncated NBR header")

    pool_tag, pool_size = struct.unpack_from(">II", pack, 12)
    if pool_tag != 1 or pool_size < 12 or 12 + pool_size > len(pack):
        raise ValueError("invalid NBR string pool")
    pool_start, pool_end = 20, 12 + pool_size

    def string(offset: int) -> str:
        start = pool_start + offset
        if not pool_start <= start < pool_end:
            raise ValueError("string offset outside NBR pool")
        end = pack.find(b"\0", start, pool_end)
        if end < 0:
            raise ValueError("unterminated NBR string")
        return pack[start:end].decode("utf-8")

    file_table = pool_end
    if file_table + 12 > len(pack):
        raise ValueError("missing NBR file table")
    file_tag, file_size, file_count = struct.unpack_from(">III", pack, file_table)
    if file_tag != 2 or file_size < 12 + 16 * file_count:
        raise ValueError("invalid NBR file table")
    declarations = file_table + file_size
    if declarations + 16 > len(pack):
        raise ValueError("missing NBR declarations")

    files = []
    for index in range(file_count):
        key, name_offset, data_offset, data_size = struct.unpack_from(
            ">4I", pack, file_table + 12 + index * 16
        )
        filename = string(name_offset)
        if key != fnv1a(filename):
            raise ValueError("NBR filename hash mismatch")
        if data_offset + data_size > declarations:
            raise ValueError("NBR file payload outside file block")
        files.append({"filename": filename, "offset": data_offset, "bytes": data_size})
    if [fnv1a(row["filename"]) for row in files] != sorted(
        fnv1a(row["filename"]) for row in files
    ):
        raise ValueError("NBR file table is not FNV-sorted")

    tag, total, resource_count, variant_count = struct.unpack_from(">4I", pack, declarations)
    if tag != 0x20001 or total != 16 + 36 * resource_count:
        raise ValueError("invalid NBR resource declaration block")
    if resource_count != file_count or variant_count != resource_count:
        raise ValueError("NBR resource/file count mismatch")

    resources_out = []
    definition = declarations + 16
    for index in range(resource_count):
        fields = struct.unpack_from(">9I", pack, definition + index * 36)
        name, plugin = string(fields[0]), string(fields[1])
        if fields[5] != 1 or fields[8] + 48 > len(pack):
            raise ValueError("invalid NBR resource variant")
        prop = struct.unpack_from(">12I", pack, fields[8])
        if prop[:4] != (0x20002, 48, 5, 0x1F):
            raise ValueError("invalid NBR resource property record")
        resources_out.append(
            {"name": name, "plugin": plugin, "filename": string(prop[4])}
        )

    return {
        "bytes": len(pack),
        "files": files,
        "resources": resources_out,
        "declarations_offset": declarations,
    }

