#!/usr/bin/env python3
"""The NBU resource format, in pure Python -- no emulator, no camera.

This is the authoring half.  `nbu_probe.py` runs the camera's own interpreter and
is what PROVES this decoder right; nothing here imports unicorn, so a build tool
can use it on its own.

Everything below was established by executing FUN_c05e6400 over
out/seg0_c0000000.bin and checking the result against the hand analysis:

  * Tokens are BIG-ENDIAN u32.  The context's reader (0xC05E5DB8) is a
    byte-swapping 32-bit load at ctx+0x24 + ctx+0x04.

  * EVERY record is `{u32 tag, u32 size, body...}` and `size` counts the tag and
    the size word.  1391 of 1391 records of MainB2 match, and the run ends on
    `FFFFFFFF 00000008`.  Record sizes are byte-granular, not word-granular --
    the reader can take single bytes -- so a record body must not be walked as
    words without knowing its tag.

  * A container (`NBU\\0`) is magic, version, one spare word, then records.
    A resource SET has no magic: it starts at its first record.

Because the records are length-delimited, splitting, reordering, replacing and
re-emitting a set needs no per-tag grammar at all.  That is what makes real
editing possible instead of another hook.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

MAGIC = b"NBU\x00"
TERMINATOR = 0xFFFFFFFF
HEADER = 8                      # tag + size

# Tag catalogue.  "case N" is the arm of the switch in FUN_c05e6400 at
# 0xC05E6460; N = tag - 0x10001.  Counts are MainB2's, from the emulated walk.
TAGS = {
    0x00010001: ("set index", "case 0: the container's table of resource sets. "
                 "Name, count, then count entries of 4 tokens (+4 floats when the "
                 "version is above 0x105FFFF), each becoming a 0x2C-byte row "
                 "{fnv, name, offset, ...}", "top level only"),
    0x00010002: ("allocation header", "case 1: object counts and the per-class "
                 "instance table that sizes the arena. objects, a second count "
                 "used only when app+0x890 is set, class count, then {name "
                 "offset, count} pairs, then further sizing loops", 1),
    0x00010003: ("object", "case 2: six tokens (+1 above version 0x105FFFF), then "
                 "FUN_c05cf808 builds the object; parent 0 makes it the root. "
                 "Their number equals the allocation header's objectBase count", 193),
    0x00010004: ("value/binding", "case 3 -> FUN_c05e8070", 199),
    0x00010005: ("property + animation", "case 4: name, key count, group name, "
                 "owner, flags; FUN_c05e8028 creates it, then the animation keys "
                 "are read through FUN_c05e7b60/FUN_c05e7b78", 120),
    0x00010006: ("property", "case 5: like 0x10005 with an extra value token", 209),
    0x00010007: ("property (layout)", "case 6", 1),
    0x00010008: ("property + key list", "case 7: also reads a nested key list", 0),
    0x00010009: ("property (short)", "case 8: two pool strings, no construction "
                 "call of its own", 430),
    0x0001000A: ("resource reference", "case 9: one pool string, FUN_c05d9e80", 159),
    0x0001000B: ("IMAGE ARRAY", "case 10 -- the image-array builder of "
                 "research/ui/README.md 5c. Confirmed by execution: this is the "
                 "only tag that calls FUN_c05e2988 (image_container_new). A new "
                 "UI state has to be added HERE and in every companion property", 52),
    0x0001000C: ("value/binding", "case 0xb -> FUN_c05e8070", 0),
    0x0001000D: ("unknown", "case 0xc", 0),
    0x0001000E: ("value/binding", "case 0xd -> FUN_c05e8070", 20),
    0x00011001: ("table", "0x110xx family: a block the interpreter allocates and "
                 "copies wholesale", 1),
    0x00011003: ("table", "0x110xx family", 1),
    0x00011004: ("table", "0x110xx family", 1),
    0x00011005: ("table", "0x110xx family", 1),
    0x00011006: ("table", "0x110xx family", 1),
    0x00011008: ("table", "0x110xx family", 1),
    0x00011009: ("table", "0x110xx family", 1),
    TERMINATOR: ("end", "eight bytes: FFFFFFFF 00000008. The interpreter returns "
                 "1 and the caller's loop stops", 1),
}


class FormatError(ValueError):
    pass


@dataclass
class Record:
    tag: int
    offset: int                 # from the start of the buffer it was split from
    body: bytes                 # without the tag and size words

    @property
    def size(self) -> int:
        return HEADER + len(self.body)

    @property
    def kind(self) -> str:
        return TAGS.get(self.tag, ("unknown", "", 0))[0]

    def to_bytes(self) -> bytes:
        return struct.pack(">II", self.tag, self.size) + self.body

    def words(self, count: int, at: int = 0) -> tuple:
        """Big-endian words out of the body; only safe where the tag says so."""
        if at + count * 4 > len(self.body):
            raise FormatError("read past the end of the record body")
        return struct.unpack_from(">%dI" % count, self.body, at)


def split(data: bytes, offset: int = 0, limit: int = 100_000) -> list[Record]:
    """Split a resource set into records, ending at the terminator.

    Refuses anything that does not close exactly: a size of 0, a size that runs
    past the buffer, or running out of data before the terminator.  Getting this
    wrong silently is how a record stream desynchronises, so it raises instead.
    """
    out: list[Record] = []
    while len(out) < limit:
        if offset + HEADER > len(data):
            raise FormatError(f"ran out of data at 0x{offset:X} with no terminator")
        tag, size = struct.unpack_from(">II", data, offset)
        if size < HEADER or offset + size > len(data):
            raise FormatError(f"record at 0x{offset:X} has an impossible size {size}")
        out.append(Record(tag, offset, data[offset + HEADER:offset + size]))
        offset += size
        if tag == TERMINATOR:
            return out
    raise FormatError(f"no terminator within {limit} records")


def join(records: list[Record]) -> bytes:
    """Re-emit records as a resource set.  `size` is recomputed from the body,
    so editing a body is enough -- there is no separate length to keep in sync."""
    return b"".join(record.to_bytes() for record in records)


def container(records: list[Record], version: int = 0x01090000) -> bytes:
    """Wrap records as a top-level NBU container."""
    return MAGIC + struct.pack(">II", version, 0) + join(records)


def split_container(data: bytes) -> tuple[int, list[Record]]:
    if data[:4] != MAGIC:
        raise FormatError("not an NBU container")
    version, _spare = struct.unpack_from(">II", data, 4)
    return version, split(data, 12)


def allocation_header(record: Record, pool: bytes) -> dict:
    """Decode a tag-0x10002 record.  `pool` is the string-pool bytes."""
    if record.tag != 0x00010002:
        raise FormatError(f"tag {record.tag:#x} is not an allocation header")
    objects, second, classes = record.words(3)
    pairs = record.words(classes * 2, at=12)
    return {"objects": objects, "second": second,
            "classes": [(string_at(pool, pairs[i * 2]), pairs[i * 2 + 1])
                        for i in range(classes)]}


class Reader:
    """Byte-granular big-endian reader, the shape the context's own four reader
    methods give the interpreter (word, signed byte, block, skip)."""

    def __init__(self, body: bytes) -> None:
        self.body, self.at = body, 0

    def u32(self) -> int:
        value = struct.unpack_from(">I", self.body, self.at)[0]
        self.at += 4
        return value

    def u8(self) -> int:
        value = self.body[self.at]
        self.at += 1
        return value

    @property
    def left(self) -> int:
        return len(self.body) - self.at


def decode_image_array(record: Record, pool: bytes, version: int = 0x01090000) -> dict:
    """Decode a tag-0x1000B record: the image array, case 10 of FUN_c05e6400.

        u32 nA, u32 nB, u32 nC, u32 group name, u32 owner
        nA x { u32 resource name, u32 a, u32 b, u32 c,
               u32 d (version > 0x10800FF), u8 e }      <- one per UI STATE
        nB x { u32 name, u32 value, u8 flag, u32 extra if flag }
        nC x { u32, u32 }
        u32 name2   (version > 0x102FFFF)
        u32 tail    (version > 0x105FFFF)

    `entries` is the ordered list a widget indexes by state, so ADDING A UI
    STATE means nA += 1 and one more entry -- and every companion property
    record has to gain the matching state as well.
    """
    if record.tag != 0x0001000B:
        raise FormatError(f"tag {record.tag:#x} is not an image array")
    r = Reader(record.body)
    count_a, count_b, count_c = r.u32(), r.u32(), r.u32()
    group = string_at(pool, r.u32())
    owner = r.u32()
    entries = []
    for _ in range(count_a):
        name = string_at(pool, r.u32())
        a, b, c = r.u32(), r.u32(), r.u32()
        d = r.u32() if version > 0x010800FF else None
        e = r.u8() if version > 0x010800FF else None
        entries.append({"name": name, "a": a, "b": b, "c": c, "d": d, "e": e})
    extras = []
    for _ in range(count_b):
        name = string_at(pool, r.u32())
        value = r.u32()
        flag = r.u8()
        extra = r.u32() if flag else None
        extras.append({"name": name, "value": value, "flag": flag, "extra": extra})
    pairs = [(r.u32(), r.u32()) for _ in range(count_c)]
    name2 = string_at(pool, r.u32()) if version > 0x0102FFFF else None
    tail = r.u32() if version > 0x0105FFFF else None
    if r.left:
        raise FormatError(f"image array at +0x{record.offset:X}: {r.left} bytes left over")
    return {"group": group, "owner": owner, "entries": entries, "extras": extras,
            "pairs": pairs, "name2": name2, "tail": tail}


def string_at(pool: bytes, offset: int) -> str | None:
    if offset == TERMINATOR or offset >= len(pool):
        return None
    end = pool.find(b"\0", offset)
    if end < 0:
        return None
    try:
        return pool[offset:end].decode("ascii")
    except UnicodeDecodeError:
        return None


def controller_maxima(records: list[Record], base: int) -> list[dict]:
    """Every tag-0x1000E record whose word at record+32 is a small whole float.

    That word is the controller maximum a list obeys: `rows - 1`, big-endian.
    A CSV row that is drawn but cannot be selected is this word not matching --
    FP3K hit it, and so did we.  Verified: 0xC1A709BC is 1.0 (the two-row
    Resolution list) and 0xC1A690D7 is 2.0 (the three-row bit-depth list).

    The same row count appears several times in a set, because a list has
    _excl variants and CINE/STILL copies -- changing one may not be enough.
    """
    out = []
    for index, record in enumerate(records):
        if record.tag != 0x0001000E or len(record.body) < 28:
            continue
        value = struct.unpack_from(">f", record.body, 24)[0]
        if value != int(value) or not 0.0 < value <= 64.0:
            continue
        out.append({"index": index, "record": base + record.offset,
                    "address": base + record.offset + 32,
                    "max": value, "rows": int(value) + 1})
    return out


def tally(records: list[Record]) -> dict:
    counts: dict[int, int] = {}
    for record in records:
        counts[record.tag] = counts.get(record.tag, 0) + 1
    return counts


# --- a thin CLI over the whole UI, with no emulator in sight ---------------

def _paths():
    from pathlib import Path
    here = Path(__file__).resolve().parent           # research/ui/tools/nbu_probe
    return here.parents[1] / "nbu_sets.json", here.parents[3] / "out" / "seg0_c0000000.bin"


def load_sets():
    """(image bytes, image base, [{name, address}]) from research/ui/nbu_sets.json."""
    import json
    from pathlib import Path
    sets_path, image_path = _paths()
    if not sets_path.exists():
        raise FormatError(f"{sets_path} is missing; regenerate it with "
                          "nbu_probe.py index --json ../../nbu_sets.json")
    data = json.loads(Path(sets_path).read_text())
    rows = sorted(({"name": s["name"], "address": int(s["address"], 16)}
                   for s in data["sets"]), key=lambda r: r["address"])
    pool = data["pool"]
    return Path(image_path).read_bytes(), 0xC0000000, rows, (int(pool["base"], 16), pool["size"])


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sweep = sub.add_parser("sweep", help="split every resource set and tally the tags")
    maxima = sub.add_parser("maxima", help="the controller maxima in a set (rows - 1)")
    maxima.add_argument("name")
    maxima.add_argument("--rows", type=int, help="only lists of this many rows")
    group = sub.add_parser("group", help="every record that names a group, per set")
    group.add_argument("name")
    records = sub.add_parser("records", help="list one set's records")
    records.add_argument("name")
    records.add_argument("--tag", help="only this tag, e.g. 0x1000B")
    args = parser.parse_args(argv)

    image, base, rows, (pool_base, pool_size) = load_sets()
    pool = image[pool_base - base:pool_base - base + pool_size]

    if args.command == "sweep":
        counts: dict[int, int] = {}
        total = closed = 0
        for index, row in enumerate(rows):
            parsed = split(image[row["address"] - base:])
            end = row["address"] + sum(r.size for r in parsed)
            total += len(parsed)
            for record in parsed:
                counts[record.tag] = counts.get(record.tag, 0) + 1
            if index + 1 < len(rows) and end == rows[index + 1]["address"]:
                closed += 1
        print(f"{len(rows)} sets, {total} records")
        print(f"{closed} of {len(rows) - 1} sets end exactly where the next begins")
        for tag in sorted(counts):
            print(f"  0x{tag:08X}  x{counts[tag]:<6d} {TAGS.get(tag, ('?', ))[0]}")
        return 0

    if args.command == "maxima":
        row = next((r for r in rows if r["name"] == args.name), None)
        if row is None:
            print(f"no resource set named {args.name!r}")
            return 1
        parsed = split(image[row["address"] - base:])
        found = controller_maxima(parsed, row["address"])
        if args.rows:
            found = [f for f in found if f["rows"] == args.rows]
        for f in found:
            print(f"  #{f['index']:<5d} record 0x{f['record']:08X}  "
                  f"max {f['max']:.1f} -> {f['rows']} rows   "
                  f"write the float at 0x{f['address']:08X}")
        print(f"-- {len(found)} controller maxima in {args.name}"
              + (f" with {args.rows} rows" if args.rows else ""))
        print("-- the same row count repeats: _excl variants and CINE/STILL copies")
        return 0

    if args.command == "group":
        needle = b"\0" + args.name.encode() + b"\0"
        at = pool_base_offset = pool.find(needle)
        if at < 0:
            print(f"{args.name!r} is not in the string pool")
            return 1
        key = struct.pack(">I", at + 1)
        total = 0
        for row in rows:
            parsed = split(image[row["address"] - base:])
            hits = [r for r in parsed if key in r.body]
            if not hits:
                continue
            total += len(hits)
            kinds: dict[str, int] = {}
            for record in hits:
                kinds[record.kind] = kinds.get(record.kind, 0) + 1
            print(f"{row['name']:<22} {len(hits):>4}  " +
                  ", ".join(f"{k} x{v}" for k, v in sorted(kinds.items())))
        print(f"-- {total} records name {args.name}")
        return 0

    row = next((r for r in rows if r["name"] == args.name), None)
    if row is None:
        print(f"no resource set named {args.name!r}")
        return 1
    wanted = int(args.tag, 16) if args.tag else None
    parsed = split(image[row["address"] - base:])
    for record in parsed:
        if wanted is not None and record.tag != wanted:
            continue
        print(f"#{parsed.index(record):5d}  0x{row['address'] + record.offset:08X}  "
              f"tag 0x{record.tag:08X}  {record.size:5d} B  {record.kind}")
    if parsed and parsed[0].tag == 0x00010002:
        header = allocation_header(parsed[0], pool)
        print(f"-- {len(parsed)} records; allocation header declares "
              f"{header['objects']} objects across {len(header['classes'])} classes")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
