#!/usr/bin/env python3
"""Add a row to a native menu list with data only -- no hook anywhere.

Three writes, and that is the whole change:

  1. the new CSV, placed over a resource that has room for it,
  2. 8 bytes repointing that CSV's NBR directory entry at the new bytes,
  3. the Settings controller maximum, which is `rows - 1` as a big-endian float
     (stock 1.0 for the two-row Resolution list; a CSV row alone is visible but
     UNSELECTABLE until this grows -- FP3K found that the hard way).

What this does NOT do: the Quick Set.  A row added this way appears and selects
in Settings; the QS tile needs 152 NBU record edits in QS_CINE / QS_STILLlike /
QS_Common (research/ui/QUICK_SET.md).  Say which of the two you tested.

    menu_row_patch.py --append "3K 3008x2000"
    menu_row_patch.py --append "3K 3008x2000" --json plan.json --autorun

Nothing here writes to a card or a camera; it prints a plan.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nbr_stock as N                                        # noqa: E402

RESOLUTION_LIST = "../MenuB12/data/ListB12/B2_5_4.cvm"
CONTROLLER_MAX = 0xC1A709BC
# An icon the camera has no menu row for; fpSup-Formats sacrifices the same one
# on a card that was verified on a camera.  Everything the loader writes is
# journalled and restored at power-off, so the icon comes back.
DEFAULT_VICTIM = "../ResXCI/data/C43_iconData_rev5ToXci/L/L_resolution_480p.xci"


class PlanError(RuntimeError):
    pass


def build_csv(stock: bytes, extra_rows: list[str]) -> bytes:
    """Append rows to a stock list, using LITERAL text so no .nloc changes.

    The stock header is kept, so the new rows carry the same columns; a TEXT
    cell that is not an id is used as it stands (that is what fpSup-Formats
    does for S16/OG2K/OG3K/OG3.5K).
    """
    text = stock.decode("utf-8-sig")
    lines = [line for line in text.replace("\r\n", "\n").split("\n") if line.strip()]
    header = [cell.strip() for cell in lines[0].split(",")]
    if header[:2] != ["NO", "TEXT"]:
        raise PlanError(f"this list's header is {lines[0]!r}; not a NO,TEXT list")
    out = list(lines)
    for offset, label in enumerate(extra_rows):
        if "," in label:
            raise PlanError(f"a row label cannot contain a comma: {label!r}")
        cells = [str(len(lines) + offset)] + [""] * (len(header) - 1)
        cells[1] = label
        for index, name in enumerate(header):
            if name.startswith("Enabled") or name.startswith("Enable"):
                cells[index] = "2" if name.endswith("2") else "1"
            elif name == "IMAGE":
                cells[index] = "blank"
            elif name == "Popup":
                cells[index] = "Popup"
        out.append(",".join(cells))
    return "﻿" + "\r\n".join(out) + "\r\n" == "" or \
        ("﻿" + "\r\n".join(out) + "\r\n").encode("utf-8")


def probe(row: int, text: str, target: str = RESOLUTION_LIST, image=None) -> dict:
    """The one-write experiment: replace one row's TEXT with a literal of the
    SAME LENGTH, in place.

    No repoint, no controller maximum, no size change -- so if the row's label
    does not change on the camera, the CSV is not being read at all and adding
    rows cannot work either.  That separates "the write did not land / the page
    was already built / the resource is cached" from everything else.
    """
    nbr = N.load(image)
    stock = nbr.read(target)
    entry = nbr.find(target)
    text_bytes = stock.decode("utf-8-sig")
    lines = text_bytes.replace("\r\n", "\n").split("\n")
    header = [c.strip() for c in lines[0].split(",")]
    if "TEXT" not in header:
        raise PlanError(f"{target} has no TEXT column")
    column = header.index("TEXT")
    for index, line in enumerate(lines[1:], start=1):
        cells = line.split(",")
        if len(cells) <= column or cells[0].strip() != str(row):
            continue
        old = cells[column]
        if len(text) != len(old):
            raise PlanError(f"row {row}'s TEXT is {old!r} ({len(old)} chars); "
                            f"the probe text must be the same length, {text!r} is {len(text)}")
        cells[column] = text
        lines[index] = ",".join(cells)
        break
    else:
        raise PlanError(f"{target} has no row numbered {row}")
    new = ("\ufeff" + "\r\n".join(l for l in lines if l.strip()) + "\r\n").encode("utf-8")
    if len(new) != len(stock):
        raise PlanError(f"the probe changed the size ({len(stock)} -> {len(new)})")
    return {"target": target, "row": row, "old": old, "new_text": text,
            "csv": new, "entry": entry,
            "sections": [{"address": entry.data_address, "data": new,
                          "what": f"row {row} TEXT {old} -> {text}, same length, in place"}]}


def plan(append: list[str], target: str = RESOLUTION_LIST,
         victim: str = DEFAULT_VICTIM, image=None) -> dict:
    nbr = N.load(image)
    stock = nbr.read(target)
    rows_before = len(nbr.menu(target))
    new_csv = build_csv(stock, append)
    rows_after = len(N.parse_menu(new_csv))
    if rows_after != rows_before + len(append):
        raise PlanError(f"expected {rows_before + len(append)} rows, built {rows_after}")

    spare = nbr.find(victim)
    if spare.path == nbr.find(target).path:
        raise PlanError("the new bytes cannot go over the list they replace")
    if spare.size < len(new_csv):
        raise PlanError(f"{victim} is {spare.size} B; the new CSV needs {len(new_csv)}")

    address, words = nbr.repoint(target, spare.data_address, len(new_csv))
    maximum = struct.pack(">f", float(rows_after - 1))
    stock_max = nbr.image[CONTROLLER_MAX - N.BASE:CONTROLLER_MAX - N.BASE + 4]

    sections = [
        {"address": spare.data_address, "data": new_csv,
         "what": f"the {rows_after}-row CSV, over {spare.path.rsplit('/', 1)[-1]}"},
        {"address": address, "data": words,
         "what": f"repoint {target.rsplit('/', 1)[-1]} at 0x{spare.data_address:08X}"},
        {"address": CONTROLLER_MAX, "data": maximum,
         "what": f"Settings controller max {struct.unpack('>f', stock_max)[0]} "
                 f"-> {float(rows_after - 1)}"},
    ]
    check_disjoint(sections)
    return {"target": target, "rows_before": rows_before, "rows_after": rows_after,
            "csv": new_csv, "victim": spare, "sections": sections,
            "stock_max": struct.unpack(">f", stock_max)[0]}


def check_disjoint(sections: list[dict]) -> None:
    spans = sorted((s["address"], s["address"] + len(s["data"])) for s in sections)
    for (a_start, a_end), (b_start, _b_end) in zip(spans, spans[1:]):
        if a_end > b_start:
            raise PlanError(f"sections overlap at 0x{b_start:08X}")


def autorun_lines(section: dict, image: bytes) -> list[str]:
    """`mem set` one 32-bit word at a time, padding with the STOCK bytes so a
    partial word at either end never clobbers a neighbour."""
    start = section["address"] & ~3
    end = (section["address"] + len(section["data"]) + 3) & ~3
    buffer = bytearray(image[start - N.BASE:end - N.BASE])
    buffer[section["address"] - start:section["address"] - start + len(section["data"])] = section["data"]
    return [f"mem set 0x{start + i:08X} 0x{struct.unpack_from('<I', buffer, i)[0]:08X}"
            for i in range(0, len(buffer), 4)]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--append", action="append", default=[], metavar="TEXT",
                        help="a row label, used literally; repeat for more rows")
    parser.add_argument("--probe", type=int, metavar="ROW",
                        help="the one-write experiment: rewrite this row's TEXT "
                             "in place with --text, same length, nothing else")
    parser.add_argument("--text", help="the probe label (must match the stock length)")
    parser.add_argument("--target", default=RESOLUTION_LIST)
    parser.add_argument("--victim", default=DEFAULT_VICTIM)
    parser.add_argument("--image")
    parser.add_argument("--json", metavar="FILE")
    parser.add_argument("--autorun", action="store_true",
                        help="also print the mem set lines")
    args = parser.parse_args(argv)
    if args.probe is not None:
        if not args.text:
            parser.error("--probe needs --text")
        result = probe(args.probe, args.text, args.target, args.image)
        print(f"{result['target']}  (one write, no repoint, no controller max)")
        print(f"  row {result['row']}: TEXT {result['old']!r} -> {result['new_text']!r}")
        print()
        print(result["csv"].decode("utf-8-sig").replace("\r\n", "\n").rstrip())
        print()
        section = result["sections"][0]
        print(f"  0x{section['address']:08X}  {len(section['data'])} B  (same size as stock)")
        print()
        print("  reboot, then open the page for the FIRST time.")
        print("  label changed -> the CSV really is read; go on to --append")
        print("  label unchanged -> stop: the write did not land, the page was "
              "already built, or the resource is cached")
        if args.autorun:
            nbr = N.load(args.image)
            print()
            for line in autorun_lines(section, nbr.image):
                print(line)
        return 0

    if not args.append:
        parser.error("give at least one --append or --probe")

    result = plan(args.append, args.target, args.victim, args.image)
    print(f"{result['target']}")
    print(f"  {result['rows_before']} rows -> {result['rows_after']}")
    print()
    print(result["csv"].decode("utf-8-sig").replace("\r\n", "\n").rstrip())
    print()
    total = 0
    for section in result["sections"]:
        print(f"  0x{section['address']:08X}  {len(section['data']):>4} B  {section['what']}")
        total += len(section["data"])
    print(f"  -- 3 writes, {total} bytes, no hook")
    print()
    print("  verified in Settings only; the Quick Set tile is untouched "
          "(research/ui/QUICK_SET.md)")

    if args.autorun:
        nbr = N.load(args.image)
        print()
        print("# `mem set` DROPS WRITES SILENTLY over the USB shell: read every")
        print("# word back.  For a card, hand the sections to the loader as VBIN")
        print("# sections instead, so they are journalled and restored at power-off.")
        for section in result["sections"]:
            print(f"# {section['what']}")
            for line in autorun_lines(section, nbr.image):
                print(line)

    if args.json:
        Path(args.json).write_text(json.dumps(
            {"target": result["target"], "rows": result["rows_after"],
             "sections": [{"address": "0x%08X" % s["address"],
                           "bytes": s["data"].hex(), "what": s["what"]}
                          for s in result["sections"]]}, indent=1) + "\n")
        print(f"\n-- wrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
