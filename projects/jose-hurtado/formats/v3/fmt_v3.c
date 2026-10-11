/* Jose Hurtado's fpSup-Formats v0.6.0 as a Loader v3 sup: the entry.
 *
 * projects/usb-shell-sup/notes/LOADER_V3.md §4 (entry contract).  There is no
 * source for the Formats core: build_v3_fmt.py moves Jose's own bytes into
 * the block and lists, from a disassembly of them, what the move changes:
 *
 *     [FSB1 header] [fmt_tab and its rows] [this, Thumb, -fropi]
 *     [piece 0: 0xC072FB00..]  [piece 1: 0xC0793060..]  [piece 2: 0xC07A4BF0..]
 *     [zeroed tail: the veneer addresses]
 *
 * A piece is a run of Jose's fixed addresses ("coordinates"); it lands in the
 * block unchanged, so code reaches code and data inside a piece exactly as
 * before.  What names a coordinate absolutely is made an address here:
 *   - 32-bit words (pointer tables, literals): word = address(word)
 *   - MOVW/MOVT pairs in the code: both immediates rewritten
 *   - firmware words that hold a coordinate (claimed first): a MOVW/MOVT pair
 *     in the firmware's code and one function pointer
 *   - the hooks: firmware site -> cave veneer -> coordinate
 * The code never branches between pieces or into the firmware with B/BL
 * (build_v3_fmt.py proves it), so nothing else moves.
 *
 * His string hook (C05E5B58) is not armed.  His ids and string table go up
 * as a standard uishare string layer instead (uis_layer_fixed: named after
 * this file, chained to whatever layer was there), so another uishare sup can
 * sit under or over it (NESTED_HOOKS.md, 2026-10-06).
 *
 * Order (§4): claim everything -> take the cave -> relocate inside the block
 * -> the string layer (the last step that can refuse) -> value patches ->
 * veneers -> hooks (Jose's section order) -> the menu compositor, called once
 * as stage2 called it.  Every refusal returns SL_RELEASE before the first
 * write outside this block.
 *
 * Compiled after uishare's ui_pool.c in one unit (build_v3_fmt.py). */
#include <stdint.h>
#include "sloader.h"

#define FMT_TAB_OFF     SL_HEADER_LEN
#define FMT_TAB_MAGIC   0x33564D46u     /* "FMV3" */
#define FMT_TAB_VERSION 2u

enum { HOOK_B = 0, HOOK_BL = 1, HOOK_THUMB_BW = 2 };

struct fmt_tab {
    uint32_t magic, version;
    uint32_t n_piece, piece_off;    /* {coordinate, bytes, block offset}           */
    uint32_t n_claim, claim_off;    /* {addr, bytes, kind, stock_off, new_off};
                                       new_off 0: claim only                        */
    uint32_t n_abs, abs_off;        /* block offsets of words holding a coordinate  */
    uint32_t n_mm, mm_off;          /* {movw offset, movt offset} in the block      */
    uint32_t n_fwmm, fwmm_off;      /* {movw site, movt site, Jose's movw, movt}:
                                       firmware code that loads a coordinate        */
    uint32_t n_fwabs, fwabs_off;    /* {firmware word, coordinate}                  */
    uint32_t n_hook, hook_off;      /* {site, coordinate, kind}                     */
    uint32_t entry;                 /* the compositor's coordinate (ARM)            */
    uint32_t scratch_off;           /* n_hook words in the zeroed tail              */
    uint32_t str_table;             /* his string table's coordinate: str_count     */
    uint32_t str_count, str_base;   /* words, string i answers offset str_base + i  */
};

static inline void wr(uint32_t a, uint32_t v) { *(volatile uint32_t *)(uintptr_t)a = v; }

/* A coordinate's address in this block; 0 when no piece holds it. */
static uint32_t where(const uint8_t *block, const struct fmt_tab *t, uint32_t c)
{
    const uint32_t *p = (const uint32_t *)(block + t->piece_off);
    for (uint32_t i = 0; i < t->n_piece; i++, p += 3)
        if (c - p[0] < p[1]) return (uint32_t)(uintptr_t)block + p[2] + (c - p[0]);
    return 0;
}

/* ARM MOVW/MOVT immediates: imm4 at [19:16], imm12 at [11:0]. */
static uint32_t imm16(uint32_t insn) { return ((insn >> 4) & 0xF000u) | (insn & 0xFFFu); }
static uint32_t with_imm16(uint32_t insn, uint32_t v)
{
    return (insn & 0xFFF0F000u) | ((v & 0xF000u) << 4) | (v & 0xFFFu);
}

static uint32_t thumb_bw(uint32_t site, uint32_t to)
{
    uint32_t d = to - site - 4;
    uint32_t s = (d >> 24) & 1u, i1 = (d >> 23) & 1u, i2 = (d >> 22) & 1u;
    uint32_t j1 = (~(i1 ^ s)) & 1u, j2 = (~(i2 ^ s)) & 1u;
    uint32_t h1 = 0xF000u | s << 10 | ((d >> 12) & 0x3FFu);
    uint32_t h2 = 0x9000u | j1 << 13 | j2 << 11 | ((d >> 1) & 0x7FFu);
    return h1 | h2 << 16;
}

