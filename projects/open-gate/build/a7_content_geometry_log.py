#!/usr/bin/env python3
"""Manage the read-only A7 content-geometry snapshot hook.

Commands:
    build   assemble and verify the local image; no camera access
    arm     stage the logger and patch ContSet_Adr1 after strict guards
    clear   clear the snapshot while the hook is paused
    read    decode the latest non-null A7 setup
    off     restore the stock instruction

All camera writes are single verified words.  The v4 profile override at
C043A19C remains active and is exact-guarded; this controller never changes it.
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
SOURCE = HERE / "a7_content_geometry_log.S"
LEGACY_SOURCE = HERE / "raw_dma_transition_log.S"

CODE = 0xC072F900
CODE_END = 0xC072FA00
LOG = 0xC072FA10
PATH_STATE = 0xC343A974
RWZM_CELLS = (
    ("live_h", 0xC0BD9A34),
    ("rec_h", 0xC0BE1684),
    ("live_v", 0xC0BD9EFC),
    ("rec_v", 0xC0BE1B4C),
)

HOOK_SITE = 0xC031C79C
HOOK_STOCK_WORD = 0xE5960038  # ldr r0,[r6,#0x38]

# The previous Cont_Pause logger must be restored before its cave is reused.
LEGACY_HOOK_SITE = 0xC031CC98
LEGACY_HOOK_STOCK_WORD = 0xE92D49F0

# The obsolete C01BE logger must also remain absent.
OLD_HOOK_SITE = 0xC01BE5E4
OLD_HOOK_STOCK_WORD = 0x0144F64D

# Preserve the successful v4 profile/canvas override.
PROFILE_HOOK_SITE = 0xC043A19C
PROFILE_HOOK_V4_WORD = 0xEB0BD597

MAGIC = 0x31473741  # little-endian ASCII "A7G1"
HEADER_WORDS = 4
SNAPSHOT_WORDS = 35
STATE_WORDS = HEADER_WORDS + SNAPSHOT_WORDS

# Previous call, hook site, following call, and its result move.
EXPECTED_CONTEXT = (
    0xFA0C654C,  # C031C798: blx C0635CD0
    HOOK_STOCK_WORD,
    0xFA0C562C,  # C031C7A0: blx C0632058
    0xE1A04000,  # C031C7A4: mov r4,r0
)
CONTEXT_BASE = HOOK_SITE - 4


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
    return blob


def legacy_image() -> bytes:
    return assemble(LEGACY_SOURCE)


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
    actual = read_words(CONTEXT_BASE, len(EXPECTED_CONTEXT))
    allowed_site = (
        (HOOK_STOCK_WORD, HOOK_ARMED_WORD)
        if allow_armed
        else (HOOK_STOCK_WORD,)
    )
    expected = ((EXPECTED_CONTEXT[0],), allowed_site) + tuple(
        (word,) for word in EXPECTED_CONTEXT[2:]
    )
    differences = []
    for index, (got, choices) in enumerate(zip(actual, expected)):
        if got not in choices:
            differences.append(
                f"0x{CONTEXT_BASE + index * 4:08X}=0x{got:08X} "
                f"(want {'/'.join(f'0x{x:08X}' for x in choices)})"
            )
    if differences:
        raise ProbeError("ContSet_Adr1 context mismatch: " + ", ".join(differences))


def verify_peer_hooks() -> None:
    legacy = read_words(LEGACY_HOOK_SITE, 1)[0]
    if legacy != LEGACY_HOOK_STOCK_WORD:
        raise ProbeError(
            f"Cont_Pause logger is still live/foreign: 0x{legacy:08X}; "
            "run raw_dma_transition_log.py off first"
        )
    old = read_words(OLD_HOOK_SITE, 1)[0]
    if old != OLD_HOOK_STOCK_WORD:
        raise ProbeError(f"old C01BE hook is live/foreign: 0x{old:08X}; no writes")
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
    legacy = legacy_image()
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
        print("A7 content logger already armed; state cleared safely")
        return
    if site != HOOK_STOCK_WORD:
        raise ProbeError(f"foreign hook word 0x{site:08X}; no writes")
    if not allowed_resident(blob):
        raise ProbeError("0xC072F900 contains neither known logger image; no writes")

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
        f"armed A7 content logger 0x{HOOK_SITE:08X} -> 0x{CODE:08X}; "
        f"{len(blob)}-byte log-only snapshot"
    )


def off() -> None:
    blob = image()
    verify_context(allow_armed=True)
    site = hook_word()
    if site == HOOK_STOCK_WORD:
        print("A7 content hook already stock")
        return
    if site != HOOK_ARMED_WORD:
        raise ProbeError(f"foreign hook word 0x{site:08X}; refusing to restore")
    if camera_bytes(CODE, len(blob)) != blob:
        raise ProbeError("hook target contains an unknown payload; refusing")
    write_word(HOOK_SITE, HOOK_STOCK_WORD)
    verify_context()
    print(f"restored 0x{HOOK_SITE:08X} = 0x{HOOK_STOCK_WORD:08X}")


def rwzm_shape(width: int, height: int, dh_word: int, dv_word: int) -> tuple[int, int] | None:
    dh = dh_word & 0x1FFF
    dv = dv_word & 0x1FFF
    if dh == 0 or dv == 0:
        return None
    out_w = (((dh >> 1) + (width & ~7) * 0x400) // dh) & ~7
    out_h = (((dv >> 1) + height * 0x400) // dv) & ~1
    return out_w, out_h


def read_log() -> None:
    site = hook_word()
    state = (
        "armed" if site == HOOK_ARMED_WORD
        else "stock" if site == HOOK_STOCK_WORD
        else f"foreign(0x{site:08X})"
    )
    values = read_words(LOG, STATE_WORDS)
    magic, calls, captures, reserved = values[:HEADER_WORDS]
    print(
        f"hook={state} calls={calls} captures={captures} "
        f"reserved=0x{reserved:08X}"
    )
    path = read_words(PATH_STATE, 8)
    enables = path[0]
    print(
        "live_path_state "
        f"enables=A0:{enables & 0xFF} A7:{(enables >> 8) & 0xFF} "
        f"A1:{(enables >> 16) & 0xFF} "
        f"selectors=A0:{path[1]} A7:{path[2]} "
        f"starts=A0:{path[5]} A7:{path[6]} A1:{path[7]}"
    )
    cells = tuple(read_words(address, 1)[0] for _, address in RWZM_CELLS)
    print(
        "profile122_RWZM "
        + " ".join(
            f"{name}=0x{value:X}"
            for (name, _), value in zip(RWZM_CELLS, cells)
        )
    )
    main = (
        read_words(0x300F06D0, 1)[0],
        read_words(0x300F0900, 1)[0],
        read_words(0x300F0908, 1)[0],
        read_words(0x300F090C, 1)[0],
    )
    print(
        f"live_main tap=0x{main[0]:08X} rwzm_on=0x{main[1]:08X} "
        f"rwzm_h=0x{main[2]:08X} rwzm_v=0x{main[3]:08X}"
    )
    if magic != MAGIC:
        print(f"log magic 0x{magic:08X} is not A7G1; log is absent or stale")
        return
    if captures == 0:
        print("no non-null A7 ContSet snapshot captured")
        return

    v = values[HEADER_WORDS:]
    (
        target, rawinfo,
        rec_w, rec_h, rec_rwzm_h, rec_rwzm_v, rec_bin_h, rec_bin_v,
        live_w, live_h, live_rwzm_h, live_rwzm_v, live_bin_h, live_bin_v,
        enable_word, a7_selector, a7_start,
        desc0, desc4, desc8, desc_c, desc10,
        bank_select,
        main_cfg, main_tap, main_rwzm_on, main_rwzm_h, main_rwzm_v,
        sub_cfg, sub_tap, sub_rwzm_on, sub_rwzm_h, sub_rwzm_v,
        a7_height, a7_pitch,
    ) = v

    enables = (
        enable_word & 0xFF,
        (enable_word >> 8) & 0xFF,
        (enable_word >> 16) & 0xFF,
    )
    desc_words = (desc0, desc4, desc8, desc_c, desc10)
    desc = struct.unpack("<10H", struct.pack("<5I", *desc_words))
    tap_names = {
        0: "Gain",
        1: "Crmf",
        2: "Vbin",
        3: "Hbin",
        4: "Hbin2",
        5: "Spc",
    }
    print(f"raw_target=0x{target:08X} RawInfo=0x{rawinfo:08X}")
    print(
        f"path enables=A0:{enables[0]} A7:{enables[1]} A1:{enables[2]} "
        f"A7_selector={a7_selector}({tap_names.get(a7_selector, 'unknown')}) "
        f"A7_start={a7_start} bank_select={bank_select}"
    )
    print(
        f"rec={rec_w}x{rec_h} rwzm=0x{rec_rwzm_h:X}/0x{rec_rwzm_v:X} "
        f"bin=0x{rec_bin_h:X}/0x{rec_bin_v:X}"
    )
    print(
        f"live={live_w}x{live_h} rwzm=0x{live_rwzm_h:X}/0x{live_rwzm_v:X} "
        f"bin=0x{live_bin_h:X}/0x{live_bin_v:X}"
    )
    print(
        "A7_desc_u16=" + ",".join(f"0x{x:04X}" for x in desc)
    )
    print(
        f"main cfg=0x{main_cfg:08X} tap=0x{main_tap:08X} "
        f"rwzm_on=0x{main_rwzm_on:08X} "
        f"rwzm_h=0x{main_rwzm_h:08X} rwzm_v=0x{main_rwzm_v:08X}"
    )
    print(
        f"sub  cfg=0x{sub_cfg:08X} tap=0x{sub_tap:08X} "
        f"rwzm_on=0x{sub_rwzm_on:08X} "
        f"rwzm_h=0x{sub_rwzm_h:08X} rwzm_v=0x{sub_rwzm_v:08X}"
    )
    print(
        f"A7_DMA height={a7_height} pitch32={a7_pitch} "
        f"pitch_bytes={a7_pitch * 4}"
    )

    active = (
        (main_rwzm_on, main_rwzm_h, main_rwzm_v)
        if bank_select == 1
        else (sub_rwzm_on, sub_rwzm_h, sub_rwzm_v)
    )
    derived = rwzm_shape(rec_w, rec_h, active[1], active[2])
    if active[0] & 1 and derived is not None:
        print(
            f"active_RWZM low13=0x{active[1] & 0x1FFF:X}/"
            f"0x{active[2] & 0x1FFF:X} => {derived[0]}x{derived[1]}"
        )
    else:
        print("active_RWZM is disabled or has a zero denominator")


def build() -> None:
    blob = image()
    print(f"payload={len(blob)} bytes code=0x{CODE:08X}..0x{CODE + len(blob):08X}")
    print(f"state={STATE_WORDS * 4} bytes log=0x{LOG:08X}..0x{LOG + STATE_WORDS * 4:08X}")
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
                raise ProbeError("A7 content logger is not armed")
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
