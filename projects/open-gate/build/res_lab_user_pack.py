"""Pack Sensor Lab's formerly fixed cave regions into one USER allocation.

This is an offline transformer, not a loader or an installer.  The caller must
allocate USER memory, copy ``image``, apply ``runtime_table`` after the copy,
publish D/I caches, and only then install its journalled external pointers and
hook veneers.  No product word belongs in the stage2 journal-excluded cave.

The packed image keeps each declared region intact, including unwritten state
bytes (which start at zero), but removes all gaps between regions.  A single
old-address map drives both internal relocations and external patch metadata.

``runtime_table`` is a sequence of little-endian eight-byte records:
    (source_image_offset | kind << 30, target_image_offset)
kind 1 = ABS32, kind 2 = adjacent ARM MOVW/MOVT.  ARM B/BL between packed
regions are rewritten offline because the USER base cancels from the delta.
External B/BL and Thumb B.W hooks need near veneers and are only described;
they are never inserted into ``image`` or emitted as static plan writes.
"""
from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Iterable


ROM_BASE = 0xC0000000
OLD_LOW = 0xC0730000
OLD_HIGH = 0xC0736000   # source-only labels up to here (imx410_plan.SOURCE_ONLY)
CORE_MAGIC = 0x534C434F  # shared identity word; checked by the late UI
ABS32 = 1
ARM_MOV32 = 2


@dataclass(frozen=True)
class Span:
    old_start: int
    old_end: int
    offset: int
    name: str


@dataclass(frozen=True)
class Relocation:
    kind: int
    source_offset: int
    target_offset: int
    old_target: int


@dataclass(frozen=True)
class BranchFixup:
    source_offset: int
    target_offset: int
    old_word: int


@dataclass(frozen=True)
class ExternalPointer:
    low_site: int
    high_site: int
    old_target: int
    target_offset: int
    stock_low: int
    stock_high: int
    note: str


@dataclass(frozen=True)
class ExternalHook:
    site: int
    kind: str  # arm_b, arm_bl, thumb_bw
    old_target: int
    target_offset: int
    stock_word: int
    late_ui: bool
    note: str
    planned_word: int

    def veneer_word(self, veneer_address: int) -> int:
        """Encode this exact hook's branch to an allocated near veneer."""
        if self.kind in ("arm_b", "arm_bl"):
            return _encode_arm_branch(self.planned_word, self.site, veneer_address)
        if self.kind == "thumb_bw":
            return _encode_thumb_bw(self.site, veneer_address)
        raise ValueError(f"unsupported external hook opcode {self.kind}")


