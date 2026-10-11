#!/usr/bin/env python3
"""Manage the read-only producer geometry hook at 0xC01BE5E4.

Commands:
    build   assemble and verify local layout; no camera access
    arm     safely replace the known first-hit logger or arm from stock
    clear   clear only the geometry log
    read    print every distinct captured tuple
    off     restore the stock instruction

The payload is deliberately written one word at a time.  The faster bulk
loader occupies 0xC072FA00..0xC072FB00, which overlaps both the existing v4
row-hook counter and this logger's state while those hooks are live.
"""

from __future__ import annotations

import argparse
import pathlib
import struct
import sys
import time

SHELL_DIR = pathlib.Path(
    "/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell"
)
sys.path.insert(0, str(SHELL_DIR))

from armasm import assemble  # noqa: E402
from putfile import mem_get, mem_set  # noqa: E402


HERE = pathlib.Path(__file__).resolve().parent
SOURCE = HERE / "producer_geometry_log.S"

CODE = 0xC072F900
CODE_END = 0xC072FA00
LOG = 0xC072FA10
LOG_END = 0xC072FAE8

HOOK_SITE = 0xC01BE5E4
HOOK_STOCK_WORD = 0x0144F64D       # movw r1, #0xd844
MAGIC = 0x324C4750                 # "PGL2"

HEADER_WORDS = 4
RECORD_WORDS = 10
RECORD_COUNT = 5
STATE_WORDS = HEADER_WORDS + RECORD_WORDS * RECORD_COUNT

# Exact 76-byte first-hit logger found on the camera before this version was
# installed.  It is accepted only to support a guarded migration; any other
# image behind the same branch is foreign and is never overwritten.
LEGACY_V1_IMAGE = bytes.fromhex(
    "2fb54ff68025ccf272052968002917d101212960a1686960e168a960daf85810"
    "e960daf860102961daf874106961daf87810a961daf87c10e961daf880102962"
    "bde82f404df6440170470000"
)

# The follow-up wide-dump logger was also observed live.  Its search loop checks
# slot zero repeatedly instead of indexing the current slot, so a second source
# width rapidly consumes every remaining entry.  Accept it only as another
# exact, known image that may be stopped before installing this implementation.
LEGACY_V2_IMAGE = bytes.fromhex(
    "2fb54ff68025ccf27205daf85820daf8603028680021814209d205f18005d5f8"
    "00c0a5f18005944522d00131f3e705281ed2c10101f1800129440a604b60002"
    "054f800c001f1080242f800c004302028f6db002000f150025af802c001f128"
    "0242f800c004303828f4db286801302860bde82f404df6440170470000"
)

LEGACY_IMAGES = (LEGACY_V1_IMAGE, LEGACY_V2_IMAGE)


class ProbeError(RuntimeError):
    pass


def thumb_bl(site: int, target: int) -> int:
    """Encode a Thumb-2 BL as the little-endian word accepted by mem set."""
    offset = target - (site + 4)
    if offset & 1 or not -(1 << 24) <= offset < (1 << 24):
        raise ProbeError("Thumb BL target is misaligned or out of range")
    sign = (offset >> 24) & 1
    i1 = (offset >> 23) & 1
    i2 = (offset >> 22) & 1
    hw1 = 0xF000 | (sign << 10) | ((offset >> 12) & 0x3FF)
    hw2 = (
        0xD000
        | (((1 ^ i1 ^ sign) & 1) << 13)
        | (((1 ^ i2 ^ sign) & 1) << 11)
        | ((offset >> 1) & 0x7FF)
    )
    return struct.unpack("<I", struct.pack("<HH", hw1, hw2))[0]


HOOK_ARMED_WORD = thumb_bl(HOOK_SITE, CODE)


def words(blob: bytes) -> tuple[int, ...]:
    if len(blob) & 3:
        raise ProbeError("assembled image is not word aligned")
    return struct.unpack(f"<{len(blob) // 4}I", blob)


def image() -> bytes:
    blob = assemble(SOURCE)
    if CODE + len(blob) > CODE_END:
        raise ProbeError(
            f"payload is {len(blob)} bytes and crosses 0x{CODE_END:08X}"
        )
    if LOG + STATE_WORDS * 4 != LOG_END:
        raise ProbeError("host log layout disagrees with the assembly layout")
    return blob


def read_words(address: int, count: int) -> tuple[int, ...]:
    got = mem_get(address, count)
    if len(got) != count or any(value is None for value in got):
        raise ProbeError(
            f"incomplete read at 0x{address:08X}: {got}"
        )
    return tuple(int(value) for value in got)


def write_word(address: int, value: int, tries: int = 8) -> None:
    value &= 0xFFFFFFFF
    for _ in range(tries):
        current = read_words(address, 1)[0]
        if current == value:
            return
        mem_set(address, value)
    current = read_words(address, 1)[0]
    if current != value:
        raise ProbeError(
            f"write verify failed at 0x{address:08X}: "
            f"wanted 0x{value:08X}, got 0x{current:08X}"
        )


