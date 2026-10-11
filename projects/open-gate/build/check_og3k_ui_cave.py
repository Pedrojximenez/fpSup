#!/usr/bin/env python3
"""Read and validate the proposed OG3K private-NBR runtime range.

The firmware shell's textual ``mem get`` reply is capped at 16 KiB, so a
single 3732-byte request is silently incomplete.  This project-coupled helper
uses four bounded reads, decodes the daemon's hex framing, and refuses any
reply with a missing or duplicate word.  It never writes camera memory.

Each invocation still requires explicit user authorization for the four ranges
printed in ``READ_RANGES``.  The confirm token prevents an accidental run.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket


SOCKET = os.environ.get("FPSHD_SOCKET", "/tmp/fpshd.sock")
START = 0xC0793060
END = 0xC0793EF4
READ_RANGES = (
    (0xC0793060, 0x400),
    (0xC0793460, 0x400),
    (0xC0793860, 0x400),
    (0xC0793C60, 0x294),
)
CONFIRM = "0xC0793060:0xC0793EF4"
LINE = re.compile(r"get\s*:\s*A:0x([0-9a-fA-F]+),\s*D:0x([0-9a-fA-F]+)")


def shell(command: str) -> bytes:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(70)
    client.connect(SOCKET)
    # HEX makes short and long replies use the same binary-safe envelope.
    client.sendall(("HEX SHL " + command + "\n").encode("ascii"))
    reply = bytearray()
    while not reply.endswith(b"\n"):
        chunk = client.recv(65536)
        if not chunk:
            break
        reply.extend(chunk)
    client.close()
    if not reply.startswith(b"OKX "):
        raise RuntimeError(reply.decode(errors="replace").strip())
    return bytes.fromhex(reply[4:].strip().decode("ascii"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--confirm-read",
        required=True,
        help=f"must be exactly {CONFIRM} after the ranges receive user consent",
    )
    args = parser.parse_args()
    if args.confirm_read != CONFIRM:
        raise SystemExit(f"refusing read: --confirm-read must equal {CONFIRM}")

    words = {}
    replies = []
    for address, length in READ_RANGES:
        raw = shell(f"mem get 0x{address:08X},,0x{length:X}")
        text = raw.decode("ascii", errors="strict")
        rows = LINE.findall(text)
        expected = list(range(address, address + length, 4))
        if len(rows) != len(expected):
            raise RuntimeError(
                f"0x{address:08X}: got {len(rows)} words, expected {len(expected)}"
            )
        for expected_address, (got_address, got_value) in zip(expected, rows):
            got_address_int = int(got_address, 16)
            if got_address_int != expected_address or got_address_int in words:
                raise RuntimeError(
                    f"address coverage mismatch at 0x{expected_address:08X}: "
                    f"got 0x{got_address_int:08X}"
                )
            words[got_address_int] = int(got_value, 16)
        replies.append({
            "start": f"0x{address:08X}",
            "end_exclusive": f"0x{address + length:08X}",
            "words": len(rows),
        })

    expected_all = set(range(START, END, 4))
    if set(words) != expected_all:
        raise RuntimeError("combined reads do not cover the requested range exactly")
    nonzero = [
        {"address": f"0x{address:08X}", "value": f"0x{value:08X}"}
        for address, value in sorted(words.items()) if value
    ]
    print(json.dumps({
        "range": f"0x{START:08X}..0x{END:08X} (end-exclusive)",
        "bytes": END - START,
        "reads": replies,
        "all_zero": not nonzero,
        "nonzero_words": nonzero,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
