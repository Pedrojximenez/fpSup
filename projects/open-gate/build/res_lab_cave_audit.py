"""Offline guards for Sensor Lab writes into the stage2 journal-excluded cave.

The shared stage2 deliberately does not save or restore C072D000..C0735000.
Consequently a fixed section in that range must never displace stock data, even
if the plan's hand-maintained layout says the address is available.  This module
reads the actual Ver.5.02 image supplied by the caller; it has no camera I/O.

The card builder packs the old source layout into an allocated USER block and
applies the strict section guard to its final VBIN.  Direct use of the old
fixed layout is rejected, as is any section pre-filling CAVE_BUMP.
The maintained loader, park stub and USB worker own separate addresses below
C0730000 and are checked by their own build contracts.
"""
from __future__ import annotations

import struct
from typing import Iterable


IMAGE_BASE = 0xC0000000
JOURNAL_EXCLUDED_LO = 0xC072D000
JOURNAL_EXCLUDED_HI = 0xC0735000
CAVE_ARENA_LO = 0xC072E064
CAVE_ARENA_HI = 0xC072EFB4
RES_LAB_STATIC_LO = 0xC0730000
RES_LAB_STATIC_HI = JOURNAL_EXCLUDED_HI


def _overlap(a: int, b: int, lo: int, hi: int) -> bool:
    return a < hi and lo < b


def _stock_word(image: bytes, address: int, image_base: int) -> int:
    offset = address - image_base
    if offset < 0 or offset + 4 > len(image):
        raise ValueError(f"firmware image does not cover cave word {address:#010x}")
    return struct.unpack_from("<I", image, offset)[0]


def _occupied_words(image: bytes, writes: Iterable[tuple[int, int, str]],
                    *, image_base: int, cave_lo: int, cave_hi: int) -> tuple[int, list[str]]:
    checked = 0
    findings = []
    for address, length, note in writes:
        if length < 0 or address < 0 or address + length > 0x100000000:
            raise ValueError(f"invalid planned write at {address:#x}, length {length}")
        if not length or not _overlap(address, address + length, cave_lo, cave_hi):
            continue
        first = max(address, cave_lo) & ~3
        last = (min(address + length, cave_hi) + 3) & ~3
        for word_address in range(first, last, 4):
            stock = _stock_word(image, word_address, image_base)
            checked += 1
            if stock:
                findings.append(f"{word_address:#010x} stock={stock:#010x} ({note})")
    return checked, findings


def _raise_if_occupied(checked: int, findings: list[str]) -> int:
    if findings:
        examples = "; ".join(findings[:8])
        suffix = f"; +{len(findings) - 8} more" if len(findings) > 8 else ""
        raise ValueError(
            f"Sensor Lab would overwrite {len(findings)} occupied factory cave words: "
            f"{examples}{suffix}"
        )
    return checked


def assert_pristine_cave_plan(items: Iterable[tuple[int, int, str]], image: bytes,
                              *, image_base: int = IMAGE_BASE,
                              cave_lo: int = JOURNAL_EXCLUDED_LO,
                              cave_hi: int = JOURNAL_EXCLUDED_HI) -> int:
    """Reject any plan word aimed at a nonzero stock word in the unjournaled cave.

    ``items`` is the exact output of ``imx410_plan.plan`` (address, value,
    annotation), before the card builder creates its output directory.  A stock
    word is reserved even when the proposed value happens to equal stock: the
    cave is not restored on a warm power cycle.  Returns cave words inspected.
    """
    writes = []
    for address, value, note in items:
        if address & 3 or not 0 <= value <= 0xFFFFFFFF:
            raise ValueError(f"invalid plan word at {address:#x}: {value!r}")
        writes.append((address, 4, str(note)))
    return _raise_if_occupied(*_occupied_words(
        image, writes, image_base=image_base, cave_lo=cave_lo, cave_hi=cave_hi))


