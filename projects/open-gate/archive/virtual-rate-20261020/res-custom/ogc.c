/* res-custom, the multi-format OpenGate core (32RESCUS.BIN): the entry and the logic.
 *
 * projects/open-gate/notes/OG_MULTIFORMAT_CORE_DESIGN.md (§3.2: virtual profile
 * and virtual mode; §4: the transaction; §12: the choice in this file; §13: the
 * menu and the Quick Set, scheme B; §14: the format data files).
 * build_v3_rescustom.py compiles this after uishare's applier (build_section
 * unity: ui_pool.c + ui_apply.c), one Thumb unit, -fropi, no data section, and
 * lays the file out as
 *
 *     [FSB1] [the BIN settings area, 0x60] [this unit]
 *     [ogc_tab, claim rows, stock bytes, hook rows, the menu template, the QS
 *      recipe, the timing records' stock words]
 *     [layout image: the shims (ogc_shims.S) at LAYOUT0, S's header at S_COORD]
 *     [zeroed tail: S's body, the veneers, the file object, the QS copy
 *      buffers, the data files' area]
 *
 * The formats are not in this file: the entry reads \fpSup\RESCUS\*.RCD
 * (parameters only -- rcd.py), checks them, and builds S from them.  Inside S
 * everything is an offset from S.  The shims reach S PC-relative and call the
 * functions below through S.FN with an 8-aligned stack.
 *
 * Nothing here writes a firmware table: the picker entries name a virtual
 * profile id and a virtual mode id; the profile row is declared in the canvas
 * (and C043A18C hands the gather a base row), the mode rows live in S and the
 * seven index lookups hand the firmware an index that lands on them. */
#include <stdint.h>
#define SL_SVC_BUTTON 1
#include "sloader.h"
#include "ogc_layout.h"
#include "virtual_rcd.h"

typedef uint32_t u32;
typedef uint8_t u8;

#ifndef OGC_TAB_OFF
#define OGC_TAB_OFF 0u
#endif
#define OGC_TAB_MAGIC 0x3343474Fu       /* "OGC3" */
#define OGC_TAB_VERSION 7u

enum { HOOK_B = 0, HOOK_BL = 1, HOOK_TW = 2 };   /* TW: a Thumb site, B.W to a Thumb veneer */

struct ogc_tab {
    u32 magic, version;
    u32 img_off, ogv;          /* block + img_off is coordinate ogv                   */
    u32 n_claim, claim_off;    /* {addr, bytes, kind, stock_off, 0}; bytes 0: claim_res */
    u32 n_hook, hook_off;      /* {site, coordinate, kind, next coordinate, replay}    */
    u32 scratch_off;           /* n_hook veneer addresses (zeroed tail)                */
    u32 fobj_off;              /* 0x1000 bytes of zeroed tail: a file object + read-back */
    u32 tpl_off, tpl_len;      /* the menu's FPUI template (rcd.ui_template), 4-aligned */
    u32 qstab_off;             /* the Quick Set recipe (uishare ui/qs.py encode())      */
    u32 tt_off;                /* the 70 timing records' stock +4..+11, for the donor claims */
    u32 qsbuf_off;             /* QS_SLOTS x 2 x QS_CAP zeroed bytes: record copies     */
    u32 data_off, data_len;    /* zeroed: the data files, then each row's menu block    */
    u32 vrtpl_off, vrtpl_len;  /* rows 9..12 in the six frame-rate CSVs + the K label strings */
    u32 vrpg_off;              /* {len, K label offsets, the B2_5 page (vr_ui.b25)}            */
    u32 vrlv_off;              /* {n; {address, len, stock, new}...}: the LV standby texts     */
    u32 vrlm_off;              /* {n; addresses}: the LV label keys (layout-major, K each)     */
    u32 virtual_off, virtual_len, virtual_state; /* optional bootstrap RCD / owned runtime */
    u32 vrcsv_off;             /* the six stock CSV addresses, in vr_template's order           */
    u32 files_off,files_len,files_state;
    u32 bit_off, bit_len;      /* native bit-depth CSV copies, independent of FPS page */
};

/* firmware */
#define TAB1 0xC0BE5810u        /* picker, eRawBitType 4 =  8-bit */
#define TAB2 0xC0BE59B0u        /* 3 = 10-bit */
#define TAB3 0xC0BE5B50u        /* else 12-bit */
#define KEYBLD 0xC043BCBCu      /* the name emitter's caller that builds lookup keys */
#define EMIT 0xC01F578Cu        /* (out, string, 15) */
#define SENSOR_W 0xC0322C70u    /* (register, value) */
#define GET_OBJ 0xC0057AE8u
#define GET_FMT 0xC005BE90u
#define GET_RES 0xC005C058u
#define CROP_GET 0xC005BB98u     /* (settings) -> Crop Mode, 0 = off */
/* the exclusion manager (FUN_c049ec58) and its recompute of a class list (FUN_c049ee78:
 * asks each class's provider, and on a change writes the cache and notifies -- the
 * notification sets EXCL_FrameRate, which picks the Settings frame-rate list variant) */
#define EXCL_MGR 0xC049EC58u
#define EXCL_RECOMPUTE 0xC049EE78u
#define EXCL_FRAMERATE 0x19u     /* (settings) -> the resolution value (FUN_c005c058) */
#define EXCL_BITDEPTH 0x1Eu
/* the resolution converter MenuValueConverterBase::v21 (C06BDA30): `movw r2 /
 * movt r2` = its {value, row} table, `mov r2, #n` = how many pairs */
#define PAIR_MOVW 0xC06BDA3Cu
#define PAIR_MOVT 0xC06BDA40u
#define PAIR_NUM 0xC06BDA48u
/* the firmware's file object (raw-view's / lossless's in-place write) */
#define F_CTOR 0xC0365E90u
#define F_OPEN 0xC0365FB0u
#define F_READ 0xC0366060u
#define F_WRITE 0xC03660E8u
#define F_SEEK 0xC03661E0u
#define F_CLOSE 0xC0366020u
#define F_DTOR 0xC0365ED0u
#define CAMSCH1 0xC0207188u
#define CS_GET 0xC0207440u
#define CS_SET 0xC02073B8u
#define LV_HOLDER 0xC0423C48u
#define LV_STOP 0xC0423D28u
#define LV_START 0xC0423C88u
#define MOV_SELECTOR 0xC347D1D4u
#define MOVREC_DEFAULT 0xC347E08Fu
#define MOVREC_SEL21 0xC3476609u
#define XMP_FOBJ_PTR 0xC358E140u
#define MOV_ACTIVE 0xC35A952Cu

#define BD12 0u
#define BD10 3u
#define BD8 4u

/* og3krestore's result codes (RLOG +0x0C) and LV reload codes (+0x14) */
enum { R_RESTORED = 1, R_NOPREF = 2, R_FORMAT = 3, R_MOVREC = 4, R_XMPFILE = 5, R_MOVWRITE = 6,
       R_VALUE = 7 };            /* the setting is not the format's stock value: not applied (§12.3) */
enum { L_RELOADED = 1, L_NOFLAG = 2, L_NOTRUN = 3 };

#define W(a) (*(volatile u32 *)(uintptr_t)(a))
#define B8(a) (*(volatile u8 *)(uintptr_t)(a))
#define SW(S, off) W((u32)(uintptr_t)(S) + (off))

static inline u32 irq_off(void)
{
    u32 s;
    __asm volatile("mrs %0, cpsr\n\tcpsid if" : "=r"(s) :: "memory");
    return s;
}
static inline void irq_restore(u32 s) { __asm volatile("msr cpsr_c, %0" :: "r"(s) : "memory"); }
static inline void dmb(void) { __asm volatile("dmb ish" ::: "memory"); }

typedef u32 (*fw0)(void);
typedef u32 (*fw1)(u32);
typedef u32 (*fw2)(u32, u32);
typedef u32 (*fw3)(u32, u32, u32);

static inline u32 rowp(u8 *S, u32 r) { return (u32)(uintptr_t)S + SW(S, S_ROWS) + ROW_SIZE * r; }
static inline u32 entp(u8 *S, u32 i) { return (u32)(uintptr_t)S + SW(S, S_ENTS) + ENT_SIZE * i; }
static inline u32 vmp(u8 *S, u32 v) { return (u32)(uintptr_t)S + SW(S, S_VMS) + OGC_VM_SIZE * v; }

static void copy(u32 dst, u32 src, u32 n)
{
    for (u32 i = 0; i < n; i += 4) W(dst + i) = W(src + i);
}

static u32 bit_flag(u32 bd) { return bd == BD8 ? 1u : bd == BD10 ? 2u : bd == BD12 ? 4u : 0; }

/* Availability belongs to the live RCD. No medium, resolution or label checks. */
static u32 bit_mask(u8 *S)
{
    u32 cur = SW(S, S_CUR);
    return SW(S, S_FLAG) && cur ? W(rowp(S, cur - 1) + ROW_BITMASK) : 0;
}

static void bit_follow(u8 *S)
{
    if (!SW(S, S_BIT_UI)) return;
    u32 mask = bit_mask(S);
    for (u32 i = 0; i < 6; i++) {
        u32 at = SW(S, S_BIT_EN_AT + 4*i), st = SW(S, S_BIT_EN_ON + 4*i);
        if (!at) continue;
        u32 on = mask & (1u << (i % 3));
        B8(at) = mask ? (on ? '1' : '0') : (u8)st;
        B8(at + 2) = mask ? (on ? '2' : '0') : (u8)(st >> 16);
    }
}

/* Preserve an allowed request, otherwise use the first RCD-enabled native
 * menu row. A legacy RCD without a declaration keeps the stock result. */
u32 ogc_bit(u8 *S, u32 requested, u32 stock)
{
    u32 mask = bit_mask(S);
    if (!mask) return stock;
    if (mask & bit_flag(requested)) return requested;
    return mask & 1u ? BD8 : mask & 2u ? BD10 : BD12;
}

/* The row a SEL value names when it is on, or -1. */
static int sel_row(u8 *S)
{
    u32 sel = SW(S, S_SEL);
    if (!sel || sel - 1 >= SW(S, S_NROWS)) return -1;
    return W(rowp(S, sel - 1) + ROW_ON) ? (int)(sel - 1) : -1;
}

/* The converter's pairs: UHD (3, 0), FHD (2, 1), then each row on (stock, its
 * menu row).  value -> row takes the first pair with the value, so the chosen
 * row's pair goes first: with the setting at FHD the cursor, the summary and
 * the Quick Set state land on the chosen format (QS_SHARE.md §12.10). */
static void pairs_build(u8 *S)
{
    u32 s = irq_off(), p = (u32)(uintptr_t)S + S_PAIRS, n = 0;
    int c = sel_row(S);
    if (c >= 0) {
        W(p + 8 * n) = W(rowp(S, (u32)c) + ROW_STOCK);
        W(p + 8 * n + 4) = W(rowp(S, (u32)c) + ROW_MROW);
        n++;
    }
    W(p + 8 * n) = 3; W(p + 8 * n + 4) = 0; n++;
    W(p + 8 * n) = 2; W(p + 8 * n + 4) = 1; n++;
    for (u32 r = 0; r < SW(S, S_NROWS); r++) {
        u32 row = rowp(S, r);
        if (!W(row + ROW_ON) || (int)r == c) continue;
        W(p + 8 * n) = W(row + ROW_STOCK);
        W(p + 8 * n + 4) = W(row + ROW_MROW);
        n++;
    }
    SW(S, S_PAIRN) = n;
    dmb();
    irq_restore(s);
}

/* SEL changes: the pairs follow, and the BIN record is owed (§12.4). */
static void sel_set(u8 *S, u32 sel)
{
    if (SW(S, S_SEL) == sel) return;
    SW(S, S_SEL) = sel;
    SW(S, S_DIRTY) = 1;
    pairs_build(S);
}

/* S.ASPECT: what the two aspect sites return (0 = not ours).  As og3kaspect:
 * FLAG && PICKOK, now with the live row's own aspect. */
static void publish_aspect(u8 *S)
{
    u32 cur = SW(S, S_CUR), a = 0;
    if (SW(S, S_FLAG) && SW(S, S_PICKOK) && cur) a = W(rowp(S, cur - 1) + ROW_ASPECT);
    SW(S, S_ASPECT) = a;
}

/* og3ksel/og3kfmt's transaction, for one core: leaving takes the flag down
 * first; entering prepares everything and publishes FLAG last.  Nothing in the
 * firmware's tables changes any more (virtual profile and mode), so this is all
 * there is.  Not live and leaving: nothing written. */
static void transact(u8 *S, int r)
{
    u32 s = irq_off();
    if (r < 0) {
        if (SW(S, S_CUR) || SW(S, S_FLAG)) {
            SW(S, S_FLAG) = 0;
            dmb();
            SW(S, S_CUR) = 0;
            publish_aspect(S);
            dmb();
        }
    } else {
        SW(S, S_CUR) = (u32)r + 1u;
        dmb();
        SW(S, S_FLAG) = 1;
        publish_aspect(S);
        dmb();
    }
    irq_restore(s);
}

/* Live = the chosen row is on, the setting is its stock value, CinemaDNG (§12.2). */
/* ---- the virtual frame rates (K = 4, core-defined) --------------------------------- *
 * 239.76 / 279.72 ride on the stock 119.88 (internal 7), 17.98 / 8.99 on 23.98
 * (internal 1).  The camera's setting only ever holds those stock values; "row
 * 9 + k was chosen" is S.VRATE (its rank, fps x 100).  The converters read our tables:
 * row -> internal (C06BDB00) and the summary's export -> state (C06CB6D0); both take
 * the first pair that matches, so the chosen row's pair goes first.  A format offers
 * a virtual rate by having picker entries for it (ENT_VRATE). */
#define RATE_PAIRS_STOCK 0xC2E40224u    /* 10 {internal, row}: 9 rows + the hidden 15 fps */
#define SUM_PAIRS_STOCK 0xC2E44EE4u     /* 9 {export, summary state} */
#define RATE_MOVW 0xC06BDB0Cu
#define RATE_MOVT 0xC06BDB10u
#define RATE_NUM 0xC06BDB18u
#define SUM_MOVW 0xC06CB6DCu
#define SUM_MOVT 0xC06CB6E0u
#define SUM_NUM 0xC06CB6E8u
#define FR_GET 0xC005C0F0u              /* (settings) -> the frame rate, internal enum */

static u32 vr_rank(u32 k) { return k == 0 ? VR_RANK0 : k == 1 ? VR_RANK1 : k == 2 ? VR_RANK2 : VR_RANK3; }
static u32 vr_base(u32 k) { return k == 0 ? VR_BASE0 : k == 1 ? VR_BASE1 : k == 2 ? VR_BASE2 : VR_BASE3; }
static u32 vr_tv(u32 k) { return k == 0 ? VR_TV0 : k == 1 ? VR_TV1 : k == 2 ? VR_TV2 : VR_TV3; }
static u32 vr_export(u32 k) { return k == 0 ? VR_EXPORT0 : k == 1 ? VR_EXPORT1 : k == 2 ? VR_EXPORT2 : VR_EXPORT3; }
static u32 vr_index(u32 rank)               /* rank -> k, K if none */
{
    for (u32 k = 0; k < VR_K; k++) if (vr_rank(k) == rank) return k;
    return VR_K;
}

static void rate_pairs_build(u8 *S)
{
    u32 s = irq_off(), p = (u32)(uintptr_t)S + S_RPAIRS, q = (u32)(uintptr_t)S + S_SPAIRS;
    u32 c = vr_index(SW(S, S_VRATE)), n = 0;
    if (SW(S, S_VR_UI) && c < VR_K) {                    /* the chosen row first */
        W(p) = vr_base(c); W(p + 4) = VR_ROW0 + c; n++;
    }
    for (u32 i = 0; i < 9; i++, n++) {                   /* 23.98 .. 119.88 */
        W(p + 8 * n) = W(RATE_PAIRS_STOCK + 8 * i);
        W(p + 8 * n + 4) = W(RATE_PAIRS_STOCK + 8 * i + 4);
    }
    if (SW(S, S_VR_UI)) {
        for (u32 k = 0; k < VR_K; k++) {
            if (k == c) continue;
            W(p + 8 * n) = vr_base(k); W(p + 8 * n + 4) = VR_ROW0 + k; n++;
        }
        W(p + 8 * n) = 0; W(p + 8 * n + 4) = VR_ROW0 + VR_K; n++;    /* the hidden 15 fps */
    } else {
        W(p + 8 * n) = W(RATE_PAIRS_STOCK + 72); W(p + 8 * n + 4) = W(RATE_PAIRS_STOCK + 76); n++;
    }
    SW(S, S_RPAIRN) = n;
    n = 0;
    if (SW(S, S_VR_UI) && c < VR_K) {                    /* the base rate's export: our label */
        W(q) = vr_export(c); W(q + 4) = VR_ROW0 + c; n++;
    }
    for (u32 i = 0; i < 9; i++, n++) {
        W(q + 8 * n) = W(SUM_PAIRS_STOCK + 8 * i);
        W(q + 8 * n + 4) = W(SUM_PAIRS_STOCK + 8 * i + 4);
    }
    if (SW(S, S_VR_UI)) { W(q + 8 * n) = 0; W(q + 8 * n + 4) = VR_ROW0 + VR_K; n++; }
    SW(S, S_SPAIRN) = n;
    dmb();
    irq_restore(s);
}

/* the live row has picker entries for virtual rate `rank` */
static int vr_offered(u8 *S, u32 rank)
{
    u32 cur = SW(S, S_CUR);
    if (!SW(S, S_FLAG) || !cur || !rank) return 0;
    for (u32 i = 0; i < SW(S, S_NENT); i++) {
        u32 e = entp(S, i);
        if (W(e + ENT_ROW) == cur - 1 && W(e + ENT_VRATE) == rank) return 1;
    }
    return 0;
}

/* The stock row (0..8) of a plain picker key's rate: key = the row's label, then
 * 23_98 / 24 / 25 / 30 / 48 / 50 / 60 / 100 / 120, nothing after; 9 = none. */
static u32 key_rate_row(u32 key, u32 lab)
{
    u32 i = 0, n = 0, d = 0;
    while (i < 8 && B8(lab + i)) { if (B8(key + i) != B8(lab + i)) return 9; i++; }
    if (B8(key + i) == '2' && B8(key + i + 1) == '3' && B8(key + i + 2) == '_' && B8(key + i + 3) == '9'
        && B8(key + i + 4) == '8' && B8(key + i + 5) == 0)
        return 0;
    for (; i < 16 && B8(key + i); i++, d++) {
        u32 c = B8(key + i);
        if (c < '0' || c > '9' || d > 2) return 9;
        n = 10 * n + c - '0';
    }
    switch (d ? n : 0) {
    case 24: return 1; case 25: return 2; case 30: return 3; case 48: return 4; case 50: return 5;
    case 60: return 6; case 100: return 7; case 120: return 8;
    }
    return 9;
}

/* Stock row j (0..8) selectable for the live format: it has a plain entry for that
 * rate (Crop Mode keys: build-checked to carry the same rates, rcd.py).  Nothing of
 * ours live: the firmware's own. */
static int rate_row_ok(u8 *S, u32 j)
{
    u32 cur = SW(S, S_CUR);
    if (!SW(S, S_FLAG) || !cur) return 1;
    u32 lab = rowp(S, cur - 1) + ROW_LABEL;
    for (u32 i = 0; i < SW(S, S_NENT); i++) {
        u32 e = entp(S, i);
        if (W(e + ENT_ROW) == cur - 1 && !W(e + ENT_VRATE) && key_rate_row(e + ENT_KEY, lab) == j) return 1;
    }
    return 0;
}

static int ogc_virtual_active(u8 *S, u32 row);

/* An applied memory recipe owns its rate availability, including the native CSV
 * variants selected by the stock medium/geometry class. Static rows retain their
 * original per-variant flags; leaving restores the firmware's own restrictions. */
