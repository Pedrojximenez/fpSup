/* OpenGate (OG3K / OG2K) as a Loader v3 sup: the entry.
 *
 * projects/usb-shell-sup/notes/LOADER_V3.md §4 (entry contract) and §8 step 4.
 * build_v3_og.py lays the file out as
 *
 *     [FSB1 header] [this, compiled with uishare's applier] [og_tab + rows]
 *     [layout image: the cave 0xC0730000..0xC0735000, then the private NBR pack]
 *     [the FPUI block]  [zeroed tail: the veneer addresses]
 *
 * The layout image is what the AutoRun card writes into the cave, assembled
 * position-independent (og_pic.inc): code reaches its own data PC-relative.
 * What the firmware is handed as an absolute address is made here, from where
 * the block landed: the format table's key pointers and the FPUI block's
 * STRBASE addresses (fixups), the hook veneers, the restore call.
 *
 * Order (§4): claim everything -> take the cave -> relocate -> apply the UI
 * block -> write the value patches -> veneers -> hooks (picker last, as on the
 * AutoRun card) -> restore.  Every refusal returns SL_RELEASE before the first
 * write outside this block; after uia_apply succeeds nothing can fail. */
#include <stdint.h>
#include "sloader.h"
#include "ui_apply.h"

#ifndef OG_TAB_OFF
#define OG_TAB_OFF 0u
#endif
#define OG_TAB_MAGIC 0x3356474Fu       /* "OGV3" */
#define OG_TAB_VERSION 1u

enum { HOOK_B = 0, HOOK_BL = 1, HOOK_THUMB_BW = 2 };

struct og_tab {
    uint32_t magic, version;
    uint32_t img_off, ogv;      /* block + img_off is where coordinate ogv landed     */
    uint32_t n_claim, claim_off;/* {addr, bytes, kind, stock_off, new_off}; new_off 0:
                                   claim only (the payloads write it at run time)    */
    uint32_t n_fix, fix_off;    /* block offsets of words that hold a coordinate     */
    uint32_t fpui_off, fpui_len;/* the FPUI block; len 0 = none                      */
    uint32_t n_hook, hook_off;  /* {site, target coordinate, kind, next, replay}:
                                   next != 0 -- a layer (CHAIN): the word at coordinate
                                   `next` gets what the site branched to before, or
                                   `replay` (this payload's own way back) if nothing */
    uint32_t restore;           /* og3krestore's coordinate (ARM), 0 = none          */
    uint32_t scratch_off;       /* n_hook words in the zeroed tail                    */
};

static inline void wr(uint32_t a, uint32_t v) { *(volatile uint32_t *)(uintptr_t)a = v; }

static uint32_t thumb_bw(uint32_t site, uint32_t to)
{
    uint32_t d = to - site - 4;
    uint32_t s = (d >> 24) & 1u, i1 = (d >> 23) & 1u, i2 = (d >> 22) & 1u;
    uint32_t j1 = (~(i1 ^ s)) & 1u, j2 = (~(i2 ^ s)) & 1u;
    uint32_t h1 = 0xF000u | s << 10 | ((d >> 12) & 0x3FFu);
    uint32_t h2 = 0x9000u | j1 << 13 | j2 << 11 | ((d >> 1) & 0x7FFu);
    return h1 | h2 << 16;
}

/* One LOAD.LOG line, "OG" + a tag + 8 hex digits: why this sup gave up.  Built
 * on the stack, character by character (no string constants: the unit has no
 * data section). */
static void og_log(const struct sl_svc *svc, char tag, uint32_t v)
{
    volatile char b[12];
    b[0] = 'O'; b[1] = 'G'; b[2] = tag;
    for (uint32_t i = 0; i < 8; i++) {
        uint32_t d = (v >> (28 - 4 * i)) & 15u;
        b[3 + i] = (char)(d < 10 ? '0' + d : 'A' + d - 10);
    }
    b[11] = 0;
    svc->log(svc, (const char *)b);
}

static uint32_t og_fnv(const uint8_t *p, uint32_t n)
{
    uint32_t h = 0x811C9DC5u;
    while (n--) { h ^= *p++; h *= 0x01000193u; }
    return h;
}