@dataclass(frozen=True)
class CorePack:
    image: bytes
    spans: tuple[Span, ...]
    relocations: tuple[Relocation, ...]
    branch_fixups: tuple[BranchFixup, ...]
    external_pointers: tuple[ExternalPointer, ...]
    external_hooks: tuple[ExternalHook, ...]
    static_words: tuple[tuple[int, int, str], ...]
    named_offsets: dict[str, int]
    core_magic: int

    @property
    def total_bytes(self) -> int:
        return len(self.image)

    @property
    def abs_fixups(self) -> tuple[tuple[int, int], ...]:
        return tuple((r.source_offset, r.target_offset) for r in self.relocations
                     if r.kind == ABS32)

    @property
    def mov_fixups(self) -> tuple[tuple[int, int, int], ...]:
        return tuple((r.source_offset, r.source_offset + 4, r.target_offset)
                     for r in self.relocations if r.kind == ARM_MOV32)

    @property
    def external_fixups(self) -> tuple[tuple[int, int, int, int, int], ...]:
        return tuple((p.low_site, p.high_site, p.stock_low, p.stock_high,
                      p.target_offset) for p in self.external_pointers)

    @property
    def core_hooks(self) -> tuple[ExternalHook, ...]:
        return tuple(h for h in self.external_hooks if not h.late_ui)

    @property
    def late_ui_hooks(self) -> tuple[ExternalHook, ...]:
        return tuple(h for h in self.external_hooks if h.late_ui)

    @property
    def core_hook_tuples(self) -> tuple[tuple[int, int, int, str], ...]:
        return tuple((h.site, h.stock_word, h.target_offset, h.kind)
                     for h in self.core_hooks)

    @property
    def dynamic_journal_words(self) -> tuple[tuple[int, int], ...]:
        """All dynamically armed sites and pointer halves, with stock bytes."""
        out = [(site, stock) for pointer in self.external_pointers
               for site, stock in ((pointer.low_site, pointer.stock_low),
                                   (pointer.high_site, pointer.stock_high))]
        out.extend((hook.site, hook.stock_word) for hook in self.external_hooks)
        if len({site for site, _ in out}) != len(out):
            raise ValueError("duplicate dynamic journal site")
        return tuple(out)

    def address_map(self, old_address: int) -> int:
        """Return the USER byte offset of any byte in a declared old region."""
        for span in self.spans:
            if span.old_start <= old_address < span.old_end:
                return span.offset + old_address - span.old_start
        raise ValueError(f"unowned Sensor Lab cave address {old_address:#x}")

    def runtime_table(self) -> bytes:
        out = bytearray()
        for reloc in self.relocations:
            if reloc.source_offset >= (1 << 30) or reloc.target_offset >= (1 << 32):
                raise ValueError("USER relocation offset exceeds format")
            out.extend(struct.pack("<II", reloc.source_offset | (reloc.kind << 30),
                                   reloc.target_offset))
        return bytes(out)

    def to_blob(self) -> bytes:
        """Versioned staging bytes: 20-byte header, image, relocation table."""
        return (struct.pack("<4sIIII", b"SLPK", 1, len(self.image),
                            len(self.relocations), self.core_magic)
                + self.image + self.runtime_table())

    def materialize(self, base: int) -> bytes:
        """Host-side reference implementation of the launcher's USER fixups."""
        if base & 3 or not 0 <= base <= 0xFFFFFFFF - len(self.image):
            raise ValueError("USER base must be aligned and fit 32-bit address space")
        body = bytearray(self.image)
        for reloc in self.relocations:
            value = base + reloc.target_offset
            if reloc.kind == ABS32:
                struct.pack_into("<I", body, reloc.source_offset, value)
            elif reloc.kind == ARM_MOV32:
                lo, hi = struct.unpack_from("<II", body, reloc.source_offset)
                _validate_mov_pair(lo, hi, reloc.source_offset)
                struct.pack_into("<II", body, reloc.source_offset,
                                 _set_mov_imm(lo, value & 0xFFFF),
                                 _set_mov_imm(hi, value >> 16))
            else:
                raise ValueError(f"unknown USER relocation kind {reloc.kind}")
        return bytes(body)


def _read_word(image: bytes, address: int) -> int:
    off = address - ROM_BASE
    if off < 0 or off + 4 > len(image):
        raise ValueError(f"stock word {address:#x} outside firmware image")
    return struct.unpack_from("<I", image, off)[0]


def _mov_kind(word: int) -> int:
    masked = word & 0x0FF00000
    return 1 if masked == 0x03000000 else 2 if masked == 0x03400000 else 0


def _mov_imm(word: int) -> int:
    return (((word >> 16) & 15) << 12) | (word & 0xFFF)


def _set_mov_imm(word: int, imm: int) -> int:
    return (word & ~0x000F0FFF) | (((imm >> 12) & 15) << 16) | (imm & 0xFFF)


def _validate_mov_pair(lo: int, hi: int, at: int) -> None:
    if (_mov_kind(lo), _mov_kind(hi)) != (1, 2) or (lo >> 12 & 15) != (hi >> 12 & 15) or (lo >> 28) != (hi >> 28):
        raise ValueError(f"unsupported ARM MOVW/MOVT pair at {at:#x}")


def _pair_target(lo: int, hi: int) -> int:
    return (_mov_imm(hi) << 16) | _mov_imm(lo)


def _arm_branch_target(site: int, word: int) -> int | None:
    if (word & 0x0E000000) != 0x0A000000 or word >> 28 == 15:
        return None
    disp = word & 0xFFFFFF
    if disp & 0x800000:
        disp -= 0x1000000
    return site + 8 + (disp << 2)