int fmt_v3_entry(uint8_t *block, const struct sl_svc *svc)
{
    const struct sl_header *hd = (const struct sl_header *)block;
    const struct fmt_tab *t = (const struct fmt_tab *)(block + FMT_TAB_OFF);
    if (t->magic != FMT_TAB_MAGIC || t->version != FMT_TAB_VERSION) return SL_RELEASE;

    /* 1. Everything this sup will change, before anything changes. */
    const uint32_t *c = (const uint32_t *)(block + t->claim_off);
    for (uint32_t i = 0; i < t->n_claim; i++, c += 5)
        if (svc->claim(svc, c[0], c[1], block + c[3], c[2]) != SL_OK) return SL_RELEASE;

    /* 2. The veneers' cave, all of it before the first write. */
    uint32_t *ven = (uint32_t *)(block + t->scratch_off);
    for (uint32_t i = 0; i < t->n_hook; i++)
        if (!(ven[i] = svc->cave_alloc(svc, 8))) return SL_RELEASE;

    /* Every coordinate the firmware will be handed must be in a piece. */
    const uint32_t *h = (const uint32_t *)(block + t->hook_off);
    const uint32_t *f;
    for (uint32_t i = 0; i < t->n_hook; i++)
        if (!where(block, t, h[3 * i + 1])) return SL_RELEASE;
    if (!where(block, t, t->entry)) return SL_RELEASE;
    f = (const uint32_t *)(block + t->fwmm_off);
    for (uint32_t i = 0; i < t->n_fwmm; i++, f += 4)
        if (!where(block, t, imm16(f[3]) << 16 | imm16(f[2]))) return SL_RELEASE;
    f = (const uint32_t *)(block + t->fwabs_off);
    for (uint32_t i = 0; i < t->n_fwabs; i++, f += 2)
        if (!where(block, t, f[1] & ~1u)) return SL_RELEASE;

    /* 3. Inside the block: coordinates to addresses. */
    f = (const uint32_t *)(block + t->abs_off);
    for (uint32_t i = 0; i < t->n_abs; i++) {
        uint32_t *w = (uint32_t *)(block + f[i]);
        uint32_t a = where(block, t, *w & ~1u);
        if (!a) return SL_RELEASE;
        *w = a | (*w & 1u);
    }
    f = (const uint32_t *)(block + t->mm_off);
    for (uint32_t i = 0; i < t->n_mm; i++, f += 2) {
        uint32_t *lo = (uint32_t *)(block + f[0]), *hi = (uint32_t *)(block + f[1]);
        uint32_t a = where(block, t, imm16(*hi) << 16 | imm16(*lo));
        if (!a) return SL_RELEASE;
        *lo = with_imm16(*lo, a & 0xFFFFu);
        *hi = with_imm16(*hi, a >> 16);
    }

    /* The string layer: his table, in place (it lives as long as the block;
     * the compositor fills it below).  Owns/remain answer for the whole block:
     * his strings are in all three pieces.  Nothing outside the block has
     * been written yet, and nothing after this can refuse. */
    uint32_t tab = where(block, t, t->str_table);
    if (!tab || uis_layer_fixed(tab, t->str_count, t->str_base, (uintptr_t)block,
                                (uintptr_t)block + hd->block_size) != UIS_OK)
        return SL_RELEASE;

    /* 4. Value patches (the claims that carry bytes), then the firmware words
     *    that name a coordinate -- their stock words were claimed in 1. */
    c = (const uint32_t *)(block + t->claim_off);
    for (uint32_t i = 0; i < t->n_claim; i++, c += 5) {
        if (!c[4]) continue;
        const uint32_t *nw = (const uint32_t *)(block + c[4]);
        for (uint32_t k = 0; k < c[1] / 4; k++) wr(c[0] + 4 * k, nw[k]);
    }
    f = (const uint32_t *)(block + t->fwmm_off);
    for (uint32_t i = 0; i < t->n_fwmm; i++, f += 4) {
        uint32_t a = where(block, t, imm16(f[3]) << 16 | imm16(f[2]));
        wr(f[0], with_imm16(f[2], a & 0xFFFFu));
        wr(f[1], with_imm16(f[3], a >> 16));
    }
    f = (const uint32_t *)(block + t->fwabs_off);
    for (uint32_t i = 0; i < t->n_fwabs; i++, f += 2)
        wr(f[0], where(block, t, f[1] & ~1u) | (f[1] & 1u));

    /* 5. Veneers, made code before any site points at them. */
    for (uint32_t i = 0; i < t->n_hook; i++) {
        uint32_t to = where(block, t, h[3 * i + 1]);
        if (h[3 * i + 2] == HOOK_THUMB_BW) {
            wr(ven[i], 0xF000F8DFu);            /* ldr.w pc, [pc, #0] */
            wr(ven[i] + 4, to | 1u);
        } else {
            wr(ven[i], 0xE51FF004u);            /* ldr pc, [pc, #-4]  */
            wr(ven[i] + 4, to);
        }
    }
    svc->publish(svc);

    /* 6. The hooks, in the order Jose's VBIN placed them. */
    for (uint32_t i = 0; i < t->n_hook; i++) {
        uint32_t site = h[3 * i], kind = h[3 * i + 2];
        if (kind == HOOK_THUMB_BW)
            wr(site, thumb_bw(site, ven[i]));
        else
            wr(site, (kind == HOOK_BL ? 0xEB000000u : 0xEA000000u)
                     | (((ven[i] - site - 8) >> 2) & 0x00FFFFFFu));
    }
    svc->publish(svc);

    /* 7. The compositor, as stage2 called a VBIN entry: r0 = its address.
     *    It builds the menu from the slots in the block and starts the
     *    boot-refresh task -- the first thing that cannot be undone. */
    uint32_t e = where(block, t, t->entry);
    ((void (*)(uint32_t))(uintptr_t)e)(e);
    return SL_KEEP;
}
