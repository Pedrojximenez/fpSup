#!/usr/bin/env python3
"""Which DRAM window is coherent with the codec's DMA writes.

The firmware's own idiom, from FUN_c062f510, is: the CPU works through the
`| 0xC0000000` alias, calls FUN_c000e91c to clean the data cache, and hands the
`| 0x40000000` address to the hardware. That says the 0xC view is cached. It
does NOT say what the CPU sees through the 0x4 view, and the flush path we hook
contains no cache maintenance that the decompiler can reach -- the call graph
runs into indirect dispatch after 22 functions.

So it is measured instead, and the measurement costs nothing extra: after a
`--keep` encode the codec has already written its output by DMA, and the same
bytes can be read through both windows.

    0x4 view shows SOI, 0xC view shows stale  ->  0x4 is the coherent window
    both show SOI                             ->  either the aliases are
                                                  coherent or the cache never
                                                  held those lines; inconclusive
                                                  on its own
    0x4 view stale                            ->  the CPU's 0x4 view is cached
                                                  too, and a clean is required

This only reads. It writes nothing to the camera and does not free anything.
"""
import argparse
import json
import re
import subprocess

SOI = "FFD8"
SOF3 = "FFC3"


def read_words(fpsh, address, count):
    out = subprocess.run([str(fpsh), "mem", "get", f"0x{address:08X},,0x{count * 4:X}"],
                         capture_output=True, text=True, timeout=75).stdout
    words = {}
    for at, data in re.findall(r"A:0x([0-9a-fA-F]+),\s*D:0x([0-9a-fA-F]+)", out):
        words[int(at, 16)] = int(data, 16)
    return [words.get(address + i * 4) for i in range(count)]


def looks_like_a_tile(words):
    """A lossless-JPEG tile starts ff d8 ff c3, little-endian in word 0."""
    if not words or words[0] is None:
        return False
    first = f"{words[0]:08X}"
    return first[6:8] + first[4:6] == SOI and first[2:4] + first[0:2] == SOF3


def compare(fpsh, handle, words=8):
    cached = handle | 0x80000000
    uncached_view = read_words(fpsh, handle, words)
    cached_view = read_words(fpsh, cached, words)
    report = {
        "handle": f"0x{handle:08X}",
        "cached_alias": f"0x{cached:08X}",
        "uncached_words": [None if w is None else f"0x{w:08X}" for w in uncached_view],
        "cached_words": [None if w is None else f"0x{w:08X}" for w in cached_view],
        "uncached_shows_tile": looks_like_a_tile(uncached_view),
        "cached_shows_tile": looks_like_a_tile(cached_view),
        "views_agree": uncached_view == cached_view,
    }
    if report["uncached_shows_tile"] and not report["cached_shows_tile"]:
        report["verdict"] = ("0x4 is the window coherent with codec DMA; the 0xC "
                             "alias is cached and stale. Write the header through "
                             "0x4, or clean before handing over.")
    elif report["uncached_shows_tile"] and report["cached_shows_tile"]:
        report["verdict"] = ("both views show the payload; inconclusive on its "
                             "own, since the cache may simply never have held "
                             "these lines")
    elif not report["uncached_shows_tile"]:
        report["verdict"] = ("the 0x4 view does not show a tile; either the "
                             "payload is elsewhere or that view is cached too")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fpsh", required=True)
    parser.add_argument("--handle", required=True, type=lambda v: int(v, 0),
                        help="the retained arena handle from status")
    parser.add_argument("--words", type=int, default=8)
    args = parser.parse_args()
    print(json.dumps(compare(args.fpsh, args.handle, args.words), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