def _encode_arm_branch(word: int, source: int, target: int) -> int:
    delta = target - source - 8
    if delta & 3 or not -(1 << 25) <= delta < (1 << 25):
        raise ValueError(f"relocated ARM branch {source:#x}->{target:#x} out of range")
    return (word & 0xFF000000) | ((delta >> 2) & 0xFFFFFF)


def _thumb_bw_target(site: int, word: int) -> int | None:
    h1, h2 = word & 0xFFFF, word >> 16
    if h1 & 0xF800 != 0xF000 or h2 & 0xD000 != 0x9000:
        return None
    s, j1, j2 = (h1 >> 10) & 1, (h2 >> 13) & 1, (h2 >> 11) & 1
    i1, i2 = (~(j1 ^ s)) & 1, (~(j2 ^ s)) & 1
    delta = (s << 24) | (i1 << 23) | (i2 << 22) | ((h1 & 0x3FF) << 12) | ((h2 & 0x7FF) << 1)
    if delta & (1 << 24):
        delta -= 1 << 25
    return site + 4 + delta


def _encode_thumb_bw(site: int, target: int) -> int:
    delta = target - site - 4
    if delta & 1 or not -(1 << 24) <= delta < (1 << 24):
        raise ValueError(f"Thumb B.W {site:#x}->{target:#x} out of range")
    s, i1, i2 = (delta >> 24) & 1, (delta >> 23) & 1, (delta >> 22) & 1
    j1, j2 = (~(i1 ^ s)) & 1, (~(i2 ^ s)) & 1
    first = 0xF000 | (s << 10) | ((delta >> 12) & 0x3FF)
    second = 0x9000 | (j1 << 13) | (j2 << 11) | ((delta >> 1) & 0x7FF)
    return first | (second << 16)