static void vrate_follow(u8 *S)
{
    if (SW(S, S_VRATE) && !vr_offered(S, SW(S, S_VRATE))) {
        SW(S, S_VRATE) = 0;
        rate_pairs_build(S);
    }
    if (!SW(S, S_VR_UI)) return;
    u32 cur = SW(S, S_CUR);
    u32 dynamic = SW(S, S_FLAG) && cur &&
        (ogc_virtual_active(S, cur - 1) || W(rowp(S, cur - 1) + ROW_BITMASK));
    for (u32 j = 0; j < VR_ROWS; j++) {
        u32 on = j < VR_ROW0 ? rate_row_ok(S, j) : vr_offered(S, vr_rank(j - VR_ROW0));
        for (u32 v = 0; v < VR_CSVS; v++) {
            u32 at = SW(S, S_VR_EN_AT + 4 * (v * VR_ROWS + j)), st = SW(S, S_VR_EN_ON + 4 * (v * VR_ROWS + j));
            if (!at) continue;
            B8(at) = on ? (dynamic ? '1' : (u8)st) : '0';
            B8(at + 2) = on ? (dynamic ? '2' : (u8)(st >> 16)) : '0';
        }
    }
}

static u32 lv_reload(u8 *S);
static int busy(void);

/* FUN_c057a6f8 / FUN_c05821b8: frame-rate commit ([var+8]), before/after native.
 * FUN_c0074d78 only notifies the pipeline when the native enum changes. Our
 * 120/240/280 rows all use enum 7, so a virtual cadence change owes a reload
 * after the native callback has finished, just like same-carrier resolution. */
u32 ogc_rcmt(u8 *S, u32 var, u32 phase)
{
    if (phase) {
        u32 owed = SW(S, S_RATE_LVOWED);
        SW(S, S_RATE_LVOWED) = 0;
        if (owed && SW(S, S_FLAG) && !busy()
            && !(SW(S, S_VRC) && W(SW(S, S_VRC) + 8u))
            && ((fw1)FR_GET)(((fw0)GET_OBJ)()) == owed - 1u
            && lv_reload(S) == L_RELOADED)
            SW(S, S_RATE_LV_RELOADS)++;
        return 0;
    }
    SW(S, S_RATE_LVOWED) = 0;
    u32 row = W(var + 8), k = row - VR_ROW0, v = 0;
    /* without our rows, row 9 is the stock list's hidden 15 fps */
    if (SW(S, S_VR_UI) && k < VR_K && vr_offered(S, vr_rank(k))) v = vr_rank(k);
    SW(S, S_VR_COMMITS)++;
    if (SW(S, S_VRATE) != v) {
        u32 old = ((fw1)FR_GET)(((fw0)GET_OBJ)());
        SW(S, S_VRATE) = v;
        SW(S, S_DIRTY) = 1;
        rate_pairs_build(S);
        /* Read the same row->enum table the original callback will use. A
         * different carrier already triggers the native notification. */
        if (SW(S, S_FLAG) && SW(S, S_VR_UI)) {
            u32 p = (u32)(uintptr_t)S + S_RPAIRS;
            for (u32 i = 0; i < SW(S, S_RPAIRN); i++) {
                if (W(p + 8u * i + 4u) == row) {
                    if (W(p + 8u * i) == old) SW(S, S_RATE_LVOWED) = old + 1u;
                    break;
                }
            }
        }
    }
    return 0;
}

/* ---- the virtual rate's shutter range and angle list (design §15) ------------------ *
 * The virtual rate is live when it is chosen, the live row offers it, and the firmware
 * still holds its base rate (`e`: the enum the site has; ~0 = ask the settings).  k or K. */
static u32 vr_live(u8 *S, u32 e)
{
    u32 rank = SW(S, S_VRATE), k = vr_index(rank);
    if (!SW(S, S_VR_UI) || k >= VR_K || !vr_offered(S, rank)) return VR_K;
    if (e == 0xFFFFFFFFu) e = ((fw1)FR_GET)(((fw0)GET_OBJ)());
    return e == vr_base(k) ? k : VR_K;
}

/* C00C9BD0 has already written the native CinemaDNG FrameRate rational. A
 * virtual selection alone is insufficient: require the matching picked entry
 * and native carrier rational. This runs in the recorder, so never call the
 * interactive settings getter here (its virtual calls can enter locks/tasks).
 * Keep the firmware's control/timecode enums intact. */
static u32 picked_entry(u8 *S, u32 wf);
u32 ogc_recrate(u8 *S, u32 out)
{
    u32 e = out ? picked_entry(S, 0) : 0, rank = SW(S, S_VRATE);
    if (!e || !rank || W(e + ENT_VRATE) != rank) return 0;
    u32 k = vr_index(rank);
    if (!SW(S, S_VR_UI) || k >= VR_K) return 0;
    if (W(out) != (k < 2u ? 120000u : 24000u) || W(out + 4) != 1001u) return 0;
    u32 nom = k == 0 ? VR_NOM0 : k == 1 ? VR_NOM1 : k == 2 ? VR_NOM2 : VR_NOM3;
    W(out) = nom * 1000u;
    W(out + 4) = 1001u;
    return 1;
}

/* Development candidate: avoid the shared DMA driver's semaphore/completion
 * wait for the small M12 high-rate DNG header. The outer Gyro2 call remains
 * intact. This function neither submits files nor releases RAW descriptors.
 * Destination must be native-owned uncached MEM1; CPU stores are visible to
 * the writer without changing aliases or adding a global cache operation.
 * Source may be that pool's original cached alias: read the address supplied
 * by its owner, including any header changes already made by the caller. */
static u32 header_phys(u32 p, u32 n)
{
    if (p >= 0x45000000u && p <= 0x60000000u - n) return p - 0x40000000u;
    if (p >= 0xC5000000u && p <= 0xE0000000u - n) return p - 0xC0000000u;
    return 0;
}

/* The entry the picker last handed out, while it is the live row's and the
 * picker agreed with the menu; 0 otherwise.  `wf`: it must carry these writer
 * flags (the RCD's SEC_WRITER), and its engine rate must be the one latched. */
static u32 picked_entry(u8 *S, u32 wf)
{
    u32 cur = SW(S, S_CUR), off = SW(S, S_LAST_ENT);
    if (SW(S, S_FLAG) != 1u || !SW(S, S_PICKOK) || !cur || cur > SW(S, S_NROWS)) return 0;
    for (u32 i = 0; i < SW(S, S_NENT); i++) {
        u32 e = entp(S, i);
        if (e - (u32)(uintptr_t)S != off) continue;
        if (W(e + ENT_ROW) + 1u != cur || !W(rowp(S, cur - 1u) + ROW_ON)) return 0;
        if ((W(e + ENT_WFLAGS) & wf) != wf || W(e + ENT_ENGFPS) != SW(S, S_FPSLATCH)) return 0;
        if (wf && !((W(e + ENT_WFLAGS) >> 8) & bit_flag(SW(S, S_BITLATCH)))) return 0;
        /* a virtual-rate entry only while that rate is the chosen one */
        if (W(e + ENT_VRATE) && (W(e + ENT_VRATE) != SW(S, S_VRATE) || !SW(S, S_VR_UI))) return 0;
        return e;
    }
    return 0;
}

/* WR_BATCH4M: 64 MiB needs about 61 small DNGs before committing, leaving too
 * little of the 96-descriptor pool to cover media completion latency at very
 * high rates (M12 279.72p). A 4 MiB batch is the existing lossless path's lower
 * bound. Change the native local descriptor, preserving its owned work buffer
 * and completion callback.  Which entries need it is the RCD's to declare. */
void ogc_bulk(u8 *S, u32 params)
{
    if (!params || (params & 3u) || !picked_entry(S, WR_BATCH4M)) return;
    if (W(params) != 0x4000000u || !W(params+4u) || W(params+8u) != 0x40000u || W(params+12u) != 0xC03A55D0u) return;
    W(params) = 0x400000u;
    SW(S, S_BULK_HITS)++;
    SW(S, S_BULK_LAST) = W(params);
}

u32 ogc_hdrcopy(u8 *S, u32 params, u32 frame, u32 caller)
{
    if (caller != 0xC038C780u) return 0;
    SW(S, S_HDR_COPY_CALLS)++;
    SW(S, S_HDR_COPY_WHY) = 1;
    /* WR_HDRCPU: the CPU copy spends ~3 ms per frame inside MovRec; the RCD
     * declares the entries that need it (M12 279.72p; 239.76p keeps the native
     * DMA header, as in the sustained SSD take A001_193). */
    if (!params || (params & 3u) || !picked_entry(S, WR_HDRCPU)) return 0;
    SW(S, S_HDR_COPY_WHY) = 2;
    u32 src = W(params), dst = W(params + 4u), n = W(params + 8u);
    SW(S, S_HDR_COPY_SRC) = src;
    SW(S, S_HDR_COPY_DST) = dst;
    SW(S, S_HDR_COPY_BYTES) = n;
    SW(S, S_HDR_COPY_FRAME) = frame;
    if (!n || n > 0x20000u || ((src | dst | n) & 3u) || W(params + 12u)) return 0;
    if (src != W(0xC358DBA8u) || n != W(0xC358DBA4u)) return 0;
    SW(S, S_HDR_COPY_WHY) = 3;
    /* C038BD98 obtains r5 from C03753C0's native 96-slot descriptor table.
     * The descriptor itself can be static BSS (observed C3585994), whereas
     * its image/header bytes are in MEM1. Check native membership before
     * dereferencing it; the image-buffer alias rules do not describe objects. */
    if ((frame & 3u) || !((frame >= 0xC3000000u && frame <= 0xC4000000u - 0x150u) || header_phys(frame, 0x150u))) return 0;
    u32 member = 0;
    for (u32 i = 0; i < 96u; i++) {
        if (W(0xC351FF48u + 4u * i) == frame) { member = 1; break; }
    }
    if (!member) return 0;
    if (W(frame + 0x14Cu) != n || W(frame + 0x4Cu) < n || W(frame + 0x4Cu) - n != dst) return 0;
    SW(S, S_HDR_COPY_WHY) = 4;
    u32 sp = header_phys(src, n), dp = header_phys(dst, n);
    if (!sp || !dp || dst < 0x45000000u || dst > 0x60000000u - n) return 0;
    if (sp < dp + n && dp < sp + n) return 0;
    ((fw3)0xC00FBDE0u)(dst, src, n);
    SW(S, S_HDR_COPY_HITS)++;
    SW(S, S_HDR_COPY_WHY) = 0;
    return 1;
}

enum { VT_TV = 0, VT_ANGLIST = 1, VT_ANGTV = 2 };

/* VT_TV: the slowest shutter's 1/n (0 = the firmware's own); VT_ANGLIST: the
 * maximum-angle list's rate enum (15p: every angle -- an unknown enum throws);
 * VT_ANGTV: the angle-to-Tv fps x 100 */
u32 ogc_vtv(u8 *S, u32 kind, u32 v, u32 e)
{
    u32 k = vr_live(S, e);
    SW(S, S_VTV_CALLS)++;
    if (k >= VR_K) return kind == VT_TV ? 0 : v;
    SW(S, S_VTV_HITS)++;
    if (kind == VT_TV) return vr_tv(k);
    if (kind == VT_ANGLIST) return 0;
    return vr_rank(k);
}

static void refresh(u8 *S)
{
    int r = sel_row(S);
    if (r >= 0 && SW(S, S_RESVAL) != W(rowp(S, (u32)r) + ROW_STOCK)) {
        sel_set(S, 0);                       /* the setting moved away from the format */
        r = -1;
    }
    transact(S, (r >= 0 && SW(S, S_FMTLATCH) == 0) ? r : -1);
    vrate_follow(S);
    bit_follow(S);
}

/* ---- C005C020: the resolution setter -- the value is always stock (2 or 3) ------ */

/* phase 0: before the firmware's setter; 1: after it */
u32 ogc_sel(u8 *S, u32 v, u32 phase)
{
    if (phase) {
        /* A Virtual RCD commit owns stop/restart and list refresh around this
         * setter. Do not start live view in the middle of that operation. */
        if (SW(S,S_VRC) && W(SW(S,S_VRC)+8u)) {
            SW(S,S_EXCLOWED)=0; SW(S,S_LVOWED)=0; return 0;
        }
        if (SW(S, S_EXCLOWED)) {
            /* the camera recomputes the frame-rate list class only when its own value
             * changes; ours changed without it (UHD <-> OG4K, OG3K <-> S16 ...) */
            u32 list[3] = {EXCL_FRAMERATE, EXCL_BITDEPTH, 0xFFFFFFFFu};
            SW(S, S_EXCLOWED) = 0;
            ((fw2)EXCL_RECOMPUTE)(((fw0)EXCL_MGR)(), (u32)(uintptr_t)list);
            SW(S, S_EXCL_RECOMPUTES)++;
        }
        if (SW(S, S_LVOWED)) {
            SW(S, S_LVOWED) = 0;
            if (lv_reload(S) == 1) SW(S, S_LV_RELOADS)++;
        }
        return 0;
    }
    u32 was = SW(S, S_CUR), old = SW(S, S_RESVAL);
    SW(S, S_SEL_COUNT)++;
    SW(S, S_RESVAL) = v;
    refresh(S);
    /* the camera only rebuilds the live view when its own value changes: OG3K <-> S16
     * (both FHD), or FHD <-> OG3K, keep the value -- then the live view is ours to redo */
    SW(S, S_LVOWED) = SW(S, S_CUR) != was && old == v;
    SW(S, S_EXCLOWED) = SW(S, S_CUR) != was;
    return 0;
}

/* ---- C005BE58: the recording-format setter (MOV guard, og3kfmt) ------------ */
u32 ogc_fmt(u8 *S, u32 fmt)
{
    SW(S, S_FMTLATCH) = fmt;
    dmb();
    refresh(S);
    return 0;
}

/* ---- FUN_c057a6a0 / FUN_c05824d0: the menu committed a resolution row --------- *
 * [var+8] = the row.  Runs before the firmware converts it (through our pairs) and
 * calls the setter: SEL first, so the setter's refresh sees it. */
u32 ogc_cmt(u8 *S, u32 var)
{
    u32 mrow = W(var + 8), sel = 0;
    for (u32 r = 0; r < SW(S, S_NROWS); r++) {
        u32 row = rowp(S, r);
        if (W(row + ROW_ON) && W(row + ROW_MROW) == mrow) { sel = r + 1; break; }
    }
    sel_set(S, sel);
    return 0;
}

/* ---- virtual modes ------------------------------------------------------------ */
static u32 vm_of(u8 *S, u32 id)
{
    u32 v = id - SW(S, S_VMID0);
    return v < SW(S, S_NVM) ? vmp(S, v) : 0;
}

static u32 tbl_field(u32 k)
{
    switch (k) {
    case T_TIM: return T_TIM_FIELD;
    case T_META: return T_META_FIELD;
    case T_R28: return T_R28_FIELD;
    case T_R38: return T_R38_FIELD;
    case T_R14: return T_R14_FIELD;
    case T_R68: return T_R68_FIELD;
    default: return T_REG_FIELD;
    }
}
static u32 tbl_count(u32 k)
{
    switch (k) {
    case T_TIM: return T_TIM_COUNT;
    case T_META: return T_META_COUNT;
    case T_R28: return T_R28_COUNT;
    case T_R38: return T_R38_COUNT;
    case T_R14: return T_R14_COUNT;
    case T_R68: return T_R68_COUNT;
    default: return T_REG_COUNT;
    }
}
static u32 tbl_stride(u32 k)
{
    switch (k) {
    case T_TIM: return T_TIM_STRIDE;
    case T_META: return T_META_STRIDE;
    case T_R28: return T_R28_STRIDE;
    case T_R38: return T_R38_STRIDE;
    case T_R14: return T_R14_STRIDE;
    case T_R68: return T_R68_STRIDE;
    default: return T_REG_STRIDE;
    }
}
static u32 tbl_buf(u32 k)
{
    switch (k) {
    case T_TIM: return VM_BUF_TIM;
    case T_META: return VM_BUF_META;
    case T_R28: return VM_BUF_R28;
    case T_R38: return VM_BUF_R38;
    case T_R14: return VM_BUF_R14;
    case T_R68: return VM_BUF_R68;
    default: return VM_BUF_REG;
    }
}

/* The donor's row of one table, copied into the vm's buffer at the place whose
 * distance to the table's base the stride's power of two divides (so an index
 * exists that lands on it), its mode id replaced by ours.  0 = no donor row. */
static u32 clone_row(u32 vm, u32 k, u32 base, u32 count)
{
    u32 stride = tbl_stride(k), donor = W(vm + VM_DONOR);
    for (u32 i = 0; i < count; i++) {
        u32 src = base + i * stride;
        if (W(src) != donor) continue;
        u32 g = stride & (0u - stride);
        u32 buf = vm + tbl_buf(k);
        u32 row = buf + ((base - buf) & (g - 1u));
        copy(row, src, stride);
        W(row) = W(vm + VM_ID);
        return row;
    }
    return 0;
}

/* What the row data asks of the cloned rows, and nothing else (the core adds no
 * difference of its own: a row that asks for nothing gives the donor, word for
 * word -- test_v3_rescustom's self-proof): the picked timing (+4 hmax|tail, +8
 * vmax|x) and, when the row says so, the video clamp of the receiver row. */
static void vm_apply(u32 vm)
{
    u32 tim = W(vm + VM_PTR + 4 * T_TIM), r38 = W(vm + VM_PTR + 4 * T_R38);
    if (tim && W(vm + VM_TW0)) {
        W(tim + 4) = W(vm + VM_TW0);
        W(tim + 8) = W(vm + VM_TW1);
    }
    if (r38 && W(vm + VM_CLAMP)) {
        W(r38 + 0x04) |= 0x8u;
        W(r38 + 0x18) |= 0xC000u;
    }
}

/* The data file's overrides of one table for this virtual mode (§14.2 VMODES):
 * {kind, offset, value}; kind T_R10 sets the +0x10 value.  Applied once, right
 * after the donor's row is cloned, so the picker's timing words still win. */
static void vm_override(u8 *S, u32 vm, u32 kind, u32 row)
{
    u32 o = (u32)(uintptr_t)S + W(vm + VM_OVR);
    for (u32 i = 0; i < W(vm + VM_NOVR); i++, o += OVR_BYTES) {
        if (W(o) != kind) continue;
        if (kind == T_R10) W(vm + VM_R10) = W(o + 8);
        else if (row) W(row + W(o + 4)) = W(o + 8);
    }
}

static void vm_fill(u8 *S, u32 vm, u32 desc)
{
    for (u32 k = 0; k < OGC_NTABLES; k++) {
        if (k == T_REG) continue;
        u32 row = clone_row(vm, k, W(desc + tbl_field(k)), W(desc + tbl_count(k)));
        W(vm + VM_PTR + 4 * k) = row;
        if (row) vm_override(S, vm, k, row);
    }
    /* the {value, mode} pair of descriptor +0x10 (FUN_c031ffa0): mode at +4 */
    u32 b10 = W(desc + R10_FIELD), n10 = W(desc + R10_COUNT), donor = W(vm + VM_DONOR);
    W(vm + VM_R10OK) = 0;
    for (u32 i = 0; i < n10; i++)
        if (W(b10 + i * R10_STRIDE + 4) == donor) {
            W(vm + VM_R10) = W(b10 + i * R10_STRIDE);
            W(vm + VM_R10OK) = 1;
            vm_override(S, vm, T_R10, 0);
            break;
        }
    vm_apply(vm);
    W(vm + VM_FILLED) = 1;
}

static void vm_fill_reg(u8 *S, u32 vm, u32 regdesc)
{
    u32 row = clone_row(vm, T_REG, W(regdesc + T_REG_FIELD), W(regdesc + T_REG_COUNT));
    W(vm + VM_PTR + 4 * T_REG) = row;
    if (row) vm_override(S, vm, T_REG, row);
    W(vm + VM_REGFILLED) = 1;
}

