"""Build the run-in-place launcher for Sensor Lab's relocated USER image."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct

from armasm import assemble
from res_lab_user_pack import CorePack


SOURCE = Path(__file__).with_suffix(".S")
GATE_SOURCE = Path(__file__).with_name("res_lab_journal_gate.S")
CAVE_FIRST_VENEER = 0xC072E064
CAVE_LAST_VENEER = 0xC072EFA8
MAX_JOURNAL_RECORDS = 512


@dataclass(frozen=True)
class CoreLauncher:
    blob: bytes
    core_bytes: int
    journal_gate_off: int
    journal_max: int
    table_offsets: dict[str, int]


def _words(pairs):
    return b"".join(struct.pack("<II", *pair) for pair in pairs)


def build_blob(pack: CorePack, journal_max: int) -> CoreLauncher:
    """Emit only staging bytes; no fixed Sensor Lab cave address is written."""
    if not 1 <= journal_max <= MAX_JOURNAL_RECORDS:
        raise ValueError("journal record bound is outside the gate's range")
    hooks = pack.core_hooks
    if not hooks or hooks[-1].site != 0xC043CCF8:
        raise ValueError("core hook list must finish with the picker")
    if any(h.kind not in ("arm_b", "arm_bl") or h.target_offset & 3 or
           h.target_offset >= (1 << 31) for h in hooks):
        raise ValueError("core hook descriptor is not an aligned ARM target")
    for index, hook in enumerate(hooks):
        # Check the full 8-byte arena window, not just the initial bump.
        hook.veneer_word(CAVE_FIRST_VENEER + index * 8)
        hook.veneer_word(CAVE_LAST_VENEER - (len(hooks) - 1 - index) * 8)
    pointers = pack.external_pointers
    if any(p.high_site != p.low_site + 4 for p in pointers):
        raise ValueError("external MOVW/MOVT pair is not adjacent")

    gate = assemble(GATE_SOURCE)
    if len(gate) % 4 or len(pack.image) % 4:
        raise ValueError("USER core or journal gate is not word aligned")
    core_image = pack.image + gate
    gate_off = len(pack.image)
    gate_pairs = _words([(h.site, h.stock_word) for h in hooks] +
                        [(site, stock) for p in pointers for site, stock in
                         ((p.low_site, p.stock_low), (p.high_site, p.stock_high))])
    arms = b"".join(struct.pack("<I", h.target_offset |
                                (0x80000000 if h.kind == "arm_bl" else 0))
                    for h in hooks)
    ptrs = b"".join(struct.pack("<III", p.low_site, p.high_site, p.target_offset)
                    for p in pointers)
    relocs = pack.runtime_table()

    common = dict(BLOCK_BYTES=(len(core_image) + 63) & ~63,
                  CORE_BYTES=len(core_image), RELOC_COUNT=len(pack.relocations),
                  GATE_COUNT=len(hooks) + 2 * len(pointers),
                  HOOK_COUNT=len(hooks), POINTER_COUNT=len(pointers),
                  JOURNAL_GATE_OFF=gate_off, JOURNAL_MAX=journal_max,
                  RESTORE_OFF=pack.address_map(0xC0731600))
    if common["GATE_COUNT"] > 64:            # res_lab_journal_gate.S MAX_SITES
        raise ValueError("core gate has too many stock-word sites")
    names = ("RELOCS_OFF", "GATE_PAIRS_OFF", "ARMS_OFF", "POINTERS_OFF", "IMAGE_OFF")

    def code(offsets):
        values = {**common, **offsets}
        return assemble(SOURCE, [f"{key}={value:#x}" for key, value in values.items()])

    stub = code(dict.fromkeys(names, 0))
    cursor = len(stub)
    offsets = {}
    for name, data in zip(names, (relocs, gate_pairs, arms, ptrs, core_image)):
        offsets[name] = cursor
        cursor += len(data)
    launcher = code(offsets)
    if len(launcher) != len(stub):
        raise ValueError("launcher changed length between its two assembly passes")
    blob = launcher + relocs + gate_pairs + arms + ptrs + core_image
    if len(blob) != cursor or len(blob) % 4:
        raise ValueError("launcher section is not an aligned, complete blob")
    return CoreLauncher(blob, len(core_image), gate_off, journal_max, offsets)