def assert_pristine_cave_sections(records: Iterable[tuple[int, int, bytes]], image: bytes,
                                  *, image_base: int = IMAGE_BASE,
                                  cave_lo: int = JOURNAL_EXCLUDED_LO,
                                  cave_hi: int = JOURNAL_EXCLUDED_HI) -> int:
    """Check decoded final VBIN sections against the same stock image.

    ``records`` has the ``(destination, file_offset, data)`` shape returned by
    ``build_res_lab_card.decode``.  Destination zero and pool offsets are
    not absolute firmware writes.  Returns cave words inspected.
    """
    writes = ((address, len(data), f"VBIN section {index}, file offset {offset:#x}")
              for index, (address, offset, data) in enumerate(records)
              if address >= 0x40000000)
    return _raise_if_occupied(*_occupied_words(
        image, writes, image_base=image_base, cave_lo=cave_lo, cave_hi=cave_hi))


def assert_no_res_lab_static_cave_sections(
        records: Iterable[tuple[int, int, bytes]],
        *, sensor_lo: int = RES_LAB_STATIC_LO,
        sensor_hi: int = RES_LAB_STATIC_HI,
        arena_lo: int = CAVE_ARENA_LO,
        arena_hi: int = CAVE_ARENA_HI) -> int:
    """Strict gate for Sensor Lab payloads: no fixed cave sections.

    The arena is reserved for runtime CAVE_BUMP claims; VBIN may not pre-fill
    it.  Sensor Lab's old fixed address area is wholly forbidden, including the
    factory-occupied gap.  The loader/worker reserved area below C0730000 is
    outside this product-specific gate.  Returns absolute sections inspected.
    """
    writes = ((address, len(data), f"section {index}")
              for index, (address, _offset, data) in enumerate(records)
              if address >= 0x40000000 and data)
    return _assert_no_res_lab_static_cave_writes(
        writes, sensor_lo=sensor_lo, sensor_hi=sensor_hi,
        arena_lo=arena_lo, arena_hi=arena_hi)


def assert_no_res_lab_static_cave_plan(
        items: Iterable[tuple[int, int, str]],
        *, sensor_lo: int = JOURNAL_EXCLUDED_LO,
        sensor_hi: int = RES_LAB_STATIC_HI,
        arena_lo: int = CAVE_ARENA_LO,
        arena_hi: int = CAVE_ARENA_HI) -> int:
    """Reject product plan words anywhere in the journal-excluded cave.

    Unlike a full card, ``items`` contains no maintained loader or USB worker
    sections, so even stock-zero words below C0730000 are forbidden.
    """
    writes = []
    for address, value, note in items:
        if address & 3 or not 0 <= value <= 0xFFFFFFFF:
            raise ValueError(f"invalid plan word at {address:#x}: {value!r}")
        writes.append((address, 4, str(note)))
    return _assert_no_res_lab_static_cave_writes(
        writes, sensor_lo=sensor_lo, sensor_hi=sensor_hi,
        arena_lo=arena_lo, arena_hi=arena_hi)


def _assert_no_res_lab_static_cave_writes(
        writes: Iterable[tuple[int, int, str]], *, sensor_lo: int,
        sensor_hi: int, arena_lo: int, arena_hi: int) -> int:
    checked = 0
    findings = []
    for address, length, note in writes:
        if length < 0 or address < 0 or address + length > 0x100000000:
            raise ValueError(f"invalid static write {note} at {address:#x}, length {length}")
        if address < 0x40000000 or not length:
            continue
        checked += 1
        end = address + length
        if _overlap(address, end, arena_lo, arena_hi):
            findings.append(f"{note} [{address:#010x},{end:#010x}) pre-fills CAVE_BUMP arena")
        if _overlap(address, end, sensor_lo, sensor_hi):
            findings.append(f"{note} [{address:#010x},{end:#010x}) uses fixed Sensor Lab cave")
    if findings:
        examples = "; ".join(findings[:8])
        suffix = f"; +{len(findings) - 8} more" if len(findings) > 8 else ""
        raise ValueError(f"Sensor Lab static cave writes forbidden: {examples}{suffix}")
    return checked