static u32 vm_zoom(u8 *S, u32 vm)
{
    if (!W(vm + VM_ZFILLED)) {
        u32 desc = W(OGC_IMAGER);
        u32 base = W(desc + Z_FIELD), n = W(desc + Z_COUNT), donor = W(vm + VM_DONOR);
        for (u32 i = 0; i < n; i++) {
            u32 src = base + i * Z_STRIDE;
            if (W(src) != donor) continue;
            copy(vm + VM_BUF_ZOOM, src, Z_STRIDE);
            W(vm + VM_BUF_ZOOM) = W(vm + VM_ID);
            vm_override(S, vm, T_ZOOM, vm + VM_BUF_ZOOM);
            W(vm + VM_ZFILLED) = 1;
            break;
        }
        if (!W(vm + VM_ZFILLED)) W(vm + VM_ZFILLED) = 2;       /* donor has no row */
    }
    return W(vm + VM_ZFILLED) == 1 ? vm + VM_BUF_ZOOM : 0;
}

/* idx with base + idx * stride == row (mod 2^32), or 0 with *ok = 0. */
static u32 fake_index(u32 row, u32 base, u32 stride, u32 *ok)
{
    u32 d = row - base, k = (u32)__builtin_ctz(stride), m = stride >> k;
    *ok = 0;
    if (d & ((1u << k) - 1u)) return 0;
    u32 x = m;                                  /* inverse of the odd m, mod 2^32 */
    for (int i = 0; i < 5; i++) x *= 2u - m * x;
    u32 idx = (d >> k) * x;
    if (k) idx &= 0xFFFFFFFFu >> k;
    if (idx * stride != d) return 0;
    *ok = 1;
    return idx;
}

/* ---- the seven index lookups (FUN_c0320ba0 ...) ------------------------------ *
 * r0 = the index, r1 = 1 when it is ours; r1 = 0: the shim goes down. */
uint64_t ogc_vlook(u8 *S, u32 k, u32 obj, u32 id)
{
    u32 vm = vm_of(S, id), ok = 0, idx = 0;
    if (!vm) return 0;
    u32 desc = W(obj);
    u32 s = irq_off();
    if (k == T_REG) {
        if (!W(vm + VM_REGFILLED)) vm_fill_reg(S, vm, desc);
    } else if (!W(vm + VM_FILLED)) {
        vm_fill(S, vm, desc);
    }
    if (k == T_R10) {                       /* a value, not an index */
        ok = W(vm + VM_R10OK);
        idx = W(vm + VM_R10);
    } else {
        u32 row = W(vm + VM_PTR + 4 * k);
        if (row) idx = fake_index(row, W(desc + tbl_field(k)), tbl_stride(k), &ok);
    }
    irq_restore(s);
    if (!ok) return 0;
    SW(S, S_LOOK_HITS)++;
    return (uint64_t)idx | ((uint64_t)1 << 32);
}

/* ---- the four shutter-angle call sites of FUN_c032c750 (og3kfps) ------------- *
 * As today's core: while an OG is live, the angle arithmetic of our mode gets the
 * picked rate's nominal fps; an entry with 0 (OG3K100) keeps the getter's answer. */
u32 ogc_fps(u8 *S, u32 mode, u32 got)
{
    u32 vm = vm_of(S, mode);
    if (!vm || SW(S, S_FLAG) != 1) return got;
    dmb();
    u32 nom = W(vm + VM_NOM);
    return nom ? nom : got;
}

/* ---- C043CCF8: the picker ------------------------------------------------------ */
static int key_has_label(u32 key, u32 lab)
{
    for (u32 i = 0; i < 15; i++) {
        u8 c = B8(lab + i);
        if (!c) return i != 0;
        if (B8(key + i) != c) return 0;
    }
    return 1;
}

/* the entry's key (16 bytes, NUL-padded) is exactly the first n bytes of key */
static int key_eq(u32 ek, u32 key, u32 n)
{
    for (u32 i = 0; i < n; i++) if (B8(ek + i) != B8(key + i)) return 0;
    return n < 16 ? B8(ek + n) == 0 : 1;
}

u32 ogc_pick(u8 *S, u32 table, u32 key)
{
    u32 bd;
    if (table == TAB3) bd = BD12;
    else if (table == TAB2) bd = BD10;
    else if (table == TAB1) bd = BD8;
    else return 0;
    u32 klen = 0;
    while (klen < 16 && B8(key + klen)) klen++;
    /* "...CROP": the key of a Crop Mode recording (FUN_c043b828 appends it) */
    u32 crop = klen > 4 && B8(key + klen - 4) == 'C' && B8(key + klen - 3) == 'R'
               && B8(key + klen - 2) == 'O' && B8(key + klen - 1) == 'P';
    for (u32 pass = 0, i = 0; pass < 2; i++) {
        if (i == SW(S, S_NENT)) { pass++; i = 0xFFFFFFFFu; continue; }
        u32 e = entp(S, i), row = rowp(S, W(e + ENT_ROW));
        if (!W(row + ROW_ON)) continue;
        /* pass 0: the entries of the virtual rate now chosen; pass 1: the plain ones */
        if (W(e + ENT_VRATE) != (pass ? 0u : SW(S, S_VRATE)) || (!pass && !SW(S, S_VRATE))) continue;
        /* a format without Crop Mode records its plain entry for a CROP key */
        u32 n = crop && !(W(row + ROW_RFLAGS) & RFLAG_CROP) ? klen - 4 : klen;
        if (!key_eq(e + ENT_KEY, key, n)) continue;
        u32 mask = W(row + ROW_BITMASK);
        if (mask && !(mask & bit_flag(bd))) continue;
        SW(S, S_BITLATCH) = bd;
        SW(S, S_PICKOK) = 1;
        SW(S, S_FPSLATCH) = W(e + ENT_ENGFPS);
        SW(S, S_LAST_ENT) = e - (u32)(uintptr_t)S;
        u32 vm = vmp(S, W(e + ENT_VM));
        u32 s = irq_off();
        W(vm + VM_TW0) = W(e + ENT_W0);
        W(vm + VM_TW1) = W(e + ENT_W1);
        W(vm + VM_NOM) = W(e + ENT_NOMINAL);
        if (W(vm + VM_FILLED)) vm_apply(vm);
        dmb();
        irq_restore(s);
        SW(S, S_HITS)++;
        publish_aspect(S);
        return e;
    }
    /* A key with one of our labels and no entry (OG3K at 119.88): the picker
     * falls back to UHD30, so the display chain must follow it (MATCH). */
    for (u32 r = 0; r < SW(S, S_NROWS); r++)
        if (key_has_label(key, rowp(S, r) + ROW_LABEL)) {
            SW(S, S_PICKOK) = 0;
            publish_aspect(S);
            break;
        }
    return 0;
}

/* ---- Crop Mode and frame-rate greying (Jose's five sites, our state) ------------ *
 * Only while one of our rows is live (S.FLAG): its data file's flags and fastest
 * rate decide; otherwise every site gives the firmware's own answer. */
enum { G_CROPST = 0, G_CROPEFF = 1, G_FRMAX = 2, G_FRCLASS = 3, G_MAG = 4, G_BITCLASS = 5 };

static u32 rank_of(u32 e)
{
    for (u32 i = 0; i < 10; i++) if (W(RATE_TABLE + 12 * i) == e) return W(RATE_TABLE + 12 * i + 8);
    return 0x7FFFFFFFu;
}

/* the rate-list state classes of FUN_c04a1120 and the fastest rate each allows
 * (MenuItemMovieFrameRate::v8 computes the same limits): {class, rate enum} */
static u32 class_max(u32 c)
{
    switch (c) { case 0: return 7; case 5: return 6; case 3: return 5; case 1: return 3;
                 case 4: return 2; case 2: return 1; }
    return 0xFFFFFFFFu;
}

static u32 limit(u32 e, u32 mx)
{
    return rank_of(e) > mx ? 0xFFFFFFFFu : e;      /* e within the row's fastest, or "no" */
}

/* The normalizer uses stock enums, even for a virtual rate. Derive the fastest
 * supported enum from the applied recipe's actual entries, including VR bases. */
static u32 virtual_rate_max(u8 *S)
{
    u32 best = 0xFFFFFFFFu, br = 0;
    for (u32 j = 0; j < VR_ROWS; j++) {
        u32 on = j < VR_ROW0 ? rate_row_ok(S, j) : vr_offered(S, vr_rank(j - VR_ROW0));
        if (!on) continue;
        u32 en = j < VR_ROW0 ? W(RATE_PAIRS_STOCK + 8 * j) : vr_base(j - VR_ROW0);
        u32 rk = rank_of(en);
        if (rk != 0x7FFFFFFFu && rk >= br) { best = en; br = rk; }
    }
    return best;
}

u32 ogc_gate(u8 *S, u32 kind, u32 v)
{
    u32 cur = SW(S, S_CUR);
    if (!SW(S, S_FLAG) || !cur) return kind == G_CROPST ? 0 : v;
    u32 row = rowp(S, cur - 1), fl = W(row + ROW_RFLAGS), mx = W(row + ROW_MAXRATE);
    if (kind == G_BITCLASS && W(row + ROW_BITMASK)) return 0;
    if ((kind == G_FRMAX || kind == G_FRCLASS) &&
        (ogc_virtual_active(S, cur - 1) || W(row + ROW_BITMASK))) {
        u32 en = virtual_rate_max(S);
        if (en != 0xFFFFFFFFu) {
            if (kind == G_FRMAX) return en;
            u32 best = v, br = 0, rk = rank_of(en);
            for (u32 c = 0; c < 6; c++) {
                u32 cr = rank_of(class_max(c));
                if (cr <= rk && cr > br) { best = c; br = cr; }
            }
            return best;
        }
    }
    /* v3: MAXRATE is the fastest mode's rate -- a virtual rate is only made when its
     * rank fits, and its base is always slower; the rows are greyed per entry */
    switch (kind) {
    case G_CROPST:              /* 1 = greyed (the shim returns 0) */
        return !(fl & RFLAG_CROP);
    case G_CROPEFF:             /* the effective Crop Mode: off where the format has none */
        return fl & RFLAG_CROP ? v : 0;
    case G_FRMAX:               /* the normalising limit (a rate enum): the slower of the two */
        if (!mx || rank_of(v) <= mx) return v;
        for (u32 e = 0, best = 0xFFFFFFFFu, br = 0; ; e++) {
            if (e == 10) return best == 0xFFFFFFFFu ? v : best;
            u32 en = W(RATE_TABLE + 12 * e), rk = W(RATE_TABLE + 12 * e + 8);
            if (rk <= mx && rk >= br) { best = en; br = rk; }
        }
    case G_FRCLASS: {           /* the list's class: the fastest class within both */
        u32 m = class_max(v);
        if (!mx || m == 0xFFFFFFFFu || rank_of(m) <= mx) return v;
        u32 best = v, br = 0;
        for (u32 c = 0; c < 6; c++) {
            u32 cm = class_max(c), rk = rank_of(cm);
            /* m is faster than mx here, so every class within mx is within m too */
            if (limit(cm, mx) != 0xFFFFFFFFu && rk > br) { best = c; br = rk; }
        }
        return best;
    }
    case G_MAG:                 /* the 4x magnifier's key: MAG8 for a narrow 1:1 window (S16) */
        return fl & RFLAG_MAG8 ? 0x46F8u : v;
    }
    return v;
}

/* ---- C03A6DD8 (og3kgs): our virtual profiles are "raw movie" ------------------- *
 * The gain dispatch asks the current LV canvas (LiveViewModeMgr +8, its +0 = the
 * pid) for its class.  A virtual pid's number cannot carry the raw-movie class
 * (131..190 has no empty slot), so it is answered for the live row's pids; a stock
 * canvas (standby, playback) keeps the firmware's own answer. */
#define LV_MGR 0xC375D840u
static u32 var_of(u8 *S, u32 pid);
u32 ogc_gs(u8 *S)
{
    if (SW(S, S_FLAG) != 1u) return 0;
    u32 c = W(LV_MGR + 8), v = c ? var_of(S, W(c)) : 0;
    return v && W(v + VAR_ROW) + 1u == SW(S, S_CUR) ? 1u : 0u;
}

/* ---- C043A19C: the canvas ------------------------------------------------------ */
static void apply_list(u32 canvas, u32 list)
{
    for (;;) {
        u32 off = W(list);
        if (off == 0xFFFFFFFFu) return;
        W(canvas + off) = W(list + 4);
        list += 8;
    }
}

/* Crop Mode as the settings hold it (FUN_c005bb98, Jose's getter): 0 = off */
static u32 crop_now(void) { return ((fw1)CROP_GET)(((fw0)GET_OBJ)()); }

/* The variant whose virtual profile is `pid`, as an address, or 0. */
static u32 var_of(u8 *S, u32 pid)
{
    u32 v = (u32)(uintptr_t)S + SW(S, S_VARS);
    for (u32 i = 0; i < SW(S, S_NVAR); i++, v += VAR_SIZE)
        if (W(v + VAR_PID) == pid) return v;
    return 0;
}

/* The live row's standby groups: a canvas of one of a group's profiles gets its
 * pairs (the six preview heights of a 3:2 row are the first group).  1 if any. */
static u32 apply_standby(u8 *S, u32 row, u32 canvas, u32 pid)
{
    u32 g = (u32)(uintptr_t)S + W(row + ROW_SBY), hit = 0;
    for (u32 i = 0; W(row + ROW_SBY) && i < W(row + ROW_NSBY); i++) {
        u32 np = W(g) & 0xFFFFu, cond = W(g) >> 16, nq = W(g + 4), pairs = g + 8 + 4 * np, mine = 0;
        for (u32 k = 0; k < np; k++) if (W(g + 8 + 4 * k) == pid) mine = 1;
        if (mine && cond) mine = (cond == 2) == (crop_now() != 0);
        if (mine) {
            for (u32 k = 0; k < nq; k++) W(canvas + W(pairs + 8 * k)) = W(pairs + 8 * k + 4);
            hit = 1;
        }
        g = pairs + 8 * nq;
    }
    return hit;
}

#define CAP_WORDS 67u             /* FUN_c0439d18's record: 65 table words + 0x17B0, 0xFCA */
u32 ogc_canvas(u8 *S, u32 canvas, u32 pid)
{
    u32 base = (u32)(uintptr_t)S, cur = SW(S, S_CUR), live = SW(S, S_FLAG) && cur;
    u32 v = var_of(S, pid);
    if (v) {
        /* our virtual profile: declared here, whole, on its base row's gather --
         * the row's lists, then the entry's own (the virtual table) */
        if (!live || W(v + VAR_ROW) != cur - 1) return 0;
#ifdef OGC_CAP_BACK
        /* diagnostic: {hits, pid, record}, the record as the firmware filled it, then ours */
        u8 *cap = S - OGC_CAP_BACK;
        W((u32)(uintptr_t)cap) += 1; W((u32)(uintptr_t)cap + 4) = pid; W((u32)(uintptr_t)cap + 8) = canvas;
        for (u32 k = 0; k < CAP_WORDS; k++) W((u32)(uintptr_t)cap + 0x10 + 4 * k) = W(canvas + 4 * k);
#endif
        u32 row = rowp(S, cur - 1);
        apply_list(canvas, base + W(row + ROW_REC));
        if (W(v + VAR_LIST)) apply_list(canvas, base + W(v + VAR_LIST));
        u32 f = SW(S, S_FPSLATCH);
        if (f) W(canvas + 0x30) = f;
        u32 bd = SW(S, S_BITLATCH);
        W(canvas + 0x80) = bd == BD12 ? 7u : 10u;
        W(canvas + 0x84) = bd == BD8 ? 10u : bd == BD10 ? 9u : 7u;
#ifdef OGC_CAP_BACK
        for (u32 k = 0; k < CAP_WORDS; k++) W((u32)(uintptr_t)cap + 0x120 + 4 * k) = W(canvas + 4 * k);
#endif
        return 1;
    }
    if (live && apply_standby(S, rowp(S, cur - 1), canvas, pid)) return 2;
    u32 pb = SW(S, S_PBROW);
    if (pb && (W(canvas + 0x80) & 0x10000u)) {
        apply_list(canvas, base + W(rowp(S, pb - 1) + ROW_PB));
        return 3;
    }
    return 0;
}

/* ---- C0437B48: the resolution name -------------------------------------------- */
u32 ogc_name(u8 *S, u32 out, u32 sizes, u32 caller)
{
    u32 w = W(sizes + 8), h = W(sizes + 0xC), r = 0xFFFFFFFFu, cur = SW(S, S_CUR);
    if (w) {
        /* a clip is known by its DNG size only: of rows sharing one, the live one */
        u32 pb = 0;
        if (cur && W(rowp(S, cur - 1) + ROW_AW) == w && W(rowp(S, cur - 1) + ROW_AH) == h) pb = cur;
        for (u32 i = 0; !pb && i < SW(S, S_NROWS); i++)
            if (W(rowp(S, i) + ROW_AW) == w && W(rowp(S, i) + ROW_AH) == h) pb = i + 1;
        SW(S, S_PBROW) = pb;
        if (pb) r = pb - 1;
    }
    if (r == 0xFFFFFFFFu) {
        if (!SW(S, S_FLAG) || !SW(S, S_CUR)) return 0;
        r = SW(S, S_CUR) - 1;
    }
    if (caller == KEYBLD) return 0;               /* lookup keys stay stock tokens */
    ((fw3)EMIT)(out, rowp(S, r) + ROW_LABEL, 0x0F);
    return 1;
}

/* ---- C0437E98: the main output descriptor (og3kout) ---------------------------- *
 * The stock descriptors 0 (1620x911) and 2 (320x180) are 16:9.  For a row of
 * another aspect -- the RCD's aspect enum -- the same width gets that aspect's
 * height (3:2: 1080 / 213; 2:1: 810 / 160).  A template is made per aspect from
 * the stock one; 16:9 and unknown aspects keep the firmware's own. */
static u32 udiv(u32 n, u32 d);
static u32 aspect_ratio(u32 a, u32 *num)        /* width : height = *num : return */
{
    switch (a) {
    case 2: *num = 3; return 2;             /* 3:2 */
    case 9: *num = 2; return 1;             /* 2:1 */
    }
    *num = 0;
    return 0;
}

u32 ogc_out(u8 *S, u32 obj, u32 idx)
{
    u32 cur = SW(S, S_CUR), pb = SW(S, S_PBROW), a = 0, num, den;
    /* the live row's aspect, else the played clip's (either one not 16:9) */
    if (SW(S, S_FLAG) && SW(S, S_PICKOK) && cur) a = W(rowp(S, cur - 1) + ROW_ASPECT);
    if (!aspect_ratio(a, &num) && pb) a = W(rowp(S, pb - 1) + ROW_ASPECT);
    if (!(den = aspect_ratio(a, &num))) return 0;
    if (idx != 0 && idx != 2) return 0;
    u32 tpl = (u32)(uintptr_t)S + (idx ? S_TPL2 : S_TPL0);
    if (W(tpl) != a) {
        u32 d = W(obj + idx * 8);
        if (d < 0xC0000000u || d >= 0xC4000000u) return 0;
        u32 w = W(d);
        if (!w || w > 4096u || W(d + 4) != (w * 9u) >> 4) return 0;     /* the stock 16:9 one */
        u32 h = udiv(w * den, num);
        copy(tpl + 4, d, 44);
        W(tpl + 0x08) = h;
        W(tpl + 0x18) = h;
        dmb();
        W(tpl) = a;
    }
    SW(S, S_OUT_HITS)++;
    return tpl + 4;
}

/* ---- the magnifier's table (descriptor +0x128) -------------------------------- */
/* FUN_c031ac38(dst, _, mode): copies the mode's 0x5C row into dst. */
u32 ogc_ac38(u8 *S, u32 dst, u32 id)
{
    u32 vm = vm_of(S, id);
    if (!vm) return 0;
    u32 z = vm_zoom(S, vm);
    if (!z) return 0;
    copy(dst, z, Z_STRIDE);
    return 1;
}

/* XC_ImageSensorIMX410::v32(imager, i): the magnifier window start, registers
 * 0x22..0x25, from the current mode's row (decompiled, same arithmetic). */