def build_pack(items: Iterable[tuple[int, int, str]],
               regions: Iterable[tuple[int, int, str]],
               payloads: Iterable[tuple[str, int, bytes]],
               firmware: bytes, *, hook_sites: Iterable[int] = (),
               late_ui_hook_sites: Iterable[int] = (),
               named_addresses: dict[str, int] | None = None) -> CorePack:
    """Build a complete, validated sparse image from one immutable plan snapshot.

    ``regions`` are the authoritative ownership declaration.  Every old cave
    word in ``items`` must be inside exactly one region.  ``payloads`` provide
    executable boundaries and must match the plan's bytes exactly.  New cave
    references, unpaired MOVW/MOVT, unsupported relative branches, overlapping
    declarations and duplicate writes all fail the build.
    """
    item_list = tuple(items)
    region_list = tuple(sorted(regions))
    code_list = tuple(payloads)
    known_hooks = set(hook_sites)
    late_hooks = set(late_ui_hook_sites)
    if late_hooks - known_hooks:
        raise ValueError("late UI hook site is not declared as a hook")
    if not region_list:
        raise ValueError("empty USER region list")
    spans = []
    cursor = 0
    for old_start, old_end, name in region_list:
        if old_start & 3 or old_end & 3 or old_start < OLD_LOW or old_end > OLD_HIGH or old_end <= old_start:
            raise ValueError(f"invalid Sensor Lab region {name}: [{old_start:#x},{old_end:#x})")
        if spans and old_start < spans[-1].old_end:
            raise ValueError(f"overlapping Sensor Lab regions {spans[-1].name} / {name}")
        spans.append(Span(old_start, old_end, cursor, name))
        cursor += old_end - old_start
    magic_offset = cursor
    body = bytearray(cursor + 4)
    struct.pack_into("<I", body, magic_offset, CORE_MAGIC)

    def mapped(old: int) -> int:
        for span in spans:
            if span.old_start <= old < span.old_end:
                return span.offset + old - span.old_start
        raise ValueError(f"unowned Sensor Lab cave address {old:#x}")

    writes = {}
    outside = []
    for address, value, note in item_list:
        if address & 3 or not 0 <= value <= 0xFFFFFFFF or address in writes:
            raise ValueError(f"duplicate, unaligned or invalid plan word {address:#x}")
        writes[address] = (value, note)
        if OLD_LOW <= address < OLD_HIGH:
            offset = mapped(address)
            if offset + 4 > magic_offset:
                raise ValueError(f"cave write crosses region end at {address:#x}")
            struct.pack_into("<I", body, offset, value)
        else:
            outside.append((address, value, note))
    # The old installer left holes in its reserved state regions untouched.
    # Zero-filling USER preserves those initial bytes only when the factory
    # image had zero there.  Reject a newly occupied hole rather than guessing
    # whether the payload depended on the factory value.
    for span in spans:
        for old in range(span.old_start, span.old_end, 4):
            if old not in writes and _read_word(firmware, old):
                raise ValueError(f"unwritten region {span.name} contains factory data at {old:#x}")

    code_ranges = []
    for name, old_start, code in code_list:
        if len(code) & 3 or not code:
            raise ValueError(f"unaligned or empty payload {name}")
        first = mapped(old_start)
        last = mapped(old_start + len(code) - 1)
        if last - first + 1 != len(code):
            raise ValueError(f"payload {name} crosses a sparse region boundary")
        if body[first:first + len(code)] != code:
            raise ValueError(f"payload {name} does not match plan words")
        code_ranges.append((name, old_start, old_start + len(code), first))
    sorted_code_ranges = sorted(code_ranges, key=lambda x: x[1])
    for i, (name, start, end, _) in enumerate(sorted_code_ranges):
        for other, other_start, other_end, _ in sorted_code_ranges[i + 1:]:
            if other_start < end and start < other_end:
                raise ValueError(f"overlapping executable payloads {name} / {other}")

    relocs = []
    branches = []
    code_word_addresses = set()
    for name, old_start, old_end, first in code_ranges:
        words = struct.unpack_from(f"<{(old_end-old_start)//4}I", body, first)
        for i, word in enumerate(words):
            old = old_start + i * 4
            code_word_addresses.add(old)
            if _mov_kind(word) == 1 and i + 1 < len(words):
                next_word = words[i + 1]
                if _mov_kind(next_word) == 2:
                    _validate_mov_pair(word, next_word, old)
                    target = _pair_target(word, next_word)
                    if OLD_LOW <= target < OLD_HIGH:
                        relocs.append(Relocation(ARM_MOV32, first + i * 4, mapped(target), target))
            if _mov_kind(word) == 2 and _mov_imm(word) == (OLD_LOW >> 16):
                paired = i > 0 and _mov_kind(words[i - 1]) == 1
                if not paired:
                    raise ValueError(f"unpaired cave MOVT in {name} at {old:#x}")
            if OLD_LOW <= word < OLD_HIGH:
                relocs.append(Relocation(ABS32, first + i * 4, mapped(word), word))
            target = _arm_branch_target(old, word)
            if target is not None and not old_start <= target < old_end:
                if OLD_LOW <= target < OLD_HIGH:
                    target_off = mapped(target)
                    source_off = first + i * 4
                    struct.pack_into("<I", body, source_off,
                                     _encode_arm_branch(word, source_off, target_off))
                    branches.append(BranchFixup(source_off, target_off, word))
                else:
                    raise ValueError(f"unsupported branch from moved payload {name} at {old:#x} to {target:#x}")

    for span in spans:
        for old in range(span.old_start, span.old_end, 4):
            if old in code_word_addresses:
                continue
            value = struct.unpack_from("<I", body, mapped(old))[0]
            if OLD_LOW <= value < OLD_HIGH:
                relocs.append(Relocation(ABS32, mapped(old), mapped(value), value))

    # External site values are re-encoded after USER allocation.  Keep them
    # out of pass-1 static sections, but publish their stock words as journal
    # declarations before any entry is called.
    out_by_addr = {address: (value, note) for address, value, note in outside}
    dynamic = set()
    pointers = []
    hooks = []
    for address, value, note in outside:
        if address in dynamic:
            continue
        if _mov_kind(value) == 1 and address + 4 in out_by_addr:
            high, _ = out_by_addr[address + 4]
            if _mov_kind(high) == 2:
                _validate_mov_pair(value, high, address)
                target = _pair_target(value, high)
                if OLD_LOW <= target < OLD_HIGH:
                    pointers.append(ExternalPointer(address, address + 4, target, mapped(target),
                                                    _read_word(firmware, address),
                                                    _read_word(firmware, address + 4), note))
                    dynamic.update((address, address + 4))
                    continue
        if _mov_kind(value) == 2 and _mov_imm(value) == (OLD_LOW >> 16):
            low = out_by_addr.get(address - 4, (None,))[0]
            if low is None or _mov_kind(low) != 1:
                raise ValueError(f"unpaired external cave MOVT at {address:#x}")
        target = _arm_branch_target(address, value)
        if target is not None and OLD_LOW <= target < OLD_HIGH:
            if known_hooks and address not in known_hooks:
                raise ValueError(f"undeclared external ARM hook {address:#x}")
            hooks.append(ExternalHook(address, "arm_bl" if value & 0x01000000 else "arm_b",
                                      target, mapped(target), _read_word(firmware, address),
                                      address in late_hooks, note, value))
            dynamic.add(address)
            continue
        target = _thumb_bw_target(address, value)
        if target is not None and OLD_LOW <= target < OLD_HIGH:
            if known_hooks and address not in known_hooks:
                raise ValueError(f"undeclared external Thumb hook {address:#x}")
            hooks.append(ExternalHook(address, "thumb_bw", target, mapped(target),
                                      _read_word(firmware, address), address in late_hooks, note,
                                      value))
            dynamic.add(address)
            continue
        if OLD_LOW <= value < OLD_HIGH:
            raise ValueError(f"external absolute cave pointer at {address:#x} needs explicit descriptor")
    if known_hooks != {hook.site for hook in hooks}:
        missing = sorted(known_hooks - {hook.site for hook in hooks})
        raise ValueError(f"declared hook missing from plan: {missing[:4]}")
    relocs.sort(key=lambda r: (r.source_offset, r.kind))
    if len({r.source_offset for r in relocs}) != len(relocs):
        raise ValueError("overlapping USER relocations")
    names = {name: mapped(old) for name, old in (named_addresses or {}).items()}
    names["core_magic"] = magic_offset
    return CorePack(bytes(body), tuple(spans), tuple(relocs), tuple(branches),
                    tuple(pointers), tuple(hooks),
                    tuple((a, v, n) for a, v, n in outside if a not in dynamic),
                    names, magic_offset)