int og_v3_entry(uint8_t *block, const struct sl_svc *svc)
{
    const struct og_tab *t = (const struct og_tab *)(block + OG_TAB_OFF);
    if (t->magic != OG_TAB_MAGIC || t->version != OG_TAB_VERSION) return SL_RELEASE;

    /* 1. Everything this sup will change, before anything changes. */
    const uint32_t *c = (const uint32_t *)(block + t->claim_off);
    for (uint32_t i = 0; i < t->n_claim; i++, c += 5) {
        /* bytes 0: not memory -- a resource (claim_res), e.g. uishare's
         * UIS_RES_QSCUR, which makes the first QS sup the issuer of the shared
         * "current format" image names (ui_pool.c uis_qs_shared). */
        int r = c[1] ? svc->claim(svc, c[0], c[1], block + c[3], c[2])
                     : svc->claim_res(svc, c[0], c[2]);
        if (r != SL_OK) { og_log(svc, 'C', i << 16 | ((uint32_t)r & 0xFFFFu)); return SL_RELEASE; }
    }

    /* 2. The veneers' cave, all of it before the first write. */
    uint32_t *ven = (uint32_t *)(block + t->scratch_off);
    for (uint32_t i = 0; i < t->n_hook; i++)
        if (!(ven[i] = svc->cave_alloc(svc, 8))) { og_log(svc, 'V', i); return SL_RELEASE; }

    /* 3. Coordinates to addresses: inside this block only. */
    uint32_t delta = (uint32_t)(uintptr_t)block + t->img_off - t->ogv;
    const uint32_t *f = (const uint32_t *)(block + t->fix_off);
    for (uint32_t i = 0; i < t->n_fix; i++) *(uint32_t *)(block + f[i]) += delta;

    /* 4. The resolution row and the labels (uishare).  Its STRBASE addresses
     *    were among the fixups, so the block's hash is made again first. */
    if (t->fpui_len) {
        uint8_t *u = block + t->fpui_off;
        uint32_t total = ((uint32_t *)u)[2];
        if (total < 0x20u || total > t->fpui_len) { og_log(svc, 'F', total); return SL_RELEASE; }
        ((uint32_t *)u)[3] = og_fnv(u + 0x20, total - 0x20);
        struct uia_outcome out;
        uint32_t ur = uia_apply((uintptr_t)u, t->fpui_len, &out);
        if (ur != UIA_OK) { og_log(svc, 'U', ur << 16 | (out.op & 0xFFFFu)); return SL_RELEASE; }
    }

    /* 5. Value patches. */
    c = (const uint32_t *)(block + t->claim_off);
    for (uint32_t i = 0; i < t->n_claim; i++, c += 5) {
        if (!c[4]) continue;
        const uint32_t *nw = (const uint32_t *)(block + c[4]);
        for (uint32_t k = 0; k < c[1] / 4; k++) wr(c[0] + 4 * k, nw[k]);
    }

    /* 6. The way down for every layer, read before any site is written; then
     *    the veneers, made code before any site points at them. */
    const uint32_t *h = (const uint32_t *)(block + t->hook_off);
    for (uint32_t i = 0; i < t->n_hook; i++) {
        const uint32_t *r = h + 5 * i;
        if (!r[3]) continue;
        uint32_t below = svc->chain_next(svc, r[0], r[2] == HOOK_THUMB_BW);
        wr(r[3] + delta, below ? below : r[4] + delta);
    }
    for (uint32_t i = 0; i < t->n_hook; i++) {
        uint32_t to = h[5 * i + 1] + delta;
        if (h[5 * i + 2] == HOOK_THUMB_BW) {
            wr(ven[i], 0xF000F8DFu);            /* ldr.w pc, [pc, #0] */
            wr(ven[i] + 4, to | 1u);
        } else {
            wr(ven[i], 0xE51FF004u);            /* ldr pc, [pc, #-4]  */
            wr(ven[i] + 4, to);
        }
    }
    svc->publish(svc);

    /* 7. The hooks, in the AutoRun card's order: the picker last of OpenGate's,
     *    then the UI's, the NBU record interpreter before the layout loader. */
    for (uint32_t i = 0; i < t->n_hook; i++) {
        uint32_t site = h[5 * i], kind = h[5 * i + 2];
        if (kind == HOOK_THUMB_BW)
            wr(site, thumb_bw(site, ven[i]));
        else
            wr(site, (kind == HOOK_BL ? 0xEB000000u : 0xEA000000u)
                     | (((ven[i] - site - 8) >> 2) & 0x00FFFFFFu));
    }
    svc->publish(svc);

    /* 8. The user's last choice back (og3krestore): it was the AutoRun card's
     *    VSHL entry, after every section; here, after every hook. */
    if (t->restore) ((void (*)(void))(uintptr_t)(t->restore + delta))();
    return SL_KEEP;
}