u32 ogc_v32(u8 *S, u32 obj, u32 i)
{
    u32 vm = vm_of(S, W(obj + 4));
    if (!vm) return 0;
    u32 z = vm_zoom(S, vm);
    if (!z) return 1;                        /* no row: write nothing, never garbage */
    u32 a = W(z + 0x1C) + W(z + 0x38 + i * 4);
    u32 b = W(z + 0x44 + i * 4) >> 1;
    ((fw2)SENSOR_W)(3, 1);
    ((fw2)SENSOR_W)(0x22, a & 0xFF);
    ((fw2)SENSOR_W)(0x23, (a & 0xFFFF) >> 8);
    ((fw2)SENSOR_W)(0x24, b & 0xFF);
    ((fw2)SENSOR_W)(0x25, (b & 0xFFFF) >> 8);
    return 1;
}

/* ---- the boot restore (og3krestore, unchanged in substance) -------------------- */
static u32 lv_reload(u8 *S)
{
    u32 holder = ((fw0)LV_HOLDER)();
    u32 msp = W(holder);
    if (!msp || !W(msp + 4)) return L_NOTRUN;
    u32 cs = ((fw0)CAMSCH1)();
    u32 st = ((fw1)CS_GET)(cs);
    SW(S, S_RLOG + 0x18) = st;
    if (st != 6) ((fw2)CS_SET)(cs, 6);
    ((fw1)LV_STOP)(holder);
    ((fw1)LV_START)(holder);
    if (st != 6) ((fw2)CS_SET)(cs, st);
    return L_RELOADED;
}

static u32 fnv(u32 p, u32 n)
{
    u32 h = 0x811C9DC5u;
    for (u32 i = 0; i < n; i++) { h ^= B8(p + i); h *= 0x01000193u; }
    return h;
}

static int busy(void)
{
    u32 sel = W(MOV_SELECTOR) == 0x21 ? MOVREC_SEL21 : MOVREC_DEFAULT;
    if (B8(sel)) return R_MOVREC;
    if (W(XMP_FOBJ_PTR)) return R_XMPFILE;
    if (B8(MOV_ACTIVE)) return R_MOVWRITE;
    return 0;
}

/* The row whose label the record's SEL names (8 bytes, 0-padded), on, or -1. */
static int row_by_label(u8 *S, u32 lab)
{
    for (u32 r = 0; r < SW(S, S_NROWS); r++) {
        u32 row = rowp(S, r);
        if (W(row + ROW_ON) && W(row + ROW_LABEL) == W(lab) && W(row + ROW_LABEL + 4) == W(lab + 4))
            return (int)r;
    }
    return -1;
}

/* §12.3: the format the BIN record names comes back when the camera's setting is
 * still that format's stock value, CinemaDNG, not recording.  Never calls the
 * firmware's setter: the setting is already what it must be. */
static int ogc_virtual_unready(u8 *S, u32 row);
static void ogc_restore(u8 *S)
{
    if (++SW(S, S_RLOG) != 1) return;
    u32 obj = ((fw0)GET_OBJ)();
    u32 fmt = ((fw1)GET_FMT)(obj);
    u32 val = ((fw1)GET_RES)(obj);
    SW(S, S_FMTLATCH) = fmt;
    SW(S, S_RESVAL) = val;
    SW(S, S_RLOG + 8) = fmt;
    SW(S, S_RLOG + 4) = val;
    dmb();
    u32 cfg = SW(S, S_CFG), code;
    int r = -1;
    if (W(cfg + CFG_MAGIC) == OGC_CFG_MAGIC && W(cfg + CFG_VERSION) == OGC_CFG_VERSION
        && W(cfg + CFG_SUM) == fnv(cfg, CFG_SUM))
        r = row_by_label(S, cfg + CFG_SEL);
    /* A memory recipe cannot be restored from the saved row identity alone.
     * Wait for the producer's first Apply instead of activating the bootstrap. */
    if (r >= 0 && ogc_virtual_unready(S, (u32)r)) r = -1;
    if (r < 0) code = R_NOPREF;
    else if (val != W(rowp(S, (u32)r) + ROW_STOCK)) code = R_VALUE;
    else if (fmt != 0) code = R_FORMAT;
    else if ((code = (u32)busy()) == 0) {
        SW(S, S_SEL) = (u32)r + 1;         /* the record already says it: not dirty */
        pairs_build(S);
        refresh(S);
        /* and 239.76, when the record says so and the camera still holds 119.88 */
        u32 rank = W(cfg + CFG_FLAGS) >> 8, k = vr_index(rank);
        if ((W(cfg + CFG_FLAGS) & CFG_FLAG_VRATE) && k < VR_K && vr_offered(S, rank)
            && ((fw1)FR_GET)(obj) == vr_base(k)) {
            SW(S, S_VRATE) = rank;
            rate_pairs_build(S);
        }
        u32 flag = SW(S, S_FLAG);
        SW(S, S_RLOG + 0x10) = flag;
        SW(S, S_RLOG + 0x14) = flag == 1 ? lv_reload(S) : L_NOFLAG;
        code = R_RESTORED;
    }
    SW(S, S_RLOG + 0xC) = code;
    dmb();
}

/* ---- C0088C60 (bl FUN_c0088660, the settings save; raw-view's point) ----------- *
 * After the firmware's own save: when SEL is owed to the BIN, write the record
 * in place (open 7 = overwrite without truncating, seek, write, seek, read back).
 * Not while recording.  Any failure: still owed, next save tries again. */
/* The file at S.PATH is still this sup -- its FSB1 header is the 32 bytes this
 * block was loaded with -- opened READ-only (mode 1 fails when the file is gone;
 * mode 7 would create it: 2026-10-08, a renamed 32RESCUS.BIN came back as a
 * 128-byte stub that the loader then refused).  0 = it is; else SAVE_* why not. */
enum { SAVE_GONE = 1, SAVE_FOREIGN = 2, SAVE_IO = 3 };
static u32 still_me(u8 *S)
{
    u32 fo = SW(S, S_FOBJ), back = fo + 0xF00, me = SW(S, S_CFG) - 32, why = SAVE_GONE;
    ((fw2)F_CTOR)(fo, 1);
    if (((fw3)F_OPEN)(fo, SW(S, S_PATH), 1)) {
        W(back + 32) = 0;
        ((u32 (*)(u32, u32, u32, u32))F_READ)(fo, back, 32, back + 32);
        why = 0;
        if (W(back + 32) != 32) why = SAVE_FOREIGN;
        for (u32 i = 0; !why && i < 32; i += 4)
            if (W(back + i) != W(me + i)) why = SAVE_FOREIGN;
        ((fw1)F_CLOSE)(fo);
    }
    ((fw2)F_DTOR)(fo, 2);
    return why;
}

static u32 ogc_save(u8 *S)
{
    if (!SW(S, S_DIRTY) || busy()) return 0;
    u32 cfg = SW(S, S_CFG), fo = SW(S, S_FOBJ), back = fo + 0xF00;
    u32 why = still_me(S);
    if (why) {                      /* renamed, deleted or replaced: never create, never write */
        SW(S, S_SAVE_FAILS)++;
        SW(S, S_SAVE_WHY) = why;
        return 0;
    }
    int r = sel_row(S);
    W(cfg + CFG_MAGIC) = OGC_CFG_MAGIC;
    W(cfg + CFG_VERSION) = OGC_CFG_VERSION;
    W(cfg + CFG_SEL) = r >= 0 ? W(rowp(S, (u32)r) + ROW_LABEL) : 0;
    W(cfg + CFG_SEL + 4) = r >= 0 ? W(rowp(S, (u32)r) + ROW_LABEL + 4) : 0;
    W(cfg + CFG_SEL_STOCK) = r >= 0 ? W(rowp(S, (u32)r) + ROW_STOCK) : 0;
    W(cfg + CFG_FLAGS) = r >= 0 && SW(S, S_VRATE) ? CFG_FLAG_VRATE | SW(S, S_VRATE) << 8 : 0u;
    W(cfg + CFG_SUM) = fnv(cfg, CFG_SUM);                  /* NEN/EN are kept as read */
    u32 ok = 0;
    ((fw2)F_CTOR)(fo, 1);
    if (((fw3)F_OPEN)(fo, SW(S, S_PATH), 7)) {             /* it exists (checked): overwrite in place */
        if (((fw3)F_SEEK)(fo, 32, 0)) {
            u32 wrote = ((fw3)F_WRITE)(fo, cfg, CFG_BYTES);
            if (wrote && ((fw3)F_SEEK)(fo, 32, 0)) {
                W(back + CFG_BYTES) = 0;
                ((u32 (*)(u32, u32, u32, u32))F_READ)(fo, back, CFG_BYTES, back + CFG_BYTES);
                if (W(back + CFG_BYTES) == CFG_BYTES) {
                    ok = 1;
                    for (u32 i = 0; i < CFG_BYTES; i += 4)
                        if (W(back + i) != W(cfg + i)) { ok = 0; break; }
                }
            }
        }
        ((fw1)F_CLOSE)(fo);
    }
    ((fw2)F_DTOR)(fo, 2);
    if (ok) { SW(S, S_DIRTY) = 0; SW(S, S_SAVES)++; SW(S, S_SAVE_WHY) = 0; }
    else { SW(S, S_SAVE_FAILS)++; SW(S, S_SAVE_WHY) = SAVE_IO; }
    return ok;
}

/* ==== §14: the format data files (\fpSup\RESCUS\*.RCD) ============================ */
#define DIR_CTOR 0xC0366918u
#define DIR_OPEN 0xC0366990u
#define DIR_NEXT 0xC03669F8u
#define DIR_DTOR 0xC0366940u
#define DRIVE_SD 1u
#define DIR_ENTRY 0x238u
#define ATTR_HIDDEN 0x02u
#define ATTR_DIR 0x10u
/* the FOBJ scratch (0x1000): the file object at +0, then */
#define FO_HOLDER 0x400u        /* the directory holder (0x10)                  */
#define FO_ENTRY 0x420u         /* one DIR_ENTRY (0x238)                        */
#define FO_PATH 0x680u          /* "\fpSup\RESCUS\NAME.RCD" (64)                */
#define FO_NAMES 0x6C0u         /* RCD_MAX_NAMES x 16: the names, sorted        */
#define FO_SIZES 0x7C0u         /* RCD_MAX_NAMES words                          */
#define FO_FILES 0x800u         /* MAX_ROWS words: each enabled row's file      */
#define FO_VMS 0x820u           /* OGC_MAX_VMS x {row, donor}                   */
#define NAME_BYTES 16u
#define TT 0xC0B59500u          /* the timing table: the donors must be stock modes */

static u32 u8at(u32 a) { return B8(a); }

