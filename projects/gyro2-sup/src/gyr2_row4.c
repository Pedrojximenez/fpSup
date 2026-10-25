/* Gyro2's ON/OFF row on the fpSup page (Loader v4 only; gyr2.S -DGYR2_V4
 * .incbin's this unit and calls g2_install from its entry).
 *
 * The user 2026-10-24: a switch for Gyro2 (Jose Hurtado's Gyro-Data had one:
 * OFF records without gyro, e.g. S16 at 100 fps), saved in the sup's own BIN.
 * OFF = tag_observer adds no MakerNote tag at the take start and writes no
 * frame block; the setting is latched at the take start.  The value is saved
 * when the row changes (the UI thread, not while recording), into this file's
 * record -- after svc->file_is says the file is still this sup, so a renamed or
 * deleted file is never re-created (sup-writeback-must-not-create).
 *
 * Built -fropi Thumb with no data section: every string is written from
 * immediates at install; the state lives in gyr2.S's g2_state (zero at load).
 */
#include <stdint.h>
#include "sloader4.h"

typedef uint32_t u32;

#define G2_MAGIC     0x54533247u          /* "G2ST" */
#define G2_VERSION   1u
#define HDR          48u                  /* SL4_HEADER_LEN */
#define F_CTOR       0xC0365E90u
#define F_OPEN       0xC0365FB0u
#define F_READ       0xC0366060u
#define F_WRITE      0xC03660E8u
#define F_SEEK       0xC03661E0u
#define F_CLOSE      0xC0366020u
#define F_DTOR       0xC0365ED0u
#define F_DCACHE     0xC000E91Cu          /* D-cache clean + invalidate, L1 and L2 */
#define ALIAS        0x80000000u
/* recording: res-custom's busy() (ogc.c) */
#define MOV_SELECTOR   0xC347D1D4u
#define MOVREC_DEFAULT 0xC347E08Fu
#define MOVREC_SEL21   0xC3476609u
#define XMP_FOBJ_PTR   0xC358E140u
#define MOV_ACTIVE     0xC35A952Cu

#define W(a)  (*(volatile u32 *)(uintptr_t)(a))
#define B8(a) (*(volatile uint8_t *)(uintptr_t)(a))

typedef u32 (*fw1)(u32);
typedef u32 (*fw2)(u32, u32);
typedef u32 (*fw3)(u32, u32, u32);
typedef u32 (*fw4)(u32, u32, u32, u32);

/* gyr2.S reserves G2_STATE_BYTES for this, zero at load */
struct g2 {
    struct sl_row row;                    /* the core keeps the pointer */
    const char *choices[2];
    u32 title[2], off[1], on[1];
    const struct sl_svc *svc;
    u32 block;                            /* the file as loaded (its header first) */
    u32 rec;                              /* the record, in the block */
    u32 *off_flag;                        /* gyr2.S V_ROWOFF: 1 = OFF */
    u32 fobj;                             /* 0x400: file object; + 0x300 read-back */
    u32 saves, save_fails, refused;
    char path[64];
};

static u32 uca(u32 a) { return a >= 0xC0000000u ? a - ALIAS : a; }

static int busy(void)
{
    u32 sel = W(MOV_SELECTOR) == 0x21u ? MOVREC_SEL21 : MOVREC_DEFAULT;
    return B8(sel) || W(XMP_FOBJ_PTR) || B8(MOV_ACTIVE);
}

static u32 check(u32 off) { return ~(G2_MAGIC ^ G2_VERSION ^ off); }

/* The record in this file: {magic, version, off, check} at HDR + rec offset. */
static u32 save(struct g2 *g, u32 off)
{
    u32 r[4] = {G2_MAGIC, G2_VERSION, off, check(off)};
    u32 at = g->rec - g->block, fo = g->fobj, back = fo + 0x300, ok = 0;
    if (!g->svc->file_is || g->svc->file_is(g->svc, g->path, (const void *)g->block, HDR) != SL_OK)
        return 0;                             /* renamed away or replaced: never write */
    for (u32 i = 0; i < 4; i++) W(back + 0x40 + 4 * i) = r[i];
    ((void (*)(void))F_DCACHE)();             /* the record reaches RAM first */
    ((fw2)F_CTOR)(fo, 1);
    if (((fw3)F_OPEN)(fo, (u32)(uintptr_t)g->path, 7)) {          /* exists (checked): in place */
        if (((fw3)F_SEEK)(fo, at, 0) && ((fw3)F_WRITE)(fo, uca(back + 0x40), 16) &&
            ((fw3)F_SEEK)(fo, at, 0)) {
            W(back + 16) = 0;
            ((void (*)(void))F_DCACHE)();
            ((fw4)F_READ)(fo, uca(back), 16, uca(back + 16));
            ((void (*)(void))F_DCACHE)();
            ok = W(back + 16) == 16;
            for (u32 i = 0; ok && i < 4; i++) ok = W(back + 4 * i) == r[i];
        }
        ((fw1)F_CLOSE)(fo);
    }
    ((fw2)F_DTOR)(fo, 2);
    return ok;
}

static int row_get(void *arg)
{
    return !*((struct g2 *)arg)->off_flag;            /* 0 OFF, 1 ON */
}

static int row_set(void *arg, int v)
{
    struct g2 *g = (struct g2 *)arg;
    if (v != 0 && v != 1) return 1;
    u32 off = !v;
    if (off == *g->off_flag) return 0;
    if (busy()) { g->refused++; return 1; }           /* not while recording */
    *g->off_flag = off;
    if (save(g, off)) g->saves++;
    else g->save_fails++;                             /* still applies until power-off */
    return 0;
}

/* gyr2.S entry: (state, svc, block, rec | off_flag in r3's words).  Returns
 * page_add's result (row number or < 0); the row is optional, Gyro2 runs either way. */
int g2_install(struct g2 *g, const struct sl_svc *svc, u32 block, const u32 *where)
{
    u32 rec = where[0];
    u32 *flag = (u32 *)(uintptr_t)where[1];
    g->svc = svc;
    g->block = block;
    g->rec = rec;
    g->off_flag = flag;
    g->fobj = uca(where[2]);
    /* the saved state; ON when none (first install) */
    *flag = W(rec) == G2_MAGIC && W(rec + 4) == G2_VERSION && W(rec + 12) == check(W(rec + 8))
            && W(rec + 8) == 1u;
    if (!svc || svc->version < 6u || !svc->page_add || !svc->self_path) return SL_BADARG;
    const char *p = svc->self_path(svc, (const void *)block);
    u32 n = 0;
    if (p) for (; n < sizeof g->path - 1 && p[n]; n++) g->path[n] = p[n];
    g->path[n] = 0;
    g->title[0] = 0x6F727947u;            /* "Gyro" */
    g->title[1] = 0x00000032u;            /* "2"    */
    g->off[0] = 0x0046464Fu;              /* "OFF"  */
    g->on[0] = 0x00004E4Fu;               /* "ON"   */
    g->choices[0] = (const char *)g->off;
    g->choices[1] = (const char *)g->on;
    g->row.kind = SL_ROW_TOGGLE;
    g->row.n_choices = 2;
    g->row.title = (const char *)g->title;
    g->row.value = 0;
    g->row.get = row_get;
    g->row.set = row_set;
    g->row.choices = g->choices;
    g->row.open = 0;
    g->row.arg = g;
    return svc->page_add(svc, &g->row);
}