def camera_bytes(address: int, length: int) -> bytes:
    values = read_words(address, (length + 3) // 4)
    return struct.pack(f"<{len(values)}I", *values)[:length]


def payload_state(blob: bytes) -> str:
    current = camera_bytes(CODE, len(blob))
    if current == blob:
        return "current"
    for index, legacy_image in enumerate(LEGACY_IMAGES, 1):
        legacy = camera_bytes(CODE, len(legacy_image))
        if legacy == legacy_image:
            return f"legacy-v{index}"
    return "foreign"


def hook_word() -> int:
    return read_words(HOOK_SITE, 1)[0]


def clear_log() -> None:
    for index in range(STATE_WORDS):
        write_word(LOG + index * 4, 0)
    write_word(LOG, MAGIC)


def clear_while_paused() -> None:
    """Clear an armed logger without racing its writes to the state block."""
    write_word(HOOK_SITE, HOOK_STOCK_WORD)
    time.sleep(0.05)
    if hook_word() != HOOK_STOCK_WORD:
        raise ProbeError("could not pause the hook before clearing")
    clear_log()
    write_word(HOOK_SITE, HOOK_ARMED_WORD)
    if hook_word() != HOOK_ARMED_WORD:
        raise ProbeError("hook did not re-arm after clearing")


def stage_payload(blob: bytes) -> None:
    for index, value in enumerate(words(blob)):
        write_word(CODE + index * 4, value)
    if camera_bytes(CODE, len(blob)) != blob:
        raise ProbeError("payload readback differs after staging")


def arm() -> None:
    blob = image()
    site = hook_word()

    if site == HOOK_ARMED_WORD:
        state = payload_state(blob)
        if state == "current":
            clear_while_paused()
            print("logger already armed; hook paused, log cleared, hook re-armed")
            return
        if not state.startswith("legacy-"):
            raise ProbeError(
                "hook targets 0xC072F900 but the resident payload is unknown; "
                "refusing to overwrite live code"
            )
        # Stop new entries before replacing the known first-hit implementation.
        write_word(HOOK_SITE, HOOK_STOCK_WORD)
        time.sleep(0.05)
        if hook_word() != HOOK_STOCK_WORD:
            raise ProbeError("could not restore the stock hook before migration")
    elif site != HOOK_STOCK_WORD:
        raise ProbeError(
            f"foreign hook word 0x{site:08X} at 0x{HOOK_SITE:08X}; no writes"
        )

    stage_payload(blob)
    clear_log()
    write_word(HOOK_SITE, HOOK_ARMED_WORD)   # arm last
    if hook_word() != HOOK_ARMED_WORD:
        raise ProbeError("hook did not remain armed")
    print(
        f"armed 0x{HOOK_SITE:08X} -> 0x{CODE:08X}; "
        f"{len(blob)}-byte read-only logger, {RECORD_COUNT} unique slots"
    )


def off() -> None:
    site = hook_word()
    if site == HOOK_STOCK_WORD:
        print("hook already stock")
        return
    if site != HOOK_ARMED_WORD:
        raise ProbeError(
            f"foreign hook word 0x{site:08X}; refusing to restore over it"
        )
    blob = image()
    state = payload_state(blob)
    if state != "current" and not state.startswith("legacy-"):
        raise ProbeError("hook target contains an unknown payload; refusing")
    write_word(HOOK_SITE, HOOK_STOCK_WORD)
    print(f"restored 0x{HOOK_SITE:08X} = 0x{HOOK_STOCK_WORD:08X}")


def read_log() -> None:
    site = hook_word()
    state = (
        "armed" if site == HOOK_ARMED_WORD
        else "stock" if site == HOOK_STOCK_WORD
        else f"foreign(0x{site:08X})"
    )
    values = read_words(LOG, STATE_WORDS)
    magic, total, unique, dropped = values[:HEADER_WORDS]
    print(f"hook={state}  calls={total}  unique={unique}  dropped={dropped}")
    if magic != MAGIC:
        print(f"log magic 0x{magic:08X} is not PGL2; log is absent or stale")
        return

    labels = (
        "sig", "channel", "producer_w", "producer_h", "source_w",
        "source_h", "target_w", "target_h", "crop_x", "crop_y",
    )
    for slot in range(RECORD_COUNT):
        start = HEADER_WORDS + slot * RECORD_WORDS
        record = values[start:start + RECORD_WORDS]
        if record[0] == 0:
            continue
        item = dict(zip(labels, record))
        print(
            f"[{slot}] ch={item['channel']}  "
            f"producer={item['producer_w']}x{item['producer_h']}  "
            f"source={item['source_w']}x{item['source_h']}  "
            f"target={item['target_w']}x{item['target_h']}  "
            f"crop={item['crop_x']},{item['crop_y']}  "
            f"sig=0x{item['sig']:08X}"
        )


def build() -> None:
    blob = image()
    print(f"payload={len(blob)} bytes  code=0x{CODE:08X}..0x{CODE + len(blob):08X}")
    print(f"state={STATE_WORDS * 4} bytes  log=0x{LOG:08X}..0x{LOG_END:08X}")
    print(f"hook stock=0x{HOOK_STOCK_WORD:08X} armed=0x{HOOK_ARMED_WORD:08X}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "arm", "clear", "read", "off"))
    args = parser.parse_args()
    try:
        if args.command == "build":
            build()
        elif args.command == "arm":
            arm()
        elif args.command == "clear":
            blob = image()
            if hook_word() != HOOK_ARMED_WORD or payload_state(blob) != "current":
                raise ProbeError("current logger is not armed; refusing to clear")
            clear_while_paused()
            print("hook paused, log cleared, hook re-armed")
        elif args.command == "read":
            read_log()
        else:
            off()
    except (OSError, ProbeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
