#!/usr/bin/env python3
"""Derive the deployable FPShell AutoRun from the verified v27 baseline."""

import argparse
import pathlib


DEFAULT_SOURCE = pathlib.Path(__file__).with_name("camera") / "AutoRun_v27_reference.txt"
DEFAULT_OUTPUT = pathlib.Path(__file__).with_name("dist") / "AutoRun.txt"


def compact(lines: list[str], settle_ms: int) -> list[str]:
    output = [
        "# FPShell Compact v1 - derived from verified v27/v29 transport.\n",
        "# One flash: started. Two flashes: connect USB. Three flashes: finished.\n",
        "# Four bounded FPSH echo rounds; no diagnostic files are written to SD.\n",
    ]
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("mem save "):
            continue
        output.append(line)
        if stripped == "log":
            output.append(f"ctrl sleep {settle_ms}\n")
    while output and not output[-1].strip():
        output.pop()
    output.append("\n")
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=pathlib.Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=pathlib.Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--settle-ms", type=int, default=200)
    args = parser.parse_args()
    if not 50 <= args.settle_ms <= 2000:
        parser.error("--settle-ms must be between 50 and 2000")
    lines = args.source.read_text(encoding="utf-8").splitlines(keepends=True)
    rendered = compact(lines, args.settle_ms)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as destination:
        destination.write("".join(rendered))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
