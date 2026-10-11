#!/usr/bin/env python3
"""Manage the read-only RAW DMA transition hook at Cont_Pause.

Commands:
    build   assemble and verify the local image; no camera access
    arm     stage the logger and patch Cont_Pause after strict guards
    clear   clear the transition state while the hook is paused
    read    print every captured geometry transition
    off     restore the stock Cont_Pause prologue

The payload is written one word at a time.  Bulk transfer helpers use the
0xC072FA00..0xC072FB00 area occupied by the live v4 profile counter and this
logger's state, so they must not be used while either hook is active.
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
SOURCE = HERE / "raw_dma_transition_log.S"
OLD_SOURCE = HERE / "producer_geometry_log.S"

CODE = 0xC072F900
CODE_END = 0xC072FA00
LOG = 0xC072FA10
LOG_END = 0xC072FAE0

HOOK_SITE = 0xC031CC98
HOOK_STOCK_WORD = 0xE92D49F0  # push {r4,r5,r6,r7,r8,r11,lr}

# The just-completed C01BECD8 diagnostic also uses CODE.  It must be restored
# before this image is staged; an exact check prevents live-code replacement.
OLD_HOOK_SITE = 0xC01BE5E4
OLD_HOOK_STOCK_WORD = 0x0144F64D

# The open-gate v4 profile override remains intentionally active and must not
# be altered by this controller.
PROFILE_HOOK_SITE = 0xC043A19C
PROFILE_HOOK_V4_WORD = 0xEB0BD597
PATH_STATE = 0xC343A974

MAGIC = 0x314C4452  # little-endian ASCII "RDL1"
HEADER_WORDS = 4
RECORD_WORDS = 12
RECORD_COUNT = 4
STATE_WORDS = HEADER_WORDS + RECORD_WORDS * RECORD_COUNT

EXPECTED_CONTEXT = (
    HOOK_STOCK_WORD,
    0xE24DD024,  # C031CC9C: sub sp,sp,#0x24
    0xE58D0020,  # C031CCA0: str r0,[sp,#0x20]
    0xE30A7950,  # C031CCA4: movw r7,#0xa950
)


class ProbeError(RuntimeError):
    pass


def arm_branch(site: int, target: int) -> int:
    offset = target - site - 8
    if offset & 3 or not -(1 << 25) <= offset < (1 << 25):
        raise ProbeError("ARM branch target is misaligned or out of range")
    return 0xEA000000 | ((offset >> 2) & 0x00FFFFFF)


HOOK_ARMED_WORD = arm_branch(HOOK_SITE, CODE)


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
        raise ProbeError("host state layout disagrees with assembly")
    return blob


def old_image() -> bytes:
    return assemble(OLD_SOURCE)


def read_words(address: int, count: int) -> tuple[int, ...]:
    got = mem_get(address, count)
    if len(got) != count or any(value is None for value in got):
        raise ProbeError(f"incomplete read at 0x{address:08X}: {got}")
    return tuple(int(value) for value in got)


def write_word(address: int, value: int, tries: int = 8) -> None:
    value &= 0xFFFFFFFF
    for _ in range(tries):
        if read_words(address, 1)[0] == value:
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


def hook_word() -> int:
    return read_words(HOOK_SITE, 1)[0]


def verify_context(allow_armed: bool = False) -> None:
    actual = read_words(HOOK_SITE, len(EXPECTED_CONTEXT))
    allowed_first = (HOOK_STOCK_WORD, HOOK_ARMED_WORD) if allow_armed else (HOOK_STOCK_WORD,)
    expected = (allowed_first,) + tuple((word,) for word in EXPECTED_CONTEXT[1:])
    differences = []
    for index, (got, choices) in enumerate(zip(actual, expected)):
        if got not in choices:
            differences.append(
                f"0x{HOOK_SITE + index * 4:08X}=0x{got:08X} "
                f"(want {'/'.join(f'0x{x:08X}' for x in choices)})"
            )
    if differences:
        raise ProbeError("Cont_Pause context mismatch: " + ", ".join(differences))


def verify_peer_hooks() -> None:
    old = read_words(OLD_HOOK_SITE, 1)[0]
    if old != OLD_HOOK_STOCK_WORD:
        raise ProbeError(
            f"old C01BE logger is still live/foreign: 0x{old:08X}; "
            "run producer_geometry_log.py off first"
        )
    profile = read_words(PROFILE_HOOK_SITE, 1)[0]
    if profile != PROFILE_HOOK_V4_WORD:
        raise ProbeError(
            f"v4 profile hook is not the expected branch: 0x{profile:08X}; no writes"
        )


def clear_state() -> None:
    for index in range(STATE_WORDS):
        write_word(LOG + index * 4, 0)
    write_word(LOG, MAGIC)


def stage_payload(blob: bytes) -> None:
    for index, value in enumerate(words(blob)):
        write_word(CODE + index * 4, value)
    if camera_bytes(CODE, len(blob)) != blob:
        raise ProbeError("payload readback differs after staging")


def allowed_resident(blob: bytes) -> bool:
    if camera_bytes(CODE, len(blob)) == blob:
        return True
    legacy = old_image()
    return camera_bytes(CODE, len(legacy)) == legacy


def clear_while_paused() -> None:
    write_word(HOOK_SITE, HOOK_STOCK_WORD)
    time.sleep(0.05)
    verify_context()
    clear_state()
    verify_peer_hooks()
    write_word(HOOK_SITE, HOOK_ARMED_WORD)
    if hook_word() != HOOK_ARMED_WORD:
        raise ProbeError("hook did not re-arm after clearing")


def arm() -> None:
    blob = image()
    verify_context(allow_armed=True)
    verify_peer_hooks()
    site = hook_word()

    if site == HOOK_ARMED_WORD:
        if camera_bytes(CODE, len(blob)) != blob:
            raise ProbeError("armed hook targets an unknown payload; refusing")
        clear_while_paused()
        print("RAW DMA logger already armed; state cleared safely")
        return
    if site != HOOK_STOCK_WORD:
        raise ProbeError(f"foreign hook word 0x{site:08X}; no writes")
    if not allowed_resident(blob):
        raise ProbeError("0xC072F900 contains neither known logger image; no writes")

    # Recheck all executable sites immediately before replacing the cave.
    verify_context()
    verify_peer_hooks()
    stage_payload(blob)
    clear_state()
    verify_peer_hooks()
    verify_context()
    write_word(HOOK_SITE, HOOK_ARMED_WORD)  # arm last
    if hook_word() != HOOK_ARMED_WORD:
        raise ProbeError("hook did not remain armed")
    print(
        f"armed Cont_Pause 0x{HOOK_SITE:08X} -> 0x{CODE:08X}; "
        f"{len(blob)}-byte log-only transition logger"
    )


def off() -> None:
    blob = image()
    verify_context(allow_armed=True)
    site = hook_word()
    if site == HOOK_STOCK_WORD:
        print("Cont_Pause hook already stock")
        return
    if site != HOOK_ARMED_WORD:
        raise ProbeError(f"foreign hook word 0x{site:08X}; refusing to restore")
    if camera_bytes(CODE, len(blob)) != blob:
        raise ProbeError("hook target contains an unknown payload; refusing")
    write_word(HOOK_SITE, HOOK_STOCK_WORD)
    verify_context()
    print(f"restored 0x{HOOK_SITE:08X} = 0x{HOOK_STOCK_WORD:08X}")


def read_log() -> None:
    site = hook_word()
    state = (
        "armed" if site == HOOK_ARMED_WORD
        else "stock" if site == HOOK_STOCK_WORD
        else f"foreign(0x{site:08X})"
    )
    values = read_words(LOG, STATE_WORDS)
    magic, transitions, last_sig, reserved = values[:HEADER_WORDS]
    print(
        f"hook={state} transitions={transitions} "
        f"last_sig=0x{last_sig:08X} reserved=0x{reserved:08X}"
    )
    if magic != MAGIC:
        print(f"log magic 0x{magic:08X} is not RDL1; log is absent or stale")
        return

    path = read_words(PATH_STATE, 8)
    path_enables = path[0]
    print(
        "live_path_state "
        f"enables=A0:{path_enables & 0xFF} "
        f"A7:{(path_enables >> 8) & 0xFF} "
        f"A1:{(path_enables >> 16) & 0xFF} "
        f"selectors=A0:{path[1]} A7:{path[2]} "
        f"starts=A0:{path[5]} A7:{path[6]} A1:{path[7]}"
    )

    names = ("A0", "A7", "A1")
    for slot in range(RECORD_COUNT):
        start = HEADER_WORDS + slot * RECORD_WORDS
        record = values[start:start + RECORD_WORDS]
        if record[0] == 0:
            continue
        sig, target, enable_word = record[:3]
        enables = (enable_word & 0xFF, (enable_word >> 8) & 0xFF, (enable_word >> 16) & 0xFF)
        print(
            f"[{slot}] raw_target=0x{target:08X} enables="
            f"A0:{enables[0]} A7:{enables[1]} A1:{enables[2]} "
            f"sig=0x{sig:08X}"
        )
        for index, name in enumerate(names):
            height, pitch, destination = record[3 + index * 3:6 + index * 3]
            print(
                f"    {name} height={height} (0x{height:X}) "
                f"pitch32={pitch} (0x{pitch:X}) "
                f"dest=0x{destination:08X}"
            )


def build() -> None:
    blob = image()
    print(f"payload={len(blob)} bytes code=0x{CODE:08X}..0x{CODE + len(blob):08X}")
    print(f"state={STATE_WORDS * 4} bytes log=0x{LOG:08X}..0x{LOG_END:08X}")
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
            if hook_word() != HOOK_ARMED_WORD:
                raise ProbeError("RAW DMA logger is not armed")
            clear_while_paused()
            print("state cleared")
        elif args.command == "read":
            read_log()
        else:
            off()
    except ProbeError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
