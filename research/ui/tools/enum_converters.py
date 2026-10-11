#!/usr/bin/env python3
"""The enum -> display-state converters, and the three immediates that move one.

A menu control turns its stored enum into a DISPLAY STATE through a tiny ARM
leaf function.  There are 329 of them, one per control, all the same shape:

    movw r2, #<low>      \\  the pair table's address, as two immediates
    movt r2, #<high>     /
    str  r2, [ip]           hand it to the caller
    mov  r2, #<count>       how many pairs
    bx   lr

The pair table is {enum, state} pairs, read on EVERY evaluation by
FUN_c06ccd10 -- which is why a write to it takes effect on the next draw
(research/ui/README.md section 4).

**A row you added that selects but then draws nothing is this**: the new enum has
no pair, so the control falls back to state 0 or to nothing.  The fix needs no
hook at all -- build your own table, then rewrite THREE IMMEDIATES:

    the movw and movt   -> your table's address
    the mov r2,#N       -> your pair count

fpSup-Formats does exactly that on a camera-verified card: it writes
0xC06BDA3C / 0xC06BDA40 / 0xC06BDA48 so the Resolution converter reads its own
six-pair table at 0xC0731C40 instead of the stock three at 0xC2E4020C.

    enum_converters.py list --count 3
    enum_converters.py at 0xC06BDA3C
"""
from __future__ import annotations

import struct
from pathlib import Path

BASE = 0xC0000000
FAMILY = (0xC06BD000, 0xC06D0000)       # where the 329 leaves live
TABLES = (0xC2E40000, 0xC2E50000)       # where their pair tables live
KNOWN = {0xC06BDA3C: "Resolution -- the one fpSup-Formats repoints to six pairs"}


def _movw(word: int):
    if (word & 0x0FF00000) != 0x03000000:
        return None
    return (((word >> 16) & 0xF) << 12) | (word & 0xFFF), (word >> 12) & 0xF


def _movt(word: int):
    if (word & 0x0FF00000) != 0x03400000:
        return None
    return (((word >> 16) & 0xF) << 12) | (word & 0xFFF), (word >> 12) & 0xF


def _mov_imm(word: int):
    if (word & 0x0FEF0000) != 0x03A00000:
        return None
    imm, rot = word & 0xFF, ((word >> 8) & 0xF) * 2
    return ((imm >> rot) | (imm << (32 - rot))) & 0xFFFFFFFF, (word >> 12) & 0xF


def converters(image: bytes) -> list[dict]:
    """Every converter in the family, with its table, count and patch sites."""
    out = []
    for address in range(FAMILY[0], FAMILY[1] - 24, 4):
        off = address - BASE
        low = _movw(struct.unpack_from("<I", image, off)[0])
        if not low:
            continue
        high = _movt(struct.unpack_from("<I", image, off + 4)[0])
        if not high or low[1] != high[1]:
            continue
        table = low[0] | (high[0] << 16)
        if not TABLES[0] <= table < TABLES[1]:
            continue
        count = None
        for step in range(2, 7):
            word = struct.unpack_from("<I", image, off + 4 * step)[0]
            got = _mov_imm(word)
            if got and 0 < got[0] < 64:
                count = (got[0], address + 4 * step)
                break
            if (word & 0x0FFFFFFF) == 0x012FFF1E:      # bx lr
                break
        if count is None:
            continue
        pairs = [struct.unpack_from("<II", image, table - BASE + 8 * i)
                 for i in range(count[0])]
        out.append({"movw": address, "movt": address + 4, "count_at": count[1],
                    "table": table, "count": count[0], "pairs": pairs,
                    "note": KNOWN.get(address, "")})
    return out


def patch(converter: dict, table: int, count: int) -> list[tuple[int, int]]:
    """(address, word) x3: point a converter at your own table of `count` pairs.

    Only immediates are rewritten -- no branch, no trampoline, no displaced
    instruction, so this is not a code hook.
    """
    if not 0 < count < 64:
        raise ValueError("count must be 1..63 (the mov is an 8-bit immediate)")
    base = struct.unpack_from("<I", _image(), converter["movw"] - BASE)[0]
    rd = (base >> 12) & 0xF
    movw = 0x03000000 | (((table & 0xF000) >> 12) << 16) | (rd << 12) | (table & 0xFFF)
    movt = 0x03400000 | ((((table >> 16) & 0xF000) >> 12) << 16) | (rd << 12) \
        | ((table >> 16) & 0xFFF)
    count_word = struct.unpack_from("<I", _image(), converter["count_at"] - BASE)[0]
    mov = (count_word & 0xFFFFFF00) | count
    return [(converter["movw"], 0xE0000000 | movw),
            (converter["movt"], 0xE0000000 | movt),
            (converter["count_at"], mov)]


_CACHE = {}


def _image() -> bytes:
    if "image" not in _CACHE:
        path = Path(__file__).resolve().parents[3] / "out" / "seg0_c0000000.bin"
        _CACHE["image"] = path.read_bytes()
    return _CACHE["image"]


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list")
    listing.add_argument("--count", type=int, help="only converters with this pair count")
    listing.add_argument("--table", help="only this table address")
    at = sub.add_parser("at")
    at.add_argument("address")
    args = parser.parse_args(argv)

    rows = converters(_image())
    if args.command == "at":
        want = int(args.address, 16)
        rows = [r for r in rows if want in (r["movw"], r["movt"], r["count_at"], r["table"])]
    else:
        if args.count:
            rows = [r for r in rows if r["count"] == args.count]
        if args.table:
            rows = [r for r in rows if r["table"] == int(args.table, 16)]
    for row in rows:
        print(f"0x{row['movw']:08X}  table 0x{row['table']:08X}  {row['count']} pairs"
              f"   patch 0x{row['movw']:08X}/0x{row['movt']:08X}/0x{row['count_at']:08X}"
              + (f"   {row['note']}" if row["note"] else ""))
        print("        " + ", ".join(f"{k}->{v}" for k, v in row["pairs"][:8])
              + (" ..." if len(row["pairs"]) > 8 else ""))
    print(f"-- {len(rows)} of {len(converters(_image()))} converters")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