static u32 text_ok(u32 a, u32 size, u32 label)
{
    u32 n = 0;
    while (n < size && u8at(a + n)) {
        u32 c = u8at(a + n);
        if (label) {
            if (!((c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z'))) return 0;
        } else if (c < 0x20 || c > 0x7E || c == ',' || c == '@' || c == '"') {
            return 0;
        }
        n++;
    }
    if (n == 0 || n >= size) return 0;               /* empty, or no NUL inside */
    for (u32 i = n; i < size; i++) if (u8at(a + i)) return 0;
    return n;
}

static int stock_mode(u32 id)
{
    for (u32 i = 0; i < 70; i++) if (W(TT + 0x20 * i) == id) return 1;
    return 0;
}

static u32 ovr_ok(u32 kind, u32 off)
{
    if (kind < OGC_NTABLES) return off >= 4 && off < tbl_stride(kind) && !(off & 3);
    if (kind == T_R10) return off == 0;
    if (kind == T_ZOOM) return off >= 4 && off < Z_STRIDE && !(off & 3);
    return 0;
}

/* The section of type `typ` (absolute address, *len), 0 = none. */
static u32 sec(u32 f, u32 typ, u32 *len)
{
    u32 t = f + W(f + RH_SECOFF);
    for (u32 i = 0; i < W(f + RH_NSEC); i++, t += RCD_SEC_BYTES)
        if (W(t) == typ) { *len = W(t + 8); return f + W(t + 4); }
    return 0;
}


/* ==== v3: the core times every rate (ogc_layout.RATES / VR_TIME / solve / gen_entries) ==== */
static u32 udiv(u32 n, u32 d)          /* the A9 has no divider; boot-time only */
{
    u32 q = 0, r = 0;
    for (int i = 31; i >= 0; i--) {
        r = r << 1 | ((n >> i) & 1u);
        if (r >= d) { r -= d; q |= 1u << i; }
    }
    return q;
}

/* candidate c: 0..8 the stock rates in the list's order, 9 + k the virtual rates */
static u32 c_cyc(u32 c)
{
    switch (c) {
    case 0: return RATE_CYC0; case 1: return RATE_CYC1; case 2: return RATE_CYC2; case 3: return RATE_CYC3;
    case 4: return RATE_CYC4; case 5: return RATE_CYC5; case 6: return RATE_CYC6; case 7: return RATE_CYC7;
    case 8: return RATE_CYC8; case 9: return VR_CYC0; case 10: return VR_CYC1; case 11: return VR_CYC2;
    }
    return VR_CYC3;
}
static u32 c_pal(u32 c)
{
    switch (c) {
    case 0: return RATE_PAL0; case 1: return RATE_PAL1; case 2: return RATE_PAL2; case 3: return RATE_PAL3;
    case 4: return RATE_PAL4; case 5: return RATE_PAL5; case 6: return RATE_PAL6; case 7: return RATE_PAL7;
    case 8: return RATE_PAL8;
    }
    return 0;
}
static u32 c_eng(u32 c)
{
    switch (c) {
    case 0: return RATE_ENG0; case 1: return RATE_ENG1; case 2: return RATE_ENG2; case 3: return RATE_ENG3;
    case 4: return RATE_ENG4; case 5: return RATE_ENG5; case 6: return RATE_ENG6; case 7: return RATE_ENG7;
    case 8: return RATE_ENG8; case 9: return VR_ENG0; case 10: return VR_ENG1; case 11: return VR_ENG2;
    }
    return VR_ENG3;
}
static u32 c_nom(u32 c)
{
    switch (c) {
    case 0: return RATE_NOM0; case 1: return RATE_NOM1; case 2: return RATE_NOM2; case 3: return RATE_NOM3;
    case 4: return RATE_NOM4; case 5: return RATE_NOM5; case 6: return RATE_NOM6; case 7: return RATE_NOM7;
    case 8: return RATE_NOM8; case 9: return VR_NOM0; case 10: return VR_NOM1; case 11: return VR_NOM2;
    }
    return VR_NOM3;
}
static u32 c_rank(u32 c)
{
    switch (c) {
    case 0: return RATE_RANK0; case 1: return RATE_RANK1; case 2: return RATE_RANK2; case 3: return RATE_RANK3;
    case 4: return RATE_RANK4; case 5: return RATE_RANK5; case 6: return RATE_RANK6; case 7: return RATE_RANK7;
    case 8: return RATE_RANK8; case 9: return VR_RANK0; case 10: return VR_RANK1; case 11: return VR_RANK2;
    }
    return VR_RANK3;
}
static u32 c_gen(u32 c)                 /* is this candidate made at all */
{
    switch (c) { case 9: return VR_GEN0; case 10: return VR_GEN1; case 11: return VR_GEN2; case 12: return VR_GEN3; }
    return c < 9;
}
static u32 c_row(u32 c)                 /* the stock row whose key it uses */
{
    switch (c) { case 9: return VR_BASEJ0; case 10: return VR_BASEJ1; case 11: return VR_BASEJ2; case 12: return VR_BASEJ3; }
    return c;
}

/* key = label + the stock row's suffix (+ "CROP"); 0 if it does not fit 15 */
static u32 key_make(u32 out, u32 lab, u32 j, u32 crop)
{
    u32 n = 0;
    for (u32 i = 0; i < 16; i++) B8(out + i) = 0;
    while (n < 8 && B8(lab + n)) { B8(out + n) = B8(lab + n); n++; }
    u32 sfx;                            /* up to five characters, little-endian packed */
    switch (j) {
    case 0: sfx = '2' | '3' << 8 | '_' << 16 | (u32)'9' << 24; break;
    case 1: sfx = '2' | '4' << 8; break;
    case 2: sfx = '2' | '5' << 8; break;
    case 3: sfx = '3' | '0' << 8; break;
    case 4: sfx = '4' | '8' << 8; break;
    case 5: sfx = '5' | '0' << 8; break;
    case 6: sfx = '6' | '0' << 8; break;
    case 7: sfx = '1' | '0' << 8 | '0' << 16; break;
    default: sfx = '1' | '2' << 8 | '0' << 16; break;
    }
    for (; sfx; sfx >>= 8) B8(out + n++) = (u8)sfx;
    if (j == 0) B8(out + n++) = '8';
    if (crop) { B8(out + n) = 'C'; B8(out + n + 1) = 'R'; B8(out + n + 2) = 'O'; B8(out + n + 3) = 'P'; n += 4; }
    return n < 16;
}

/* (vmax, tail) for `cyc` at hmax `hm`: the real period is hmax x vmax (§36) -> vmax
 * rounded; tail keeps hmax x (vmax - 1) + tail exact, at least MIN_TAIL.  0 = none. */
static u32 solve(u32 hm, u32 cyc, u32 *tail)
{
    u32 vm = udiv(2u * cyc + hm, 2u * hm), t = cyc - hm * (vm - 1u);
    if (t < MIN_TAIL) { vm--; t += hm; }
    if (vm < 2 || vm > 0xFFFFu || t > 0xFFFFu) return 0;
    *tail = t;
    return vm;
}

/* gen record: key[16], donor, w0, w1, engfps, nominal, vrate, rank, crop */
enum { G_KEY = 0, G_DONOR = 16, G_W0 = 20, G_W1 = 24, G_ENG = 28, G_NOM = 32, G_VRATE = 36,
       G_RANK = 40, G_CROP = 44, G_BYTES = 48 };

/* The i-th picker entry the core makes for file f (ogc_layout.gen_entries, same order)
 * into out; 0 = there are fewer. */
static u32 gen_entry(u32 f, u32 i, u32 out)
{
    u32 ln, md = sec(f, SEC_MODES, &ln), n = 0, crops = W(f + RH_FLAGS) & RFLAG_CROP ? 2u : 1u;
    for (u32 c = 0; c < 9 + VR_K; c++) {
        if (!c_gen(c)) continue;
        u32 rank = c_rank(c), m = 0;
        for (u32 k = 0; k < W(md); k++)
            if (rank <= W(md + 4 + RCD_MODE_BYTES * k + 4)) { m = md + 4 + RCD_MODE_BYTES * k; break; }
        if (!m) continue;
        u32 hm = c_pal(c) && W(m + 12) ? W(m + 12) : W(m + 8), tail = 0, vm = solve(hm, c_cyc(c), &tail);
        if (!vm) continue;
        for (u32 crop = 0; crop < crops; crop++, n++) {
            if (n != i) continue;
            if (!key_make(out + G_KEY, f + RH_LABEL, c_row(c), crop)) return 0;
            W(out + G_DONOR) = W(m);
            W(out + G_W0) = hm | tail << 16;
            W(out + G_W1) = vm | W(m + 16) << 16;
            W(out + G_ENG) = c_eng(c);
            W(out + G_NOM) = c_nom(c);
            W(out + G_VRATE) = c < 9 ? 0u : rank;
            W(out + G_RANK) = rank;
            W(out + G_CROP) = crop;
            /* An explicit, required RCD section can reconstruct the historical
             * sensor240/native30 experiment without changing normal entries.
             * Sensor/engine/shutter cadence is explicit; the UI/container key stays native. */
            u32 sln, sensor = sec(f, SEC_CAPTURE_TIMING, &sln);
            if (sensor && sln >= 4) {
                u32 nt = W(sensor);
                if (nt <= MAX_GEN && sln == 4u + 24u * nt)
                    for (u32 t = sensor + 4; nt--; t += 24)
                        if (W(t) == rank && W(t + 4) == crop) {
                            W(out + G_W0) = W(t + 8);
                            W(out + G_W1) = W(t + 12);
                            W(out + G_ENG) = W(t + 16);
                            W(out + G_NOM) = W(t + 20);
                        }
            }
            return 1;
        }
    }
    return 0;
}

static u32 gen_count(u32 f)
{
    u32 g[G_BYTES / 4], n = 0;
    while (n <= MAX_GEN && gen_entry(f, n, (u32)(uintptr_t)g)) n++;
    return n;
}

/* the rate canvas (absolute) a generated entry takes: its rank or every rank, its Crop Mode */
static u32 rc_match(u32 sel, u32 g)
{
    return (W(sel) == 0 || W(sel) == W(g + G_RANK)) && W(sel + 4) == W(g + G_CROP);
}

/* A generated entry's writer policy: the file's first SEC_WRITER record for its
 * rank (0 = every rank) and Crop Mode, as flags | bit mask << 8; 0 = the firmware's own. */
static u32 writer_flags(u32 f, u32 g)
{
    u32 ln, a = sec(f, SEC_WRITER, &ln);
    for (u32 i = 0; a && i < W(a); i++) {
        u32 t = a + 4 + 16 * i;
        if ((W(t) == 0 || W(t) == W(g + G_RANK)) && W(t + 4) == W(g + G_CROP)) return W(t + 12) | W(t + 8) << 8;
    }
    return 0;
}

/* rcd.decode(), the same checks in the same order: 0 = good, else WHY_*. */

static int in_pool(u8 *S, u32 pid)
{
    for (u32 i = 0; i < OGC_MAX_VARS; i++) if (SW(S, S_POOL + 4 * i) == pid) return 1;
    return 0;
}

static int profile_ok(u8 *S, u32 pid)
{
    return !in_pool(S, pid) && pid <= 0x200u && W(OGC_MAPPING + 4 * pid) != 0xFFFFFFFFu;
}

static int pairs_ok(u32 at, u32 n)
{
    for (u32 i = 0; i < n; i++) {
        u32 o = W(at + 8 * i);
        if (o >= 0x108 || (o & 3)) return 0;
    }
    return 1;
}

static u32 rcd_check(u8 *S, u32 f, u32 n)
{
    if (n < RCD_HDR || n > RCD_MAX_FILE || (n & 3)) return WHY_SIZE;
    if (W(f + RH_MAGIC) != RCD_MAGIC) return WHY_MAGIC;
    if (W(f + RH_VERSION) < RCD_VERSION_MIN || W(f + RH_VERSION) > RCD_VERSION_MAX
        || W(f + RH_HLEN) != RCD_HDR)
        return WHY_VERSION;
    if (W(f + RH_MINCORE) > OGC_CORE_VERSION) return WHY_NEWER;
    if (W(f + RH_FLEN) != n) return WHY_SIZE;
    if (W(f + RH_SUM) != fnv(f + RCD_HDR, n - RCD_HDR)) return WHY_SUM;
    if (u8at(f + RH_LABEL + 7) || !text_ok(f + RH_LABEL, 8, 1)) return WHY_FIELD;
    u32 st = W(f + RH_STOCK), as = W(f + RH_ASPECT);
    if ((st != 2 && st != 3) || (as != 2 && as != 3 && as != 9)
        || (as == 9 && W(f + RH_MINCORE) < 2) || (W(f + RH_FLAGS) & ~15u))
        return WHY_FIELD;
    /* every key the core makes fits 15: a Crop Mode label + "23_98CROP" */
    if ((W(f + RH_FLAGS) & RFLAG_CROP) && u8at(f + RH_LABEL + 6)) return WHY_FIELD;
    u32 ns = W(f + RH_NSEC), so = W(f + RH_SECOFF);
    if (!ns || ns > RCD_MAX_SECS || so < RCD_HDR || (so & 3) || so + RCD_SEC_BYTES * ns > n)
        return WHY_SECTION;
    u32 seen = 0;
    for (u32 i = 0; i < ns; i++) {
        u32 t = f + so + RCD_SEC_BYTES * i, typ = W(t), off = W(t + 4), ln = W(t + 8), fl = W(t + 12);
        if (off < RCD_HDR || (off & 3) || ln > n - off || (fl & ~1u)) return WHY_SECTION;
        if ((typ < SEC_VMODES || typ > SEC_PACK) && typ != SEC_STANDBY && typ != SEC_MODES
            && typ != SEC_RATECANVAS && typ != SEC_BINFILT && typ != SEC_CAPTURE_TIMING
            && typ != SEC_BITDEPTH && typ != SEC_WRITER) {
            if (fl & 1u) return WHY_UNKNOWN;
            continue;
        }
        if (seen & (1u << typ)) return WHY_SECTION;
        if (typ == SEC_CAPTURE_TIMING && fl != 1u) return WHY_ENTRY;
        if (typ == SEC_BITDEPTH && fl != 1u) return WHY_BITDEPTH;
        if (typ == SEC_WRITER && fl != 1u) return WHY_WRITER;
        seen |= 1u << typ;
    }
    u32 need = 1u << SEC_MODES | 1u << SEC_CANVAS | 1u << SEC_UI | 1u << SEC_PACK;
    if ((seen & need) != need) return WHY_SECTION;
    u32 pid = W(f + RH_PROFILE);
    if (!profile_ok(S, pid)) return WHY_PROFILE;
    u32 ln, a = sec(f, SEC_MODES, &ln), nm = ln >= 4 ? W(a) : 0, mx = 0;
    if (!nm || nm > RCD_MAX_MODES || ln != 4 + RCD_MODE_BYTES * nm) return WHY_ENTRY;
    for (u32 i = 0; i < nm; i++) {
        u32 m = a + 4 + RCD_MODE_BYTES * i;
        if (!W(m + 4) || W(m + 4) > 100000u || !W(m + 8) || W(m + 8) > 0xFFFFu || W(m + 12) > 0xFFFFu
            || W(m + 16) > 0xFFFFu || !stock_mode(W(m)))
            return WHY_ENTRY;
        if (W(m + 4) > mx) mx = W(m + 4);
    }
    if (W(f + RH_MAXRATE) != mx) return WHY_FIELD;
    u32 bits = sec(f, SEC_BITDEPTH, &ln);
    if (bits && (W(f + RH_MINCORE) < 4u || ln != 4u || !W(bits) || W(bits) > 7u))
        return WHY_BITDEPTH;
    u32 md = a;
    if ((a = sec(f, SEC_CAPTURE_TIMING, &ln)) != 0) {
        u32 nt = ln >= 4 ? W(a) : 0;
        if (!nt || nt > MAX_GEN || ln != 4u + 24u * nt) return WHY_ENTRY;
        for (u32 i = 0, t = a + 4; i < nt; i++, t += 24) {
            u32 rank = W(t), crop = W(t + 4), m = 0, c;
            for (c = 0; c < 9 + VR_K; c++) if (c_gen(c) && c_rank(c) == rank) break;
            if (c == 9 + VR_K || crop > ((W(f + RH_FLAGS) & RFLAG_CROP) ? 1u : 0u)) return WHY_ENTRY;
            for (u32 k = 0; k < nm; k++)
                if (rank <= W(md + 4 + RCD_MODE_BYTES * k + 4)) { m = md + 4 + RCD_MODE_BYTES * k; break; }
            if (!m) return WHY_ENTRY;
            u32 hm = c_pal(c) && W(m + 12) ? W(m + 12) : W(m + 8);
            if ((W(t + 8) & 0xFFFFu) != hm || (W(t + 8) >> 16) < MIN_TAIL ||
                (W(t + 12) & 0xFFFFu) < 2u || (W(t + 12) >> 16) != W(m + 16) ||
                W(t + 16) < 0x3F800000u || W(t + 16) > 0x447A0000u ||
                !W(t + 20) || W(t + 20) > 1000u) return WHY_ENTRY;
            for (u32 j = 0; j < i; j++)
                if (W(a + 4 + 24*j) == rank && W(a + 8 + 24*j) == crop) return WHY_ENTRY;
        }
    }
    u32 ne = gen_count(f);
    if (!ne || ne > MAX_GEN) return WHY_ENTRY;
    if ((a = sec(f, SEC_WRITER, &ln)) != 0) {
        u32 nw = ln >= 4 ? W(a) : 0;
        if (W(f + RH_MINCORE) < 5u || !nw || nw > RCD_MAX_WRITER || ln != 4u + 16u * nw) return WHY_WRITER;
        for (u32 i = 0, t = a + 4; i < nw; i++, t += 16) {
            u32 rk = W(t), known = !rk;
            for (u32 c = 0; c < 9 + VR_K; c++) if (c_rank(c) == rk) known = 1;
            if (!known || W(t + 4) > ((W(f + RH_FLAGS) & RFLAG_CROP) ? 1u : 0u) || !W(t + 8) || W(t + 8) > 7u
                || !W(t + 12) || (W(t + 12) & ~(WR_BATCH4M | WR_HDRCPU)))
                return WHY_WRITER;
            for (u32 j = 0; j < i; j++)
                if (W(a + 4 + 16 * j) == rk && W(a + 8 + 16 * j) == W(t + 4)) return WHY_WRITER;
        }
    }
    a = sec(f, SEC_CANVAS, &ln);
    if (ln < RCD_CANVAS_HEAD) return WHY_CANVAS;
    u32 nr = W(a + 12), npb = W(a + 16);
    if (W(a + 20) || W(a + 24) || W(a + 28) || nr > RCD_MAX_PAIRS || npb > RCD_MAX_PAIRS
        || ln != RCD_CANVAS_HEAD + 8 * (nr + npb))
        return WHY_CANVAS;
    for (u32 i = 0; i < nr + npb; i++) {
        u32 o = W(a + RCD_CANVAS_HEAD + 8 * i);
        if (o >= 0x108 || (o & 3)) return WHY_CANVAS;
    }
    a = sec(f, SEC_UI, &ln);
    if (ln != RCD_UI_BYTES || !text_ok(a, RCD_UI_ROW, 0) || !text_ok(a + RCD_UI_ROW, RCD_UI_SUM, 0))
        return WHY_UI;
    a = sec(f, SEC_PACK, &ln);
    if ((a - f) & 63u || ln < 16 || W(a) != 0x0052424Eu) return WHY_PACK;
    if ((a = sec(f, SEC_STANDBY, &ln)) != 0) {
        u32 ng = ln >= 4 ? W(a) : 0, at = a + 4, end = a + ln;
        if (!ng || ng > OGC_MAX_SBY_GROUPS) return WHY_STANDBY;
        for (u32 g = 0; g < ng; g++) {
            if (at + 8 > end) return WHY_STANDBY;
            u32 np = W(at) & 0xFFFFu, nq = W(at + 4);
            if ((W(at) >> 16) > 2 || !np || np > OGC_MAX_SBY_PIDS || !nq || nq > OGC_MAX_SBY_PAIRS
                || at + 8 + 4 * np + 8 * nq > end)
                return WHY_STANDBY;
            if (!pairs_ok(at + 8 + 4 * np, nq)) return WHY_STANDBY;
            for (u32 k = 0; k < np; k++) {
                u32 q = W(at + 8 + 4 * k);
                if (q > 0x200u || in_pool(S, q)) return WHY_STANDBY;
            }
            at += 8 + 4 * np + 8 * nq;
        }
        if (at != end) return WHY_STANDBY;
    }
    if ((a = sec(f, SEC_RATECANVAS, &ln)) != 0) {
        u32 nl = ln >= 4 ? W(a) : 0, at = a + 4, end = a + ln;
        if (!nl || nl > RCD_MAX_RCANVAS) return WHY_ENTRY;
        for (u32 l = 0; l < nl; l++) {
            if (at + 16 > end) return WHY_ENTRY;
            u32 rk = W(at), bp = W(at + 8), nq = W(at + 12), known = !rk;
            for (u32 c = 0; c < 9 + VR_K; c++) if (c_rank(c) == rk) known = 1;
            if (!known || W(at + 4) > 1 || nq > RCD_MAX_PAIRS || at + 16 + 8 * nq > end) return WHY_ENTRY;
            if (!pairs_ok(at + 16, nq)) return WHY_ENTRY;
            if (!profile_ok(S, bp ? bp : pid)) return WHY_PROFILE;
            at += 16 + 8 * nq;
        }
        if (at != end) return WHY_ENTRY;
    }
    if ((a = sec(f, SEC_BINFILT, &ln)) != 0) {
        if (W(f + RH_MINCORE) < 3 || ln != 20 ||
            (W(a) != 1 && W(a) != 3) || (W(a+4) != 1 && W(a+4) != 3) ||
            W(a+8) >= 6 || W(a+12) >= 6 || W(a+16) > 1) return WHY_BINFILT;
    }
    if ((a = sec(f, SEC_VMODES, &ln)) != 0) {
        u32 no = ln >= 4 ? W(a) : 0xFFFFFFFFu;
        if (no > RCD_MAX_OVR || ln != 4 + RCD_OVR_BYTES * no) return WHY_OVERRIDE;
        u32 g[G_BYTES / 4], ga = (u32)(uintptr_t)g;
        for (u32 i = 0; i < no; i++) {
            u32 o = a + 4 + RCD_OVR_BYTES * i, d = W(o), hit = 0;
            for (u32 j = 0; j < ne; j++) if (gen_entry(f, j, ga) && W(ga + G_DONOR) == d) hit = 1;
            if (!hit || !ovr_ok(W(o + 4), W(o + 8))) return WHY_OVERRIDE;
        }
    }
    return 0;
}

static void why(u8 *S, u32 i, u32 reason, u32 bad)
{
    if (bad && i < 32) SW(S, S_RCD_BAD) |= 1u << i;
    if (i < RCD_MAX_NAMES) B8((u32)(uintptr_t)S + S_RCD_WHYS + i) = (u8)reason;
    if (!SW(S, S_RCD_WHY)) SW(S, S_RCD_WHY) = i << 16 | reason;
}

/* label (8 bytes at a) equals label at b */
static int same_label(u32 a, u32 b) { return W(a) == W(b) && W(a + 4) == W(b + 4); }

/* Enabled (§14.3): the BIN's enable list when it is valid and not empty, else
 * the first MAX_ROWS valid files. */
static int enabled(u8 *S, u32 label)
{
    u32 cfg = SW(S, S_CFG), nen = W(cfg + CFG_NEN);
    if (W(cfg + CFG_MAGIC) != OGC_CFG_MAGIC || W(cfg + CFG_VERSION) != OGC_CFG_VERSION
        || W(cfg + CFG_SUM) != fnv(cfg, CFG_SUM) || !nen || nen > OGC_MAX_ROWS)
        return 1;
    for (u32 i = 0; i < nen; i++) if (same_label(cfg + CFG_EN + 8 * i, label)) return 1;
    return 0;
}

static u32 slen(u32 a) { u32 n = 0; while (u8at(a + n)) n++; return n; }

static int name_less(u32 a, u32 b)
{
    for (u32 i = 0; i < NAME_BYTES; i++) {
        u32 x = u8at(a + i), y = u8at(b + i);
        if (x != y) return x < y;
        if (!x) return 0;
    }
    return 0;
}

/* The .RCD names in <dir of path>\RESCUS, sorted; their sizes.  Returns how many. */
static u32 list_rcd(u8 *S, const char *path, u32 *seen)
{
    u32 fo = SW(S, S_FOBJ), holder = fo + FO_HOLDER, ent = fo + FO_ENTRY, dir = fo + FO_PATH;
    u32 names = fo + FO_NAMES, sizes = fo + FO_SIZES, n = 0, d = 0, cut = 0;
    *seen = 0;
    for (u32 i = 0; i < 40 && path[i]; i++) if (path[i] == '\\') cut = i + 1;
    for (; d < cut; d++) B8(dir + d) = (u8)path[d];
    B8(dir + d++) = 'R'; B8(dir + d++) = 'E'; B8(dir + d++) = 'S';
    B8(dir + d++) = 'C'; B8(dir + d++) = 'U'; B8(dir + d++) = 'S';
    B8(dir + d) = 0;
    ((fw2)DIR_CTOR)(holder, DRIVE_SD);
    if (!((fw2)DIR_OPEN)(holder, dir)) { ((fw2)DIR_DTOR)(holder, 2); return 0; }
    for (;;) {
        for (u32 i = 0; i < DIR_ENTRY; i += 4) W(ent + i) = 0;
        if (!((fw2)DIR_NEXT)(holder, ent)) break;
        if (B8(ent + 0x218) & (ATTR_DIR | ATTR_HIDDEN)) continue;
        u32 len = 0, ok = 1;
        u8 nm[NAME_BYTES];
        for (;; len++) {
            u32 c = B8(ent + 2 * len) | B8(ent + 2 * len + 1) << 8;
            if (!c) break;
            if (len == 12 || c < 0x21 || c > 0x7E || c == '\\') { ok = 0; break; }
            nm[len] = (u8)c;
        }
        if (!ok || len < 5 || nm[0] == '.') continue;
        if (nm[len - 4] != '.' || (nm[len - 3] | 0x20) != 'r' || (nm[len - 2] | 0x20) != 'c'
            || (nm[len - 1] | 0x20) != 'd')
            continue;
        (*seen)++;
        if (n == RCD_MAX_NAMES || W(ent + 0x214)) continue;
        u32 at = names + NAME_BYTES * n;
        for (u32 i = 0; i < NAME_BYTES; i++) B8(at + i) = i < len ? nm[i] : 0;
        W(sizes + 4 * n) = W(ent + 0x210);
        n++;
    }
    ((fw2)DIR_DTOR)(holder, 2);
    for (u32 i = 1; i < n; i++)                         /* insertion sort, n <= 16 */
        for (u32 j = i; j && name_less(names + NAME_BYTES * j, names + NAME_BYTES * (j - 1)); j--) {
            for (u32 k = 0; k < NAME_BYTES; k += 4) {
                u32 t = W(names + NAME_BYTES * j + k);
                W(names + NAME_BYTES * j + k) = W(names + NAME_BYTES * (j - 1) + k);
                W(names + NAME_BYTES * (j - 1) + k) = t;
            }
            u32 t = W(sizes + 4 * j);
            W(sizes + 4 * j) = W(sizes + 4 * (j - 1));
            W(sizes + 4 * (j - 1)) = t;
        }
    return n;
}

/* Read one file into the files' area (64-aligned): its address, or 0. */
static u32 read_rcd(u8 *S, u32 name, u32 size, u32 *reason)
{
    u32 fo = SW(S, S_FOBJ), dir = fo + FO_PATH, p = dir + slen(dir), got = 0;
    u32 at = (SW(S, S_DATA) + SW(S, S_DATA_USED) + 63u) & ~63u;
    if (size < RCD_HDR || size > RCD_MAX_FILE) { *reason = WHY_SIZE; return 0; }
    if (at + size > SW(S, S_DATA) + SW(S, S_DATA_CAP)) { *reason = WHY_ROOM; return 0; }
    B8(p) = '\\';
    for (u32 i = 0; i <= 12; i++) B8(p + 1 + i) = B8(name + i);
    ((fw2)F_CTOR)(fo, DRIVE_SD);
    u32 ok = ((fw3)F_OPEN)(fo, dir, 1);
    if (ok) {
        ((u32 (*)(u32, u32, u32, u32))F_READ)(fo, at, size, (u32)(uintptr_t)&got);
        ((fw1)F_CLOSE)(fo);
    }
    ((fw2)F_DTOR)(fo, 2);
    B8(p) = 0;
    if (!ok) { *reason = WHY_OPEN; return 0; }
    if (got != size) { *reason = WHY_READ; return 0; }
    return at;
}

/* S's body from the enabled files (ogc_layout.state_blob, the same bytes):
 * rows, entries, the variant table, each row's lists, each variant's own list,
 * each row's standby groups, the overrides, then (64-aligned) the virtual modes. */
#define FO_VARS 0x920u          /* OGC_MAX_VARS x {row, base row, list source, entry} */

static u32 fill_s(u8 *S, u32 n)
{
    u32 base = (u32)(uintptr_t)S, fo = SW(S, S_FOBJ), files = fo + FO_FILES, vms = fo + FO_VMS;
    u32 fv = fo + FO_VARS, nvm = 0, nent = 0, nvar = 0, ln, p;
    for (u32 r = 0; r < n; r++) {
        u32 f = W(files + 4 * r);
        W(fv + 16 * r) = r;
        W(fv + 16 * r + 4) = W(OGC_MAPPING + 4 * W(f + RH_PROFILE));
        W(fv + 16 * r + 8) = 0;
        W(fv + 16 * r + 12) = 0xFFFFFFFFu;
    }
    nvar = n;
    u32 g[G_BYTES / 4], ga = (u32)(uintptr_t)g;
    for (u32 r = 0; r < n; r++) {
        u32 f = W(files + 4 * r), ne = gen_count(f);
        for (u32 i = 0; i < ne; i++) {
            gen_entry(f, i, ga);
            u32 d = W(ga + G_DONOR), have = 0;
            for (u32 v = 0; v < nvm; v++) if (W(vms + 8 * v) == r && W(vms + 8 * v + 4) == d) have = 1;
            if (!have) {
                if (nvm == OGC_MAX_VMS) return 0;
                W(vms + 8 * nvm) = r; W(vms + 8 * nvm + 4) = d; nvm++;
            }
        }
        u32 c = sec(f, SEC_RATECANVAS, &ln);
        for (u32 l = 0, at = c + 4; c && l < W(c); l++) {
            if (nvar == OGC_MAX_VARS) return 0;
            u32 bp = W(at + 8);
            W(fv + 16 * nvar) = r;
            W(fv + 16 * nvar + 4) = W(OGC_MAPPING + 4 * (bp ? bp : W(f + RH_PROFILE)));
            W(fv + 16 * nvar + 8) = at;
            W(fv + 16 * nvar + 12) = 0xFFFFFFFFu;
            nvar++;
            at += 16 + 8 * W(at + 12);
        }
        nent += ne;
    }
    /* sizes first: nothing is written past S_BYTES */
    p = S_BODY + ROW_SIZE * n + ENT_SIZE * nent + VAR_SIZE * nvar;
    for (u32 r = 0; r < n; r++) {
        u32 f = W(files + 4 * r), a = sec(f, SEC_CANVAS, &ln);
        p += 8 * (W(a + 12) + W(a + 16)) + 8;
        if (W(f + RH_ASPECT) == 2 && W(a)) p += 8 + 4 * 6 + 8;
        if ((a = sec(f, SEC_STANDBY, &ln)) != 0) p += ln - 4;
        if ((a = sec(f, SEC_VMODES, &ln)) != 0) p += OVR_BYTES * W(a);
    }
    for (u32 v = n; v < nvar; v++) p += 8 * W(W(fv + 16 * v + 8) + 12) + 4;
    p = (p + 63u) & ~63u;
    if (p + OGC_VM_SIZE * nvm > OGC_S_BYTES) return 0;
    for (u32 i = S_BODY; i < p + OGC_VM_SIZE * nvm; i += 4) SW(S, i) = 0;

    u32 rows = S_BODY, ents = rows + ROW_SIZE * n, vars = ents + ENT_SIZE * nent;
    u32 at = vars + VAR_SIZE * nvar, e0 = 0;
    for (u32 r = 0; r < n; r++) {
        u32 f = W(files + 4 * r), row = base + rows + ROW_SIZE * r, a = sec(f, SEC_CANVAS, &ln);
        u32 aspect = W(f + RH_ASPECT), nr = W(a + 12), npb = W(a + 16);
        W(row + ROW_ENUM) = W(f + RH_ENUM);
        W(row + ROW_PID) = SW(S, S_POOL + 4 * r);
        W(row + ROW_ASPECT) = aspect;
        W(row + ROW_AW) = W(a + 4);
        W(row + ROW_AH) = W(a + 8);
        W(row + ROW_REC) = at;
        for (u32 i = 0; i < nr; i++, at += 8) {
            SW(S, at) = W(a + RCD_CANVAS_HEAD + 8 * i);
            SW(S, at + 4) = W(a + RCD_CANVAS_HEAD + 8 * i + 4);
        }
        SW(S, at) = 0xFFFFFFFFu; at += 4;
        W(row + ROW_PB) = at;
        for (u32 i = nr; i < nr + npb; i++, at += 8) {
            SW(S, at) = W(a + RCD_CANVAS_HEAD + 8 * i);
            SW(S, at + 4) = W(a + RCD_CANVAS_HEAD + 8 * i + 4);
        }
        SW(S, at) = 0xFFFFFFFFu; at += 4;
        u32 ne = gen_count(f);
        W(row + ROW_ENT0) = e0;
        W(row + ROW_NENT) = ne;
        W(row + ROW_PREV_H) = aspect == 2 ? W(a) : 0;
        W(row + ROW_BASE) = W(OGC_MAPPING + 4 * W(f + RH_PROFILE));
        W(row + ROW_LABEL) = W(f + RH_LABEL);
        W(row + ROW_LABEL + 4) = W(f + RH_LABEL + 4);
        W(row + ROW_STOCK) = W(f + RH_STOCK);
        W(row + ROW_RFLAGS) = W(f + RH_FLAGS);
        W(row + ROW_MAXRATE) = W(f + RH_MAXRATE);
        u32 bits = sec(f, SEC_BITDEPTH, &ln);
        W(row + ROW_BITMASK) = bits ? W(bits) : 0;
        u32 bf = sec(f, SEC_BINFILT, &ln);
        SW(S, S_BINFILT + 4*r) = bf ? 0x800u | W(bf+8) | (W(bf+12)<<4) |
            (W(bf+16)<<8) | ((W(bf)==3u)<<9) | ((W(bf+4)==3u)<<10) : 0;
        SW(S, S_BASEROW + 4 * r) = W(row + ROW_BASE);
        for (u32 i = 0; i < ne; i++, e0++) {
            u32 src = ga, e = base + ents + ENT_SIZE * e0, v = 0, vr = r;
            gen_entry(f, i, ga);
            while (!(W(vms + 8 * v) == r && W(vms + 8 * v + 4) == W(src + G_DONOR))) v++;
            for (u32 k = nvar; k-- > n;)            /* the row's first matching rate canvas */
                if (W(fv + 16 * k) == r && rc_match(W(fv + 16 * k + 8), ga)) vr = k;
            W(e + ENT_FIVE) = 5;
            W(e + ENT_PID) = SW(S, S_POOL + 4 * vr);
            W(e + ENT_MODE) = SW(S, S_VMID0) + v;
            W(e + ENT_ROW) = r;
            for (u32 k = 0; k < 16; k += 4) W(e + ENT_KEY + k) = W(src + k);
            W(e + ENT_W0) = W(src + G_W0);
            W(e + ENT_W1) = W(src + G_W1);
            W(e + ENT_ENGFPS) = W(src + G_ENG);
            W(e + ENT_NOMINAL) = W(src + G_NOM);
            W(e + ENT_VM) = v;
            W(e + ENT_VAR) = vr;
            W(e + ENT_VRATE) = W(src + G_VRATE);
            W(e + ENT_WFLAGS) = writer_flags(f, ga);
        }
    }
    /* each variant: its pid, its base row, its row; an entry's own list here */
    for (u32 v = 0; v < nvar; v++) {
        u32 var = base + vars + VAR_SIZE * v, src = W(fv + 16 * v + 8);
        W(var + VAR_PID) = SW(S, S_POOL + 4 * v);
        W(var + VAR_BASE) = W(fv + 16 * v + 4);
        W(var + VAR_ROW) = W(fv + 16 * v);
        if (!src) continue;
        W(var + VAR_LIST) = at;
        for (u32 k = 0; k < W(src + 12); k++, at += 8) {
            SW(S, at) = W(src + 16 + 8 * k);
            SW(S, at + 4) = W(src + 16 + 8 * k + 4);
        }
        SW(S, at) = 0xFFFFFFFFu; at += 4;
    }
    /* standby groups: the preview heights of a 3:2 row first, then the file's */
    for (u32 r = 0; r < n; r++) {
        u32 f = W(files + 4 * r), row = base + rows + ROW_SIZE * r, ng = 0, start = at;
        if (W(row + ROW_PREV_H)) {
            SW(S, at) = 6; SW(S, at + 4) = 1;
            SW(S, at + 8) = PREV_PID0; SW(S, at + 12) = PREV_PID1; SW(S, at + 16) = PREV_PID2;
            SW(S, at + 20) = PREV_PID3; SW(S, at + 24) = PREV_PID4; SW(S, at + 28) = PREV_PID5;
            SW(S, at + 32) = 0x28; SW(S, at + 36) = W(row + ROW_PREV_H);
            at += 40; ng++;
        }
        u32 a = sec(f, SEC_STANDBY, &ln);
        if (a) {
            for (u32 k = 4; k < ln; k += 4, at += 4) SW(S, at) = W(a + k);
            ng += W(a);
        }
        W(row + ROW_SBY) = ng ? start : 0;
        W(row + ROW_NSBY) = ng;
    }
    u32 o = at, vms_off;
    for (u32 v = 0; v < nvm; v++) {
        u32 r = W(vms + 8 * v), d = W(vms + 8 * v + 4), f = W(files + 4 * r);
        u32 a = sec(f, SEC_VMODES, &ln), start = o, cnt = 0;
        for (u32 i = 0; a && i < W(a); i++) {
            u32 src = a + 4 + RCD_OVR_BYTES * i;
            if (W(src) != d) continue;
            SW(S, o) = W(src + 4); SW(S, o + 4) = W(src + 8); SW(S, o + 8) = W(src + 12);
            o += OVR_BYTES; cnt++;
        }
        W(fo + FO_VMS + 8 * OGC_MAX_VMS + 8 * v) = cnt ? start : 0;
        W(fo + FO_VMS + 8 * OGC_MAX_VMS + 8 * v + 4) = cnt;
    }
    vms_off = (o + 63u) & ~63u;
    for (u32 v = 0; v < nvm; v++) {
        u32 vm = base + vms_off + OGC_VM_SIZE * v, r = W(vms + 8 * v);
        W(vm + VM_ID) = SW(S, S_VMID0) + v;
        W(vm + VM_DONOR) = W(vms + 8 * v + 4);
        W(vm + VM_CLAMP) = W(W(files + 4 * r) + RH_FLAGS) & 1u;
        W(vm + VM_OVR) = W(fo + FO_VMS + 8 * OGC_MAX_VMS + 8 * v);
        W(vm + VM_NOVR) = W(fo + FO_VMS + 8 * OGC_MAX_VMS + 8 * v + 4);
        SW(S, S_VMDONOR + 4 * v) = W(vms + 8 * v + 4);
    }
    SW(S, S_NROWS) = n;
    SW(S, S_ROWS) = rows;
    SW(S, S_NENT) = nent;
    SW(S, S_ENTS) = ents;
    SW(S, S_NVAR) = nvar;
    SW(S, S_VARS) = vars;
    SW(S, S_NVM) = nvm;
    SW(S, S_VMS) = vms_off;
    SW(S, S_S_END) = vms_off + OGC_VM_SIZE * nvm;
    return n;
}

/* The whole §14.3 pass: list, read, check, choose, fill.  Writes nothing
 * outside this block.  Returns the rows filled. */
static u32 load_rcd(u8 *S, const char *path, u32 row_cap)
{
    u32 fo = SW(S, S_FOBJ), seen, nn = list_rcd(S, path, &seen), n = 0;
    u32 names = fo + FO_NAMES, sizes = fo + FO_SIZES, files = fo + FO_FILES;
    SW(S, S_RCD_FOUND) = seen;
    for (u32 i = 0; i < nn; i++) {
        u32 reason = 0;
        u32 f = read_rcd(S, names + NAME_BYTES * i, W(sizes + 4 * i), &reason);
        if (f && !(reason = rcd_check(S, f, W(sizes + 4 * i)))) {
            for (u32 j = 0; j < SW(S, S_NAVAIL); j++)
                if (same_label(f + RH_LABEL, (u32)(uintptr_t)S + S_AVAIL + 8 * j)) reason = WHY_DUPLICATE;
        }
        if (reason) { why(S, i, reason, 1); continue; }
        SW(S, S_RCD_OK)++;
        if (SW(S, S_NAVAIL) < OGC_MAX_AVAIL) {
            u32 at = (u32)(uintptr_t)S + S_AVAIL + 8 * SW(S, S_NAVAIL);
            W(at) = W(f + RH_LABEL); W(at + 4) = W(f + RH_LABEL + 4);
            SW(S, S_NAVAIL)++;
        }
        if (!enabled(S, f + RH_LABEL)) { why(S, i, WHY_DISABLED, 0); continue; }
        if (n == row_cap) { why(S, i, WHY_EXCESS, 0); continue; }
        W(files + 4 * n++) = f;
        SW(S, S_DATA_USED) = f + W(sizes + 4 * i) - SW(S, S_DATA);
    }
    /* the virtual modes and S's room: drop formats from the end until they fit */
    while (n && !fill_s(S, n)) { why(S, 0xFF, WHY_S_FULL, 0); n--; }
    return n;
}

/* ---- the future sixth page (§14, defined, not wired): the enable list ---------- *
 * labels: n 8-byte labels (n <= MAX_ROWS; 0 = the default, the first six).  Goes
 * into the BIN record at the next save; takes effect at the next boot. */
static u32 ogc_enable_set(u8 *S, u32 n, u32 labels)
{
    u32 cfg = SW(S, S_CFG);
    if (n > OGC_MAX_ROWS) return 0;
    for (u32 i = 0; i < OGC_MAX_ROWS; i++) {
        W(cfg + CFG_EN + 8 * i) = i < n ? W(labels + 8 * i) : 0;
        W(cfg + CFG_EN + 8 * i + 4) = i < n ? W(labels + 8 * i + 4) : 0;
    }
    W(cfg + CFG_NEN) = n;
    SW(S, S_DIRTY) = 1;
    return 1;
}

/* ==== §13: the menu (uishare's applier, the core's template) ======================== */
/* One row's FPUI block from the template: @R/@S/@L replaced from the data file,
 * the STRBASE targets moved onto the row, the hash made again.  Length or 0. */
static u32 ui_make(u32 tpl, u32 dst, u32 cap, u32 f, u32 row)
{
    u32 ln, ui = sec(f, SEC_UI, &ln), ns = W(tpl + 16), nw = W(tpl + 20), total = W(tpl + 8);
    u32 cur = 0x20, o = 0x20;
    for (u32 i = 0; i < ns; i++) {
        u32 hint = W(tpl + cur), n = W(tpl + cur + 4), src = tpl + cur + 8, len = 0;
        if (o + 8 + 64 + 4 > cap) return 0;
        W(dst + o) = hint;
        u32 t = dst + o + 8;
        for (u32 k = 0; k < n; k++) {
            u32 c = u8at(src + k), with = 0;
            if (c == '@' && k + 1 < n) {
                u32 m = u8at(src + k + 1);
                with = m == 'R' ? ui : m == 'S' ? ui + RCD_UI_ROW : m == 'L' ? f + RH_LABEL : 0;
            }
            if (with) {
                for (u32 j = 0; u8at(with + j); j++) { if (len == 63) return 0; B8(t + len++) = B8(with + j); }
                k++;
            } else {
                if (len == 63) return 0;
                B8(t + len++) = (u8)c;
            }
        }
        if (!len) return 0;
        W(dst + o + 4) = len;
        B8(t + len) = 0;
        o += 8 + len + 1;
        while (o & 3) B8(dst + o++) = 0;
        cur += (8 + n + 1 + 3) & ~3u;
    }
    u32 rest = total - cur;
    if (o + rest > cap) return 0;
    copy(dst + o, tpl + cur, rest);
    for (u32 i = 0; i < nw;) {                            /* STRBASE (16): the row's word */
        u32 h = W(dst + o + 4 * i), code = h >> 24, k = h & 0xFFFFFFu;
        if (code == 16u && k == 2) W(dst + o + 4 * i + 8) += row;
        i += 1 + k;
    }
    o += rest;
    W(dst) = W(tpl); W(dst + 4) = W(tpl + 4); W(dst + 8) = o;
    W(dst + 12) = fnv(dst + 0x20, o - 0x20);
    W(dst + 16) = ns; W(dst + 20) = nw; W(dst + 24) = W(tpl + 24); W(dst + 28) = 0;
    return o;
}

typedef u32 (*uia_fn)(uintptr_t, u32, struct uia_outcome *);

/* Each enabled row's menu: its block, then uia_apply.  A row is on when its
 * block went in; it holds the CSV row (slot) uia_apply handed it.  Returns the rows on. */
static u32 ui_rows(u8 *S, u32 tpl)
{
    u32 on = 0, fo = SW(S, S_FOBJ), files = fo + FO_FILES;
    for (u32 r = 0; r < SW(S, S_NROWS); r++) {
        u32 row = rowp(S, r), f = W(files + 4 * r), ln;
        u32 dst = (SW(S, S_DATA) + SW(S, S_DATA_USED) + 63u) & ~63u;
        u32 cap = SW(S, S_DATA) + SW(S, S_DATA_CAP) - dst;
        u32 n = cap > 0x40 ? ui_make(tpl, dst, cap, f, row) : 0;
        u32 pk = sec(f, SEC_PACK, &ln);
        W(row + ROW_PACK) = pk;
        W(row + ROW_PACKLEN) = ln;
        if (!n) { W(row + ROW_UIRES) = 0x100u; continue; }
        SW(S, S_DATA_USED) = dst + n - SW(S, S_DATA);
        struct uia_outcome out;
        out.n_slots = 0;
        u32 res = ((uia_fn)SW(S, S_UIA_FN))(dst, n, &out);
        W(row + ROW_UIRES) = res + 1u;
        if (res != UIA_OK || !out.n_slots || out.slots[0] < 2) continue;
        W(row + ROW_MROW) = out.slots[0];
        W(row + ROW_ON) = 1;
        on |= 1u << r;
    }
    SW(S, S_UI_OK) = on;
    return on;
}

/* ==== §13: the Quick Set, scheme B ================================================== */
#define NBU_BASE 0xC18C0460u
#define QS_STOCK_NBR 0xC0D22400u
#define R_POS 4u
#define R_CTX 8u
#define R_BASE 36u
#define RCACHE 0xC37B7254u
#define RCACHE_V2 0xC05663E8u
#define RCACHE_V3 0xC0566498u
#define FV_SITE 0xC05E5BECu
#define FV_STOCK 0x60681840u
#define FV_MAGIC 0x4B485346u
#define FV_ENTRY_OFF 16u
#define RES_CSV 0xC0F8E7ECu
#define THUMB_VENEER 0xF000F8DFu
enum { QS_CLONE = 0, QS_END = 1, QS_MAXR = 2, QS_CURSOR = 3, QS_FOOTER_N8 = 4, QS_FOOTER_LABEL = 5 };

static u32 le16(u32 a) { return u8at(a) | u8at(a + 1) << 8; }
static u32 le32(u32 a) { return le16(a) | le16(a + 2) << 16; }
static u32 be32(u32 a) { return u8at(a) << 24 | u8at(a + 1) << 16 | u8at(a + 2) << 8 | u8at(a + 3); }
static void put_be32(u32 a, u32 v) { B8(a) = (u8)(v >> 24); B8(a + 1) = (u8)(v >> 16); B8(a + 2) = (u8)(v >> 8); B8(a + 3) = (u8)v; }
static void copy8(u32 to, u32 from, u32 n) { for (u32 i = 0; i < n; i++) B8(to + i) = B8(from + i); }

static u32 qs_find(u32 tab, u32 src)
{
    u32 rows = tab + le32(tab + 8), lo = 0, hi = le32(tab + 4);
    while (lo < hi) {
        u32 mid = (lo + hi) >> 1, a = le32(rows + 16 * mid);
        if (a == src) return mid + 1u;
        if (src > a) lo = mid + 1u; else hi = mid;
    }
    return 0;
}

static u32 fn_row(u32 tab, u32 n)
{
    if (n > le32(tab + 20)) return 0;
    u32 f = tab + le32(tab + 16) + 12 * n;
    return le32(f) ? f : 0;
}

static u32 bw_target(u32 site, u32 w)
{
    u32 hw1 = w & 0xFFFFu, hw2 = w >> 16, s, j1, j2, i1, i2, off;
    if ((hw1 & 0xF800u) != 0xF000u || (hw2 & 0xD000u) != 0x9000u) return 0;
    s = (hw1 >> 10) & 1u; j1 = (hw2 >> 13) & 1u; j2 = (hw2 >> 11) & 1u;
    i1 = 1u ^ (j1 ^ s); i2 = 1u ^ (j2 ^ s);
    off = s << 24 | i1 << 23 | i2 << 22 | (hw1 & 0x3FFu) << 12 | (hw2 & 0x7FFu) << 1;
    if (s) off |= 0xFE000000u;
    return site + 4u + off;
}

static u32 thumb_bw(u32 site, u32 to)
{
    u32 off = to - (site + 4u), s = off >> 31, i1 = (off >> 23) & 1u, i2 = (off >> 22) & 1u;
    u32 j1 = (1u ^ i1) ^ s, j2 = (1u ^ i2) ^ s;
    u32 hw1 = 0xF000u | s << 10 | ((off >> 12) & 0x3FFu);
    u32 hw2 = 0x9000u | j1 << 13 | j2 << 11 | ((off >> 1) & 0x7FFu);
    return hw1 | hw2 << 16;
}

/* The resolution list's rows (uishare qs_layer.c qs_rows_now): the FV table's copy. */
static u32 rows_now(void)
{
    u32 w = W(FV_SITE), rows = 0, start = 1, copy_at = 0, size = 0;
    if (w == FV_STOCK) return 2;
    u32 ven = bw_target(FV_SITE, w);
    if (!ven || (ven & 3u) || W(ven) != THUMB_VENEER) return 0;
    u32 head = W(ven + 4) - FV_ENTRY_OFF;
    if (W(head) != FV_MAGIC) return 0;
    u32 table = W(head + 8), n = W(table + 8);
    for (u32 i = 0; i < n; i++)
        if (W(table + 16 + 12 * i) == RES_CSV) { copy_at = W(table + 20 + 12 * i); size = W(table + 24 + 12 * i); }
    if (!copy_at) return 2;
    for (u32 i = 0; i < size; i++) {
        u32 c = u8at(copy_at + i);
        if (c == '\n') { start = 1; continue; }
        if (c == '\r') continue;
        if (start) { rows++; start = 0; }
    }
    return rows ? rows - 1u : 0;
}

/* row r takes part in the Quick Set: on, its images named, its pack not failed */
static int qs_row(u8 *S, u32 r)
{
    u32 row = rowp(S, r);
    return W(row + ROW_ON) && W(row + ROW_QSID) && W(row + ROW_PACKST) != 3 && W(row + ROW_MROW) <= 7;
}

static u32 qs_row_of_k(u8 *S, u32 k)
{
    for (u32 r = 0; r < SW(S, S_NROWS); r++)
        if (qs_row(S, r) && W(rowp(S, r) + ROW_MROW) == k) return rowp(S, r);
    return 0;
}

static u32 qs_id(u32 row, u32 marker) { return W(row + ROW_QSID + 4 * (marker == 3 ? 1u : marker)); }

/* Append every format's state in one pass. The former per-format clone loop
 * copied the entire growing record again for every row (up to six times).
 * Each added key still copies the original property's first key, in row order. */
static u32 qs_clone(u8 *S, u32 old, u32 len, u32 out, u32 cap, u32 n, u32 prop, u32 has, u32 marker)
{
    u32 rows[6], times[6], nr = 0, count, src = 28, o = 28;
    if (len < 28 || cap < 28) return 0;
    for (u32 k = 2; k < n && k <= 7; k++) {
        u32 row = qs_row_of_k(S, k);
        if (!row) continue;
        rows[nr] = row; times[nr++] = 100u * k / 3u;
    }
    if (!nr) return 0;
    copy8(out, old, 28);
    count = be32(old + 12);
    for (u32 p = 0; p < count; ++p) {
        if (src + 20 > len) return 0;
        u32 keys = be32(old + src);
        if (keys == 0 || keys > 255u - nr || src + 20 + 10 * keys > len ||
            o + 20 + 10 * (keys + nr) > cap) return 0;
        copy8(out + o, old + src, 20 + 10 * keys);
        put_be32(out + o, keys + nr);
        o += 20 + 10 * keys;
        for (u32 k = 0; k < nr; k++) {
            copy8(out + o, old + src + 20, 10);
            put_be32(out + o + 2, times[k]);
            if (has && p == prop) put_be32(out + o + 6, qs_id(rows[k], marker));
            o += 10;
        }
        src += 20 + 10 * keys;
    }
    if (src != len) return 0;
    put_be32(out + 4, o);
    return o;
}

static u32 qs_edit(u32 edits, u32 old, u32 len, u32 out, u32 cap, u32 row)
{
    u32 cur = 0, o = 0;
    for (;;) {
        u32 at = le16(edits), del = le16(edits + 2), n = le16(edits + 4);
        if (at == 0xFFFFu) break;
        if (at < cur || at > len || o + (at - cur) > cap) return 0;
        copy8(out + o, old + cur, at - cur);
        o += at - cur;
        edits += 6;
        if (n & 0x8000u) {
            if (o + 4u > cap) return 0;
            put_be32(out + o, qs_id(row, n & 3u));
            o += 4;
        } else {
            if (o + n > cap) return 0;
            copy8(out + o, edits, n);
            o += n;
            edits += (n + 1u) & ~1u;
        }
        cur = at + del;
    }
    if (cur > len || o + (len - cur) > cap) return 0;
    copy8(out + o, old + cur, len - cur);
    return o + (len - cur);
}

/* Scheme B on one record (rcd.qs_target): the new bytes in a, *len; 0 = leave it. */
static u32 qs_b(u8 *S, u32 tab, u32 r, u32 old, u32 *len, u32 a, u32 cap, u32 n)
{
    u32 rule = u8at(r + 10), pa = u8at(r + 11), pb = le16(r + 12);
    u32 edits = tab + le32(tab + 12) + le16(r + 14), f = fn_row(tab, n), any = 0;
    for (u32 k = 2; k < n && k <= 7; k++) if (qs_row_of_k(S, k)) any = 1;
    if (!f || !any) return 0;
    u32 l = *len, got;
    switch (rule) {
    case QS_CLONE: {
        u32 mk = pb & 0xFFu;
        l = qs_clone(S, old, l, a, cap, n, pa ? pa - 1u : 0u, pa && mk != 0xFFu, mk & 3u);
        if (!l) return 0;
        *len = l;
        return a;
    }
    case QS_END: {
        if (l < 40 || l > cap) return 0;
        u32 end = be32(old + 36), t = 100u * (n - 1u) / 3u;
        copy8(a, old, l);
        put_be32(a + 36, end > t ? end : t);
        return a;
    }
    case QS_MAXR:
        if (l < 32 || l + 4 > cap || (u8at(old + 31) & 2u)) return 0;
        copy8(a, old, 32);
        put_be32(a + 32, le32(f));
        copy8(a + 36, old + 32, l - 32);
        put_be32(a + 4, l + 4);
        B8(a + 31) = (u8)(u8at(old + 31) | 2u);
        *len = l + 4;
        return a;
    case QS_CURSOR:
        if (pa + 4 > l || pb + 4 > l || l > cap) return 0;
        copy8(a, old, l);
        put_be32(a + pa, le32(f + 4));
        put_be32(a + pb, le32(f + 4));
        return a;
    case QS_FOOTER_N8:
        if (!u8at(f + 8)) return 0;
        got = qs_edit(edits, old, l, a, cap, 0);
        if (!got) return 0;
        *len = got;
        return a;
    case QS_FOOTER_LABEL: {
        u32 row = qs_row_of_k(S, pa);
        if (!row) return 0;
        got = qs_edit(edits, old, l, a, cap, row);
        if (!got) return 0;
        *len = got;
        return a;
    }
    }
    return 0;
}

/* Register each row's pack in resource context `ctx` once (og3k_ui.S ensure_ui_pack). */
static void qs_packs(u8 *S, u32 ctx)
{
    for (u32 r = 0; r < SW(S, S_NROWS); r++) {
        u32 row = rowp(S, r);
        if (!W(row + ROW_ON) || !W(row + ROW_PACK)) continue;
        if (W(row + ROW_PACKCTX) == ctx && W(row + ROW_PACKST)) continue;
        W(row + ROW_PACKCTX) = ctx;
        W(row + ROW_PACKST) = 2;
        u32 st = ((u32 (*)(u32, u32, u32, u32))SW(S, NX_QSLOAD))(ctx, W(row + ROW_PACK),
                                                                 W(row + ROW_PACKLEN), 0);
        W(row + ROW_PACKST) = st == 0 ? 1u : 3u;
        if (st) SW(S, S_QS_PACKFAIL)++;
    }
}

/* Three literal texts in place of the FPS image. The existing record hook parses
 * resident copies; the original resource stream and its next record never move.
 * table = {count, bytes, {site, stock_len, stock_hash, new_len, nrec, nmark,
 *                       records[new_len], aligned, {offset, label_index}...}...}. */
static u32 lv_text_record(u8 *S, u32 reader, fw1 next, u32 *handled)
{
    u32 tab = SW(S, S_LV_RECORDS), base = W(reader + R_BASE), pos = W(reader + R_POS);
    *handled = 0;
    if (!tab || base != NBU_BASE) return 0;
    u32 src = base + pos;
    if (src < SW(S, S_LV_MIN) || src > SW(S, S_LV_MAX)) return 0;
    if (W(tab) != 16u || W(tab + 4) > 0x20000u) return 0;
    u32 at = tab + 8, end = tab + W(tab + 4);
    for (u32 i = 0; i < 16u; i++) {
        if (at + 24 > end) return 0;
        u32 n = W(at + 12), nr = W(at + 16), nm = W(at + 20), out = at + 24;
        if (!n || n > 0x4000u || !nr || nr > 51u || nm > 512u ||
            out + ((n + 3u) & ~3u) + 8u * nm > end) return 0;
        if (W(at) == src) {
            u32 old = W(at + 4), cur = 0, res = 0;
            if (be32(src + 4) != old || fnv(src, old) != W(at + 8)) return 0;
            for (u32 k = 0; k < nr; k++) {
                if (cur + 8 > n) return 0;
                u32 size = be32(out + cur + 4);
                if (size < 8 || cur + size > n) return 0;
                cur += size;
            }
            if (cur != n) return 0;
            *handled = 1;
            cur = 0;
            W(reader + R_BASE) = out - pos;
            for (u32 k = 0; k < nr; k++) {
                W(reader + R_POS) = pos + cur;
                res = next(reader);
                cur += be32(out + cur + 4);
                /* +1c is set by successful native resource registration
                 * (C05E69AE..C05E69B4); it is not a fatal parse status. */
            }
            W(reader + R_BASE) = base;
            W(reader + R_POS) = pos + old;
            return res;
        }
        at = out + ((n + 3u) & ~3u) + 8u * nm;
    }
    return 0;
}

/* ---- C05E6400: parse one NBU record (reader: +4 position, +8 context, +36 base) ---- */
u32 ogc_qsrec(u8 *S, u32 reader)
{
    fw1 next = (fw1)SW(S, NX_QSREC);
    u32 handled, lv_result = lv_text_record(S, reader, next, &handled);
    if (handled) return lv_result;
    if (SW(S, S_QS_READY) != 1) return next(reader);
    u32 base = W(reader + R_BASE), pos = W(reader + R_POS), tab = SW(S, S_QS_TAB);
    if (base != NBU_BASE) return next(reader);
    u32 src = NBU_BASE + pos, i = qs_find(tab, src);
    if (!i) return next(reader);
    u32 r = tab + le32(tab + 8) + 16 * (i - 1u), len = le16(r + 8);
    if (be32(src + 4) != len || fnv(src, len) != le32(r + 4)) { SW(S, S_QS_ERR)++; return next(reader); }
    qs_packs(S, W(reader + R_CTX));
    if (!SW(S, S_QS_N)) {
        u32 n = rows_now();
        SW(S, S_QS_N) = n;
        if (!fn_row(tab, n)) { SW(S, S_QS_READY) = 2; return next(reader); }
    }
    u32 d = SW(S, S_QS_DEPTH);
    if (d >= OGC_QS_SLOTS) { SW(S, S_QS_FULL)++; return next(reader); }
    u32 a = SW(S, S_QS_BUF) + d * 2u * OGC_QS_CAP, l = len;
    u32 out = qs_b(S, tab, r, src, &l, a, OGC_QS_CAP, SW(S, S_QS_N));
    if (!out) { SW(S, S_QS_PASS)++; return next(reader); }
    SW(S, S_QS_DEPTH) = d + 1;
    W(reader + R_BASE) = out - pos;
    u32 res = next(reader);
    W(reader + R_BASE) = base;
    W(reader + R_POS) = pos + len;                       /* past the stock record */
    SW(S, S_QS_DEPTH) = d;
    SW(S, S_QS_HITS)++;
    return res;
}

/* ---- C05D90F0: load one layout.  Once per boot: the Quick Set layout the
 * resource cache parsed before our hooks went up is let go and loaded again
 * (v3 then v2, QS_SHARE §13.1/§13.4) -- after this load, never inside it,
 * never the one being loaded, only when the cache can let it go. */
static int releasable(u32 l)
{
    u32 tree = W(l + 0xC), ctx = W(l + 4);
    return tree && B8(RCACHE + 0x28) == 0 && W(tree + 0xC) == 1 && W(ctx + 0x84C) != l
           && W(ctx + 0x848) != l;
}

u32 ogc_qslay(u8 *S, u32 layout)
{
    u32 res = ((fw1)SW(S, NX_QSLAY))(layout);
    if (SW(S, S_QS_READY) != 1 || SW(S, S_QS_BOOT) || SW(S, S_QS_INRELOAD)) return res;
    u32 held = W(RCACHE + 4);
    if (!held || held != SW(S, S_QS_PRE)) { SW(S, S_QS_BOOT) = 1; return res; }  /* parsed through us */
    if (held == layout || !releasable(held)) return res;                         /* later */
    SW(S, S_QS_BOOT) = 1;
    SW(S, S_QS_INRELOAD) = 1;
    ((fw1)RCACHE_V3)(RCACHE);
    ((fw1)RCACHE_V2)(RCACHE);
    SW(S, S_QS_INRELOAD) = 0;
    SW(S, S_QS_RELOADS)++;
    return res;
}

/* ---- C05E84D8: load an NBR pack (ctx, pack, bytes, 0): after the stock one, ours */
u32 ogc_qsload(u8 *S, u32 *args)
{
    u32 r = ((u32 (*)(u32, u32, u32, u32))SW(S, NX_QSLOAD))(args[0], args[1], args[2], args[3]);
    if (r == 0 && args[1] == QS_STOCK_NBR && SW(S, S_QS_READY) == 1) qs_packs(S, args[0]);
    return r;
}

/* ==== the virtual frame rates' menu (rows 9..12) ====================================== *
 * Always (the four rows exist whenever res-custom is in; a format without entries for
 * one sees it greyed).  From the build (vr_ui.py, rcd.vr_template):
 *  1. B2_5 (the movie settings page) as uishare's page copy (FSPG): the summary's K new
 *     labels, K cursor pairs, ListItem instances and the maxima -- built here, the
 *     runtime entry switched to it BEFORE the rows' own menu blocks copy the page;
 *  2. rows 9..12 in the six frame-rate CSVs and the K label strings (uia_apply);
 *  3. the LV standby texts, in place (claimed EXCL at the entry, put back at power-off);
 *  the label string ids go into the page copy and the LV keys (vrpg/vrlv marks). */
#define B25_START 0xC1A5C590u
#define B25_LEN 0x1CD6Bu
#define B25_ENTRY 0x19C130u
#define READER_ENTRIES 0xA8u
#define READER_TABLE 0xACu

static int vr_claims(const struct sl_svc *svc, u32 lv)
{
    u32 at = lv + 4;
    for (u32 i = 0; i < W(lv); i++) {
        u32 a = W(at), n = W(at + 4);
        if (svc->claim(svc, a, n, (const void *)(uintptr_t)(at + 8), SL_EXCL) != SL_OK) return 0;
        at += 8 + 2 * n;
    }
    return 1;
}

/* the runtime page entry named "B2_5" */
static u32 b25_entry(void)
{
    u32 reader = uis_reader();
    if (!reader) return 0;
    for (u32 i = 0; i < W(reader + READER_ENTRIES) && i < 512; i++) {
        u32 e = W(reader + READER_TABLE) + 44 * i, nm = W(e + 4);
        if (nm && B8(nm) == 'B' && B8(nm + 1) == '2' && B8(nm + 2) == '_' && B8(nm + 3) == '5'
            && B8(nm + 4) == 0)
            return e;
    }
    return 0;
}

/* the FV table's copy of a stock file: its address, *size; 0 = none */
static u32 fv_copy(u32 stock, u32 *size)
{
    u32 w = W(FV_SITE);
    if (w == FV_STOCK) return 0;
    u32 ven = bw_target(FV_SITE, w);
    if (!ven || (ven & 3u) || W(ven) != THUMB_VENEER) return 0;
    u32 head = W(ven + 4) - FV_ENTRY_OFF;
    if (W(head) != FV_MAGIC) return 0;
    u32 table = W(head + 8);
    for (u32 i = 0; i < W(table + 8); i++)
        if (W(table + 16 + 12 * i) == stock) { *size = W(table + 24 + 12 * i); return W(table + 20 + 12 * i); }
    return 0;
}

static void put_be(u32 a, u32 v) { put_be32(a, v); }

static u32 bit_install(u8 *S, u32 block, const struct ogc_tab *t)
{
    struct uia_outcome out;
    out.n_slots = 0;
    if (((uia_fn)SW(S, S_UIA_FN))(block + t->bit_off, t->bit_len, &out) != UIA_OK) return 0;
    for (u32 v = 0; v < 2; v++) {
        u32 size = 0, csv = fv_copy(v ? 0xC0F8E71Cu : 0xC0F8E6A8u, &size);
        if (!csv || size != 113u) return 0;
        u32 end = csv + size;
        for (u32 k = 3; k-- > 0;) {
            while (end > csv && (B8(end - 1) == '\n' || B8(end - 1) == '\r')) end--;
            if (end - csv < 3 || B8(end - 2) != ',') return 0;
            SW(S, S_BIT_EN_AT + 4*(3*v + k)) = end - 3;
            SW(S, S_BIT_EN_ON + 4*(3*v + k)) = B8(end - 3) | B8(end - 1) << 16;
            while (end > csv && B8(end - 1) != '\n') end--;
        }
    }
    SW(S, S_BIT_UI) = 1;
    bit_follow(S);
    return 1;
}

static u32 vr_install(u8 *S, u32 block, const struct ogc_tab *t)
{
    u32 e = b25_entry();
    if (!e || W(e + 8) != B25_ENTRY) return 2;                  /* someone else's B2_5 */
    /* 1. the page copy: 128-byte FSPG header, then the page, rebuilt from the stock set
     *    by vrpg = {len, nseg, marks[K], {stock offset, len} | {-1, len, bytes}...} */
    u32 pg = block + t->vrpg_off, len = W(pg);
    u32 dst = (SW(S, S_DATA) + SW(S, S_DATA_USED) + 63u) & ~63u;
    if (dst + 128 + len + 4 > SW(S, S_DATA) + SW(S, S_DATA_CAP)) return 3;
    u32 page = dst + 128, o = 0, sg = pg + 8 + 4 * VR_K;
    for (u32 i = 0; i < W(pg + 4); i++) {
        u32 so = W(sg), n = W(sg + 4);
        if (o + n > len) return 4;
        if (so == 0xFFFFFFFFu) { copy8(page + o, sg + 8, n); sg += 8 + ((n + 3u) & ~3u); }
        else { if (so + n > B25_LEN) return 4; copy8(page + o, B25_START + so, n); sg += 8; }
        o += n;
    }
    if (o != len) return 4;
    W(dst + 0) = UIA_MAGIC; W(dst + 4) = UIA_VERSION; W(dst + 8) = len;
    W(dst + 12) = len; W(dst + 16) = B25_LEN; W(dst + 20) = 1;
    for (u32 o = 24; o < 128; o += 4) W(dst + o) = 0;
    SW(S, S_DATA_USED) = page + len - SW(S, S_DATA);
    /* 2. rows 9..12 in the six CSVs + the K label strings: the template's STRBASE
     *    targets are S offsets -- moved onto S, the hash made again */
    u32 tpl = block + t->vrtpl_off, ns = W(tpl + 16), nw = W(tpl + 20), cur = 0x20;
    for (u32 i = 0; i < ns; i++) cur += (8 + W(tpl + cur + 4) + 1 + 3) & ~3u;
    for (u32 i = 0; i < nw;) {
        u32 h = W(tpl + cur + 4 * i), code = h >> 24, k = h & 0xFFFFFFu;
        if (code == 16u && k == 2 && W(tpl + cur + 4 * i + 8) < 0x10000u)
            W(tpl + cur + 4 * i + 8) += (u32)(uintptr_t)S;
        i += 1 + k;
    }
    W(tpl + 12) = fnv(tpl + 0x20, W(tpl + 8) - 0x20);
    struct uia_outcome out;
    out.n_slots = 0;
    u32 res = ((uia_fn)SW(S, S_UIA_FN))(tpl, t->vrtpl_len, &out);
    if (res != UIA_OK) return 0x10 + res;
    /* each copy's last 9 + K rows: where its "a,b" is, and the stock value */
    for (u32 v = 0; v < VR_CSVS; v++) {
        u32 size = 0, csv = fv_copy(W(block + t->vrcsv_off + 4 * v), &size);
        if (!csv || size < 8) return 5;
        u32 end = csv + size;
        for (u32 k = VR_ROWS; k-- > 0;) {
            while (end > csv && (B8(end - 1) == '\n' || B8(end - 1) == '\r' || B8(end - 1) == 0)) end--;
            if (end - csv < 3 || B8(end - 2) != ',') return 6;
            SW(S, S_VR_EN_AT + 4 * (v * VR_ROWS + k)) = end - 3;
            SW(S, S_VR_EN_ON + 4 * (v * VR_ROWS + k)) = B8(end - 3) | B8(end - 1) << 16;
            while (end > csv && B8(end - 1) != '\n') end--;       /* the line before */
        }
    }
    /* the label ids into the page copy and (below) the LV keys */
    for (u32 k = 0; k < VR_K; k++) put_be(page + W(pg + 8 + 4 * k), SW(S, S_VR_LABEL + 4 * k));
    /* 3. Validate all resident substitutions together before changing any LV
     * object count. A changed header cannot fund our extra text components. */
    u32 lv = block + t->vrlv_off, at = lv + 4;
    for (u32 i = 0; i < W(lv); i++) {
        u32 n = W(at + 4);
        at += 8 + 2 * n;
    }
    /* Resident LV records: fill literal string keys before the hook sees them.
     * Each record blob belongs to this core's block, never loader staging. */
    {
    u32 rec = at, cur = rec + 8, end = rec + W(rec + 4);
    u32 lo = 0xFFFFFFFFu, hi = 0;
    if (W(rec) != 16u || W(rec + 4) > 0x20000u) return 7;
    for (u32 i = 0; i < 16u; i++) {
        if (cur + 24 > end) return 7;
        u32 n = W(cur + 12), nm = W(cur + 20), data = cur + 24;
        u32 mk = data + ((n + 3u) & ~3u);
        if (!n || n > 0x4000u || nm > 512u || mk + 8u * nm > end) return 7;
        u32 src = W(cur), old = W(cur + 4);
        if (src < lo) lo = src;
        if (src > hi) hi = src;
        if (!old || old > 0x2800u || be32(src + 4) != old || fnv(src, old) != W(cur + 8)) return 7;
        for (u32 k = 0; k < nm; k++) {
            u32 off = W(mk + 8u * k), label = W(mk + 8u * k + 4);
            if (off + 4 > n || label >= 29u) return 7;
            put_be(data + off, SW(S, S_LV_LABEL + 4u * label));
        }
        cur = mk + 8u * nm;
    }
    if (cur != end) return 7;
    SW(S, S_LV_MIN) = lo; SW(S, S_LV_MAX) = hi;
    at = lv + 4;
    for (u32 i = 0; i < W(lv); i++) {
        u32 a = W(at), n = W(at + 4);
        copy(a, at + 8 + n, n);
        at += 8 + 2 * n;
    }
    SW(S, S_LV_RECORDS) = rec;
    }
    u32 lm = block + t->vrlm_off;
    for (u32 i = 0; i < W(lm); i++) put_be(W(lm + 4 + 4 * i), SW(S, S_VR_LABEL + 4 * (i % VR_K)));
    /* the switch, last: the next time Settings opens it reads our page */
    dmb();
    W(e + 8) = page - NBU_BASE;
    SW(S, S_VR_UI) = 1;
    vrate_follow(S);
    return 1;
}

#include "ogc_virtual.c"
#include "ogc_files.c"
#include "ogc_binfilt.c"

/* ==== the entry ======================================================================== */
static void ogc_log(const struct sl_svc *svc, char tag, u32 v)
{
    volatile char b[12];
    b[0] = 'O'; b[1] = 'C'; b[2] = tag;
    for (u32 i = 0; i < 8; i++) {
        u32 d = (v >> (28 - 4 * i)) & 15u;
        b[3 + i] = (char)(d < 10 ? '0' + d : 'A' + d - 10);
    }
    b[11] = 0;
    svc->log(svc, (const char *)b);
}

static u32 mov_imm(u32 word, u32 imm)
{
    return (word & 0xFFF0F000u) | ((imm >> 12) & 0xFu) << 16 | (imm & 0xFFFu);
}

/* A standalone consumer with all valid files disabled must still offer its
 * settings. Keep only the page-name routing hook; stock recording and
 * resolution tables remain untouched until an enabled file is loaded. */
static int ogc_files_only(u8 *block,u8 *S,const struct ogc_tab *t,
                          const struct sl_svc *svc,const char *path,u32 delta)
{
    if(svc->version<4 || !svc->button)return SL_RELEASE;
    const u32 *h=(const u32 *)(block+t->hook_off),*r=0;
    for(u32 i=0;i<t->n_hook;i++)if(h[5u*i]==0xC056461Cu)r=h+5u*i;
    if(!r)return SL_RELEASE;
    const u32 *c=(const u32 *)(block+t->claim_off);u32 found=0;
    for(u32 i=0;i<t->n_claim;i++,c+=5u)if(c[0]==r[0]) {
        if(svc->claim(svc,c[0],c[1],block+c[3],c[2])!=SL_OK)return SL_RELEASE;
        found=1;break;
    }
    u32 ven=found?svc->cave_alloc(svc,8u):0;
    if(!ven)return SL_RELEASE;
    SW(S,FN_VGUI)=(u32)(uintptr_t)&ogc_virtual_gui;
    u32 below=svc->chain_next(svc,r[0],0);
    W(r[3]+delta)=below?below:r[4]+delta;
    W(ven)=0xE51FF004u;W(ven+4u)=r[1]+delta;
    svc->publish(svc);
    W(r[0])=0xEB000000u|(((ven-r[0]-8u)>>2)&0x00FFFFFFu);
    svc->publish(svc);
    if(ogc_files_init(S,(u32)(uintptr_t)block+t->files_off,(u32)(uintptr_t)block+t->files_state))
        svc->button(svc,ogc_files_button,S,path);
    return SL_KEEP;
}

int ogc_v3_entry(u8 *block, const struct sl_svc *svc, const char *path)
{
    const struct ogc_tab *t = (const struct ogc_tab *)(block + OGC_TAB_OFF);
    if (t->magic != OGC_TAB_MAGIC || t->version != OGC_TAB_VERSION) return SL_RELEASE;
    if (svc->version < 3) { ogc_log(svc, 'S', svc->version); return SL_RELEASE; }
    u32 delta = (u32)(uintptr_t)block + t->img_off - t->ogv;
    u8 *S = (u8 *)(uintptr_t)(OGC_S_COORD + delta);
    if (SW(S, S_MAGIC) != OGC_MAGIC) return SL_RELEASE;
    SW(S, S_PATH) = (u32)(uintptr_t)path;
    SW(S, S_CFG) = (u32)(uintptr_t)block + 32;
    SW(S, S_FOBJ) = (u32)(uintptr_t)block + t->fobj_off;
    SW(S, S_DATA) = (u32)(uintptr_t)block + t->data_off;
    SW(S, S_DATA_CAP) = t->data_len;

    /* 1. the data files: read, checked, chosen, S filled -- inside this block only */
    /* Reserve the common virtual row before selecting file-backed rows. A
     * sixth saved RCD must not unload the entire consumer at the next boot.
     * Continue validating/cataloguing the other files for the enable list. */
    u32 n = load_rcd(S, path, OGC_MAX_ROWS - (t->virtual_len ? 1u : 0u));
    ogc_log(svc, 'D', SW(S, S_RCD_FOUND) << 24 | SW(S, S_RCD_OK) << 16 | n << 8 | (SW(S, S_RCD_WHY) & 0xFFu));
    if (t->virtual_len) {
        if (n==OGC_MAX_ROWS) { ogc_log(svc,'U',n); return SL_RELEASE; }
        u32 boot=(u32)(uintptr_t)block+t->virtual_off;
        if (rcd_check(S,boot,t->virtual_len)) return SL_RELEASE;
        W(SW(S,S_FOBJ)+FO_FILES+4u*n)=boot;
        if (!fill_s(S,++n)) return SL_RELEASE;
        struct vrc_state *v=(struct vrc_state *)(block+t->virtual_state);
        v->magic=VRC_MAGIC; v->abi=VRC_ABI; v->row=n-1u;
        SW(S,S_VRC)=(u32)(uintptr_t)v;
    }
    if (!n) {
        ogc_log(svc, 'R', SW(S, S_RCD_WHY));
        return SW(S,S_NAVAIL)?ogc_files_only(block,S,t,svc,path,delta):SL_RELEASE;
    }

    /* 2. claims: every hook site, the menu's sites, the converter; the donors'
     *    timing records (EXCL, claim only), their stock bytes from the tab */
    const u32 *c = (const u32 *)(block + t->claim_off);
    for (u32 i = 0; i < t->n_claim; i++, c += 5) {
        int r = c[1] ? svc->claim(svc, c[0], c[1], block + c[3], c[2]) : svc->claim_res(svc, c[0], c[2]);
        if (r != SL_OK) { ogc_log(svc, 'C', i << 16 | ((u32)r & 0xFFFFu)); return SL_RELEASE; }
    }
    for (u32 v = 0; v < (t->virtual_len ? 70u : SW(S, S_NVM)); v++) {
        u32 d = t->virtual_len ? W(TT+0x20u*v) : SW(S, S_VMDONOR + 4 * v), seen = 0;
        for (u32 w = 0; !t->virtual_len && w < v; w++) if (SW(S, S_VMDONOR + 4 * w) == d) seen = 1;
        if (seen) continue;
        u32 i = 0;
        while (W(TT + 0x20 * i) != d) i++;               /* rcd_check: a stock mode */
        int r = svc->claim(svc, TT + 0x20 * i + 4, 8, block + t->tt_off + 8 * i, SL_EXCL);
        if (r != SL_OK) { ogc_log(svc, 'T', d << 16 | ((u32)r & 0xFFFFu)); return SL_RELEASE; }
    }
    /* what the formats ask for: the virtual rates' menu rows (some entry is for one,
     * or a producer may offer one), the >99 fps clock (some mode is that fast) */
    u32 want_vr = t->virtual_len != 0, want_fast = t->virtual_len != 0;
    for (u32 i = 0; i < SW(S, S_NENT); i++) if (W(entp(S, i) + ENT_VRATE)) want_vr = 1;
    for (u32 r = 0; r < SW(S, S_NROWS); r++) if (W(rowp(S, r) + ROW_MAXRATE) >= 10000u) want_fast = 1;
    /* the virtual rate's LV texts, when a row offers it (claimed like everything else) */
    u32 vr_ok = want_vr && vr_claims(svc, (u32)(uintptr_t)block + t->vrlv_off);
    /* 3. veneers */
    u32 *ven = (u32 *)(block + t->scratch_off);
    for (u32 i = 0; i < t->n_hook; i++)
        if (!(ven[i] = svc->cave_alloc(svc, t->virtual_len && i==t->n_hook-1u ? 24u : 8u))) { ogc_log(svc, 'V', i); return SL_RELEASE; }

    /* 4. run-time words */
    SW(S, FN_PICK) = (u32)(uintptr_t)&ogc_pick;
    SW(S, FN_SEL) = (u32)(uintptr_t)&ogc_sel;
    SW(S, FN_FMT) = (u32)(uintptr_t)&ogc_fmt;
    SW(S, FN_CANVAS) = (u32)(uintptr_t)&ogc_canvas;
    SW(S, FN_NAME) = (u32)(uintptr_t)&ogc_name;
    SW(S, FN_OUT) = (u32)(uintptr_t)&ogc_out;
    SW(S, FN_VLOOK) = (u32)(uintptr_t)&ogc_vlook;
    SW(S, FN_V32) = (u32)(uintptr_t)&ogc_v32;
    SW(S, FN_AC38) = (u32)(uintptr_t)&ogc_ac38;
    SW(S, FN_FPS) = (u32)(uintptr_t)&ogc_fps;
    SW(S, FN_RECRATE) = (u32)(uintptr_t)&ogc_recrate;
    SW(S, FN_HDRCOPY) = (u32)(uintptr_t)&ogc_hdrcopy;
    SW(S, FN_BULK) = (u32)(uintptr_t)&ogc_bulk;
    SW(S, FN_CMT) = (u32)(uintptr_t)&ogc_cmt;
    SW(S, FN_SAVE) = (u32)(uintptr_t)&ogc_save;
    SW(S, FN_QSREC) = (u32)(uintptr_t)&ogc_qsrec;
    SW(S, FN_QSLAY) = (u32)(uintptr_t)&ogc_qslay;
    SW(S, FN_QSLOAD) = (u32)(uintptr_t)&ogc_qsload;
    SW(S, S_UIA_FN) = (u32)(uintptr_t)&uia_apply;
    SW(S, FN_GATE) = (u32)(uintptr_t)&ogc_gate;
    SW(S, FN_BIT) = (u32)(uintptr_t)&ogc_bit;
    SW(S, FN_GS) = (u32)(uintptr_t)&ogc_gs;
    SW(S, FN_RCMT) = (u32)(uintptr_t)&ogc_rcmt;
    SW(S, FN_VTV) = (u32)(uintptr_t)&ogc_vtv;
    SW(S, FN_VGUI) = (u32)(uintptr_t)&ogc_virtual_gui;
    SW(S, FN_BINPATH) = (u32)(uintptr_t)&ogc_binpath;
    SW(S, FN_BINKERNEL) = (u32)(uintptr_t)&ogc_binkernel;
    SW(S, S_ENABLE_FN) = (u32)(uintptr_t)&ogc_enable_set;
    for (u32 i = 0; i < SW(S, S_NENT); i++) W(entp(S, i) + ENT_KEYPTR) = entp(S, i) + ENT_KEY;

    /* 5. the menu: the virtual rate's page first (the rows' blocks build on it), then
     *    each row's Settings entry (uishare's applier, our template) */
    if (!bit_install(S, (u32)(uintptr_t)block, t)) return SL_RELEASE;
    if (vr_ok) SW(S, S_VR_WHY) = vr_install(S, (u32)(uintptr_t)block, t);
    u32 on = ui_rows(S, (u32)(uintptr_t)block + t->tpl_off);
    ogc_log(svc, 'O', on);
    if (!on) return SL_RELEASE;            /* the loader puts every claimed range back */

    /* 6. the converter reads our pairs: movw/movt r2 = S.PAIRS, mov r2, #n (claimed EXCL) */
    pairs_build(S);
    {
        u32 pa = (u32)(uintptr_t)S + S_PAIRS;
        W(PAIR_MOVW) = mov_imm(W(PAIR_MOVW), pa & 0xFFFFu);
        W(PAIR_MOVT) = mov_imm(W(PAIR_MOVT), pa >> 16);
        W(PAIR_NUM) = (W(PAIR_NUM) & 0xFFFFFF00u) | SW(S, S_PAIRN);
    }
    rate_pairs_build(S);
    {
        u32 pa = (u32)(uintptr_t)S + S_RPAIRS, qa = (u32)(uintptr_t)S + S_SPAIRS;
        W(RATE_MOVW) = mov_imm(W(RATE_MOVW), pa & 0xFFFFu);
        W(RATE_MOVT) = mov_imm(W(RATE_MOVT), pa >> 16);
        W(RATE_NUM) = (W(RATE_NUM) & 0xFFFFFF00u) | SW(S, S_RPAIRN);
        W(SUM_MOVW) = mov_imm(W(SUM_MOVW), qa & 0xFFFFu);
        W(SUM_MOVT) = mov_imm(W(SUM_MOVT), qa >> 16);
        W(SUM_NUM) = (W(SUM_NUM) & 0xFFFFFF00u) | SW(S, S_SPAIRN);
    }
    /* channel 0's >99 fps clock gate 5/16 -> full (claimed EXCL, restored at power-off),
     * only when a format records that fast */
    if (want_fast && W(0xC0189440u) == 0x2C49F241u) W(0xC0189440u) = 0x7CFFF64Fu;   /* movw ip,#0x1249 -> #0xffff */
    SW(S, S_QS_TAB) = (u32)(uintptr_t)block + t->qstab_off;
    SW(S, S_QS_BUF) = (u32)(uintptr_t)block + t->qsbuf_off;
    SW(S, S_QS_PRE) = W(RCACHE + 4);          /* parsed before us: let go once (ogc_qslay) */
    SW(S, S_QS_READY) = 1;
    svc->publish(svc);

    /* 7. hooks: the way down, the veneers, then the sites (picker last) */
    const u32 *h = (const u32 *)(block + t->hook_off);
    for (u32 i = 0; i < t->n_hook; i++) {
        const u32 *r = h + 5 * i;
        u32 below = svc->chain_next(svc, r[0], r[2] == HOOK_TW);
        W(r[3] + delta) = below ? below : r[4] + delta;
    }
    for (u32 i = 0; i < t->n_hook; i++) {
        W(ven[i]) = h[5 * i + 2] == HOOK_TW ? THUMB_VENEER : 0xE51FF004u;
        W(ven[i] + 4) = h[5 * i + 1] + delta;           /* an ARM shim either way */
    }
    if (t->virtual_len) {
        struct vrc_endpoint *e=(struct vrc_endpoint *)(uintptr_t)(ven[t->n_hook-1u]+8u);
        e->magic=VRC_MAGIC; e->abi=VRC_ABI;
        e->dispatch=&ogc_virtual_dispatch; e->context=(uintptr_t)S;
    }
    svc->publish(svc);
    for (u32 i = 0; i < t->n_hook; i++) {
        u32 site = h[5 * i], kind = h[5 * i + 2];
        W(site) = kind == HOOK_TW ? thumb_bw(site, ven[i])
                  : (kind == HOOK_BL ? 0xEB000000u : 0xEA000000u) | (((ven[i] - site - 8) >> 2) & 0x00FFFFFFu);
    }
    svc->publish(svc);

    /* 8. the user's last choice back */
    ogc_restore(S);
    if (ogc_files_init(S,(u32)(uintptr_t)block+t->files_off,(u32)(uintptr_t)block+t->files_state)
        && svc->version>=4 && svc->button)
        svc->button(svc,ogc_files_button,S,path);
    return SL_KEEP;
}
