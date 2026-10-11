#!/usr/bin/env python3
"""Apply or restore the profile-122 RAW-ZOOM unity data patch.

The existing v4 hook changes the DNG/A7 envelope to 3032x2012.  Four profile
table cells still contain 0x640, so the IMX410 policy selects Hbin2 and feeds
1936x1288 content into that full envelope.  This patch changes both record and
live-view H/V ratios together from 0x640 to identity 0x400.

Commands:
    status  read guards and the four table cells; never writes
    on      exact-guard, then change all four cells to 0x400
    off     exact-guard, then restore all four cells to 0x640

Every write is a single verified word.  Mixed or foreign states are refused.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

SHELL_DIR = pathlib.Path(
    "/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell"
)
sys.path.insert(0, str(SHELL_DIR))

from putfile import mem_get, mem_set  # noqa: E402


STOCK = 0x640
UNITY = 0x400

# C0439D18 row 122 sources consumed by C0438018:
#   row+60/+D0 -> RawInfo+A0/+A4 (live-view H/V RWZM)
#   row+64/+D4 -> RawInfo+48/+4C (record H/V RWZM)
CELLS = (
    ("live_h", 0xC0BD9A34),
    ("rec_h",  0xC0BE1684),
    ("live_v", 0xC0BD9EFC),
    ("rec_v",  0xC0BE1B4C),
)

# Other independently verified pieces of the 3032x2012 @29.97 test state.
OPEN_GATE_INPUTS = (
    ("mode117_timing", 0xC0B59A28),
    ("picker_1_idx7", 0xC0BE5888),
    ("picker_2_idx7", 0xC0BE5A28),
    ("picker_3_idx7", 0xC0BE5BC8),
    ("movie_enum2_w", 0xC074222C),
    ("movie_enum2_h", 0xC0742230),
    ("still_pair_w", 0xC074288C),
    ("still_pair_h", 0xC0742890),
)

# No diagnostic hook may be live while the shared profile state changes.
PEER_GUARDS = (
    ("v4_profile", 0xC043A19C, 0xEB0BD597),
    ("A7_logger",  0xC031C79C, 0xE5960038),
    ("DMA_logger", 0xC031CC98, 0xE92D49F0),
    ("old_C01BE",  0xC01BE5E4, 0x0144F64D),
)


class PatchError(RuntimeError):
    pass


def read_words(address: int, count: int) -> tuple[int, ...]:
    got = mem_get(address, count)
    if len(got) != count or any(value is None for value in got):
        raise PatchError(f"incomplete read at 0x{address:08X}: {got}")
    return tuple(int(value) for value in got)


def write_word(address: int, value: int, tries: int = 8) -> None:
    value &= 0xFFFFFFFF
    for _ in range(tries):
        if read_words(address, 1)[0] == value:
            return
        mem_set(address, value)
    current = read_words(address, 1)[0]
    if current != value:
        raise PatchError(
            f"write verify failed at 0x{address:08X}: "
            f"wanted 0x{value:08X}, got 0x{current:08X}"
        )


def read_cells() -> tuple[int, ...]:
    return tuple(read_words(address, 1)[0] for _, address in CELLS)


def classify(values: tuple[int, ...]) -> str:
    if all(value == STOCK for value in values):
        return "stock"
    if all(value == UNITY for value in values):
        return "unity"
    return "mixed/foreign"


def verify_peers() -> None:
    differences = []
    for name, address, expected in PEER_GUARDS:
        actual = read_words(address, 1)[0]
        if actual != expected:
            differences.append(
                f"{name}@0x{address:08X}=0x{actual:08X} "
                f"(want 0x{expected:08X})"
            )
    if differences:
        raise PatchError("peer guard mismatch: " + ", ".join(differences))


def show_status(check_peers: bool = True) -> tuple[int, ...]:
    if check_peers:
        verify_peers()
    values = read_cells()
    print(f"RWZM state={classify(values)}")
    for (name, address), value in zip(CELLS, values):
        print(f"  {name:6} 0x{address:08X} = 0x{value:08X}")
    print("Open-gate prerequisite state:")
    for name, address in OPEN_GATE_INPUTS:
        value = read_words(address, 1)[0]
        print(f"  {name:16} 0x{address:08X} = 0x{value:08X}")
    return values


def set_state(target: int) -> None:
    verify_peers()
    before = read_cells()
    state = classify(before)
    expected_before = STOCK if target == UNITY else UNITY
    target_name = "unity" if target == UNITY else "stock"

    if all(value == target for value in before):
        print(f"RWZM patch already {target_name}")
        show_status()
        return
    if state == "mixed/foreign" or not all(
        value == expected_before for value in before
    ):
        raise PatchError(
            "four RWZM cells are mixed or foreign; refusing partial update: "
            + ", ".join(f"0x{x:08X}" for x in before)
        )

    written: list[int] = []
    try:
        for _, address in CELLS:
            # Recheck every cell immediately before changing it.
            current = read_words(address, 1)[0]
            if current != expected_before:
                raise PatchError(
                    f"concurrent change at 0x{address:08X}: "
                    f"0x{current:08X}, expected 0x{expected_before:08X}"
                )
            write_word(address, target)
            written.append(address)
    except Exception as exc:
        rollback_errors = []
        for address in reversed(written):
            try:
                write_word(address, expected_before)
            except Exception as rollback_exc:  # pragma: no cover - live failure path
                rollback_errors.append(f"0x{address:08X}: {rollback_exc}")
        suffix = (
            "; rollback errors: " + ", ".join(rollback_errors)
            if rollback_errors else "; completed writes rolled back"
        )
        raise PatchError(f"update aborted: {exc}{suffix}") from exc

    verify_peers()
    after = read_cells()
    if not all(value == target for value in after):
        raise PatchError(
            "post-write verification is not uniform: "
            + ", ".join(f"0x{x:08X}" for x in after)
        )
    print(f"RWZM patch set to {target_name} (0x{target:X})")
    show_status()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("status", "on", "off"))
    args = parser.parse_args()
    try:
        if args.command == "status":
            show_status()
        elif args.command == "on":
            set_state(UNITY)
        else:
            set_state(STOCK)
    except PatchError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