def res_lab_pack(items: Iterable[tuple[int, int, str]], *, blobs=None,
                    firmware: bytes | None = None):
    """Adapter for the current imx410_plan flags and one plan snapshot."""
    import imx410_plan as plan
    import sl_excl as slx

    blobs = blobs if blobs is not None else plan.blobs()
    firmware = firmware if firmware is not None else plan.FIRMWARE.read_bytes()
    payloads = tuple((name, address, blobs[name]) for name, _, address in plan.payloads())
    core_hooks = {site for _, group in plan._stages() for site, _, _, _ in group}
    late_hooks = ({site for site, _, _ in slx.HOOKS}
                  | {site for site, _, _ in slx.SETTER_HOOKS}
                  | {slx.DNG_SITE, slx.GUI_SITE, slx.PAGE_SITE}) if plan.WITH_SL_EXCL else set()
    named = {"axis": plan.AXIS, "gtab": plan.GTAB, "flag": 0xC0731C08,
             "coltab": plan.COLTAB, "asptab": plan.ASPTAB,
             "recipe": plan.RECIPE, "ratetab": plan.RATETAB,
             "tmgtab": plan.TMGTAB, "rate240": plan.RATE_NATIVE.RATE240,
             "mark": plan.SL_MENU_MARK, "fmt_code": plan.FMT_CODE,
             "restore_code": plan.RESTORE_CODE}
    if plan._with_binfilt():
        named["binfilt"] = plan.BINFILT.BINFILT
    return build_pack(items, plan.regions(blobs), payloads, firmware,
                      hook_sites=core_hooks | late_hooks,
                      late_ui_hook_sites=late_hooks, named_addresses=named)
