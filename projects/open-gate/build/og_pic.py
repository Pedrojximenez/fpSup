"""Make an OG_V3_PAIR payload position-independent at build time (og_pic.inc).

Under OG_V3_PAIR the LDA macro still emits `movw rd, #lo; movt rd, #hi` with
the layout coordinate, so a payload keeps its exact size -- Sensor Lab's
payloads are packed into the old cave with no slack (2026-10-06: 13 overlaps
with the three-instruction PC-relative form).  This pass rewrites every such
pair whose value lies in the layout into the same two words, PC-relative:

    add|sub rd, pc, #(|d| & 0xFF00)
    add|sub rd, rd, #(|d| & 0x00FF)        d = value - (pair + 8)

A `ldr pc, [pc, #-4]` whose literal is in the layout (RETURN_TO into another
payload) becomes `b` + `nop`, the same two words.

It is the transform the old Sensor Lab launcher made at run time (its
ARM_MOV32 and in-code ABS32 relocations, res_lab_user_pack.py), made once, offline: what runs
on the camera has no relocation left.  A movt carrying the layout's upper half
without its movw is refused; anything else absolute into the layout (a .word,
a literal) is left for the builder's two-origin proof to catch.
"""
import struct


def _kind(word):
    m = word & 0x0FF00000
    return 1 if m == 0x03000000 else 2 if m == 0x03400000 else 0


def _imm(word):
    return (((word >> 16) & 15) << 12) | (word & 0xFFF)


def pc_relative(blob, org, lo, hi):
    """(new blob, pairs rewritten).  org: the payload's own coordinate;
    [lo, hi): the layout."""
    if len(blob) % 4 or hi - lo > 0x10000:
        raise ValueError('payload not word-sized, or the layout is too large')
    words = list(struct.unpack(f'<{len(blob) // 4}I', blob))
    done = 0
    i = 0
    while i < len(words):
        w = words[i]
        if _kind(w) == 1 and i + 1 < len(words) and _kind(words[i + 1]) == 2:
            h = words[i + 1]
            rd = (w >> 12) & 15
            if (h >> 12) & 15 == rd and w >> 28 == 0xE and h >> 28 == 0xE:
                value = _imm(h) << 16 | _imm(w)
                if lo <= value < hi:
                    if rd == 15:
                        raise ValueError(f'pc as destination at +{4 * i:#x}')
                    d = value - (org + 4 * i + 8)
                    op = 0x00800000 if d >= 0 else 0x00400000          # ADD / SUB
                    m = abs(d)
                    words[i] = 0xE20F0000 | op | rd << 12 | 0xC00 | (m >> 8) & 0xFF
                    words[i + 1] = 0xE2000000 | op | rd << 16 | rd << 12 | m & 0xFF
                    done += 1
                    i += 2
                    continue
        if w == 0xE51FF004 and i + 1 < len(words) and lo <= words[i + 1] < hi:
            # RETURN_TO into the layout: `ldr pc, [pc, #-4]; .word to` -> `b to; nop`
            d = words[i + 1] - (org + 4 * i + 8)
            if d % 4 or not -(1 << 25) <= d < (1 << 25):
                raise ValueError(f'branch out of reach at +{4 * i:#x}')
            words[i] = 0xEA000000 | (d >> 2) & 0xFFFFFF
            words[i + 1] = 0xE320F000
            done += 1
            i += 2
            continue
        if _kind(w) == 2 and lo >> 16 <= _imm(w) <= (hi - 1) >> 16:
            prev = words[i - 1] if i else 0
            if not (_kind(prev) == 1 and (prev >> 12) & 15 == (w >> 12) & 15):
                raise ValueError(f'a layout movt without its movw at +{4 * i:#x}')
        i += 1
    return struct.pack(f'<{len(words)}I', *words), done
