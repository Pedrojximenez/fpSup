#!/usr/bin/env python3
"""uinav -- navigate the SIGMA fp Ver.5.02 native UI.

Curated knowledge lives in research/ui/ui_map.json.  The bulk vocabulary (string
pool, GUI page table, icon manifest, icon blobs) is not stored anywhere: it is
read out of the pinned firmware image on demand, so it cannot drift from it.

    uinav.py at 0xC05E6400          what is this address, and who hooks it
    uinav.py pool Resolution        search the 14k UI string pool
    uinav.py pages B2               the 196 native GUI pages, name -> id
    uinav.py sets Main              the 221 NBU resource sets and their bytes
    uinav.py screens                screen-shaped pool names (1_03_CINE ...)
    uinav.py vars MV_               camera/UI variable names by prefix
    uinav.py icons qs_resolution    the .xci build manifest, with blob w/h
    uinav.py who fpsup-formats      every address one product touches
    uinav.py routes                 the six ways into the UI, and their cost
    uinav.py traps                  the mistakes this project already made
    uinav.py emu                    what is already executed offline
    uinav.py find resolution        everything matching, across every index
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
UI_MAP = HERE.parent / "ui_map.json"
NBU_SETS = HERE.parent / "nbu_sets.json"
BASE = 0xC0000000

POOL_START, POOL_END = 0xC18C0474, 0xC1900000
PAGE_TABLE_START = 0xC0D0DB68
MANIFEST_START, MANIFEST_END = 0xC0D24968, 0xC0D90000
BLOBS_START, BLOBS_END = 0xC1240014, 0xC151C348


def load_map(path: Path = UI_MAP) -> dict:
    return json.loads(path.read_text())


def parse_addr(text: str) -> int:
    value = int(text, 16 if text.lower().startswith("0x") or re.fullmatch(r"[0-9A-Fa-f]+", text) else 0)
    return value


def _tree_root() -> Path:
    return HERE.parent.parent.parent


class Image:
    """The pinned firmware image, read lazily."""

    def __init__(self, ui_map: dict, path: Path | None = None) -> None:
        self.meta = ui_map["firmware"]
        self.path = Path(path) if path else _tree_root() / self.meta["image"]
        self._data: bytes | None = None

    @property
    def data(self) -> bytes:
        if self._data is None:
            if not self.path.exists():
                raise SystemExit(f"firmware image not found: {self.path}")
            self._data = self.path.read_bytes()
            if len(self._data) != self.meta["size"]:
                raise SystemExit(
                    f"{self.path} is {len(self._data)} bytes, expected {self.meta['size']}"
                )
        return self._data

    def verify(self) -> str:
        digest = hashlib.sha256(self.data).hexdigest()
        if digest != self.meta["sha256"]:
            raise SystemExit(f"{self.path} sha256 {digest}, expected {self.meta['sha256']}")
        return digest

    def slice(self, start: int, end: int) -> bytes:
        return self.data[start - BASE : end - BASE]

    def word(self, addr: int) -> int:
        return struct.unpack_from("<I", self.data, addr - BASE)[0]

    def cstr(self, addr: int, limit: int = 96) -> str | None:
        if not BASE <= addr < BASE + len(self.data):
            return None
        raw = self.data[addr - BASE : addr - BASE + limit].split(b"\x00")[0]
        if not raw or any(c < 32 or c > 126 for c in raw):
            return None
        return raw.decode("ascii")

    # --- generated indexes -------------------------------------------------

    def pool(self) -> list[tuple[int, str]]:
        """(pool offset, string).  Records reference these offsets big-endian."""
        out, offset = [], 0
        for part in self.slice(POOL_START, POOL_END).split(b"\x00"):
            if part and all(32 <= c <= 126 for c in part):
                out.append((offset, part.decode("ascii")))
            offset += len(part) + 1
        return out

    def pages(self) -> list[tuple[int, str, int]]:
        """(table address, page name, page id) from the 196-entry GUI page table."""
        out, addr, gaps = [], PAGE_TABLE_START, 0
        while True:
            name_ptr, page_id = self.word(addr), self.word(addr + 4)
            if name_ptr == 0 and page_id == 0:
                # the table carries a few {0, 0} padding pairs between groups
                gaps += 1
                if gaps > 4:
                    break
                addr += 8
                continue
            name = self.cstr(name_ptr)
            if name is None or page_id > 0x2000:
                break
            gaps = 0
            out.append((addr, name, page_id))
            addr += 8
        return out

    def icons(self) -> list[tuple[int, str]]:
        """(manifest address, short icon name) in blob order, with one known gap."""
        region = self.slice(MANIFEST_START, MANIFEST_END)
        return [
            (MANIFEST_START + m.start(), m.group().decode("ascii"))
            for m in re.finditer(rb"\.\./[ -~]{5,200}?\.xci", region)
        ]

    def blobs(self) -> list[tuple[int, int, int]]:
        """(blob address, width, height) for every XCI blob in the icon archive."""
        region = self.slice(BLOBS_START, BLOBS_END)
        out = []
        for m in re.finditer(rb"XC\x00\x00", region):
            width, height = struct.unpack_from("<HH", region, m.start() + 8)
            out.append((BLOBS_START + m.start(), width, height))
        return out


# --- commands --------------------------------------------------------------

def _match(pattern: str | None):
    if not pattern:
        return lambda _s: True
    rx = re.compile(pattern, re.IGNORECASE)
    return lambda s: rx.search(s) is not None


def cmd_at(ui_map: dict, image: Image, args) -> int:
    addr = parse_addr(args.address)
    hit = False
    for region in ui_map["regions"]:
        start, end = parse_addr(region["start"]), parse_addr(region["end"])
        if start <= addr < end:
            hit = True
            print(f"region  {region['name']}  [{region['start']}..{region['end']})")
            print(f"        {region['what']}")
            print(f"        read when: {region['read_when']}")
            print(f"        patch: {region['patch']}")
            print(f"        source: {region['source']}")
    for func in ui_map["funcs"]:
        if parse_addr(func["addr"]) == addr:
            hit = True
            print(f"func    {func['name']}  ({func['isa']})")
            print(f"        {func['what']}")
            print(f"        source: {func['source']}")
    for site in ui_map["hook_sites"]:
        if parse_addr(site["addr"]) == addr:
            hit = True
            print(f"hooked  by {', '.join(site['owners'])}")
            print(f"        {site['role']}")
    if POOL_START <= addr < POOL_END:
        text = image.cstr(addr)
        print(f"pool    offset 0x{addr - POOL_START:06X}"
              + (f"  string {text!r}" if text else "  (not the start of a string)"))
    else:
        name = image.cstr(addr)
        if name:
            print(f"string  the image has ASCII there: {name!r}")
    if NBU_SETS.exists():
        data = json.loads(NBU_SETS.read_text())
        rows = sorted(((int(r["address"], 16), r["name"]) for r in data["sets"]))
        for (start, name), (end, _next) in zip(rows, rows[1:] + [(1 << 32, "")]):
            if start <= addr < end:
                print(f"set     {name}  [0x{start:08X}..0x{end:08X})  +0x{addr - start:X}"
                      + ("  (its first record is the allocation header)" if addr == start else ""))
                hit = True
                break
    for page_addr, page_name, page_id in image.pages():
        if page_addr == addr:
            print(f"page    {page_name}  id {page_id}")
            hit = True
    if not hit:
        print(f"0x{addr:08X} is not in the curated map.")
        return 1
    return 0


def cmd_pool(ui_map: dict, image: Image, args) -> int:
    keep = _match(args.pattern)
    rows = [(o, s) for o, s in image.pool() if keep(s)]
    for offset, text in rows[: args.limit]:
        print(f"0x{offset:06X}  0x{POOL_START + offset:08X}  {text}")
    print(f"-- {len(rows)} of {len(image.pool())} pool strings"
          + (f" (showing {args.limit})" if len(rows) > args.limit else ""))
    return 0


def cmd_pages(ui_map: dict, image: Image, args) -> int:
    keep = _match(args.pattern)
    rows = [r for r in image.pages() if keep(r[1])]
    for addr, name, page_id in rows[: args.limit]:
        print(f"0x{addr:08X}  id {page_id:5d}  {name}")
    print(f"-- {len(rows)} of {len(image.pages())} GUI pages")
    return 0


def cmd_sets(ui_map: dict, image: Image, args) -> int:
    """The resource-set table, as the emulated interpreter built it."""
    if not NBU_SETS.exists():
        print(f"{NBU_SETS} is missing. Regenerate it with:\n"
              "  cd research/ui/tools/nbu_probe && "
              "python3 nbu_probe.py index --json ../../nbu_sets.json")
        return 1
    data = json.loads(NBU_SETS.read_text())
    keep = _match(args.pattern)
    rows = [row for row in data["sets"] if keep(row["name"])]
    for row in rows[: args.limit]:
        print(f"{row['hash'][2:]}  {row['address']}  +{row['offset']:>9}  {row['name']}")
    print(f"-- {len(rows)} of {len(data['sets'])} resource sets, "
          f"offsets from {data['nbu_base']}")
    print(f"-- {data['_source']}")
    return 0


def cmd_screens(ui_map: dict, image: Image, args) -> int:
    keep = _match(args.pattern)
    shape = re.compile(r"^\d+_\d\d(_|$)")
    rows = [(o, s) for o, s in image.pool() if shape.match(s) and keep(s)]
    for offset, text in rows[: args.limit]:
        print(f"0x{offset:06X}  {text}")
    print(f"-- {len(rows)} screen-shaped names (use them with `gui scr set <name>`)")
    return 0


def cmd_vars(ui_map: dict, image: Image, args) -> int:
    keep = _match(args.pattern)
    shape = re.compile(r"^[A-Z][A-Za-z0-9]*_[A-Za-z0-9_]+$")
    rows = [(o, s) for o, s in image.pool() if shape.match(s) and keep(s)]
    if args.count:
        tally: dict[str, int] = {}
        for _o, s in rows:
            tally[s.split("_", 1)[0]] = tally.get(s.split("_", 1)[0], 0) + 1
        for prefix, n in sorted(tally.items(), key=lambda kv: -kv[1]):
            print(f"{n:5d}  {prefix}_")
        return 0
    for offset, text in rows[: args.limit]:
        print(f"0x{offset:06X}  {text}")
    print(f"-- {len(rows)} variable-shaped names")
    return 0


def cmd_icons(ui_map: dict, image: Image, args) -> int:
    keep = _match(args.pattern)
    manifest, blobs = image.icons(), image.blobs()
    drift = len(manifest) - len(blobs)
    for index, (addr, path) in enumerate(manifest):
        short = path.rsplit("/", 1)[-1]
        if not keep(short):
            continue
        # The manifest has more paths than the archive has blobs, so a name maps
        # to a blob at index-k for some 0 <= k <= drift.  Offer every candidate
        # with its dimensions rather than guessing; confirm by dimension.
        candidates = [blobs[index - k] for k in range(drift + 1) if 0 <= index - k < len(blobs)]
        shown = "  ".join(f"0x{a:08X} {w}x{h}" for a, w, h in candidates)
        print(f"#{index:04d}  {short}\n        {shown}")
    if drift:
        print(f"-- {len(manifest)} manifest paths, {len(blobs)} blobs: {drift} gap(s). "
              "Each line lists every candidate blob; pick the one whose w x h fits the widget.")
    return 0


def cmd_who(ui_map: dict, image: Image, args) -> int:
    keep = _match(args.pattern)
    for owner in ui_map["owners"]:
        if not (keep(owner["id"]) or keep(owner["who"])):
            continue
        print(f"{owner['id']}  --  {owner['who']}  [{owner['kind']}]")
        print(f"  ui:     {owner['ui']}")
        print(f"  status: {owner['status']}")
        print(f"  where:  {owner['where']}")
        sites = [s for s in ui_map["hook_sites"] if owner["id"] in s["owners"]]
        for site in sites:
            print(f"  hook    {site['addr']}  {site['role']}")
        print()
    return 0


def cmd_routes(ui_map: dict, image: Image, args) -> int:
    for route in ui_map["routes"]:
        print(f"{route['id']}  {route['name']}   [{route['verified']}]")
        print(f"  how:  {route['how']}")
        print(f"  cost: {route['cost']}")
        print(f"  gets: {route['gets']}")
        print(f"  not:  {route['does_not']}")
        print()
    return 0


def cmd_traps(ui_map: dict, image: Image, args) -> int:
    for trap in ui_map["traps"]:
        print(f"* {trap['trap']}")
        print(f"  {trap['what']}")
        print(f"  {trap['source']}")
        print()
    return 0


def cmd_emu(ui_map: dict, image: Image, args) -> int:
    for probe in ui_map["emulated"]:
        tests = f"{probe['tests']} tests" if probe["tests"] else "no test count recorded"
        print(f"{probe['probe']}  ({tests})")
        if probe["entries"]:
            print(f"  entries: {', '.join(probe['entries'])}")
        print(f"  {probe['what']}")
        print()
    return 0


def cmd_find(ui_map: dict, image: Image, args) -> int:
    keep = _match(args.pattern)
    for func in ui_map["funcs"]:
        if keep(func["name"]) or keep(func["what"]):
            print(f"func    {func['addr']}  {func['name']}")
    for region in ui_map["regions"]:
        if keep(region["name"]) or keep(region["what"]):
            print(f"region  {region['start']}  {region['name']}")
    for site in ui_map["hook_sites"]:
        if keep(site["role"]):
            print(f"hook    {site['addr']}  {site['role']}  <- {', '.join(site['owners'])}")
    for owner in ui_map["owners"]:
        if keep(owner["id"]) or keep(owner["ui"]):
            print(f"owner   {owner['id']}  {owner['who']}")
    pages = [r for r in image.pages() if keep(r[1])]
    for addr, name, page_id in pages[:12]:
        print(f"page    0x{addr:08X}  id {page_id}  {name}")
    pool = [(o, s) for o, s in image.pool() if keep(s)]
    for offset, text in pool[:12]:
        print(f"string  0x{offset:06X}  {text}")
    if len(pool) > 12:
        print(f"        ... and {len(pool) - 12} more pool strings (uinav.py pool {args.pattern})")
    return 0


def cmd_verify(ui_map: dict, image: Image, args) -> int:
    print(f"image   {image.path}")
    print(f"sha256  {image.verify()}  (matches the pinned map)")
    print(f"pages   {len(image.pages())}")
    print(f"pool    {len(image.pool())} strings")
    print(f"icons   {len(image.icons())} manifest paths, {len(image.blobs())} blobs")
    return 0


COMMANDS = {
    "at": cmd_at, "pool": cmd_pool, "pages": cmd_pages, "screens": cmd_screens,
    "vars": cmd_vars, "icons": cmd_icons, "who": cmd_who, "routes": cmd_routes,
    "sets": cmd_sets,
    "traps": cmd_traps, "emu": cmd_emu, "find": cmd_find, "verify": cmd_verify,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--image", help="override the firmware image path")
    parser.add_argument("--map", default=str(UI_MAP), help="override ui_map.json")
    parser.add_argument("--limit", type=int, default=60, help="rows to print (default 60)")
    sub = parser.add_subparsers(dest="command", required=True)

    at = sub.add_parser("at", help="what lives at an address, and who hooks it")
    at.add_argument("address")
    for name in ("pool", "pages", "screens", "sets", "find"):
        p = sub.add_parser(name)
        p.add_argument("pattern", nargs="?" if name != "find" else None)
    v = sub.add_parser("vars")
    v.add_argument("pattern", nargs="?")
    v.add_argument("--count", action="store_true", help="tally by prefix instead of listing")
    i = sub.add_parser("icons")
    i.add_argument("pattern", nargs="?")
    w = sub.add_parser("who")
    w.add_argument("pattern", nargs="?")
    for name in ("routes", "traps", "emu", "verify"):
        sub.add_parser(name)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ui_map = load_map(Path(args.map))
    image = Image(ui_map, args.image)
    return COMMANDS[args.command](ui_map, image, args)


if __name__ == "__main__":
    sys.exit(main())
