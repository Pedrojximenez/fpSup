#!/usr/bin/env python3
"""The stock NBR resource container, and how to replace any resource in it.

This is the hook-free half of "really changing the UI".  Every icon, font,
localisation file and -- the useful part -- every MENU LIST CSV the camera draws
is one entry in one sorted directory.  Repointing an entry is an 8-byte write.

    0xC0D22400  "NBR\\0", version 1.5, spare word, then length-delimited records
                (the same {u32 tag, u32 size, body} shape as the NBU container;
                 nbu_probe/nbu_format.py splits both)

        tag 1        177,572 B  the NAME POOL: 2,260 NUL-separated build paths
        tag 2     11,817,672 B  the DIRECTORY and the data it points at
        tag 0x20001   81,844 B  (not decoded here)
        terminator         8 B

    record 2's body:  u32 count = 2259, then `count` entries of 16 bytes,
                      big-endian, sorted ascending by key:

        +0x00  u32  FNV-1a(path)        the lookup key
        +0x04  u32  path offset in the name pool
        +0x08  u32  data offset FROM 0xC0D22400
        +0x0C  u32  data size in bytes

Checks that make this more than a guess, all against out/seg0_c0000000.bin:

  * 2259 of 2259 entries' path offsets resolve to the path whose FNV-1a is the
    key -- so the key, the pool and the offset field all agree.
  * For the 2004 .xci entries, `0xC0D22400 + data offset` is the XCI blob's
    address and `size` is its exact byte length: 2004 of 2004.
  * fpSup-Formats v0.3.0a writes exactly 8 bytes at 0xC0D4DE04.  That is entry
    68 + 0x08: the data offset and size of `../MenuB12/data/ListB12/B2_5_4.cvm`,
    whose stock content is the Resolution menu's row list --

        NO,TEXT,Popup,IMAGE,Enabled,Enabled2
        1,0313,Popup,blank,1,2
        2,0314,Popup,blank,1,2

    two rows, UHD and FHD.  The card writes its six-row CSV into spare space and
    repoints that entry at it.  No interpreter hook is involved.

So a resource is replaced by: put the new bytes anywhere the loader can journal,
then write {offset, size} into its directory entry.  A row also needs the
Settings controller maximum at 0xC1A709BC (FP3K: a CSV row alone is visible but
unselectable), and any new UI state needs its NBU records too -- see
nbu_probe/README.md.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

BASE = 0xC0000000
CONTAINER = 0xC0D22400
MAGIC = b"NBR\x00"
ENTRY = 16
SEG0_SIZE = 49_245_696


class NbrError(RuntimeError):
    pass


def fnv1a(text: str) -> int:
    value = 0x811C9DC5
    for byte in text.encode("utf-8"):
        value = ((value ^ byte) * 0x01000193) & 0xFFFFFFFF
    return value


@dataclass(frozen=True)
class Entry:
    index: int
    key: int
    path: str
    entry_address: int          # where the 16 bytes live
    data_address: int           # CONTAINER + data offset
    size: int

    @property
    def patch_address(self) -> int:
        """Where the two words a repoint changes live: entry + 0x08."""
        return self.entry_address + 8

    @property
    def extension(self) -> str:
        return self.path.rsplit(".", 1)[-1] if "." in self.path else ""


class StockNbr:
    """Read-only view of the NBR container inside a firmware image."""

    def __init__(self, image: bytes, container: int = CONTAINER) -> None:
        if len(image) != SEG0_SIZE:
            raise NbrError(f"expected the pinned {SEG0_SIZE}-byte seg0 image")
        self.image = image
        self.container = container
        if self._bytes(container, 4) != MAGIC:
            raise NbrError(f"no NBR magic at 0x{container:08X}")
        self.version = self._be(container + 4)
        self.records = self._split()
        by_tag = {tag: (address, size) for tag, address, size in self.records}
        if 1 not in by_tag or 2 not in by_tag:
            raise NbrError("the container is missing the name pool or the directory")
        self.pool_address, pool_size = by_tag[1]
        self.pool = self._bytes(self.pool_address + 8, pool_size - 8)
        directory, _size = by_tag[2]
        self.count = self._be(directory + 8)
        self.entries_address = directory + 12
        self.entries = self._entries()
        self.by_path = {entry.path: entry for entry in self.entries}

    # --- plumbing ---------------------------------------------------------

    def _bytes(self, address: int, length: int) -> bytes:
        start = address - BASE
        if start < 0 or start + length > len(self.image):
            raise NbrError(f"0x{address:08X}+{length} is outside the image")
        return self.image[start:start + length]

    def _be(self, address: int) -> int:
        return struct.unpack(">I", self._bytes(address, 4))[0]

    def _split(self) -> list[tuple[int, int, int]]:
        """(tag, address, size) for each length-delimited record."""
        out, address = [], self.container + 12
        while True:
            tag, size = struct.unpack(">II", self._bytes(address, 8))
            if size < 8:
                raise NbrError(f"record at 0x{address:08X} has size {size}")
            out.append((tag, address, size))
            if tag == 0xFFFFFFFF:
                return out
            address += size

    def _string(self, offset: int) -> str:
        end = self.pool.find(b"\0", offset)
        if end < 0:
            raise NbrError(f"pool offset 0x{offset:X} is not terminated")
        return self.pool[offset:end].decode("latin1")

    def _entries(self) -> list[Entry]:
        out = []
        for index in range(self.count):
            address = self.entries_address + index * ENTRY
            key, name_offset, data_offset, size = struct.unpack(
                ">IIII", self._bytes(address, ENTRY))
            out.append(Entry(index, key, self._string(name_offset), address,
                             self.container + data_offset, size))
        return out

    # --- the useful part --------------------------------------------------

    def find(self, path: str) -> Entry:
        entry = self.by_path.get(path) or self.by_path.get("../" + path.lstrip("./"))
        if entry is None:
            raise NbrError(f"no resource named {path!r}")
        return entry

    def read(self, path: str) -> bytes:
        entry = self.find(path)
        return self._bytes(entry.data_address, entry.size)

    def repoint(self, path: str, data_address: int, size: int) -> tuple[int, bytes]:
        """(address, 8 big-endian bytes) that make this resource point elsewhere.

        The bytes replace the entry's {data offset, size}.  The offset is stored
        relative to the container, which is why a caller cannot just write the
        absolute address.
        """
        entry = self.find(path)
        if data_address < self.container:
            raise NbrError("a resource has to live at or after the container base")
        if size <= 0:
            raise NbrError("size must be positive")
        offset = data_address - self.container
        return entry.patch_address, struct.pack(">II", offset, size)

    # --- menus and their text -------------------------------------------

    def strings(self, language: str = "English") -> dict:
        """id -> text from `Common/Strings/<language>.nloc`.  See parse_nloc."""
        return parse_nloc(self.read(f"../Common/Strings/{language}.nloc"))

    def menu(self, path: str, strings: dict | None = None) -> list[dict]:
        """Parse a .cvm menu list.  See parse_menu."""
        return parse_menu(self.read(path), strings)

    def free_space(self) -> list[tuple[int, int]]:
        """(address, length) of the bytes inside the data record that no entry
        owns.  The answer is 3,486 bytes in 1,718 gaps of 3 bytes each -- the
        container is PACKED, so a longer resource has to be written over
        something.  fpSup-Formats writes its six-row CSV over
        `L_resolution_480p.xci` (3,314 B), an icon a 5.02 fp never draws.
        """
        data = [(tag, address, size) for tag, address, size in self.records if tag == 2]
        if not data:
            raise NbrError("no data record")
        _tag, start, size = data[0]
        end = start + size
        gaps, cursor = [], self.entries_address + ENTRY * self.count
        for entry in sorted(self.entries, key=lambda e: e.data_address):
            if entry.data_address > cursor:
                gaps.append((cursor, entry.data_address - cursor))
            cursor = max(cursor, entry.data_address + entry.size)
        if cursor < end:
            gaps.append((cursor, end - cursor))
        return gaps

    def owner_of(self, address: int) -> Entry | None:
        for entry in self.entries:
            if entry.data_address <= address < entry.data_address + entry.size:
                return entry
        return None

    NON_DESTINATIONS = ("popup", "zzz")

    def submenus(self) -> list[dict]:
        """Every menu row whose Popup column names another page.

        The column holds one of three things: `Popup` (an ordinary value popup
        in place), a placeholder of x's or `zzz` (nothing), or A PAGE NAME --
        and that is the row that opens a submenu when you press right.
        """
        strings = self.strings()
        out = []
        for entry in self.entries:
            if entry.extension != "cvm":
                continue
            for row in self.menu(entry.path, strings):
                target = (row.get("Popup") or row.get("POPUP") or "").strip()
                if not target or target.lower() in self.NON_DESTINATIONS:
                    continue
                if set(target) <= set("x"):          # xx / xxx / xxxxx = nothing
                    continue
                out.append({"list": entry.path, "no": row.get("NO"),
                            "text": row.get("text", row.get("TEXT", "")),
                            "target": target})
        return out

    def verify(self) -> dict:
        """Re-derive the two claims in the docstring from the image."""
        keys_agree = sum(1 for e in self.entries if fnv1a(e.path) == e.key)
        sorted_by_key = all(self.entries[i].key < self.entries[i + 1].key
                            for i in range(len(self.entries) - 1))
        xci = [e for e in self.entries if e.extension == "xci"]
        blobs_agree = sum(1 for e in xci
                          if self._bytes(e.data_address, 4) == b"XC\x00\x00")
        return {"entries": len(self.entries), "keys_agree": keys_agree,
                "sorted_by_key": sorted_by_key, "xci": len(xci),
                "xci_blob_at_data_address": blobs_agree}


def parse_nloc(data: bytes) -> dict:
    """id -> text, from a .nloc string table.

        "NDB\\0", u32 version, u32 count, then `count` 8-byte entries
            u32 LE  FNV-1a of the ASCII id
            u8      0
            u24 LE  offset of the record          <- three bytes, not four:
                                                     the LE word at +4 is 256x
                                                     too big and lands outside
                                                     the file
        record: u32 LE offset of the id, u32 LE offset of the text, then both
                NUL-terminated Latin-1

    The ids are exactly what a menu CSV's TEXT column holds: 0313 is
    "UHD 3840x2160", 0314 is "FHD 1920x1080".  Every key is checked against
    fnv1a(id) -- 46,376 of 46,376 across the 17 languages.
    """
    if data[:4] != b"NDB\x00":
        raise NbrError("no NDB magic")
    count = struct.unpack_from("<I", data, 8)[0]
    out = {}
    for index in range(count):
        entry = 12 + 8 * index
        key = struct.unpack_from("<I", data, entry)[0]
        offset = int.from_bytes(data[entry + 5:entry + 8], "little")
        id_at, text_at = struct.unpack_from("<II", data, offset)
        ident = data[offset + id_at:data.index(b"\0", offset + id_at)].decode("latin1")
        text = data[offset + text_at:data.index(b"\0", offset + text_at)].decode("latin1")
        if fnv1a(ident) != key:
            raise NbrError(f"nloc entry {index}: key is not fnv1a({ident!r})")
        out[ident] = text
    return out


def parse_menu(data: bytes, strings: dict | None = None) -> list[dict]:
    """Parse a .cvm menu list.

    Columns are named by the HEADER LINE, which is why the 195 stock files do
    not all have the same one (13 different headers, and fpSup-Formats' own
    replacement drops the Popup column).  A decoder with fixed columns reads the
    wrong cells.

    A TEXT cell is either a string id for `strings`, or -- as that card does for
    its new rows -- a literal used as it stands, so a new row needs no .nloc
    change at all.
    """
    import csv as _csv
    import io as _io
    text = data.decode("utf-8-sig")
    lines = [line for line in text.replace("\r\n", "\n").split("\n") if line.strip()]
    if not lines:
        return []
    # Cells are quoted when they contain a comma -- e.g. B4_1_3_4_1.cvm has
    # `1,"90<!font_G_degree,CENTER>",xx,...` -- so a plain split desynchronises
    # the columns and invents destinations like `CENTER>"`.
    parsed = list(_csv.reader(_io.StringIO("\n".join(lines))))
    header = [cell.strip() for cell in parsed[0]]
    rows = []
    for cells in parsed[1:]:
        cells = [cell.strip() for cell in cells]
        row = dict(zip(header, cells + [""] * (len(header) - len(cells))))
        if strings is not None and "TEXT" in row:
            row["text"] = strings.get(row["TEXT"], row["TEXT"])
        rows.append(row)
    return rows


def load(image_path=None) -> StockNbr:
    path = Path(image_path) if image_path else \
        Path(__file__).resolve().parents[3] / "out" / "seg0_c0000000.bin"
    return StockNbr(path.read_bytes())


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--image")
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list", help="list resources")
    listing.add_argument("pattern", nargs="?")
    listing.add_argument("--ext", help="only this extension, e.g. cvm")
    show = sub.add_parser("show", help="print one resource (text if it is text)")
    show.add_argument("path")
    point = sub.add_parser("repoint", help="the 8-byte write that moves a resource")
    point.add_argument("path")
    point.add_argument("address")
    point.add_argument("size", type=int)
    menu = sub.add_parser("menu", help="parse a .cvm list with its text resolved")
    menu.add_argument("path")
    menu.add_argument("--lang", default="English")
    strings = sub.add_parser("strings", help="look up menu text by id")
    strings.add_argument("pattern", nargs="?")
    strings.add_argument("--lang", default="English")
    sub.add_parser("verify", help="re-derive the format claims from the image")
    sub.add_parser("submenus", help="every row that opens another page")
    room = sub.add_parser("room", help="what owns an address, and how much slack the container has")
    room.add_argument("address", nargs="?")
    args = parser.parse_args(argv)

    nbr = load(args.image)
    if args.command == "verify":
        for key, value in nbr.verify().items():
            print(f"{key:28s} {value}")
        print(f"{'container':28s} 0x{nbr.container:08X} version 0x{nbr.version:08X}")
        for tag, address, size in nbr.records:
            print(f"  record tag 0x{tag:08X}  {size:>10d} B at 0x{address:08X}")
        return 0

    if args.command == "list":
        rows = nbr.entries
        if args.ext:
            rows = [e for e in rows if e.extension == args.ext]
        if args.pattern:
            needle = args.pattern.lower()
            rows = [e for e in rows if needle in e.path.lower()]
        for entry in sorted(rows, key=lambda e: e.path):
            print(f"0x{entry.data_address:08X} {entry.size:>7d} B  "
                  f"entry 0x{entry.entry_address:08X}  {entry.path}")
        print(f"-- {len(rows)} of {len(nbr.entries)} resources")
        return 0

    if args.command == "show":
        data = nbr.read(args.path)
        entry = nbr.find(args.path)
        print(f"{entry.path}  0x{entry.data_address:08X}  {entry.size} B  "
              f"entry 0x{entry.entry_address:08X} (repoint at 0x{entry.patch_address:08X})")
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            print(data[:256].hex(" "))
        else:
            print(text if text.isprintable() or "\n" in text else repr(text))
        return 0

    if args.command == "submenus":
        rows = nbr.submenus()
        for row in rows:
            print(f"{row['list'].replace('../', ''):<46} {str(row['no']):>3}  "
                  f"{row['text'][:28]:<28} -> {row['target']}")
        targets = sorted({row["target"] for row in rows})
        print(f"-- {len(rows)} rows, {len(targets)} destinations")
        return 0

    if args.command == "room":
        if args.address:
            address = int(args.address, 16)
            entry = nbr.owner_of(address)
            if entry is None:
                print(f"0x{address:08X} is not owned by any resource")
            else:
                print(f"0x{address:08X} is inside {entry.path}\n"
                      f"  0x{entry.data_address:08X}  {entry.size} B  "
                      f"(+{address - entry.data_address}), repoint at 0x{entry.patch_address:08X}")
            return 0
        gaps = nbr.free_space()
        total = sum(length for _a, length in gaps)
        print(f"{len(gaps)} unowned gaps, {total} bytes in total; "
              f"largest {max(length for _a, length in gaps)} bytes")
        print("the container is packed: a longer resource has to be written over another one")
        return 0

    if args.command == "strings":
        table = nbr.strings(args.lang)
        rows = [(i, t) for i, t in sorted(table.items())
                if not args.pattern or args.pattern.lower() in i.lower()
                or args.pattern.lower() in t.lower()]
        for ident, text in rows[:200]:
            print(f"{ident:8s} {text}")
        print(f"-- {len(rows)} of {len(table)} strings in {args.lang}")
        return 0

    if args.command == "menu":
        table = nbr.strings(args.lang)
        rows = nbr.menu(args.path, table)
        entry = nbr.find(args.path)
        print(f"{entry.path}  0x{entry.data_address:08X}  {entry.size} B  "
              f"repoint at 0x{entry.patch_address:08X}")
        for row in rows:
            flags = " ".join(f"{k}={v}" for k, v in row.items()
                             if k not in ("NO", "TEXT", "text") and v)
            print(f"  {row.get('NO','?'):>3}  {row.get('text', ''):<26} {flags}")
        return 0

    address, words = nbr.repoint(args.path, int(args.address, 16), args.size)
    entry = nbr.find(args.path)
    print(f"{entry.path}")
    print(f"  stock: 0x{entry.data_address:08X}  {entry.size} B")
    print(f"  write 8 bytes at 0x{address:08X}: {words.hex(' ')}")
    print(f"  (offset 0x{struct.unpack('>I', words[:4])[0]:X} from 0x{nbr.container:08X})")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
