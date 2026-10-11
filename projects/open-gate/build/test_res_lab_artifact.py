#!/usr/bin/env python3
"""Inspect the final Sensor Lab card bytes, including the appended B2_5 block.

This is a parser and artifact audit, not an ARM or camera test.  It can inspect
an existing card after the source has moved on; ``--matrix`` builds fresh
plain/debug/Fast variants when the current plan is safe to package.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SHELL = ROOT / "fpSup/fp_usb_shell"
sys.path[:0] = [str(HERE), str(SHELL)]

VBIN_HEAD = 16
SLMP_HEAD = 0x24
SLMP_AT = 0xF000
PAGES_REF = 0x80000000
SL_MENU_STRINGS = 128  # sl_menu.h: distinct private string offsets
SL_MENU_TEXT = 2048    # sl_menu.h: copied strings, including NUL bytes
JOURNAL_EXCLUDED_CAVE = (0xC072D000, 0xC0735000)  # stage2.S
SHARED_CAVE_HI = 0xC0730000
ABORT_AT = 0xC072F080
DEBUG_STATE_AT = 0xC072F000
FIRMWARE = ROOT / "out/MAIN_c0000000.bin"
CORE_MAGIC = 0x534C434F
CORE_LAUNCH = HERE / "res_lab_user_launch.S"
JOURNAL_GATE = HERE / "res_lab_journal_gate.S"


class ArtifactError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ArtifactError(message)


def u32(data, offset):
    require(0 <= offset <= len(data) - 4, f"word outside file at {offset:#x}")
    return struct.unpack_from("<I", data, offset)[0]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def align4(value):
    return (value + 3) & ~3


def fnv(data):
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xFFFFFFFF
    return value


def vbin(blob, limit):
    """Decode exactly what the shared loader may read before SLMP_AT."""
    require(len(blob) >= VBIN_HEAD and blob[:4] == b"VBIN", "missing VBIN header")
    count, entry, body_bytes = struct.unpack_from("<III", blob, 4)
    table_end = VBIN_HEAD + 8 * count
    end = table_end + body_bytes
    require(count and table_end <= limit and end <= limit, "VBIN exceeds loader limit")
    require(body_bytes % 4 == 0, "unaligned VBIN body length")
    records = []
    cursor = table_end
    for index in range(count):
        address, size = struct.unpack_from("<II", blob, VBIN_HEAD + 8 * index)
        require(size and size % 4 == 0 and cursor + size <= end,
                f"VBIN section {index} has an invalid length")
        require(address % 4 == 0, f"VBIN section {index} has an unaligned destination")
        records.append((address, cursor, blob[cursor:cursor + size]))
        cursor += size
    require(cursor == end, "VBIN section table does not fill its body")
    require(not any(blob[end:limit]), "nonzero bytes between VBIN and SLMP")
    placed = sorted((a, a + len(data)) for a, _, data in records if a)
    require(all(hi <= 0x100000000 for _, hi in placed), "VBIN destination wraps 32 bits")
    require(all(hi <= next_lo for (_, hi), (next_lo, _) in zip(placed, placed[1:])),
            "overlapping absolute VBIN sections")
    return entry, records, end


def shared_lower_cave(records, manifest):
    """Allow only the shared builder's exact fixed sections below C0730000.

    The product plan is checked separately before packaging.  This check also
    catches an unexpected section added by the shared builder to the delivered
    VBIN.  Historical Fast cards whose abort source differs cannot be proved
    from the current assembly and are rejected rather than guessed at.
    """
    expected = {}
    if manifest["fast"]:
        source = SHELL / "asm/abort.S"
        name = "fpSup/fp_usb_shell/asm/abort.S"
        require(manifest.get("source_sha256", {}).get(name) == sha(source.read_bytes()),
                "Fast abort source differs from this artifact; lower cave cannot be verified")
        from armasm import assemble
        expected[ABORT_AT] = assemble(source, ["ECHO_SLOT=0xC0BAC2F8",
                                               "ECHO_ORIG=0xC03D99A0"])
    if manifest["debug"]:
        expected[DEBUG_STATE_AT] = bytes(96)
    seen = set()
    lo = JOURNAL_EXCLUDED_CAVE[0]
    for index, (address, _, data) in enumerate(records):
        end = address + len(data)
        if address >= SHARED_CAVE_HI or end <= lo:
            continue
        require(address in expected and address not in seen and data == expected[address],
                f"VBIN section {index} has an unrecognized lower cave write at {address:#010x}")
        seen.add(address)
    require(seen == expected.keys(),
            "VBIN is missing an expected shared lower cave section")
    return len(seen)


def entry_chain(entry, records, manifest):
    """Check the final file's trampoline and both staged installers."""
    source = SHELL / "asm/entries.S"
    candidates = [(a, offset, data) for a, offset, data in records if offset == entry]
    require(len(candidates) == 1 and candidates[0][0] == 0,
            "VBIN entry does not name one destination-zero trampoline")
    trampoline = candidates[0][2]
    migrated = manifest.get("core") is not None
    expected_count = (1 if manifest["debug"] else 0) + (1 if migrated else 0) + (1 if manifest.get("b25_menu") else 0)
    if not migrated:
        expected_count += 1  # historical fixed restore entry
    expected = [int(value, 16) for value in manifest["entry_check"]["entries"]]
    require(len(expected) == expected_count, "manifest entry count differs from card variant")
    source_hash = manifest.get("source_sha256", {}).get("fpSup/fp_usb_shell/asm/entries.S")
    if source_hash == sha(source.read_bytes()):
        from armasm import assemble, symbols
        table = symbols(source)["table"]
        code = assemble(source)
        require(trampoline[:table] == code[:table], "entry trampoline code differs")
    else:
        # Historical cards remain inspectable after entries.S changes.  Its
        # self-relative table word and the manifest's recorded chain locate
        # the table without trusting a newer assembly layout.
        possible = [offset for offset in range(0, len(trampoline) - 4 * (expected_count + 2) + 1, 4)
                    if u32(trampoline, offset) == entry + offset
                    and [u32(trampoline, offset + 4 * (i + 1)) for i in range(expected_count)] == expected
                    and u32(trampoline, offset + 4 * (expected_count + 1)) == 0]
        require(len(possible) == 1, "historical trampoline table is ambiguous")
        table = possible[0]
    require(u32(trampoline, table) == entry + table, "trampoline base offset differs")
    require(len(trampoline) == align4(table + 4 * (expected_count + 2)),
            "trampoline table has unexpected length")
    entries = [u32(trampoline, table + 4 * (i + 1)) for i in range(expected_count)]
    require(u32(trampoline, table + 4 * (expected_count + 1)) == 0,
            "trampoline table is not terminated")
    require(entries == expected,
            "final entry chain differs from the packaged entry check")
    menu_entry = None
    if manifest.get("b25_menu"):
        menu_entry = entries[-1] if migrated else entries[-2]
        installer = manifest["b25_menu"]["installer"]
        menu = [(a, offset, data) for a, offset, data in records
                if a == 0 and offset == menu_entry and len(data) == installer["blob_len"]]
        require(len(menu) == 1, "menu entry does not point to the expected run-in-place blob")
        require(installer["install"] & 1 and installer["ui"] & 1 and installer["live"] & 1,
                "menu installer Thumb entries are missing")
        require(0 < installer["c_base"] < installer["blob_len"] <= installer["state_off"]
                < installer["area_off"] < installer["block_bytes"],
                "menu installer memory layout is invalid")
        require(installer["area_off"] + installer["area_bytes"] == installer["block_bytes"],
                "menu installer area length is invalid")
        require(installer["area_bytes"] - 0x1000 > manifest["b25_menu"]["block_bytes"],
                "menu installer has insufficient file room")
        if migrated:
            require(installer.get("arm", 0) & 1 and
                    installer.get("core_offsets") == manifest["core"]["core_offsets"],
                    "late menu installer does not use the relocated core")
    if manifest["debug"]:
        worker = [(a, offset, data) for a, offset, data in records
                  if a == 0 and offset <= entries[0] < offset + len(data)]
        require(len(worker) == 1 and worker[0][1] != menu_entry,
                "debug worker entry is missing")
    if migrated:
        core_entry = entries[1 if manifest["debug"] else 0]
        require(core_entry < 0x40000000 and core_entry != 0,
                "Sensor Lab core entry is not run in place")
        require(len([1 for a, offset, data in records
                     if a == 0 and offset == core_entry and len(data) == manifest["core"]["launcher_bytes"]]) == 1,
                "core entry does not point to the expected run-in-place blob")
    else:
        last = entries[-1]
        require(last >= 0x40000000 and any(a <= last < a + len(data)
                for a, _, data in records if a >= 0x40000000),
                "Sensor Lab restore entry is not carried")
    return entries


def _address(value, label):
    """Read a manifest address without accepting booleans or truncated words."""
    try:
        number = int(value, 0) if isinstance(value, str) else value
    except ValueError as error:
        raise ArtifactError(f"{label} is not an address") from error
    require(type(number) is int and 0 <= number <= 0xFFFFFFFF,
            f"{label} is not a 32-bit address")
    return number


def _addresses(values, label):
    require(isinstance(values, list), f"{label} is not a list")
    result = [_address(value, label) for value in values]
    require(len(set(result)) == len(result), f"{label} repeats an address")
    return result


def _mov_kind(word):
    masked = word & 0x0FF00000
    return 1 if masked == 0x03000000 else 2 if masked == 0x03400000 else 0


def _mov_target(low, high):
    require((_mov_kind(low), _mov_kind(high)) == (1, 2)
            and (low >> 12 & 15) == (high >> 12 & 15)
            and (low >> 28) == (high >> 28),
            "USER relocation is not an adjacent ARM MOVW/MOVT pair")
    immediate = lambda word: ((word >> 16 & 15) << 12) | (word & 0xFFF)
    return (immediate(high) << 16) | immediate(low)


def migrated_core(records, entries, manifest):
    """Audit the staged core, its USER image and every deferred stock site.

    The build manifest records the installer's offsets, but this routine reads
    the actual descriptor tables and words from the delivered VBIN.  When the
    build sources still match, it also rebuilds the launcher and gate code.
    """
    core = manifest["core"]
    require(isinstance(core, dict), "core descriptor is missing")
    core_hooks = _addresses(core["core_hook_sites"], "core hook sites")
    late_hooks = _addresses(core["late_ui_hook_sites"], "late UI hook sites")
    all_hooks = _addresses(core["hook_sites"], "all hook sites")
    pointer_sites = _addresses(core["pointer_sites"], "pointer sites")
    require(core_hooks and core_hooks[-1] == 0xC043CCF8,
            "core hook order does not finish with picker")
    require(set(all_hooks) == set(core_hooks) | set(late_hooks)
            and len(all_hooks) == len(core_hooks) + len(late_hooks),
            "core and late UI hook declarations differ")
    require(bool(late_hooks) == bool(manifest.get("b25_menu")),
            "late UI hook declaration differs from menu variant")
    # rate rank / rate pair / bit pair (imx410_bit14) tables, plus the rate list
    require(len(pointer_sites) in (6, 8) and
            all(pointer_sites[i + 1] == pointer_sites[i] + 4 for i in range(0, len(pointer_sites), 2)),
            "external pointer sites are not three or four adjacent MOVW/MOVT pairs")
    required_sites = set(all_hooks) | set(pointer_sites)
    require(len(required_sites) == len(all_hooks) + len(pointer_sites),
            "hook and pointer sites overlap")
    declared = core["dynamic_stock_sites"]
    require(isinstance(declared, dict), "dynamic stock sites are not a mapping")
    stock_sites = {_address(address, "dynamic stock address"):
                   _address(value, "dynamic stock word")
                   for address, value in declared.items()}
    require(len(stock_sites) == len(declared) and set(stock_sites) == required_sites,
            "dynamic stock declarations do not match hook and pointer sites")
    firmware = FIRMWARE.read_bytes()
    placed_words = {address + index: u32(data, index)
                    for address, _, data in records if address >= 0x40000000
                    for index in range(0, len(data), 4)}
    for site, expected in stock_sites.items():
        require(site & 3 == 0 and not JOURNAL_EXCLUDED_CAVE[0] <= site < JOURNAL_EXCLUDED_CAVE[1],
                f"dynamic site {site:#010x} is unaligned or unjournaled")
        require(expected == u32(firmware, site - 0xC0000000),
                f"dynamic site {site:#010x} does not declare its factory word")
        require(placed_words.get(site) == expected,
                f"dynamic site {site:#010x} is armed by static VBIN bytes")

    core_entry = entries[1 if manifest["debug"] else 0]
    section = [(offset, data) for address, offset, data in records
               if address == 0 and offset == core_entry]
    require(len(section) == 1, "core entry does not name one run-in-place section")
    launcher = section[0][1]
    launcher_bytes = _address(core["launcher_bytes"], "launcher length")
    core_bytes = _address(core["core_bytes"], "USER core length")
    require(len(launcher) == launcher_bytes and launcher_bytes & 3 == 0,
            "core launcher length differs from the delivered section")
    offsets = core["table_offsets"]
    names = ("RELOCS_OFF", "GATE_PAIRS_OFF", "ARMS_OFF", "POINTERS_OFF", "IMAGE_OFF")
    require(isinstance(offsets, dict) and all(name in offsets for name in names),
            "core launcher table offsets are incomplete")
    positions = {name: _address(offsets[name], name) for name in names}
    require(all(value & 3 == 0 for value in positions.values()),
            "core launcher has an unaligned descriptor table")
    image_off = positions["IMAGE_OFF"]
    require(_address(core["core_blob_off"], "core blob offset") == image_off
            and image_off + core_bytes == launcher_bytes,
            "USER image offset or length differs from launcher")
    relocations = core["relocations"]
    require(isinstance(relocations, dict) and
            relocations.get("format") == "source_offset|kind<<30,target_offset" and
            relocations.get("record_bytes") == 8,
            "USER relocation descriptor format differs")
    reloc_off = _address(relocations["offset"], "relocation table offset")
    reloc_count = _address(relocations["count"], "relocation count")
    require(reloc_off == positions["RELOCS_OFF"] and
            0 < reloc_off < launcher_bytes and reloc_count <= core_bytes // 4,
            "USER relocation table is outside the launcher")
    gate_count = len(core_hooks) + len(pointer_sites)
    require(0 < gate_count <= 64 and 1 <= core["journal_max"] <= 512,   # res_lab_journal_gate.S MAX_SITES
            "journal gate bounds differ")
    journal_sections = sum(address >= 0x40000000 and
                           not JOURNAL_EXCLUDED_CAVE[0] <= address < JOURNAL_EXCLUDED_CAVE[1]
                           for address, _, _ in records)
    require(core["journal_max"] >= journal_sections,
            "journal gate cannot scan every stage2 record")
    require(positions["GATE_PAIRS_OFF"] == reloc_off + 8 * reloc_count
            and positions["ARMS_OFF"] == positions["GATE_PAIRS_OFF"] + 8 * gate_count
            and positions["POINTERS_OFF"] == positions["ARMS_OFF"] + 4 * len(core_hooks)
            and image_off == positions["POINTERS_OFF"] + 12 * (len(pointer_sites) // 2),
            "core launcher descriptor tables are not contiguous")

    core_image = launcher[image_off:]
    require(sha(core_image) == core["core_blob_sha256"],
            "USER core image differs from its descriptor hash")
    gate_off = _address(core["journal_gate_off"], "journal gate offset")
    magic_off = _address(core["core_magic_off"], "core magic offset")
    require(magic_off + 4 == gate_off and 0 < gate_off < core_bytes,
            "USER magic and journal gate are not adjacent")
    require(_address(core["core_magic_word"], "core magic word") == CORE_MAGIC
            and u32(core_image, magic_off) == CORE_MAGIC,
            "USER core magic differs")
    named = core["core_offsets"]
    require(isinstance(named, dict) and
            {"axis", "gtab", "flag", "coltab", "asptab", "recipe", "ratetab", "tmgtab",
             "rate240", "mark", "fmt_code", "restore_code", "core_magic"}.issubset(named),
            "USER core named offsets are incomplete")
    require(all(type(value) is int and 0 <= value < gate_off for value in named.values())
            and named["core_magic"] == magic_off,
            "USER core named offset is outside its image")

    previous_end = -1
    relocation_kinds = {1: 0, 2: 0}
    for index in range(reloc_count):
        packed, target = struct.unpack_from("<II", launcher, reloc_off + 8 * index)
        kind, source = packed >> 30, packed & 0x3FFFFFFF
        width = 4 if kind == 1 else 8
        require(kind in relocation_kinds and source & 3 == 0 and target & 3 == 0
                and source >= previous_end and source + width <= gate_off
                and target < gate_off,
                f"USER relocation {index} is outside its image or overlaps")
        old = (u32(core_image, source) if kind == 1 else
               _mov_target(u32(core_image, source), u32(core_image, source + 4)))
        require(0xC0730000 <= old < 0xC0736000,   # res_lab_user_pack.OLD_LOW..OLD_HIGH
                f"USER relocation {index} does not carry an old cave address")
        previous_end = source + width
        relocation_kinds[kind] += 1

    gate_sites = core_hooks + pointer_sites
    for index, site in enumerate(gate_sites):
        found_site, found_stock = struct.unpack_from("<II", launcher,
                                                      positions["GATE_PAIRS_OFF"] + 8 * index)
        require((found_site, found_stock) == (site, stock_sites[site]),
                f"journal gate pair {index} differs from a stock site")
    for index in range(len(core_hooks)):
        target = u32(launcher, positions["ARMS_OFF"] + 4 * index) & 0x7FFFFFFF
        require(target & 3 == 0 and target < gate_off,
                f"core hook target {index} is outside the USER image")
    for index in range(0, len(pointer_sites), 2):
        low, high, target = struct.unpack_from("<III", launcher,
                                               positions["POINTERS_OFF"] + 6 * index)
        require((low, high) == tuple(pointer_sites[index:index + 2])
                and target & 3 == 0 and target < gate_off,
                f"external pointer descriptor {index // 2} differs")

    sources = manifest.get("source_sha256", {})
    launcher_source = str(CORE_LAUNCH.relative_to(ROOT))
    if sources.get(launcher_source) == sha(CORE_LAUNCH.read_bytes()):
        from armasm import assemble
        definitions = dict(BLOCK_BYTES=(core_bytes + 63) & ~63,
                           CORE_BYTES=core_bytes, RELOC_COUNT=reloc_count,
                           GATE_COUNT=gate_count, HOOK_COUNT=len(core_hooks),
                           POINTER_COUNT=len(pointer_sites) // 2,
                           JOURNAL_GATE_OFF=gate_off, JOURNAL_MAX=core["journal_max"],
                           RESTORE_OFF=named["restore_code"], **positions)
        expected_code = assemble(CORE_LAUNCH,
                                 [f"{key}={value:#x}" for key, value in definitions.items()])
        require(launcher[:reloc_off] == expected_code,
                "core launcher code differs from its matching source")
    gate_source = str(JOURNAL_GATE.relative_to(ROOT))
    if sources.get(gate_source) == sha(JOURNAL_GATE.read_bytes()):
        from armasm import assemble
        require(core_image[gate_off:] == assemble(JOURNAL_GATE),
                "journal gate code differs from its matching source")
    return dict(launcher_bytes=launcher_bytes, user_bytes=core_bytes,
                relocations=reloc_count, relocation_kinds=relocation_kinds,
                core_hooks=len(core_hooks), late_ui_hooks=len(late_hooks),
                external_pointer_words=len(pointer_sites), stock_sites=len(stock_sites))


def slmp(blob, at):
    block = blob[at:]
    require(len(block) >= SLMP_HEAD and len(block) % 4 == 0, "SLMP block is missing or unaligned")
    magic, version, page_len, strings_len, count, b25, checksum, nbr_len, pages_len = (
        struct.unpack_from("<9I", block))
    require((magic, version, b25) == (0x504D4C53, 4, 0x19C130),
            "SLMP magic, version or B2_5 offset differs")
    require(page_len > 0 and count < len(block) // 8, "SLMP page or relocation count is invalid")
    refs_end = SLMP_HEAD + page_len + strings_len + 8 * count
    require(refs_end <= len(block), "SLMP page, strings or relocations are truncated")
    page = block[SLMP_HEAD:SLMP_HEAD + page_len]
    strings = block[SLMP_HEAD + page_len:SLMP_HEAD + page_len + strings_len]
    sys.path.insert(0, str(ROOT / "research/ui/tools/nbu_probe"))
    import nbu_format as nbu
    try:
        require(nbu.join(nbu.split(page)) == page, "B2_5 page record stream differs")
    except (AssertionError, IndexError, ValueError, struct.error) as error:
        raise ArtifactError(f"B2_5 page record stream is invalid: {error}") from error
    refs_at = SLMP_HEAD + page_len + strings_len
    cursor = refs_end
    nbr = b""
    pages = b""
    if nbr_len:
        require(not any(block[cursor:align4(cursor)]), "nonzero NBR alignment bytes")
        cursor = align4(cursor)
        require(nbr_len >= 20 and cursor + nbr_len <= len(block), "private NBR is truncated")
        nbr = block[cursor:cursor + nbr_len]
        require(nbr.startswith(b"NBR\0\x01\x05"), "private NBR version differs")
        cursor += nbr_len
    if pages_len:
        require(not any(block[cursor:align4(cursor)]), "nonzero pages alignment bytes")
        cursor = align4(cursor)
        require(pages_len >= 20 and cursor + pages_len <= len(block), "pages pack is truncated")
        pages = block[cursor:cursor + pages_len]
        require(pages.startswith(b"NBR\0\x01\x09"), "pages pack version differs")
        cursor += pages_len
    require(len(block) == align4(cursor) and not any(block[cursor:]),
            "SLMP has an unexpected tail")
    require(fnv(block[SLMP_HEAD:cursor]) == checksum, "SLMP checksum differs")
    page_refs = 0
    unique_strings = {}
    for index in range(count):
        destination, string = struct.unpack_from("<II", block, refs_at + 8 * index)
        into_pages = bool(destination & PAGES_REF)
        destination &= ~PAGES_REF
        room = pages_len if into_pages else page_len
        require(room >= 4 and destination <= room - 4,
                f"SLMP relocation {index} points outside its page")
        require(string < strings_len, f"SLMP relocation {index} has no string")
        stop = strings.find(b"\0", string)
        require(stop > string, f"SLMP relocation {index} has no terminated text")
        unique_strings[string] = stop - string + 1
        page_refs += into_pages
    require(len(unique_strings) <= SL_MENU_STRINGS,
            "SLMP exceeds the menu installer's private string count")
    require(sum(unique_strings.values()) <= SL_MENU_TEXT,
            "SLMP exceeds the menu installer's private text buffer")
    # These readers check the NBR index and referenced pages/lists, independently
    # of the SLMP wrapper.  They do not execute firmware or use Unicorn.
    from sl_pages import inspect_pack as inspect_pages
    from sl_lists import inspect_pack as inspect_lists
    if nbr:
        try:
            lists = inspect_lists(nbr)
        except (AssertionError, IndexError, ValueError, struct.error) as error:
            raise ArtifactError(f"private list pack is invalid: {error}") from error
    else:
        lists = {}
    if pages:
        try:
            page_map = inspect_pages(pages)
        except (AssertionError, IndexError, ValueError, struct.error) as error:
            raise ArtifactError(f"private pages pack is invalid: {error}") from error
    else:
        page_map = {}
    require(not page_refs or pages, "SLMP has flagged page references without a pages pack")
    return dict(bytes=len(block), page_bytes=page_len, strings_bytes=strings_len,
                relocations=count, page_relocations=page_refs, list_names=sorted(lists),
                page_names=sorted(page_map))


def inspect_binary(blob, manifest):
    menu = manifest.get("b25_menu")
    require(menu is not None, "card has no B2_5 menu manifest")
    at = menu["block_at"]
    require(at == SLMP_AT and len(blob) == menu["file_bytes"]
            and len(blob) - at == menu["block_bytes"],
            "final fpSup.BIN length differs from the menu manifest")
    entry, records, vbin_end = vbin(blob, at)
    require(entry == manifest["entry"] and len(records) == manifest["sections"],
            "VBIN header differs from the manifest")
    require(sha(blob[:at]) == manifest["entry_check"]["bin_sha256"],
            "final VBIN prefix differs from the verified pre-append BIN")
    require(len(records) == manifest["entry_check"]["sections"],
            "final VBIN section count differs from the entry check")
    lower_sections = shared_lower_cave(records, manifest)
    entries = entry_chain(entry, records, manifest)
    core = migrated_core(records, entries, manifest) if manifest.get("core") else None
    if core:
        # A migrated card may reserve only the common loader's exact lower
        # cave bytes.  The core/UI payload lives in allocated USER memory.
        from res_lab_cave_audit import (assert_no_res_lab_static_cave_sections,
                                           assert_pristine_cave_sections)
        try:
            assert_pristine_cave_sections(records, FIRMWARE.read_bytes())
            assert_no_res_lab_static_cave_sections(records)
        except ValueError as error:
            raise ArtifactError(str(error)) from error
    block = slmp(blob, at)
    if menu["test_page"] == "lab" and menu["custom_lists"]:
        require("SL_LAB" in block["page_names"] and
                {"SL_RATE", "SL_BIT", "SL_MODE", "SL_SIZE"}.issubset(block["list_names"]),
                "lab page or essential private lists are missing")
    return dict(vbin_bytes=vbin_end, loader_prefix_bytes=at, sections=len(records),
                shared_lower_cave_sections=lower_sections,
                entries=[f"0x{value:08X}" for value in entries], core=core, slmp=block)


def stock_cave_changes(blob):
    """Count changed original nonzero bytes in cave words stage2 never journals."""
    stock = FIRMWARE.read_bytes()
    _entry, records, _end = vbin(blob, SLMP_AT)
    lo, hi = JOURNAL_EXCLUDED_CAVE
    changed = []
    for address, _, data in records:
        if address >= hi or address + len(data) <= lo:
            continue
        for offset in range(max(0, lo - address), min(len(data), hi - address)):
            where = address + offset - 0xC0000000
            require(0 <= where < len(stock), "cave destination is outside the firmware image")
            original = stock[where]
            if original and data[offset] != original:
                changed.append(address + offset)
    return dict(count=len(changed), first=[f"0x{address:08X}" for address in changed[:12]])


def verify_card(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "MANIFEST.json").read_text())
    blob = (directory / "fpSup.BIN").read_bytes()
    for name, digest in manifest["artifacts"].items():
        require(sha((directory / name).read_bytes()) == digest,
                f"artifact hash differs: {name}")
    require(manifest["entry_check"]["autorun_sha256"] == manifest["artifacts"]["AutoRun.txt"],
            "AutoRun hash differs from the entry check")
    result = inspect_binary(blob, manifest)
    result["directory"] = str(directory)
    result["artifacts"] = manifest["artifacts"]
    result["source_differences"] = sorted(
        name for name, expected in manifest["source_sha256"].items()
        if not (ROOT / name).is_file() or sha((ROOT / name).read_bytes()) != expected)
    result["stock_nonzero_cave_changes"] = stock_cave_changes(blob)
    from res_lab_cave_audit import (assert_no_res_lab_static_cave_sections,
                                       assert_pristine_cave_sections)
    _entry, records, _end = vbin(blob, SLMP_AT)
    try:
        result["stock_cave_words_checked"] = assert_pristine_cave_sections(
            records, FIRMWARE.read_bytes())
        result["absolute_sections_checked"] = assert_no_res_lab_static_cave_sections(records)
    except ValueError as error:
        changed = result["stock_nonzero_cave_changes"]
        raise ArtifactError(f"{error}; {changed['count']} changed original nonzero bytes; "
                            f"first: {', '.join(changed['first'])}") from error
    require(manifest["persistent_settings_write"] == manifest["fast"],
            "Fast settings write declaration differs from the card variant")
    require(bool(manifest["loader_hook_mark"]) == (manifest["fast"] and manifest["debug"]),
            "Fast debug loader mark differs from the card variant")
    if manifest["fast"]:
        ui = sorted(p.name for p in (directory / "FPSUPUI").glob("*.BIN"))
        require(ui == [f"{index}.BIN" for index in range(5)], "Fast UI assets differ")
    return result


def mutation_checks(directory):
    """Prove malformed delivered bytes are rejected, using a real card in memory."""
    directory = Path(directory)
    manifest = json.loads((directory / "MANIFEST.json").read_text())
    original = (directory / "fpSup.BIN").read_bytes()
    baseline = inspect_binary(original, manifest)
    at = manifest["b25_menu"]["block_at"]
    cases = []

    def repair_slmp_checksum(damaged):
        page_len, strings_len, count = struct.unpack_from("<III", damaged, at + 8)
        nbr_len, pages_len = struct.unpack_from("<II", damaged, at + 0x1C)
        end = SLMP_HEAD + page_len + strings_len + 8 * count
        if nbr_len:
            end = align4(end) + nbr_len
        if pages_len:
            end = align4(end) + pages_len
        struct.pack_into("<I", damaged, at + 0x18,
                         fnv(damaged[at + SLMP_HEAD:at + end]))

    damaged = bytearray(original)
    damaged[at + 0x18] ^= 1
    cases.append(("checksum", damaged))

    damaged = bytearray(original)
    damaged[baseline["vbin_bytes"]] = 1
    cases.append(("VBIN padding", damaged))

    damaged = bytearray(original)
    page_len, strings_len, count = struct.unpack_from("<III", damaged, at + 8)
    require(count > 0, "fixture has no SLMP relocation")
    refs_at = at + SLMP_HEAD + page_len + strings_len
    struct.pack_into("<I", damaged, refs_at, 0x7FFFFFFF)
    # Repair the checksum so the relocation bounds check, rather than FNV,
    # must reject this mutation.  The exact unpadded body end is recovered
    # from the original header's component lengths.
    repair_slmp_checksum(damaged)
    cases.append(("relocation bounds", damaged))

    damaged = bytearray(original)
    damaged[at + SLMP_HEAD + page_len + strings_len + 8 * count] ^= 1
    cases.append(("alignment", damaged))

    # Keep every reference in bounds and its text NUL-terminated, then exceed
    # the installer's fixed 128-string table.  A checksum-only check would miss
    # this file, while the camera installer would reject it at runtime.
    damaged = bytearray(original)
    refs_at = at + SLMP_HEAD + page_len + strings_len
    strings_at = at + SLMP_HEAD + page_len
    strings = damaged[strings_at:refs_at]
    offsets = [u32(damaged, refs_at + 8 * index + 4) for index in range(count)]
    frequency = {offset: offsets.count(offset) for offset in set(offsets)}
    choices = sorted((strings.find(b"\0", offset) - offset + 1, offset)
                     for offset, byte in enumerate(strings)
                     if byte and offset not in frequency and strings.find(b"\0", offset) > offset)
    needed = SL_MENU_STRINGS + 1 - len(frequency)
    require(needed > 0 and len(choices) >= needed,
            "fixture cannot exercise the menu private string limit")
    changed = 0
    for index, old in enumerate(offsets):
        if changed == needed:
            break
        if frequency[old] > 1:
            frequency[old] -= 1
            struct.pack_into("<I", damaged, refs_at + 8 * index + 4,
                             choices[changed][1])
            changed += 1
    require(changed == needed, "fixture has too few duplicate private strings")
    repair_slmp_checksum(damaged)
    cases.append(("private string count", damaged))

    for label, damaged in cases:
        try:
            inspect_binary(bytes(damaged), manifest)
        except ArtifactError:
            continue
        raise AssertionError(f"{label} mutation escaped final-BIN validation")
    _entry, records, _end = vbin(original, at)
    lower_cases = [("unexpected lower cave section",
                    records + [(0xC072F200, 0, b"\0" * 4)])]
    for enabled, address, name in ((manifest["fast"], ABORT_AT, "Fast abort"),
                                   (manifest["debug"], DEBUG_STATE_AT, "debug state")):
        if not enabled:
            continue
        lower_cases.append((f"missing {name}",
                            [record for record in records if record[0] != address]))
        lower_cases.append((f"changed {name}",
                            [(a, offset, b"\xff" + data[1:] if a == address else data)
                             for a, offset, data in records]))
    for label, altered in lower_cases:
        try:
            shared_lower_cave(altered, manifest)
        except ArtifactError:
            continue
        raise AssertionError(f"{label} escaped lower-cave validation")
    core_labels = []
    if manifest.get("core"):
        # Call the semantic validator directly, so these tests do not pass
        # merely because the changed VBIN no longer matches its SHA-256.
        core = manifest["core"]
        entries = [int(value, 16) for value in manifest["entry_check"]["entries"]]
        core_entry = entries[1 if manifest["debug"] else 0]
        offsets = core["table_offsets"]
        stock_site = _address(core["core_hook_sites"][0], "first core hook")
        stock_record = next((file_at + stock_site - address
                             for address, file_at, data in records
                             if address <= stock_site < address + len(data)), None)
        require(stock_record is not None, "fixture lacks a deferred stock hook")
        def changed_word(file_at, value):
            damaged = bytearray(original)
            struct.pack_into("<I", damaged, file_at, value)
            return vbin(bytes(damaged), at)[1]
        core_cases = [
            ("deferred hook stock word", stock_record,
             u32(original, stock_record) ^ 1),
            ("USER core magic", core_entry + offsets["IMAGE_OFF"] + core["core_magic_off"],
             CORE_MAGIC ^ 1),
            ("journal gate stock word", core_entry + offsets["GATE_PAIRS_OFF"] + 4,
             u32(original, core_entry + offsets["GATE_PAIRS_OFF"] + 4) ^ 1),
            ("core hook target", core_entry + offsets["ARMS_OFF"], 0x7FFFFFFF),
            ("external pointer target", core_entry + offsets["POINTERS_OFF"] + 8,
             core["core_bytes"]),
        ]
        if core["relocations"]["count"]:
            first = core_entry + offsets["RELOCS_OFF"]
            core_cases.append(("USER relocation kind", first,
                               u32(original, first) & 0x3FFFFFFF))
        for label, file_at, word in core_cases:
            altered = changed_word(file_at, word)
            checked_manifest = manifest
            if label == "USER core magic":
                # Recompute the descriptor's image hash so the magic check,
                # rather than the earlier hash comparison, must reject it.
                changed_launcher = next(data for address, offset, data in altered
                                        if address == 0 and offset == core_entry)
                checked_manifest = {**manifest, "core": {**core,
                    "core_blob_sha256": sha(changed_launcher[offsets["IMAGE_OFF"]:])}}
            try:
                migrated_core(altered, entries, checked_manifest)
            except ArtifactError:
                core_labels.append(label)
                continue
            raise AssertionError(f"{label} escaped migrated core validation")
        from res_lab_cave_audit import assert_no_res_lab_static_cave_sections
        try:
            assert_no_res_lab_static_cave_sections(
                records + [(0xC0732A40, 0, b"\x00" * 4)])
        except ValueError:
            core_labels.append("fixed Sensor Lab cave section")
        else:
            raise AssertionError("fixed Sensor Lab cave section escaped validation")
    return dict(card=str(directory), baseline=baseline,
                rejected=[label for label, _ in cases + lower_cases] + core_labels)


def build_matrix(output, axis=None):
    import build_res_lab_card as builder
    import imx410_plan as plan

    require(not output.exists(), f"matrix output already exists: {output}")
    output.mkdir(parents=True)
    results = []
    for fast in (False, True):
        for debug in (False, True):
            name = ("fast-" if fast else "") + ("debug" if debug else "plain")
            directory = output / name
            builder.build(directory, debug=debug, fast=fast, axis=axis, b25_menu=True)
            result = verify_card(directory)
            require(not result["source_differences"], f"{name}: source changed since build")
            results.append(result)
            print(f"PASS {name}: final VBIN + SLMP + cave", flush=True)
            alternate = list(axis or plan.INITIAL_AXIS)
            alternate[5] = 1600 if alternate[5] != 1600 else 1500
            other = output / f"{name}-alternate-axis"
            builder.build(other, debug=debug, fast=fast, axis=alternate, b25_menu=True)
            alternate_result = verify_card(other)
            require(not alternate_result["source_differences"],
                    f"{name} alternate axis: source changed since build")
            require((other / "AutoRun.txt").read_bytes() == (directory / "AutoRun.txt").read_bytes(),
                    f"{name}: payload-only change altered AutoRun")
            require((other / "fpSup.BIN").read_bytes() != (directory / "fpSup.BIN").read_bytes(),
                    f"{name}: alternate axis did not alter the payload")
    report = dict(cards=results, autorun_independent=True, hardware_verified=False,
                  arm_emulation="separate; this parser does not execute the loader or installer")
    (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--card", type=Path, help="inspect an existing final card directory")
    choice.add_argument("--matrix", action="store_true", help="build and audit four B2_5 variants")
    choice.add_argument("--mutations", type=Path, help="test parser rejection using an existing card")
    parser.add_argument("--out", type=Path, help="new output directory for --matrix")
    parser.add_argument("--axis-preset")
    args = parser.parse_args()
    try:
        if args.card:
            result = verify_card(args.card)
            print(json.dumps(result, indent=2))
        elif args.mutations:
            print(json.dumps(mutation_checks(args.mutations), indent=2))
        else:
            require(args.out is not None, "--matrix needs --out")
            axis = None
            if args.axis_preset:
                from imx410_axis import preset_axis
                import imx410_plan as plan
                axis, _ = preset_axis(plan.Registry(), args.axis_preset)
            report = build_matrix(args.out, axis=axis)
            print(f"PASS {len(report['cards'])} card variants: {args.out / 'verification.json'}")
    except (ArtifactError, ValueError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
