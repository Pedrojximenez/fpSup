#include "sl_menu.h"

/* Sensor Lab: the MODE popup, built on the camera (design §8.12).  It lists
 * modes for the chosen bit depth that can run at any supported rate; only the
 * FILTER FPS row narrows them by frame rate.  The user's current FPS does not
 * remove MODE rows.  None -> one "No matching" row.
 *
 * The scan is og3krecipe.S's own acceptance test, mode by mode, so every row
 * is one the recipe can solve (a row it could not would fall back to FHD):
 *   depth   bit 14 wants metadata +0x3C == 1, any other bit 0 or 3
 *   hmax    one of the six the timing budget table knows
 *   cycles  RATETAB[ridx].cycles >= (raster_h + vblank) * hmax
 *   budget  TMGTAB[hmax_index * N_RATE + ridx] != 0
 * Table bases come from the imager descriptor, as og3krecipe takes them.  The
 * one timing record imx410_fmt rewrites (RECIPE's donor) is read from the
 * stock copy RECIPE keeps (R_SAVE0).
 *
 * The rewrite is the stock in-place model update FUN_c055fe88 runs on the UI
 * thread: find the resource by name, its instance, the model interface; delete
 * every row; per row insert, make current, write each cell; notify the views.
 * Stock asserts when a step fails; here every step is checked and a failure
 * stops with the step recorded.  The interface must be modelCSV's -- the five
 * slots used must hold exactly modelCSV's wrappers -- or nothing is touched.
 * (r10 on camera: the interface came back at another address than the image's
 * table 0xC2E01DB0 -- FUN_c05d8358 returns [[instance+0x30]+4] -- so the check
 * is on the slots, not the table's address.)  No setting is written.
 * The OUTPUT panel drives AXIS's geometry words (axis_post: raster, binning,
 * RWZM, the visible size, the mode); bit depth and rate stay imx410_fmt's, from
 * the menu.  og3krecipe recomputes RECIPE from AXIS when the picker runs. */
#define IMAGER        0xC343B588u
#define META_STRIDE   0x64u
#define TMG_STRIDE    0x20u
#define R_VALID       (9u * 4u)
#define R_IDX         (11u * 4u)
#define R_SAVE0       (21u * 4u)
/* modelCSV's interface wrappers (Thumb), as the image's table holds them */
#define W_ROWS        0xC05F4861u
#define W_CURRENT     0xC05F4879u
#define W_STRING      0xC05F4929u
#define W_INSERT      0xC05F4941u
#define W_DELETE      0xC05F4959u
#define IF_ROWS       0x14u
#define IF_CURRENT    0x18u
#define IF_STRING     0x30u          /* FUN_c05f5cf0: (model, column, text) */
#define IF_INSERT     0x34u
#define IF_DELETE     0x38u
#define DESC_VALUE    0x08u
#define GUI_OBJECT    0xC37B7048u
#if defined(SL_DYNAMIC_CORE)
/* The early launcher owns these tables in one USER allocation.  Keep offsets in
 * one build-time contract and use the base cached by the late UI launcher. */
#if !defined(SL_OFF_AXIS) || !defined(SL_OFF_MARK) || !defined(SL_OFF_RATE240)
#error "Sensor Lab USER offsets must come from the core packer"
#endif
#define SL_ADDR(m, field) ((m)->core_base + SL_OFF_##field)
#else
#ifndef SL_AXIS
#error "legacy/host Sensor Lab addresses come from imx410_plan"
#endif
#define SL_ADDR(m, field) ((void)(m), SL_##field)
#endif
#define CUSTOM_RES    4u

#if defined(SL_MENU_HOST_TEST)
#define N (&sl_menu_test_natives)
#define peek(a) N->read(a)
#define poke(a, v) N->write(a, v)
#define res_find(app, name, out) N->res_find(app, name, out)
#define res_count(r, out) N->res_count(r, out)
#define res_load(r) N->res_load(r)
#define res_get(r, out) N->res_get(r, out)
#define model_iface(i, out) N->model_iface(i, out)
#define notify(i, arg) N->notify(i, arg)
#define m_rows(f, i, out) N->m_rows(i, out)
#define m_current(f, i, r) N->m_current(i, r)
#define m_string(f, i, c, s) N->m_string(i, c, s)
#define m_insert(f, i, r, n) N->m_insert(i, r, n)
#define m_delete(f, i, r, n) N->m_delete(i, r, n)
#define nbr_register(app, pack, len, out) N->nbr_register(app, pack, len, out)
#define settings() N->settings()
#define get_res(s) N->get_res(s)
#define get_bit(s) N->get_bit(s)
#define get_rate(s) N->get_rate(s)
#define subscribe(name, fn) N->subscribe(name, fn)
#define post_int(name, v) N->post_int(name, v)
#define post_str(name, t) N->post_str(name, t)
#define tick_ms() N->tick_ms()
extern struct sl_menu *sl_test_menu;            /* the fixture's: MARK+8 holds a 32-bit pointer */
#define the_menu() sl_test_menu
#elif defined(__arm__) && UINTPTR_MAX == UINT32_MAX
#define peek(a) (*(volatile const uint32_t *)(a))
#define poke(a, v) (*(volatile uint32_t *)(a) = (v))
typedef uint32_t (*fn1)(uintptr_t);
typedef uint32_t (*fn2)(uintptr_t, uintptr_t);
typedef uint32_t (*fn3)(uintptr_t, uintptr_t, uintptr_t);
/* all Thumb (checked against the image: push {r4, lr} / cmp r0, #0 ...) */
#define res_find(app, name, out) ((fn3)0xC05E0321u)(app, (uintptr_t)(name), (uintptr_t)(out))
#define res_count(r, out) ((fn2)0xC05D8BD9u)(r, (uintptr_t)(out))
#define res_load(r) ((fn1)0xC05D8B79u)(r)
#define res_get(r, out) ((fn2)0xC05D8BF9u)(r, (uintptr_t)(out))
#define model_iface(i, out) ((fn2)0xC05D8359u)(i, (uintptr_t)(out))
#define notify(i, arg) ((fn2)0xC05D83A9u)(i, (uintptr_t)(arg))
#define m_rows(f, i, out) ((fn2)peek((f) + IF_ROWS))(i, (uintptr_t)(out))
#define m_current(f, i, r) ((fn2)peek((f) + IF_CURRENT))(i, r)
#define m_string(f, i, c, s) ((fn3)peek((f) + IF_STRING))(i, c, (uintptr_t)(s))
#define m_insert(f, i, r, n) ((fn3)peek((f) + IF_INSERT))(i, r, n)
#define m_delete(f, i, r, n) ((fn3)peek((f) + IF_DELETE))(i, r, n)
typedef uint32_t (*fn4)(uintptr_t, uintptr_t, uint32_t, uintptr_t);
/* C05E84D8 (Thumb): (resource ctx = the UI app, pack, bytes, &new reader) */
#define nbr_register(app, pack, len, out) ((fn4)0xC05E84D9u)(app, pack, len, (uintptr_t)(out))
typedef uintptr_t (*fn0)(void);
/* the settings manager and three getters (ARM), as sl_excl.S ROLE 6/11 call them */
#define settings() ((fn0)0xC0057AE8u)()
#define get_res(s) ((fn1)0xC005C058u)(s)       /* resolution: 4 = CUSTOM */
#define get_bit(s) ((fn1)0xC005BF28u)(s)       /* eRawBitType: 1 = 14-bit */
#define get_rate(s) ((fn1)0xC005C0F0u)(s)      /* frame rate, internal enum */
/* C0560FB0 (ARM): subscribe fn to an app variable's writes, through the binding
 * context {app, 0, 1} at GUI_OBJECT (it walks [ctx+i*4] for i < [ctx+8]); stock
 * passes its GUI object's +0x1C the same way (C057A448).  fn(descriptor, ...) runs
 * on the UI thread with the new value at descriptor +8, returns 0 (C057A6F8). */
#define subscribe(name, fn) ((fn3)0xC0560FB0u)(GUI_OBJECT, (uintptr_t)(name), (uintptr_t)(fn))
/* C0593F30 (ARM): queue an integer app-variable update {2, 0, name, value} to the
 * GUI (668 stock callers); applied on the UI thread, views notified. */
#define post_int(name, v) ((fn3)0xC0593F30u)(0, (uintptr_t)(name), (uintptr_t)(v))
/* C0593FE0 (ARM): queue a string app-variable update {2, 2, name, text}; the
 * GUI keeps the pointer, so the text must stay put (struct sl_menu holds it) */
#define post_str(name, t) ((fn3)0xC0593FE0u)(0, (uintptr_t)(name), (uintptr_t)(t))
/* C002B920 (ARM): milliseconds since boot (the shell's "time tickm") */
#define tick_ms() ((fn0)0xC002B920u)()
#if defined(SL_CALC_ONLY)
/* Owned .text word, addressed PC-relative. No recording hook or fixed cave anchor. */
extern const uintptr_t rl_calc_menu;
#define the_menu() ((struct sl_menu *)*(volatile const uintptr_t *)&rl_calc_menu)
#elif defined(SL_DYNAMIC_CORE)
/* The picker is the only cross-entry anchor.  Its short cave veneer contains
 * the relocated FMT function address.  No cave word is reserved for a pointer
 * or UI state.  A callback can find MARK again without a mutable global. */
static uintptr_t sl_core_base(void) {
    uint32_t branch = peek(0xC043CCF8u), veneer, target, base;
    if ((branch & 0xFF000000u) != 0xEA000000u) return 0;
    veneer = 0xC043CD00u + ((int32_t)(branch << 8) >> 6);
    if (veneer < 0xC072E064u || veneer > 0xC072EFB4u - 8u || (veneer & 3u) ||
        peek(veneer) != 0xE51FF004u) return 0;
    target = peek(veneer + 4u);
    if ((target & 3u) || target < SL_OFF_FMT_CODE) return 0;
    base = target - SL_OFF_FMT_CODE;
    if ((base & 7u) || base < 0x40000000u || base >= 0xF0000000u ||
        peek(base + SL_OFF_CORE_MAGIC) != 0x534C434Fu) return 0;
    return base;
}
static struct sl_menu *sl_core_menu(void) {
    uintptr_t base = sl_core_base();
    uintptr_t state;
    if (!base || peek(base + SL_OFF_MARK) != 0x534D4C53u) return 0;
    state = peek(base + SL_OFF_MARK + 8u);
    if (!state || (state & 7u)) return 0;
    return ((struct sl_menu *)state)->core_base == base ? (struct sl_menu *)state : 0;
}
#define the_menu() sl_core_menu()
#else
#define the_menu() ((struct sl_menu *)peek(SL_MARK + 8u))
#endif
#else
#error "ARM32 native ABI required; host tests must explicitly substitute it"
#endif

static uint32_t hmax_index(uint32_t h) {     /* og3krecipe hmax_set */
    switch (h) {
    case 330: return 0; case 360: return 1; case 395: return 2;
    case 445: return 3; case 450: return 4; case 911: return 5;
    default: return 0xFFFFFFFFu;
    }
}

/* Units are separate blobs (build_sl_menu: no linker): calls inside this file go
 * to static functions, the public names below are thin entry points. */
/* TIMING word 1 (hmax | tail << 16) of metadata row i: imx410_fmt's donor row
 * reads its stock copy from RECIPE (R_SAVE0) */
static uint32_t timing_w1(const struct sl_menu *m, uintptr_t tmg, uint32_t i) {
#if defined(SL_CALC_ONLY)
    (void)m;
    return peek(tmg + TMG_STRIDE * i + 4u);
#else
    uintptr_t recipe = SL_ADDR(m, RECIPE);
    if (peek(recipe + R_VALID) && peek(recipe + R_IDX) == i && peek(recipe + R_SAVE0))
        return peek(recipe + R_SAVE0);
    return peek(tmg + TMG_STRIDE * i + 4u);
#endif
}

/* does the mode at metadata `row` (its hmax and hmax index) run at rate ridx?
 * The recipe's own test: its rows plus blanking fit the rate's cycles, and the
 * timing table has a budget for that hmax at that rate */
static uint32_t runs_at(const struct sl_menu *m, uintptr_t row, uint32_t hmax, uint32_t hi, uint32_t ridx) {
    if (hi == 0xFFFFFFFFu) return 0;
    if ((peek(row + 8u) + peek(row + 0x5Cu)) * hmax > peek(SL_ADDR(m, RATETAB) + 12u * ridx)) return 0;
    if (!peek(SL_ADDR(m, TMGTAB) + 4u * (hi * SL_NRATE + ridx))) return 0;
    return 1;
}

/* ridx == SL_NRATE builds the MODE catalogue across every supported rate;
 * concrete indices remain available for exact recipe checks and tests. */
static uint32_t scan_modes(const struct sl_menu *m, uint32_t bit, uint32_t ridx, uint8_t *ids) {
    uintptr_t desc = peek(IMAGER), meta, tmg;
    uint32_t count, n = 0, k1[SL_MODES_MAX], k2[SL_MODES_MAX];
#if defined(SL_DYNAMIC_CORE)
    if (!m || !m->core_base) return 0;
#endif
    if (!desc || (desc & 3u) || ridx > SL_NRATE) return 0;
    tmg = peek(desc);
    meta = peek(desc + 8u);
    count = peek(desc + 12u);
    if (!tmg || !meta || count > 256u) return 0;
    if (count > SL_MODES_MAX) count = SL_MODES_MAX; /* res-custom may append virtual rows */
    for (uint32_t i = 0; i < count; ++i) {
        uintptr_t row = meta + META_STRIDE * i;
        uint32_t depth = peek(row + 0x3Cu), w1, hmax, hi, id;
        if (bit && (bit == 14 ? depth != 1u : (depth != 0u && depth != 3u))) continue;
        w1 = timing_w1(m, tmg, i);                 /* imx410_fmt's donor: the stock word */
        hmax = w1 & 0xFFFFu;
        hi = hmax_index(hmax);
        if (hi == 0xFFFFFFFFu) continue;
        if (ridx == SL_NRATE) {
            uint32_t k;
            for (k = 0; k < SL_NRATE; ++k)
                if (runs_at(m, row, hmax, hi, k)) break;
            if (k == SL_NRATE) continue;
        } else if (!runs_at(m, row, hmax, hi, ridx)) continue;
        id = peek(row);
        if (id > 0xFFu) continue;
        /* best guessed quality first (the user 2026-10-03; insertion, at most 70):
         * less reduction (+0x4C x +0x50), then the slower rolling shutter (the
         * larger HMAX: the quiet readouts), then the lower design rate (+0x40),
         * then the larger raster (+0x04 x +0x08), then the mode id */
        uint32_t a = peek(row + 0x4Cu) * peek(row + 0x50u), f = peek(row + 0x40u);
        uint32_t q1 = (a > 0xFFu ? 0xFFu : a) << 24 | (0xFFFu - (hmax > 0xFFFu ? 0xFFFu : hmax)) << 12
                      | (f > 0xFFFu ? 0xFFFu : f);
        uint32_t q2 = 0xFFFFFFFFu - peek(row + 4u) * peek(row + 8u);
        uint32_t k = n;
        while (k && (k1[k - 1] > q1 || (k1[k - 1] == q1 && (k2[k - 1] > q2 ||
                                                          (k2[k - 1] == q2 && ids[k - 1] > id))))) {
            ids[k] = ids[k - 1]; k1[k] = k1[k - 1]; k2[k] = k2[k - 1];
            --k;
        }
        ids[k] = (uint8_t)id; k1[k] = q1; k2[k] = q2;
        ++n;
    }
    return n;
}

/* What the menu shows now, read from the settings (not AXIS: imx410_fmt moves
 * AXIS's rate only when the picker runs, after the LV restarts).  Frame rate
 * internal enum -> imx410_block.RATE_KEYS index; 239.76 is stored as 119.88
 * (internal 7) with the RAM flag RATE240 (imx410_rate_native,
 * SETTINGS_AREA_FIRST_RULE).  Unknown (internal 0 = the hidden 15 fps) ->
 * an index past the table: nothing matches. */
static uint32_t rate_index(const struct sl_menu *m, uint32_t internal) {
    switch (internal) {
    case 1: return 0;   /* 23.98 */
    case 12: return 1;  /* 24 */
    case 2: return 2;   /* 25 */
    case 3: return 3;   /* 29.97 */
    case 13: return 4;  /* 48 */
    case 4: return 5;   /* 50 */
    case 5: return 6;   /* 59.94 */
    case 6: return 7;   /* 100 */
    case 7: return peek(SL_ADDR(m, RATE240)) ? 9u : 8u;   /* 239.76 or 119.88 */
    default: return SL_NRATE;
    }
}

static uint32_t decimal(char *to, uint32_t v) {   /* to[] >= 4; v < 1000 */
    volatile char *t = to;
    uint32_t n = 0;
    if (v >= 100) t[n++] = (char)('0' + v / 100);
    if (v >= 10) t[n++] = (char)('0' + v / 10 % 10);
    t[n++] = (char)('0' + v % 10);
    t[n] = 0;
    return n;
}

/* v (< 100000) in decimal at t, no leading zeros; returns the length.  Constant
 * divisors: the compiler multiplies (no __aeabi_uidiv) */
static uint32_t dec5(volatile char *t, uint32_t v) {
    uint32_t n = 0;
    if (v >= 10000u) t[n++] = (char)('0' + v / 10000u % 10u);
    if (v >= 1000u) t[n++] = (char)('0' + v / 1000u % 10u);
    if (v >= 100u) t[n++] = (char)('0' + v / 100u % 10u);
    if (v >= 10u) t[n++] = (char)('0' + v / 10u % 10u);
    t[n++] = (char)('0' + v % 10u);
    t[n] = 0;
    return n;
}

/* "M98 3032x2012": the mode id and its raster (metadata +0x04 / +0x08) */
static void mode_label(volatile char *t, uint32_t id) {
    uintptr_t desc = peek(IMAGER), meta = desc ? peek(desc + 8u) : 0;
    uint32_t count = desc ? peek(desc + 12u) : 0, n = 0;
    t[n++] = 'M';
    n += dec5(t + n, id);
    for (uint32_t i = 0; meta && i < count && i < SL_MODES_MAX; ++i) {
        uintptr_t row = meta + META_STRIDE * i;
        if (peek(row) != id) continue;
        t[n++] = ' ';
        n += dec5(t + n, peek(row + 4u) & 0xFFFFu);
        t[n++] = 'x';
        dec5(t + n, peek(row + 8u) & 0xFFFFu);
        break;
    }
}

/* The MODE row's summary (SL_M_Text) and the lists' cap (SL_ModeMax = rows - 1);
 * a selection past the list (it got shorter) goes back to the first, best row */
/* the raster of mode `id` (metadata +0x04 / +0x08) and its reduction (+0x4C /
 * +0x50), or 0 */
static void raster_of(uint32_t id, uint32_t *w, uint32_t *h, uint32_t *sx, uint32_t *sy) {
    uintptr_t desc = peek(IMAGER), meta = desc ? peek(desc + 8u) : 0;
    uint32_t count = desc ? peek(desc + 12u) : 0;
    *w = *h = *sx = *sy = 0;
    for (uint32_t i = 0; meta && i < count && i < SL_MODES_MAX; ++i) {
        uintptr_t row = meta + META_STRIDE * i;
        if (peek(row) != id) continue;
        *w = peek(row + 4u) & 0xFFFFu;
        *h = peek(row + 8u) & 0xFFFFu;
        *sx = peek(row + 0x4Cu);
        *sy = peek(row + 0x50u);
        return;
    }
}

static void mode_post(struct sl_menu *m) {
    uint32_t n = m->modes_rows, sel = m->mode_sel, w = 0, h = 0, sx = 0, sy = 0;
    volatile char *t = m->mode_text;
    if (n && sel >= n) {
        sel = m->mode_sel = 0;
        post_int(m->names[16], 0u);                        /* SL_M_Sel */
    }
    if (n) mode_label(t, m->mode_ids[sel]);
    else { t[0] = '-'; t[1] = 0; }
    if (n) raster_of(m->mode_ids[sel], &w, &h, &sx, &sy);
    if (w != m->ro_w || h != m->ro_h || sx != m->ro_sx || sy != m->ro_sy) {
        m->ro_w = w; m->ro_h = h;                          /* OUTPUT's readout moves (readout_apply) */
        m->ro_sx = sx; m->ro_sy = sy;
        m->ro_changed = 1u;
    }
    post_int(m->names[24], n ? n - 1u : 0u);               /* SL_ModeMax */
    post_str(m->names[25], m->mode_text);                  /* SL_M_Text */
    t = m->tab_text;                                       /* SL_M_Tab: "MODES (62)" */
    t[0] = 'M'; t[1] = 'O'; t[2] = 'D'; t[3] = 'E'; t[4] = 'S'; t[5] = ' '; t[6] = '(';
    {
        uint32_t k = 7u + dec5(t + 7, n);
        t[k++] = ')'; t[k] = 0;
    }
    post_str(m->names[40], m->tab_text);
}

/* ---- the record settings' Frame rate / Bit depth rows follow the mode ----------
 * (the user 2026-10-03: "選擇好mode後退出 外面的fps bit 要遭受mode限制反灰").
 * Our own lists SL_RATE (10 rows, rate_index order) and SL_BIT (4 rows: 8 / 10 /
 * 12 / 14 bit, eRawBitType 4 / 3 / 0 / 1) take Enabled,Enabled2 = 1,2 or 0,0 --
 * stock greys a 0,0 row and answers it with its "cannot be selected" dialog.
 * Nothing reaches the settings area: these are the lists, not the values. */
static uint32_t list_enable(uint32_t w0, uint32_t w1, uint32_t n, uint32_t mask) {
    uintptr_t app = peek(GUI_OBJECT), res = 0, inst = 0, iface = 0;
    uint32_t name_words[2], arg[1], rows = 0, have = 0;
    char on1[2], on2[2], off[2];
    volatile char *v;
    { volatile uint32_t *w = name_words; w[0] = w0; w[1] = w1; }
    v = on1; v[0] = '1'; v[1] = 0;
    v = on2; v[0] = '2'; v[1] = 0;
    v = off; v[0] = '0'; v[1] = 0;
    if (!app || res_find(app, (const char *)name_words, &res) || !res) return 1;
    if (res_count(res, &have)) return 2;
    if (!have && res_load(res)) return 3;
    if (res_get(res, &inst) || !inst) return 4;
    if (model_iface(inst, &iface) || !iface || (iface & 3u)) return 5;
    if (peek(iface + IF_ROWS) != W_ROWS || peek(iface + IF_CURRENT) != W_CURRENT ||
        peek(iface + IF_STRING) != W_STRING)
        return 6;                                         /* not modelCSV's: leave it */
    if (m_rows(iface, inst, &rows)) return 7;
    for (uint32_t r = 0; r < rows && r < n; ++r) {
        uint32_t on = (mask >> r) & 1u;
        m_current(iface, inst, r);
        if (m_string(iface, inst, 3u, on ? on1 : off) || m_string(iface, inst, 4u, on ? on2 : off)) return 8;
    }
    arg[0] = 1u;
    return notify(inst, arg) ? 9u : 0u;
}

/* the chosen mode's rates (bit k = rate_index k: the scan's own test) and bit
 * depth rows; no mode: everything open */
static void excl_update(struct sl_menu *m) {
#if defined(SL_CALC_ONLY)
    (void)m; /* Calculator inputs never alter recording lists. */
#else
    uintptr_t desc = peek(IMAGER), meta = desc ? peek(desc + 8u) : 0, tmg = desc ? peek(desc) : 0;
    uint32_t count = desc ? peek(desc + 12u) : 0, rates = 0x3FFu, bits = 0xFu, key = 0;
    if (meta && tmg && m->modes_rows && m->mode_sel < m->modes_rows) {
        uint32_t id = m->mode_ids[m->mode_sel];
        key = id + 1u;
        for (uint32_t i = 0; i < count && i < SL_MODES_MAX; ++i) {
            uintptr_t row = meta + META_STRIDE * i;
            uint32_t hmax, hi, k;
            if (peek(row) != id) continue;
            hmax = timing_w1(m, tmg, i) & 0xFFFFu;
            hi = hmax_index(hmax);
            rates = 0;
            for (k = 0; k < 10u && k < SL_NRATE; ++k)
                if (runs_at(m, row, hmax, hi, k)) rates |= 1u << k;
            bits = peek(row + 0x3Cu) == 1u ? 0x8u : 0x7u;   /* 14-bit mode: 14 only; else 8 / 10 / 12 */
            break;
        }
    }
    if (key == m->excl_key) return;                       /* the same mode: the lists already say so */
    m->excl_key = key;
    list_enable(0x525F4C53u, 0x00455441u, 10u, rates);    /* SL_RATE */
    list_enable(0x425F4C53u, 0x00005449u, 4u, bits);      /* SL_BIT */
#endif
}

static uint32_t stop(struct sl_menu *m, uint32_t step) {
    m->modes_step = step;
    if (m->count_desc) poke(m->count_desc + DESC_VALUE, 1u);   /* one row: what stock parsed */
    return step;
}

static uint32_t value_of(struct sl_menu *m, uint32_t index);
static uint32_t filter_modes(struct sl_menu *m, uint32_t n);
static uint32_t filter_now(struct sl_menu *m);

static uint32_t modes(struct sl_menu *m) {
    uint32_t bit, key, filter, n, rows = 0, have = 0;
#if defined(SL_CALC_ONLY)
    uint32_t previous=m && m->modes_rows && m->mode_sel<m->modes_rows ? m->mode_ids[m->mode_sel] : 0xffffffffu;
#endif
#if !defined(SL_CALC_ONLY)
    uintptr_t mgr;
#endif
    uintptr_t app, res = 0, inst = 0, iface = 0;
    uint32_t name_words[2], arg[1];
    char no[4], text[24], popup[4], blank[8], on[2], two[2];
    volatile char *v;
    if (!m || m->result != SL_MENU_INSTALLED) return SL_MODES_NOT_INSTALLED;
#if defined(SL_CALC_ONLY)
    bit = 12u;
#else
    mgr = settings();
    if (!mgr) return SL_MODES_NO_IMAGER;
    bit = get_bit(mgr) == 1u ? 14u : 12u;
#endif
    {   /* FILTER's Bit depth, when set, is the depth listed (the user: "14bit mode只有0個"
         * -- a 12-bit menu showed no 14-bit mode); the menu's otherwise */
        uint32_t fb = value_of(m, 12u);                  /* V_FBIT */
#if defined(SL_CALC_ONLY)
        bit=fb==1u?14u:12u;
#else
        if (fb == 1u) bit = 12u;
        else if (fb == 2u) bit = 14u;
#endif
    }
    key = (bit & 0xFFu) | 1u << 31;
    filter = filter_now(m);
    if (key == m->modes_key && filter == m->filter_key) return m->modes_step;
    m->filter_key = filter;
    m->modes_key = key;
    m->modes_runs++;
    if (!peek(IMAGER)) return stop(m, SL_MODES_NO_IMAGER);
    n = filter_modes(m, scan_modes(m, bit, SL_NRATE, m->mode_ids));
    m->modes_rows = n;
#if defined(SL_CALC_ONLY)
    m->mode_sel=0;
    for(uint32_t j=0;j<n;j++)if(m->mode_ids[j]==previous)m->mode_sel=j;
    if(n && previous!=m->mode_ids[m->mode_sel])m->ro_changed=1;
#endif

    app = peek(GUI_OBJECT);
    { volatile uint32_t *w = name_words; w[0] = 0x4D5F4C53u; w[1] = 0x0045444Fu; }   /* SL_MODE */
    if (!app || res_find(app, (const char *)name_words, &res) || !res) return stop(m, SL_MODES_FIND);
    if (res_count(res, &have)) return stop(m, SL_MODES_COUNT);
    if (!have && res_load(res)) return stop(m, SL_MODES_LOAD);
    if (res_get(res, &inst) || !inst) return stop(m, SL_MODES_GET);
    if (model_iface(inst, &iface) || !iface || (iface & 3u)) return stop(m, SL_MODES_IFACE);
    m->modes_inst = inst;
    m->modes_iface = iface;
    if (peek(iface + IF_ROWS) != W_ROWS || peek(iface + IF_CURRENT) != W_CURRENT ||
        peek(iface + IF_STRING) != W_STRING || peek(iface + IF_INSERT) != W_INSERT ||
        peek(iface + IF_DELETE) != W_DELETE)
        return stop(m, SL_MODES_NOT_CSV);

    /* the lab page's list columns (sl_lists.rows_csv lab: NO,TEXT,Popup,IMAGE,
     * Enabled,Enabled2 -- its ListItem draws a ListIcon from IMAGE; r23 froze
     * on a lab list without one) */
    v = popup; v[0] = 'x'; v[1] = 'x'; v[2] = 0;
    v = blank; v[0] = 'b'; v[1] = 'l'; v[2] = 'a'; v[3] = 'n'; v[4] = 'k'; v[5] = 0;
    v = two; v[0] = '2'; v[1] = 0;
    if (m_rows(iface, inst, &rows)) return stop(m, SL_MODES_DELETE);
    if (rows && m_delete(iface, inst, 0, rows)) return stop(m, SL_MODES_DELETE);
    for (uint32_t r = 0; r < (n ? n : 1u); ++r) {
        if (m_insert(iface, inst, r, 1u)) return stop(m, SL_MODES_INSERT);
        m_current(iface, inst, r);
        decimal(no, r + 1u);
        v = on;
        if (n) {
            v[0] = '1';
            mode_label(text, m->mode_ids[r]);
        } else {
            v[0] = '0';                                  /* greyed */
            v = text;
            v[0] = 'N'; v[1] = 'o'; v[2] = ' '; v[3] = 'm'; v[4] = 'a'; v[5] = 't'; v[6] = 'c';
            v[7] = 'h'; v[8] = 'i'; v[9] = 'n'; v[10] = 'g'; v[11] = 0;
        }
        on[1] = 0;
        if (m_string(iface, inst, 0u, no) || m_string(iface, inst, 1u, text) ||
            m_string(iface, inst, 2u, popup) || m_string(iface, inst, 3u, blank) ||
            m_string(iface, inst, 4u, on) || m_string(iface, inst, 5u, n ? two : on))
            return stop(m, SL_MODES_WRITE);
    }
    arg[0] = 1u;
    if (notify(inst, arg)) return stop(m, SL_MODES_NOTIFY);
    if (m->count_desc) poke(m->count_desc + DESC_VALUE, n ? n : 1u);
    mode_post(m);
#if defined(SL_CALC_ONLY)
    /* The native selector clamps to SL_ModeMax. Publish its new range before
     * the stable mode's index, especially when expanding a filtered list. */
    post_int(m->names[16],m->mode_sel);
#endif
    m->modes_step = SL_MODES_OK;
    return SL_MODES_OK;
}


/* ---- private pages (sl_pages.py) -----------------------------------------
 * The stock loader parses the pack's index (case 0 of FUN_c05e6400) and builds
 * one screen (FUN_c05e0cc8 -> FUN_c05d74a8 onto app+7C) and one runtime entry
 * per page, in a reader of its own.  Checked first: the ctx is the UI app (r4
 * on camera froze when it was not), and the screen vector has room -- a push
 * at capacity reallocates it (FUN_c05d75b8), which a walker holding the old
 * array would not survive.  Camera 2026-10-02: 221 screens, capacity 224; the
 * same for the state machines the pack adds (17 of 24).
 * After registration the new reader takes the shared pool (stock + private
 * strings) from the stock reader: the pages' records use those offsets; the
 * index names were already resolved from the pack's own pool. */
#define SCREENS_COUNT 0x80u
#define SCREENS_CAP   0x84u
#define MACHINES_COUNT 0xF8u    /* app+0xF4 state machines (FUN_c05de938): camera 17 / 24 */
#define MACHINES_CAP   0xFCu
#define READER_APP    0x08u
#define READER_POOL_LEN 0x10u
#define READER_POOL   0x14u
enum { PAGES_NONE = 0, PAGES_OK = 1, PAGES_TRYING = 2, PAGES_REFUSED = 3, PAGES_NO_ROOM = 4,
       PAGES_NOT_APP = 5 };

static uint32_t register_pages(struct sl_menu *m) {
    uintptr_t app = peek(GUI_OBJECT), rd = 0;
    m->pages_state = PAGES_TRYING;
    if (!app || peek(m->reader + READER_APP) != app) return m->pages_state = PAGES_NOT_APP;
    if (peek(app + SCREENS_COUNT) >= peek(app + SCREENS_CAP)) return m->pages_state = PAGES_NO_ROOM;
    /* the pack also adds one state machine (sl_pages.py: the page switches) */
    if (peek(app + MACHINES_COUNT) >= peek(app + MACHINES_CAP)) return m->pages_state = PAGES_NO_ROOM;
    if (nbr_register(app, m->pages, m->pages_len, &rd) || !rd || (rd & 3u))
        return m->pages_state = PAGES_REFUSED;
    poke(rd + READER_POOL_LEN, peek(m->reader + READER_POOL_LEN));
    poke(rd + READER_POOL, peek(m->reader + READER_POOL));
    m->pages_reader = rd;
    return m->pages_state = PAGES_OK;
}

/* ---- OUTPUT's info panel, edited in place --------------------------------
 * "W x H   binH x binV   scaleW x scaleH %" (sl_lab_page.py PANEL_*): integers
 * its number fields show with %d.  Like the date / time page: Right / OK on the
 * panel row start editing, Left / Right pick a field (arrows SL_O_A0..A3), Up /
 * Down step it -- held, faster -- the front dial in big steps, OK / MENU end.
 * The page only writes a key code to SL_O_Key; every value is snapped here, the
 * one place the rules live (IMX410_FULL_DESIGN.md 3.1): width a multiple of 16
 * (nothing masks it: a bad width silently shears rows), height even, both no
 * larger than the sensor over the binning; a Ratio other than Free holds W:H;
 * changing the binning sets the largest output it allows.  The last two
 * numbers are the RWZM scale (output / (readout / binning), "0.32", text
 * variables); the readout is the whole sensor until the mode exists. */
enum { V_BTXT = 48, V_W = 0, V_H = 1, V_IN = 2, V_BH = 3, V_BV = 4, V_SW = 5, V_SCALE = 7, V_SH = 8, V_BIN = 9,
       V_MODE = 16, V_KEY = 18, V_ARROW = 19, V_RATE = 23, V_RFPS = 26, V_DIAG = 27, V_DTEXT = 35,
       V_CTEXT = 41, V_DCROP = 42, V_DCTEXT = 46 };
enum { K_LEFT = 1, K_RIGHT = 2, K_UP = 3, K_DOWN = 4, K_EDIT = 5, K_DONE = 6, K_DIAL_UP = 7, K_DIAL_DOWN = 8 };
#define K_CROP 10u          /* the Crop row's editor writes 10 + the same codes (sl_lab_page CROP_KEY_BASE) */
#define CROP_KEEP 64u       /* the least readout a crop leaves */
#define SENSOR_W   6064u
#define SENSOR_H   4040u
#define W_STEP     16u
#define H_STEP     2u
#define HOLD_MS    350u         /* a repeat sooner than this is the key held */

static uint32_t value_of(struct sl_menu *m, uint32_t index) {
    uint32_t v = 0;
#if defined(SL_MENU_HOST_TEST)
    if (!sl_menu_value(m, index, &v)) v = 0;
#else
    /* sl_menu.c's variable(): units are separate blobs here, no calls between them */
    uintptr_t reg = peek(m->app + 0x888u), d = 0;
    if (!reg || (reg & 3u)) return 0;
    if (((fn3)0xC05DB419u)(reg + 0x60u, (uintptr_t)m->names[index], (uintptr_t)&d) || !d || (d & 3u)) return 0;
    if (peek(d) != 0u) return 0;                       /* an integer */
    v = peek(d + DESC_VALUE);
#endif
    return v;
}

/* a / b without a divide instruction (Cortex-A9; the blob has no libgcc) */
static uint32_t udiv(uint32_t a, uint32_t b) {
    uint32_t q = 0, r = 0;
    if (!b) return 0;
    for (int32_t i = 31; i >= 0; --i) {
        r = (r << 1) | ((a >> i) & 1u);
        if (r >= b) { r -= b; q |= 1u << i; }
    }
    return q;
}

/* OUTPUT's readout: the chosen mode's raster (the user 2026-10-03: "算出來的最大
 * 解析度要改動第三頁"), the whole sensor while no mode is listed */
static uint32_t raster_w(const struct sl_menu *m) { return m->ro_w ? m->ro_w : SENSOR_W; }
static uint32_t raster_h(const struct sl_menu *m) { return m->ro_h ? m->ro_h : SENSOR_H; }
/* the readout after the Crop row's centred cut (the user 2026-10-03: "設定寬柴切
 * 多少px 高柴切多少px 然後解析度要跟著配合") */
static uint32_t readout_w(const struct sl_menu *m) { return raster_w(m) - m->crop_w; }
static uint32_t readout_h(const struct sl_menu *m) { return raster_h(m) - m->crop_h; }
/* the sensor area the readout covers: AUTO's shape (the user 2026-10-03: M12, a
 * 2016 x 672 raster reduced 3 x 6, covers 3:2 -- AUTO squeezes its width) */
/* the uncut raster's: a crop keeps the shape (the user: "crop必須受到ratio的約束") */
static uint32_t auto_w(const struct sl_menu *m) { return raster_w(m) * (m->ro_sx ? m->ro_sx : 1u); }
static uint32_t auto_h(const struct sl_menu *m) { return raster_h(m) * (m->ro_sy ? m->ro_sy : 1u); }

/* the Ratio row (sl_lists SCALE_ROWS); a W:H ratio and an anamorphic squeeze are
 * one choice (the user 2026-10-03: "幾:幾 和 1.33x ... 只能擇一").  The W:H
 * rows are the widescreen ones (3:2 / 16:9 / 17:9 went); each holds exactly by
 * the common-multiple step where one is usable (exact_step) */
#define R_AUTO   0u      /* the readout's shape, both sides scaled alike */
#define R_RAW    1u      /* the largest W x H the binning gives, locked */
#define R_SQZ0   8u      /* 1.25x .. 2.0x: AUTO with the width stretched by it */
#define R_FREE   16u
#define R_ROWS   17u

/* The output pixels' width : height as num : den, or num 0 (Free / RAW) -- the
 * final pixels', whatever the binning (the user 2026-10-03: "比例是最終畫素的
 * 比例"; r45 scaled AUTO / the squeezes by it, so a binning change moved them).
 * AUTO = the shape of the sensor area the readout covers (raster x reduction:
 * 3:2 for M12's 2016 x 672 at 3 x 6), a squeeze = AUTO x it, in ten-thousandths.
 * No table: the blob has no .rodata (-fropi leaves it absolute). */
static void ratio_of(const struct sl_menu *m, uint32_t row, uint32_t *num, uint32_t *den) {
#if defined(SL_CALC_ONLY)
    if (row==R_RAW && m->output_policy==1u && m->lock_num && m->lock_den) {
        *num=m->lock_num;*den=m->lock_den;return;
    }
    if (row == R_AUTO || row == R_RAW) {
        uint32_t sx = row == R_AUTO && m->ro_sx ? m->ro_sx : 1u;
        uint32_t sy = row == R_AUTO && m->ro_sy ? m->ro_sy : 1u;
        uint32_t lens = m->lens_on ? (m->lens_factor ? m->lens_factor : 133u) : 100u;
        *num = udiv(readout_w(m) * sx * lens * 100u, readout_h(m) * sy);
        *den = 10000u;
        return;
    }
#endif
    uint32_t x = 0;                                      /* the squeeze, hundredths */
    *num = 0; *den = 1;
    switch (row) {
    case 2: *num = 37; *den = 20; break;                 /* 1.85 : 1 */
    case 3: *num = 2; *den = 1; break;
    case 4: *num = 47; *den = 20; break;                 /* 2.35 : 1 */
    case 5: *num = 239; *den = 100; break;               /* 2.39 : 1 */
    case 6: *num = 12; *den = 5; break;                  /* 2.40 : 1 */
    case 7: *num = 69; *den = 25; break;                 /* 2.76 : 1 */
    case R_AUTO: x = 100u; break;
    case R_SQZ0: x = 125u; break;
    case R_SQZ0 + 1u: x = 133u; break;
    case R_SQZ0 + 2u: x = 150u; break;
    case R_SQZ0 + 3u: x = 155u; break;
    case R_SQZ0 + 4u: x = 160u; break;
    case R_SQZ0 + 5u: x = 165u; break;
    case R_SQZ0 + 6u: x = 180u; break;
    case R_SQZ0 + 7u: x = 200u; break;
    default: break;
    }
    if (x) {
        *num = udiv(auto_w(m) * x * 100u, auto_h(m));
        *den = 10000u;
    }
}

/* The exact W:H sizes are multiples of one step (the user: "最小公倍數"):
 * W = num t and H = den t, with W x16 and H even, so t is a multiple of
 * 16 / gcd(num, 16) and of 2 / gcd(den, 2) -- both powers of two, so their lcm
 * is the larger (no divide).  Returns the width step, or 0 when it is coarser
 * than EXACT_MAX_W (2.39:1 is 3824 x 1600: one size on the sensor; AUTO and the
 * squeezes likewise) -- those keep the nearest legal shape instead. */
#define EXACT_MAX_W 1200u       /* 2.76:1 (69:25) steps 1104 x 400: exact, 5 sizes */
static uint32_t exact_step(uint32_t num, uint32_t den, uint32_t *h_step) {
    uint32_t t = 16u, v = num, ws;
    if (!num || den >= 10000u) return 0;                 /* Free / RAW; AUTO and the squeezes */
    while (t > 1u && !(v & 1u)) { t >>= 1; v >>= 1; }    /* 16 / gcd(num, 16) */
    if ((den & 1u) && t < 2u) t = 2u;                    /* height even */
    ws = num * t;
    if (ws > EXACT_MAX_W) return 0;
    *h_step = den * t;
    return ws;
}

/* step is a power of two (16, 2): no division -- a Cortex-A9 has no udiv and the
 * blob no libgcc (build_sl_menu: __aeabi_uidiv undefined) */
static uint32_t clamp_step(int32_t v, uint32_t step, uint32_t max) {
    uint32_t top = max & ~(step - 1u);
    if (top < step) return 0;
    if (v < (int32_t)step) return step;
    if ((uint32_t)v > top) return top;
    return (uint32_t)v & ~(step - 1u);
}

/* the readout over the binning (1 / 3 / 5), less the record matrix's margins
 * (imx410_full MARGIN_W / MARGIN_H: rec = visible + 16 x + 10, the stock
 * custom-frame rule) -- the largest visible output with RWZM at unity; snap
 * makes the width x16, the height even */
#define MARGIN_W 16u
#define MARGIN_H 10u
/* No record-size envelope (the user 2026-10-04: "如果上限是怕緩存爆掉 那應該是把
 *緩存加大而不是限制他").  The r67 / r69 freezes were the preview, not the frame
 * buffers: the borrowed p83 previewed at the record RWZM, so a 6064-wide readout
 * overflowed its 2024-wide preview buffer.  Our own declared row previews a
 * full-width readout through CRCT /3 like stock UHD (declare_post), and the
 * frame buffers follow the geometry (OG4K_SIZING: class 10, RAW + 0x15400).
 * What is left is the card's write rate -- the RAW area fills and the take stops.
 * The envelope stays as a seam (rec_cap_w / _h) for tests and for a later cap. */
#define REC_MAX_W 0xFFFFu
#define REC_MAX_H 0xFFFFu
/* the binned readout, scaled down alike on both sides when it is larger than
 * the envelope -- never more on one (anisotropic RWZM squeezes live view) */
static void envelope(const struct sl_menu *m, uint32_t bh, uint32_t bv, uint32_t *w, uint32_t *h) {
    uint32_t cw = m->rec_cap_w ? m->rec_cap_w : REC_MAX_W, ch = m->rec_cap_h ? m->rec_cap_h : REC_MAX_H;
    *w = udiv(readout_w(m), bh);
    *h = udiv(readout_h(m), bv);
    if (*w > cw && *w * ch >= *h * cw) { *h = udiv(*h * cw, *w); *w = cw; }
    else if (*h > ch) { *w = udiv(*w * ch, *h); *h = ch; }
}
static uint32_t max_w(const struct sl_menu *m, uint32_t bin) {
    uint32_t w, h;
    envelope(m, bin, m->bin_v, &w, &h);
    w &= ~(W_STEP - 1u);
    return w > MARGIN_W ? w - MARGIN_W : 0;
}
static uint32_t max_h(const struct sl_menu *m, uint32_t bin) {
    uint32_t w, h;
    envelope(m, m->bin_h, bin, &w, &h);
    h &= ~1u;
    return h > MARGIN_H ? h - MARGIN_H : 0;
}

static void snap(struct sl_menu *m) {
#if defined(SL_CALC_ONLY)
    if (m->bin_h != 1u && m->bin_h != 3u) m->bin_h = 1u;
#else
    if (m->bin_h != 1u && m->bin_h != 3u && m->bin_h != 5u) m->bin_h = 1u;
#endif
    if (m->bin_v != 1u && m->bin_v != 3u) m->bin_v = 1u;
    /* A crop must leave room for at least one aligned visible pixel block
     * AND the record margins after binning. 64 readout pixels are too few
     * for horizontal /3: only 16 aligned pixels remain, all used by margins. */
    uint32_t keepw = (W_STEP + MARGIN_W) * m->bin_h;
    uint32_t keeph = (H_STEP + MARGIN_H) * m->bin_v;
    if (keepw < CROP_KEEP) keepw = CROP_KEEP;
    if (keeph < CROP_KEEP) keeph = CROP_KEEP;
    uint32_t cw = raster_w(m) > keepw ? (raster_w(m) - keepw) & ~(W_STEP - 1u) : 0;
    uint32_t ch = raster_h(m) > keeph ? (raster_h(m) - keeph) & ~(H_STEP - 1u) : 0;
    if (m->crop_w > cw) m->crop_w = cw;
    if (m->crop_h > ch) m->crop_h = ch;
    m->out_w = clamp_step((int32_t)m->out_w, W_STEP, max_w(m, m->bin_h));
    m->out_h = clamp_step((int32_t)m->out_h, H_STEP, max_h(m, m->bin_v));
}

/* the legal size nearest to the exact one, rounded once: height = width * den /
 * num to the nearest even, width = height * num / den to the nearest x16 */
static uint32_t h_for(uint32_t w, uint32_t num, uint32_t den) {
    return udiv(w * den + num, 2u * num) * 2u;
}
static uint32_t w_for(uint32_t h, uint32_t num, uint32_t den) {
    return udiv(h * num + den * (W_STEP / 2u), den * W_STEP) * W_STEP;
}

/* Hold the ratio, `from_w`: the width leads (else the height); whichever side
 * would pass its limit then leads instead.  Rounded to the nearest, then
 * snapped (width x16, height even): the nearest legal shape, not an exact one. */
static void fit(struct sl_menu *m, uint32_t from_w) {
    uint32_t num, den;
#if defined(SL_CALC_ONLY)
    uint32_t height_led = !from_w;
#endif
    snap(m);
#if !defined(SL_CALC_ONLY)
    if (m->ratio == R_RAW) {                 /* the whole binned readout, whatever was stepped */
        m->out_w = max_w(m, m->bin_h);
        m->out_h = max_h(m, m->bin_v);
        snap(m);
        return;
    }
#endif
    ratio_of(m, m->ratio, &num, &den);
    if (!num) return;
    {   /* an exact ratio: the multiple of the step nearest the leading side */
        uint32_t hs = 0, ws = exact_step(num, den, &hs);
        if (ws) {
            uint32_t k = from_w ? udiv(m->out_w + ws / 2u, ws) : udiv(m->out_h + hs / 2u, hs);
            uint32_t kw = udiv(max_w(m, m->bin_h), ws), kh = udiv(max_h(m, m->bin_v), hs);
            uint32_t top = kw < kh ? kw : kh;
            if (top) {
                if (k > top) k = top;
                if (k < 1u) k = 1u;
                m->out_w = k * ws;
                m->out_h = k * hs;
                return;
            }
            /* No exact common multiple fits this mode/crop/binning. Use
             * the nearest aligned shape, never force an oversized first step. */
        }
    }
    uint32_t limited = 0;
    if (from_w) {
        m->out_h = h_for(m->out_w, num, den);
        if (m->out_h < H_STEP) from_w = 0, limited = 1, m->out_h = H_STEP;
        if (m->out_h > max_h(m, m->bin_v)) from_w = 0, limited = 1, m->out_h = max_h(m, m->bin_v);
    }
    if (!from_w) {
        m->out_w = w_for(m->out_h, num, den);
        if (m->out_w < W_STEP) m->out_w = W_STEP, limited = 1;
        if (m->out_w > max_w(m, m->bin_h)) m->out_w = max_w(m, m->bin_h), limited = 1;
    }
    snap(m);
    /* at a limit the width (the coarser x16 side) decides: the height follows it
     * back, so the shape is the nearest one, not the width's rounding plus the
     * height's.  Not when the user steps the height: that step must stay. */
    if (limited) {
#if defined(SL_CALC_ONLY)
        uint32_t mh = max_h(m,m->bin_v);
        if (m->out_w * den > mh * num) {
            m->out_w = udiv(mh*num,den) & ~(W_STEP-1u);
            if (m->out_w<W_STEP) m->out_w=W_STEP;
        }
#endif
        m->out_h = h_for(m->out_w, num, den);
        snap(m);
    }
#if defined(SL_CALC_ONLY)
    /* Very wide free crops make a two-pixel height step coarser than width's
     * x16 step. Canonicalize the trailing width after a height-led clamp so
     * refreshing the same setting cannot shrink it a second time. */
    if(height_led){m->out_w=w_for(m->out_h,num,den);snap(m);}
#endif
}

/* RWZM as the scale it applies: output over (readout / binning), "0.32" -- below
 * 1 shrinks (the user: a "503 %" read as a 5x enlargement).  Rounded to two
 * decimals; the readout is the whole sensor until the mode exists. */
static void scale_text(char *t, uint32_t sensor, uint32_t bin, uint32_t out) {
    uint32_t c = udiv(out * bin * 100u + sensor / 2u, sensor);      /* hundredths */
    uint32_t whole = udiv(c, 100u), frac = c - whole * 100u, tens = udiv(frac, 10u);
    t[0] = (char)('0' + (whole > 9u ? 9u : whole));
    t[1] = '.';
    t[2] = (char)('0' + tens);
    t[3] = (char)('0' + frac - tens * 10u);
    t[4] = 0;
}

/* The recorded data rate, matrix W x H x bits x fps / 8, in MB/s (10^6): "29.97p 1101
 * MB/s".  Bits: eRawBitType (FUN_c02da870's table: 0 12, 1 14, 3 10, 4 8); fps:
 * the Data rate row (SL_O_RFps, sl_lists RATE_SEL_ROWS: 0 = the frame-rate
 * setting, k = rate_index k - 1 -- the user: every rate's result), hundredths.
 * Pixels only, no container. */
static uint32_t rate_bits(uint32_t raw) {
    return raw == 1u ? 14u : raw == 3u ? 10u : raw == 4u ? 8u : 12u;
}
static uint32_t rate_fps100(uint32_t ridx) {
    switch (ridx) {
    case 0: return 2398u; case 1: return 2400u; case 2: return 2500u; case 3: return 2997u;
    case 4: return 4800u; case 5: return 5000u; case 6: return 5994u; case 7: return 10000u;
    case 8: return 11988u; case 9: return 23976u; case 10: return 27972u;
    default: return 0;
    }
}
/* is the chosen mode a 14-bit one (metadata +0x3C == 1)? */
static uint32_t mode_depth14(struct sl_menu *m) {
    uintptr_t desc = peek(IMAGER), meta = desc ? peek(desc + 8u) : 0;
    uint32_t count = desc ? peek(desc + 12u) : 0;
    if (!meta || !m->modes_rows || m->mode_sel >= m->modes_rows) return 0;
    for (uint32_t i = 0; i < count && i < SL_MODES_MAX; ++i) {
        uintptr_t row = meta + META_STRIDE * i;
        if (peek(row) == m->mode_ids[m->mode_sel]) return peek(row + 0x3Cu) == 1u;
    }
    return 0;
}

static void rate_format(struct sl_menu *m, char *t, uint32_t fps, uint32_t bits) {
    uint32_t n = 0, mb, d, started = 0, whole, frac;
    whole = udiv(fps, 100u); frac = fps - whole * 100u;
    for (d = 100u; d; d = udiv(d, 10u)) {                /* "29.97p", "24p", "239.76p" */
        uint32_t q = udiv(whole, d);
        if (q || started || d == 1u) { t[n++] = (char)('0' + q); started = 1; }
        whole -= q * d;
    }
    if (frac) {
        t[n++] = '.';
        t[n++] = (char)('0' + udiv(frac, 10u));
        t[n++] = (char)('0' + frac - udiv(frac, 10u) * 10u);
    }
    t[n++] = 'p'; t[n++] = ' ';
    started = 0;
    /* The calculator uses the actual record matrix, including border pixels
     * and a full matrix retained behind a centred crop. Keep the legacy
     * recording UI's estimate unchanged. */
#if defined(SL_CALC_ONLY)
    uint32_t bitpixels = m->canvas_valid ? m->canvas[0] * m->canvas[1] * bits : 0;
    uint32_t q = udiv(bitpixels, 80000u), rem = bitpixels - q * 80000u;
    /* Exact rounding at the displayed hundredths FPS, without 64-bit divide.
     * rem*fps <= 79999*27972, and q*fps also fits uint32 for every mode. */
    mb = udiv(q * fps + udiv(rem * fps, 80000u) + 5000u, 10000u);
#else
    /* kB per frame (<= 49k) x fps x 100 (<= 23976): below 2^32 */
    mb = udiv(udiv(udiv(m->out_w * m->out_h, 1000u) * bits, 8u) * fps
              + 50000u, 100000u);
#endif
    for (d = 10000u; d; d = udiv(d, 10u)) {              /* no leading zeros, up to 99999 */
        uint32_t q = udiv(mb, d);
        if (q > 9u) q = 9u;
        if (q || started || d == 1u) { t[n++] = (char)('0' + q); started = 1; }
        mb -= q * d;
    }
    t[n++] = ' '; t[n++] = 'M'; t[n++] = 'B'; t[n++] = '/'; t[n++] = 's'; t[n] = 0;
}

static void rate_post(struct sl_menu *m) {
    uint32_t sel=value_of(m,V_RFPS),fps,bits;
#if defined(SL_CALC_ONLY)
    fps=rate_fps100(sel);bits=mode_depth14(m)?14u:12u;
#else
    uintptr_t mgr=settings();if(!mgr)return;
    fps = rate_fps100(sel ? sel - 1u : rate_index(m, get_rate(mgr)));
    bits=mode_depth14(m)?14u:rate_bits(get_bit(mgr));
#endif
    rate_format(m,m->rate_text,fps,bits);
    post_str(m->names[V_RATE],m->rate_text);
}

#if defined(SL_CALC_ONLY)
static uint32_t rate_changed(uintptr_t desc, uintptr_t unused) {
    struct sl_menu *m=the_menu();(void)desc;(void)unused;
    /* Browsing an estimate neither changes FPS nor applies a new recipe. */
    if(m && m->result==SL_MENU_INSTALLED)rate_post(m);
    return 0;
}
#endif

/* ---- the MODE tab's diagram (sl_lab_page.diagram) --------------------------
 * White: the sensor, 6064 x 4040 drawn DIAG_W x DIAG_H at DIAG_X, DIAG_Y (tab
 * pixels).  Green: the area the chosen mode uses, its raster x reduction (+0x4C
 * / +0x50) on the sensor, centred (the readout's offset is not decoded).  Red:
 * the mode's largest output -- its raster, width x16 and height even -- at the
 * sensor's pixel scale, centred (the user 2026-10-03: "紅匡標示最大輸出"), so a
 * reduced mode's red sits inside its green.  Labels say which is which ("Area",
 * "Max out"); then the mode's own rate (72 MHz / (hmax (vmax - 1) + tail)) and
 * rolling shutter (hmax x raster height / 72 MHz) -- SENSOR_MODE_METADATA.md
 * section 3. */
#if defined(SL_CALC_ONLY)
#define DIAG_X 444u
#define DIAG_Y 145u
#define DIAG_W 510u
#define DIAG_H 340u
#else
#define DIAG_X 40u
#define DIAG_Y 180u
#define DIAG_W 420u
#define DIAG_H 280u
#endif
/* the rects are the true areas: drawRect draws its border inside, over the
 * sensor's filled block (the user 2026-10-03: "填滿的話，線就往內畫") */

static uint32_t diag_px(uint32_t v) { return udiv(v * DIAG_W + SENSOR_W / 2u, SENSOR_W); }

/* "3032x2012" after the `prefix` characters already in t; returns the length */
static uint32_t wxh(volatile char *t, uint32_t prefix, uint32_t w, uint32_t h) {
    uint32_t n = prefix + dec5(t + prefix, w);
    t[n++] = 'x';
    return n + dec5(t + n, h);
}

/* " (16:9)": the shape's common name within 1 %, else "(1.92:1)" (the user
 * 2026-10-03: the green and red labels name their ratio).  Appended at t[n];
 * returns the new length.  No table: the blob has no .rodata. */
static uint32_t ratio_label(volatile char *t, uint32_t n, uint32_t w, uint32_t h) {
    uint32_t a = h ? udiv(w * 1000u + h / 2u, h) : 0, k, v, hit = 0;
    t[n++] = ' '; t[n++] = '(';
    for (k = 0; k < 8u && !hit; ++k) {
        v = k == 0 ? 1000u : k == 1 ? 1333u : k == 2 ? 1500u : k == 3 ? 1778u :
            k == 4 ? 1850u : k == 5 ? 2000u : k == 6 ? 2390u : 3000u;
        if ((a > v ? a - v : v - a) * 100u > v) continue;
        hit = 1u;
        switch (k) {
        case 0: t[n++] = '1'; t[n++] = ':'; t[n++] = '1'; break;
        case 1: t[n++] = '4'; t[n++] = ':'; t[n++] = '3'; break;
        case 2: t[n++] = '3'; t[n++] = ':'; t[n++] = '2'; break;
        case 3: t[n++] = '1'; t[n++] = '6'; t[n++] = ':'; t[n++] = '9'; break;
        case 4: t[n++] = '1'; t[n++] = '.'; t[n++] = '8'; t[n++] = '5'; t[n++] = ':'; t[n++] = '1'; break;
        case 5: t[n++] = '2'; t[n++] = ':'; t[n++] = '1'; break;
        case 6: t[n++] = '2'; t[n++] = '.'; t[n++] = '3'; t[n++] = '9'; t[n++] = ':'; t[n++] = '1'; break;
        default: t[n++] = '3'; t[n++] = ':'; t[n++] = '1'; break;
        }
    }
    if (!hit) {                                         /* "1.92:1" */
        uint32_t c = udiv(a + 5u, 10u);                  /* hundredths */
        t[n++] = (char)('0' + udiv(c, 100u) % 10u);
        t[n++] = '.';
        t[n++] = (char)('0' + udiv(c, 10u) % 10u);
        t[n++] = (char)('0' + c % 10u);
        t[n++] = ':'; t[n++] = '1';
    }
    t[n++] = ')';
    t[n] = 0;
    return n;
}

/* sensor pixels in mm, one decimal ("35.9"): 6064 px = 35.9 mm (5.92 um) */
static uint32_t mm_text(volatile char *t, uint32_t n, uint32_t px) {
    uint32_t v = udiv(px * 359u + SENSOR_W / 2u, SENSOR_W), whole = udiv(v, 10u);
    n += dec5(t + n, whole);
    t[n++] = '.';
    t[n++] = (char)('0' + v - whole * 10u);
    t[n] = 0;
    return n;
}

/* "29.97 fps" / "RS 8.31 ms": v in hundredths */
static void hundredths(volatile char *t, uint32_t v) {
    uint32_t n = dec5(t, udiv(v, 100u)), f = v - udiv(v, 100u) * 100u;
    t[n++] = '.';
    t[n++] = (char)('0' + udiv(f, 10u));
    t[n++] = (char)('0' + f - udiv(f, 10u) * 10u);
    t[n] = 0;
}

static void diagram_post(struct sl_menu *m) {
    uintptr_t desc = peek(IMAGER), meta = desc ? peek(desc + 8u) : 0, tmg = desc ? peek(desc) : 0;
    uint32_t count = desc ? peek(desc + 12u) : 0, g[4], r[4], c[4], i, n;
    volatile char *t;
    for (i = 0; i < 4u; ++i) g[i] = r[i] = c[i] = 0;
    for (n = 0; n < 4u; ++n) { t = m->diag_text[n]; t[0] = 0; }
    t = m->diag_crop; t[0] = ' '; t[1] = 0;
    if (m->modes_rows && meta && tmg && m->mode_sel < m->modes_rows) {
        uint32_t id = m->mode_ids[m->mode_sel];
        for (i = 0; i < count && i < SL_MODES_MAX; ++i) {
            uintptr_t row = meta + META_STRIDE * i;
            uint32_t w, h, cw, ch, w1, w2, hmax, cyc, q, f;
            if (peek(row) != id) continue;
            w = peek(row + 4u) & 0xFFFFu; h = peek(row + 8u) & 0xFFFFu;
            cw = w * peek(row + 0x4Cu); ch = h * peek(row + 0x50u);
            if (cw > SENSOR_W) cw = SENSOR_W;
            if (ch > SENSOR_H) ch = SENSOR_H;
            if (m->crop_w || m->crop_h) {            /* yellow: what the Crop row leaves */
                uint32_t kw = readout_w(m) * peek(row + 0x4Cu), kh = readout_h(m) * peek(row + 0x50u);
                if (kw > cw) kw = cw;
                if (kh > ch) kh = ch;
                c[2] = diag_px(kw); c[3] = diag_px(kh);
                c[0] = DIAG_X + udiv(DIAG_W - c[2], 2u); c[1] = DIAG_Y + udiv(DIAG_H - c[3], 2u);
                t = m->diag_crop;
                t[0] = 'C'; t[1] = 'r'; t[2] = 'o'; t[3] = 'p'; t[4] = ' ';
                n = mm_text(t, 5u, kw);
                t[n++] = 'x';
                n = mm_text(t, n, kh);
                t[n++] = 'm'; t[n++] = 'm';
                ratio_label(t, n, kw, kh);
            }
            g[2] = diag_px(cw); g[3] = diag_px(ch);
            g[0] = DIAG_X + udiv(DIAG_W - g[2], 2u); g[1] = DIAG_Y + udiv(DIAG_H - (g[3] > DIAG_H ? DIAG_H : g[3]), 2u);
            t = m->diag_text[0];                     /* "Sensor 35.9x20.2mm (16:9)": the area, in mm */
            t[0] = 'S'; t[1] = 'e'; t[2] = 'n'; t[3] = 's'; t[4] = 'o'; t[5] = 'r'; t[6] = ' ';
            n = mm_text(t, 7u, cw);
            t[n++] = 'x';
            n = mm_text(t, n, ch);
            t[n++] = 'm'; t[n++] = 'm';
            ratio_label(t, n, cw, ch);
            r[2] = diag_px(w & ~15u); r[3] = diag_px(h & ~1u);   /* the largest output: x16, even */
            r[0] = DIAG_X + udiv(DIAG_W - r[2], 2u); r[1] = DIAG_Y + udiv(DIAG_H - r[3], 2u);
            t = m->diag_text[1];                     /* "Native 3024x1708 (16:9)": the largest output */
            t[0] = 'N'; t[1] = 'a'; t[2] = 't'; t[3] = 'i'; t[4] = 'v'; t[5] = 'e'; t[6] = ' ';
            ratio_label(t, wxh(t, 7u, w & ~15u, h & ~1u), w & ~15u, h & ~1u);
            w1 = timing_w1(m, tmg, i); w2 = peek(tmg + TMG_STRIDE * i + 8u);
            hmax = w1 & 0xFFFFu;
            cyc = hmax * ((w2 & 0xFFFFu) - 1u) + (w1 >> 16);
            if (cyc) {
                q = udiv(72000000u, cyc);
                f = udiv((72000000u - q * cyc) * 100u, cyc);
                hundredths(m->diag_text[2], q * 100u + f);
                t = m->diag_text[2]; n = 0; while (t[n]) ++n;
                t[n++] = ' '; t[n++] = 'f'; t[n++] = 'p'; t[n++] = 's'; t[n] = 0;
            }
            t = m->diag_text[3];
            t[0] = 'R'; t[1] = 'S'; t[2] = ' ';
            hundredths(t + 3, udiv(hmax * h + 360u, 720u));      /* ms x 100 */
            n = 0; while (t[n]) ++n;
            t[n++] = ' '; t[n++] = 'm'; t[n++] = 's'; t[n] = 0;
            break;
        }
    }
#if defined(SL_CALC_ONLY)
    uint32_t final[4]={0,0,0,0};
    if (m->modes_rows && m->mode_sel < m->modes_rows) {
        r[2]=diag_px(m->ro_w);r[3]=diag_px(m->ro_h);
        c[2]=diag_px(readout_w(m));c[3]=diag_px(readout_h(m));
        final[2]=diag_px(m->out_w);final[3]=diag_px(m->out_h);
        for (i=0;i<3u;i++) {
            uint32_t *a=i==0?r:i==1?c:final;
            a[0]=DIAG_X+udiv(DIAG_W-a[2],2u);a[1]=DIAG_Y+udiv(DIAG_H-a[3],2u);
        }
        t=m->diag_text[0];t[0]='M';t[1]='o';t[2]='d';t[3]='e';t[4]=' ';
        t[5]='C';t[6]='o';t[7]='r';t[8]='p';t[9]=' ';wxh(t,10u,auto_w(m),auto_h(m));
        t=m->diag_crop;t[0]='O';t[1]='u';t[2]='t';t[3]='p';t[4]='u';t[5]='t';t[6]=' ';
        t[7]='C';t[8]='o';t[9]='r';t[10]='p';t[11]=' ';wxh(t,12u,readout_w(m),readout_h(m));
        t=m->final_text;t[0]='O';t[1]='u';t[2]='t';t[3]=' ';wxh(t,4u,m->out_w,m->out_h);
    } else m->final_text[0]=0;
    for (i=0;i<4u;i++) post_int(m->names[61+i],final[i]);
    post_str(m->names[60],m->final_text);
    /* Eight dotted corner paths, in the same sensor-pixel coordinate system. */
    for (uint32_t line=0;line<8u;line++) {
        uint32_t corner=line&3u, *a=line<4u?g:c, *b=line<4u?r:final;
        for (uint32_t dot=0;dot<8u;dot++) for(uint32_t axis=0;axis<2u;axis++) {
            uint32_t far=axis?(corner>=2u):(corner==1u||corner==2u);
            uint32_t start=a[axis]+(far?a[axis+2u]:0u),end=b[axis]+(far?b[axis+2u]:0u);
            post_int(m->names[65+(line*8u+dot)*2u+axis],udiv(start*(15u-dot*2u)+end*(dot*2u+1u),16u));
        }
    }
#endif
    for (i = 0; i < 4u; ++i) {
        post_int(m->names[V_DIAG + i], g[i]);
        post_int(m->names[V_DIAG + 4u + i], r[i]);
    }
    for (i = 0; i < 4u; ++i) post_str(m->names[V_DTEXT + i], m->diag_text[i]);
    for (i = 0; i < 4u; ++i) post_int(m->names[V_DCROP + i], c[i]);
    post_str(m->names[V_DCTEXT], m->diag_crop);
}

/* ---- FILTER (sl_lab_page rows_spec 92, sl_lists F_*_ROWS) -------------------
 * The MODE catalogue covers any supported rate.  FILTER FPS alone limits its
 * rate; row 0 = Any.  Bit depth: the
 * mode's (+0x3C: 1 = 14-bit); Frame rate N+: the fastest the mode reads,
 * 72 MHz / ((raster H + vblank) x hmax) -- the scan's own cycle test -- at least
 * N; Width N+: its largest output (the raster's width) at least N; Proportion:
 * the option nearest its area's shape (raster x reduction); Crop: its area's
 * width, Full frame >= 5600, Super35 4100-4300, APS-C 3900-4000. */
#define V_FBIT 12u
#define V_FFPS 13u
#define V_FWIDTH 14u
#define V_FPROP 15u
#define V_FCROP 39u

static uint32_t filter_now(struct sl_menu *m) {
    return (value_of(m, V_FBIT) & 15u) | (value_of(m, V_FFPS) & 15u) << 4 | (value_of(m, V_FWIDTH) & 15u) << 8 |
           (value_of(m, V_FPROP) & 15u) << 12 | (value_of(m, V_FCROP) & 15u) << 16;
}

static uint32_t filter_fps100(uint32_t row) {      /* sl_lists F_FPS_ROWS: "23.98p+" .. */
    switch (row) {
    case 1: return 2397u; case 2: return 2400u; case 3: return 2500u; case 4: return 2997u;
    case 5: return 4800u; case 6: return 5000u; case 7: return 5994u; case 8: return 10000u;
    case 9: return 11988u; case 10: return 23976u; case 11: return 27972u;
    default: return 0;
    }
}

static uint32_t filter_width(uint32_t row) {       /* F_WIDTH_ROWS: "1920+" .. */
    switch (row) {
#if defined(SL_CALC_ONLY)
    case 1:return 2850u;case 2:return 3800u;case 3:return 5700u;
#else
    case 1: return 1920u; case 2: return 2048u; case 3: return 3840u; case 4: return 4096u; case 5: return 6064u;
#endif
    default: return 0;
    }
}

#if !defined(SL_CALC_ONLY)
static uint32_t prop_nearest(uint32_t a1000) {     /* F_PROP_ROWS 1..5: 3:2 16:9 1.85 2:1 2.39 */
    uint32_t best = 1u, bd = 0xFFFFFFFFu, k, t, d;
    for (k = 1u; k <= 5u; ++k) {
        t = k == 1u ? 1500u : k == 2u ? 1778u : k == 3u ? 1850u : k == 4u ? 2000u : 2390u;
        d = a1000 > t ? a1000 - t : t - a1000;
        if (d < bd) { bd = d; best = k; }
    }
    return best;
}
#endif

static uint32_t filter_modes(struct sl_menu *m, uint32_t n) {
    uintptr_t desc = peek(IMAGER), meta = desc ? peek(desc + 8u) : 0, tmg = desc ? peek(desc) : 0;
    uint32_t count = desc ? peek(desc + 12u) : 0, fb, ff, fw, fp, fc, out = 0;
#if defined(SL_CALC_ONLY)
    uint32_t order_key[SL_MODES_MAX];
#endif
    if (!meta || !tmg) return n;
    fb = value_of(m, V_FBIT); ff = value_of(m, V_FFPS); fw = value_of(m, V_FWIDTH);
    fp = value_of(m, V_FPROP); fc = value_of(m, V_FCROP);
    if (!(fb | ff | fw | fp | fc)) return n;
    for (uint32_t r = 0; r < n; ++r) {
        uint32_t id = m->mode_ids[r], keep = 0;
        for (uint32_t i = 0; i < count && i < SL_MODES_MAX; ++i) {
            uintptr_t row = meta + META_STRIDE * i;
            uint32_t w, h, aw, ah, cyc, q, f;
            if (peek(row) != id) continue;
            w = peek(row + 4u) & 0xFFFFu; h = peek(row + 8u) & 0xFFFFu;
            aw = w * peek(row + 0x4Cu); ah = h * peek(row + 0x50u);
            keep = 1u;
#if !defined(SL_CALC_ONLY)
            if (fb == 1u && peek(row + 0x3Cu) == 1u) keep = 0;          /* 12-bit wanted */
            if (fb == 2u && peek(row + 0x3Cu) != 1u) keep = 0;          /* 14-bit wanted */
#endif
            if (ff) {
                cyc = (h + peek(row + 0x5Cu)) * (timing_w1(m, tmg, i) & 0xFFFFu);
                q = cyc ? udiv(72000000u, cyc) : 0;
                f = cyc ? udiv((72000000u - q * cyc) * 100u, cyc) : 0;
                if (q * 100u + f < filter_fps100(ff)) keep = 0;
            }
            if (fw && w < filter_width(fw)) keep = 0;
#if defined(SL_CALC_ONLY)
            /* Complete physical footprint catalogue of the 70 stock modes. */
            if(fc==1u && !(aw>=6000u && ah>=3900u))keep=0;
            if(fc==2u && !(aw>=6000u && ah>=3300u && ah<=3500u))keep=0;
            if(fc==3u && !(aw>=4100u && aw<=4300u))keep=0;
            if(fc==4u && !(aw>=3900u && aw<=4000u))keep=0;
            if(fc==5u && !(aw>=6000u && ah<=2100u))keep=0;
            if(fc==6u && !(aw>=5600u && aw<6000u))keep=0;
            uint32_t hm=timing_w1(m,tmg,i)&0xffffu;
            order_key[out]=hm*(fp==1u?h+peek(row+0x5cu):h);
#else
            if (fp && ah && prop_nearest(udiv(aw * 1000u, ah)) != fp) keep = 0;
            if (fc == 1u && aw < 5600u) keep = 0;
            if (fc == 2u && (aw < 4100u || aw > 4300u)) keep = 0;
            if (fc == 3u && (aw < 3900u || aw > 4000u)) keep = 0;
#endif
            break;
        }
        if (keep) {
#if defined(SL_CALC_ONLY)
            uint32_t pos=out,sort=order_key[out];
            /* Equal rates retain the quality order. Smaller periods are faster. */
            while(fp && pos && order_key[pos-1]>sort){
                order_key[pos]=order_key[pos-1];m->mode_ids[pos]=m->mode_ids[pos-1];pos--;
            }
            order_key[pos]=sort;m->mode_ids[pos]=(uint8_t)id;out++;
#else
            m->mode_ids[out++]=(uint8_t)id;
#endif
        }
    }
    return out;
}

/* The Crop row: "-1024x-540 (5040x2872)" -- what is cut and what is left (the
 * user: both); the field being edited in [brackets] */
static void crop_post(struct sl_menu *m) {
    volatile char *t = m->crop_text;
    uint32_t n = 0;
    for (uint32_t f = 0; f < 2u; ++f) {
        uint32_t v = f ? m->crop_h : m->crop_w, on = m->crop_editing && m->crop_field == f;
        if (f) t[n++] = 'x';
        if (on) t[n++] = '[';
        if (v) t[n++] = '-';
        n += dec5(t + n, v);
        if (on) t[n++] = ']';
    }
    t[n++] = ' '; t[n++] = '(';
    n = wxh(t, n, readout_w(m), readout_h(m));
    t[n++] = ')'; t[n] = 0;
    post_str(m->names[V_CTEXT], m->crop_text);
}

/* ---- the OUTPUT panel -> AXIS (imx410_block.axis_words / expected_recipe) ------
 * raster = the mode's, binning, RWZM so the record matrix is the visible
 * output + its margins (rec = (raster / bin) x 1024 / zoom, aligned), A_CROP =
 * the visible output (explicit: the DNG's crop), mode = the chosen one.  A cut
 * readout (the Crop row) widens the zoom by it, so the visible output is the
 * cut's centre.  No mode: AXIS is left alone. */
#define AX_RW   (2u * 4u)
#define AX_RH   (3u * 4u)
#define AX_BIN  (4u * 4u)
#define AX_ZH   (5u * 4u)
#define AX_ZV   (6u * 4u)
#define AX_CROP (7u * 4u)
#define AX_MODE (8u * 4u)
#define RWZM_UNITY 1024u

/* RWZM for a record matrix: unity when the aligned source already is it (the
 * largest output -- M98 at RAW = OG3K's own 3024 x 2012), never up-scale */
static uint32_t zoom(uint32_t cut_readout, uint32_t bin, uint32_t rec, uint32_t align) {
    uint32_t src = udiv(cut_readout, bin), z;
    if (!rec || (src & ~(align - 1u)) <= rec) return RWZM_UNITY;
    z = udiv(src * RWZM_UNITY, rec);
#if defined(SL_CALC_ONLY)
    /* Preserve the planner's 1024..16384 scaling domain. Smaller visible
     * outputs use a centred crop within the retained record matrix. */
    if (z > 16384u) z = 16384u;
#endif
    return z < RWZM_UNITY ? RWZM_UNITY : z;
}

/* Live view's shape (camera r69 2026-10-03: M7 16:9 squeezed vertically, 0.84
 * = 1125 / 1334): the six preview profiles' visible height was set once at
 * install, from the card's 3:2 default (1334), and never followed the panel.
 * Here it follows the aspect enum the recipe declares (og3krecipe /
 * imx410_block.aspect_enum: act x scale x RWZM, nearest of ASPTAB's five) with
 * imx410_plan.preview_visible_height's heights: 4:3 1334 (clamped), 3:2 1334,
 * 16:9 1125 (stock), 1:1 1334, 21:9 857.  GTAB's selected value is what
 * og3ksel / og3kfmt write when CUSTOM is chosen; the profiles themselves only
 * while CUSTOM is on (FLAG). */
#define GTAB_GROUPS 0u
#define GTAB_COUNT  4u
#define GTAB_SEL    8u
#define GTAB_ADDR   16u
#define PREV_N      6u
#define ASPECT_N    5u
static uint32_t aspect_of(const struct sl_menu *m, uint32_t zh, uint32_t zv) {
    /* the recorded pixels' shape (og3krecipe aspect_pick, 2026-10-04): no mode
     * reduction, no RWZM -- M12 RAW looks squeezed in live view as in the DNG */
    uint32_t r, e, best = 3u, berr = ~0u;
    (void)zh; (void)zv;
    if (!m->out_h) return 3u;
    r = udiv(m->out_w * 1024u, m->out_h);
    for (e = 0; e < ASPECT_N; e++) {
        uint32_t q = peek(SL_ADDR(m, ASPTAB) + e * 4u), err = r > q ? r - q : q - r;
        if (err < berr) { berr = err; best = e + 1u; }
    }
    return best;
}
#define GTAB_G1     (GTAB_ADDR + PREV_N * 4u)   /* group 1: the visible width (+0x20) */
static void gtab_group(const struct sl_menu *m, uint32_t g, uint32_t v) {  /* g = the group's count word */
    uint32_t i;
    poke(SL_ADDR(m, GTAB) + g + 4u, v);
    if (peek(SL_ADDR(m, FLAG)) != 1u) return;
    for (i = 0; i < PREV_N; i++) {
        uint32_t a = peek(SL_ADDR(m, GTAB) + g + 12u + i * 4u);
        if (a >= 0xC0B00000u && a < 0xC0C00000u) poke(a, v);
    }
}
static void preview_post(struct sl_menu *m, uint32_t zh, uint32_t zv) {
    uint32_t e = aspect_of(m, zh, zv), w = 2000u, h;
    h = e == 3u ? 1125u : e == 5u ? 857u : 1334u;
    if (m->sb_vis_w) { w = m->sb_vis_w; h = m->sb_vis_h; }   /* = what recording shows */
    if (peek(SL_ADDR(m, GTAB) + GTAB_GROUPS) != 2u || peek(SL_ADDR(m, GTAB) + GTAB_COUNT) != PREV_N
        || peek(SL_ADDR(m, GTAB) + GTAB_G1) != PREV_N) return;          /* not the table we know */
    gtab_group(m, GTAB_COUNT, h);
    gtab_group(m, GTAB_G1, w);
}

/* Our own PARAM profile (imx410_profile.declare, 2026-10-04).  The card used to
 * borrow p83 -- a stills profile whose preview buffers are sized for a 3032-wide
 * readout; a 6064-wide one overflowed them (r67 / r69: garbled, frozen).  Now
 * the panel writes a whole row of the profile tables itself: every field the
 * formula owns, into one of the two rows nobody references (6 = p13, 7 = p14),
 * then points our private id at it (mapping[87]).  The firmware rebuilds the
 * row from the 65 column tables on every live-view configuration, so it picks
 * the row up as is; imx410_canvas still lays the recipe's rec / act / RWZM and
 * the menu's plane format / >60 flag on top.  Two rows: the one not in use is
 * written, then the id flips -- never a half-written row in use.
 * SL_COLTAB holds each column table's address by field offset (imx410_plan). */
#define DECL_ROW_A   6u
#define DECL_ROW_B   7u
#define DECL_N       29u            /* imx410_profile.DECLARED_BY_PANEL */
#define BIN3_WINDOW  6000u          /* a full-width readout previews through CRCT /3 */
#define PREV_SRC_MAX 2100u          /* the widest stock preview source (2088) */
#define PREV_VIS_W   2000u
#define PREV_MW      16u
#define PREV_MH      10u
#define RWZM_STOCK1  1023u          /* stock writes unity as 1023 */
static uint32_t f32_bits(uint32_t n) {   /* a small positive integer as IEEE-754 bits */
    uint32_t msb = 31u - (uint32_t)__builtin_clz(n | 1u);
    if (!n) return 0;
    return (127u + msb) << 23 | (n - (1u << msb)) << (23u - msb);
}
static uint32_t next_preview_zoom(uint32_t z) {   /* stock preview RWZM values above z */
    return z < 1536u ? 1536u : z < 1600u ? 1600u : z < 2048u ? 2048u : z < 3072u ? 3072u : 0;
}
static void preview_axis(uint32_t p, uint32_t *bin, uint32_t *z) {   /* x1024 factor -> CRCT enum + RWZM */
    uint32_t q;
    if (p >= 3u * RWZM_UNITY) { *bin = 1u; q = p / 3u; if (q < RWZM_UNITY) q = RWZM_UNITY; }
    else { *bin = 0; q = p; }
    *z = q <= RWZM_UNITY ? RWZM_STOCK1 : q;
}
static uint32_t near(uint32_t a, uint32_t b) { return (a > b ? a - b : b - a) <= 4u; }
static uint32_t bin_enum(uint32_t b) { return b == 5u ? 2u : b == 3u ? 1u : 0; }
static void declare_post(struct sl_menu *m, uint32_t zh, uint32_t zv) {
    uint32_t ww = m->ro_w, wh = m->ro_h, aw = m->out_w, ah = m->out_h;
    uint32_t rec_w, rec_h, fh, fv, ph, pv, binh, binv, zph, zpv, sw, sh, vw, vh, row, i, v[DECL_N];
    m->sb_vis_w = m->sb_vis_h = 0;
#if defined(SL_CALC_ONLY)
    m->canvas_valid = 0;
    if (!aw || !ah || !zh || !zv) return;
#else
    if (!peek(SL_ADDR(m, COLTAB)) || !aw || !ah || !zh || !zv) return;
#endif     /* not installed / nothing to declare */
    rec_w = udiv(udiv(ww, m->bin_h) * RWZM_UNITY, zh) & ~15u;     /* og3krecipe's own rule */
    rec_h = udiv(udiv(wh, m->bin_v) * RWZM_UNITY, zv) & ~1u;
    /* Match imx410_profile's preview_factors / preview_path / preview_visible.
     * Only binning needs a matching record tap (branch C). Without binning,
     * keep the preview isotropic as in the camera-verified r78. Extending C to
     * unequal record zooms in v11 brought back r77's first-second LCD seam. */
    fh = m->bin_h * (zh > RWZM_UNITY ? zh : RWZM_UNITY);
    fv = m->bin_v * (zv > RWZM_UNITY ? zv : RWZM_UNITY);
    if ((m->bin_h > 1u || m->bin_v > 1u) && udiv(ww * RWZM_UNITY, fh) <= PREV_SRC_MAX) {
        /* branch C (imx410_profile.preview_factors): preview bin and RWZM equal the
         * record's on each axis, so the path selector opens the Hbin2 tap */
        ph = fh; pv = fv;
    } else if (ww >= BIN3_WINDOW) {
        ph = pv = 3u * RWZM_UNITY;
    } else {
        uint32_t c = fh < fv ? fh : fv;
        while (c && udiv(ww * RWZM_UNITY, c) > PREV_SRC_MAX) c = next_preview_zoom(c);
        if (!c) return;
        ph = pv = c;
    }
    if ((m->bin_h > 1u || m->bin_v > 1u) && udiv(ww * RWZM_UNITY, fh) <= PREV_SRC_MAX) {
        /* Equal products do not imply equal taps. Keep the exact record pair,
         * rather than decomposing a no-bin zoom >= 3x into preview binning. */
        binh = m->bin_h == 3u; binv = m->bin_v == 3u;
        zph = zh <= RWZM_UNITY ? RWZM_STOCK1 : zh;
        zpv = zv <= RWZM_UNITY ? RWZM_STOCK1 : zv;
    } else {
        preview_axis(ph, &binh, &zph);
        preview_axis(pv, &binv, &zpv);
    }
    sw = udiv(ww * RWZM_UNITY, ph); sh = udiv(wh * RWZM_UNITY, pv);
    if (sw <= PREV_MW || sh <= PREV_MH) return;
    sw -= PREV_MW; sh -= PREV_MH;
    uint32_t vis_w = udiv(aw * fh, ph), vis_h = udiv(ah * fv, pv);
    vw = vis_w; vh = vis_h;                     /* act in preview pixels */
    if (!vis_w || !vis_h) return;
    {
        uint32_t cap = sw < PREV_VIS_W ? sw : PREV_VIS_W;
        if (vw > cap) { vw = cap; vh = ph != pv ? udiv(cap * vis_h, vis_w) : udiv(udiv(cap * ah, aw) * fv, fh); }
        if (vh > sh) { vh = sh; vw = ph != pv ? udiv(vh * vis_w, vis_h) : udiv(udiv(vh * aw, ah) * fh, fv); }
    }
    vw = (vw + 15u) & ~15u;
    /* Rounding up at the source edge can make the declared preview raster
     * wider than the pixels available (M98 Free 1504x1006: 1536 > 1531).
     * Keep its aligned visible width inside the source and refit the height. */
    if (vw > (sw & ~15u)) {
        vw = sw & ~15u;
        vh = ph != pv ? udiv(vw * vis_h, vis_w) : udiv(udiv(vw * ah, aw) * fv, fh);
        if (vh > sh) vh = sh;
    }
    if (!vw || !vh) return;
    if (vw == PREV_VIS_W) {                       /* never past the source (r71: M98 1344 > 1341) */
        if (near(vh, 1125u) && 1125u <= sh) vh = 1125u;          /* 16:9, stock UHD */
        else if (near(vh, 1334u) && 1334u <= sh) vh = 1334u;     /* 3:2, OG3K / formats / FP3K */
    }
    {   /* standby live view shows the region recording shows: a preview pixel covers
         * (ph sx, pv sy) / 1024 sensor pixels, a standby one 3 -- squeezed pixels too */
        uint32_t sx = m->ro_sx ? m->ro_sx : 1u, sy = m->ro_sy ? m->ro_sy : 1u;
        uint32_t sbw = vw * ph * sx / 3072u, sbh = vh * pv * sy / 3072u;
        m->sb_vis_w = sbw > 2000u ? 2000u : sbw;
        m->sb_vis_h = sbh > 1334u ? 1334u : sbh;
    }
    /* in imx410_profile.DECLARED_BY_PANEL's order: SL_COLTAB holds those 29
     * column tables' addresses, nothing else (the cave has 144 B to spare) */
    v[0] = rec_w; v[1] = rec_h;                         /* 0x00 0x04 rec */
    v[2] = vw + PREV_MW; v[3] = vh + PREV_MH;           /* 0x0C 0x10 preview raster */
    v[4] = 1u;                                          /* 0x1C video class */
    v[5] = vw;                                          /* 0x20 preview visible */
    v[6] = aw;                                          /* 0x24 act */
    v[7] = vh;                                          /* 0x28 */
    v[8] = ah;                                          /* 0x2C */
    v[9] = binh ? 16u : 1u;                             /* 0x38 */
    v[10] = binh;                                       /* 0x58 preview hbin */
    v[11] = bin_enum(m->bin_h);                         /* 0x5C record hbin */
    v[12] = zph;                                        /* 0x60 preview RWZM H */
    v[13] = zh == RWZM_UNITY ? RWZM_STOCK1 : zh;        /* 0x64 record RWZM H */
    v[14] = 0; v[15] = 1u; v[16] = 0;                   /* 0x88 0x90 0xC0 video class */
    v[17] = binv;                                       /* 0xC4 preview vbin */
    v[18] = bin_enum(m->bin_v);                         /* 0xC8 record vbin */
    v[19] = zpv;                                        /* 0xD0 preview RWZM V */
    v[20] = zv == RWZM_UNITY ? RWZM_STOCK1 : zv;        /* 0xD4 record RWZM V */
    v[21] = vw + PREV_MW;                               /* 0xD8 producer */
    v[22] = rec_w;                                      /* 0xDC */
    v[23] = vh + PREV_MH;                               /* 0xE0 */
    v[24] = rec_h;                                      /* 0xE4 */
    v[25] = ww; v[26] = wh;                             /* 0xF4 0xF8 window */
    v[27] = f32_bits(m->ro_sx ? m->ro_sx : 1u);         /* 0xFC 0x100 the mode's reduction */
    v[28] = f32_bits(m->ro_sy ? m->ro_sy : 1u);
#if defined(SL_CALC_ONLY)
    (void)row;
    for (i = 0; i < DECL_N; i++) m->canvas[i] = v[i];
    m->canvas_valid = 1;
#else
    row = peek(SL_MAPPING_SLOT) == DECL_ROW_A ? DECL_ROW_B : DECL_ROW_A;
    for (i = 0; i < DECL_N; i++) {
        uint32_t col = peek(SL_ADDR(m, COLTAB) + 4u * i);
        if (col < 0xC0B00000u || col >= 0xC0D00000u) return;    /* not the table we know: leave the id */
        poke(col + row * 4u, v[i]);
    }
    poke(SL_MAPPING_SLOT, row);               /* the id now loads our row */
#endif
}

static void axis_post(struct sl_menu *m) {
    uint32_t zh, zv;
    /* not before the user acts on the page: until then AXIS stays the card's
     * shipped OG3K-equivalent default, so a CUSTOM recording is the validated one */
#if !defined(SL_CALC_ONLY)
    if (!m->axis_armed) return;
#endif
    if (!m->ro_w || !m->modes_rows || m->mode_sel >= m->modes_rows) return;
    poke(SL_ADDR(m, AXIS) + AX_RW, m->ro_w);
    poke(SL_ADDR(m, AXIS) + AX_RH, m->ro_h);
    poke(SL_ADDR(m, AXIS) + AX_BIN, m->bin_h | m->bin_v << 16);
#if defined(SL_OFF_BINFILT) || defined(SL_BINFILT)
    poke(SL_ADDR(m, BINFILT), m->bin_kh | m->bin_kv << 4 | (m->bin_mode & 1u) << 8);   /* imx410_binfilt / sellog */
#endif
    zh = zoom(readout_w(m), m->bin_h, m->out_w + MARGIN_W, W_STEP);
    zv = zoom(readout_h(m), m->bin_v, m->out_h + MARGIN_H, 2u);
    poke(SL_ADDR(m, AXIS) + AX_ZH, zh);
    poke(SL_ADDR(m, AXIS) + AX_ZV, zv);
    poke(SL_ADDR(m, AXIS) + AX_CROP, m->out_w | m->out_h << 16);
    poke(SL_ADDR(m, AXIS) + AX_MODE, m->mode_ids[m->mode_sel]);
    declare_post(m, zh, zv);                   /* first: it works out the standby size too */
#if !defined(SL_CALC_ONLY)
    preview_post(m, zh, zv);
#endif
}

static void caption_bin(struct sl_menu *m);
#if defined(SL_CALC_ONLY)
static void pair_text(char *t,uint32_t w,uint32_t h,uint32_t field,uint32_t editing) {
    uint32_t n=0;
    if(editing && !field)t[n++]='[';
    n+=dec5(t+n,w);if(editing && !field)t[n++]=']';t[n++]='x';
    if(editing && field==1u)t[n++]='[';
    n+=dec5(t+n,h);if(editing && field==1u)t[n++]=']';t[n]=0;
}
#endif
#if defined(SL_CALC_ONLY)
/* Seven alphanumeric characters, as allowed by the consumer's RCD label.
 * Empty slots are omitted; seven empty slots retain automatic LABnnn names. */
static uint32_t save_label(struct sl_menu *m, char *label) {
    uint32_t n=0;
    for(uint32_t i=0;i<7u;i++) {
        uint32_t c=(uint8_t)m->save_name[i];
        if(!c)continue;
        if(!((c>='A'&&c<='Z')||(c>='0'&&c<='9')))return 8u;
        label[n++]=(char)c;
    }
    label[n]=0;return n;
}
static void save_name_post(struct sl_menu *m) {
    char *p=m->name_text;uint32_t n=0;
    if(m->name_editing) {
        for(uint32_t i=0;i<7u;i++) {
            if(i==m->name_field)p[n++]='[';
            p[n++]=m->save_name[i]?m->save_name[i]:'_';
            if(i==m->name_field)p[n++]=']';
        }
    } else {
        n=save_label(m,p);
        if(n&&n<8u){p[n++]='.';p[n++]='R';p[n++]='C';p[n++]='D';}
        else {p[0]='N';p[1]='a';p[2]='m';p[3]='e';p[4]=' ';p[5]='A';p[6]='U';p[7]='T';p[8]='O';n=9;}
    }
    p[n]=0;post_str(m->names[197],p);
}
static void save_name_key(struct sl_menu *m,uint32_t k) {
    if(k==65u){m->name_editing=1;m->name_field=0;}
    else if(k==66u)m->name_editing=0;
    else if(m->name_editing) {
        uint32_t i=m->name_field,c=(uint8_t)m->save_name[i];
        if(k==61u)m->name_field=i?i-1u:6u;
        else if(k==62u)m->name_field=i==6u?0u:i+1u;
        else if(k==63u||k==64u||k==67u||k==68u) {
            uint32_t v=c>='A'&&c<='Z'?c-'A'+1u:c>='0'&&c<='9'?c-'0'+27u:0u;
            v=(k==63u||k==67u)?(v==36u?0u:v+1u):(v?v-1u:36u);
            m->save_name[i]=v?(v<=26u?'A'+v-1u:'0'+v-27u):0;
        }
    }
    save_name_post(m);
}
#endif
static uint32_t panel_post(struct sl_menu *m) {
    post_int(m->names[V_W], m->out_w);
    post_int(m->names[V_H], m->out_h);
    post_int(m->names[V_BH], m->bin_h);
    post_int(m->names[V_BV], m->bin_v);
    caption_bin(m);
    post_str(m->names[V_BTXT], m->bin_caption);
    /* the RWZM actually written to AXIS (axis_post's own zoom()), shown as a
     * scale: 1024 / RWZM.  Not out / readout -- that counted the record matrix's
     * 16 x 10 margin as scaling and showed 0.99 at unity (the user 2026-10-04) */
    scale_text(m->rwzm_text[0], zoom(readout_w(m), m->bin_h, m->out_w + MARGIN_W, W_STEP), 1u, RWZM_UNITY);
    scale_text(m->rwzm_text[1], zoom(readout_h(m), m->bin_v, m->out_h + MARGIN_H, 2u), 1u, RWZM_UNITY);
    post_str(m->names[V_SW], m->rwzm_text[0]);
    post_str(m->names[V_SH], m->rwzm_text[1]);
    for (uint32_t i = 0; i < 4u; ++i)
        post_int(m->names[V_ARROW + i], m->editing && m->edit_field == i ? 1u : 0u);
    crop_post(m);
#if defined(SL_CALC_ONLY)
    m->crop_text[0]='C';m->crop_text[1]='r';m->crop_text[2]='o';m->crop_text[3]='p';m->crop_text[4]=' ';
    pair_text(m->crop_text+5,readout_w(m),readout_h(m),m->crop_field,m->crop_editing);
    post_str(m->names[41],m->crop_text);
    m->output_text[0]='O';m->output_text[1]='u';m->output_text[2]='t';m->output_text[3]='p';m->output_text[4]='u';m->output_text[5]='t';m->output_text[6]=' ';
    pair_text(m->output_text+7,m->out_w,m->out_h,m->edit_field,m->small_edit==30u);
    pair_text(m->bins_text,m->bin_h,m->bin_v,m->edit_field&1u,m->small_edit==40u);
    hundredths(m->lens_text,m->lens_factor?m->lens_factor:133u);
    uint32_t n=0;while(m->lens_text[n])n++;m->lens_text[n++]='x';m->lens_text[n]=0;
    post_str(m->names[57],m->output_text);post_str(m->names[58],m->bins_text);post_str(m->names[59],m->lens_text);
    post_int(m->names[54],m->ro_sx!=m->ro_sy);
    post_int(m->names[53],m->output_policy);
    post_int(m->names[55],m->crop_editing && m->crop_field==2u);
    post_int(m->names[56],m->small_edit==30u && m->edit_field==4u);
    post_int(m->names[193],!m->crop_lock);
    post_int(m->names[194],m->output_policy==0u && m->ro_sx!=m->ro_sy);
    post_int(m->names[195],m->output_policy==1u);post_int(m->names[196],m->output_policy==2u);
    save_name_post(m);
    axis_post(m);                            /* current matrix before its data-rate estimate */
#endif
    rate_post(m);
    diagram_post(m);
#if !defined(SL_CALC_ONLY)
    axis_post(m);
#endif
    return 0;
}

/* Binning, every setting the hardware has (the user 2026-10-05): each axis steps
 * 1 -> 3 with kernel (1,1,1) (1,2,1) (1,4,1) (1,6,1) (1,14,1) (0,1,0) in record
 * mode soft (record 0), then the same six in std (record 1) (13 steps).  Kernels are per axis; the
 * record's control bits (0x300F0800 / 0840 bit16) are one for both, so the mode
 * stepped on either axis is the mode of both (imx410_binfilt / imx410_sellog).
 * No x5: Ver.5.02 has no 5-tap kernel and vbin x5 asserts */
#define BIN_KERNELS 6u
static void bin_step(uint32_t *bin, uint32_t *kern, uint32_t *mode, int32_t dir) {
    uint32_t n = 1u + 2u * BIN_KERNELS;
    uint32_t code = *bin == 3u ? 1u + *mode % 2u * BIN_KERNELS + *kern % BIN_KERNELS : 0;
    code = dir > 0 ? (code + 1u == n ? 0 : code + 1u) : (code ? code - 1u : n - 1u);
    *bin = code ? 3u : 1u;
    if (code) { *kern = (code - 1u) % BIN_KERNELS; *mode = (code - 1u) / BIN_KERNELS; }
}

/* SL_O_BTxt: "bin", or each binned axis's kernel and the mode -- "(1,1,1)x(1,14,1) std",
 * "H(1,6,1) soft", "V(0,1,0) std" (soft = record 0, extra smoothing; std = record 1).  Byte immediates, no .rodata (-fropi) */
static uint32_t put_kernel(char *t, uint32_t i, uint32_t k) {
    uint32_t mid = k == 0 ? 1u : k == 1 ? 2u : k == 2 ? 4u : k == 3 ? 6u : k == 4 ? 14u : 1u;
    char side = k == 5 ? '0' : '1';
    t[i++] = '('; t[i++] = side; t[i++] = ',';
    if (mid >= 10u) t[i++] = '1';
    t[i++] = (char)('0' + mid % 10u);
    t[i++] = ','; t[i++] = side; t[i++] = ')';
    return i;
}
static void caption_bin(struct sl_menu *m) {
    char *t = m->bin_caption;
    uint32_t i = 0, h = m->bin_h == 3u, v = m->bin_v == 3u;
    if (!h && !v) {
#if defined(SL_CALC_ONLY)
        t[0]=' ';t[1]=0;
#else
        t[0] = 'b'; t[1] = 'i'; t[2] = 'n'; t[3] = 0;
#endif
        return;
    }
    if (h && v) { i = put_kernel(t, i, m->bin_kh); t[i++] = 'x'; i = put_kernel(t, i, m->bin_kv); }
    else { t[i++] = h ? 'H' : 'V'; i = put_kernel(t, i, h ? m->bin_kh : m->bin_kv); }
    t[i++] = ' ';                                  /* the record mode, by what it does (the user) */
    if (m->bin_mode & 1u) { t[i++] = 's'; t[i++] = 't'; t[i++] = 'd'; }   /* record 1: close to a plain average */
    else { t[i++] = 's'; t[i++] = 'o'; t[i++] = 'f'; t[i++] = 't'; }      /* record 0: extra smoothing */
    t[i] = 0;
}

/* held: the key repeats -- 1x, then 5x after ~10 repeats, 20x after ~25 */
static uint32_t key_mult(struct sl_menu *m, uint32_t key, uint32_t stepping) {
    uint32_t now = tick_ms(), mult = 1u;
    if (stepping) {
        if (key == m->key_last && now - m->key_tick < HOLD_MS) m->key_run++;
        else m->key_run = 0;
        mult = m->key_run >= 25u ? 20u : m->key_run >= 10u ? 5u : 1u;
    }
    m->key_tick = now;
    m->key_last = key;
    return mult;
}

/* The Crop row's editor (codes K_CROP + 1..8): Left / Right pick the width or the
 * height, Up / Down cut more / less (16 px / 2 px, the output's own alignment),
 * the dial x10; the output then takes the largest the cut readout allows.  With
 * a ratio held (not Free / RAW) the crop obeys it (the user): the other side's
 * cut is undone, the output fitted from the edited side, and both cuts set from
 * the output -- what is left is the output x binning, at the ratio, 1:1. */
#if defined(SL_CALC_ONLY)
static void lock_crop(struct sl_menu *m,uint32_t from_w,uint32_t contain) {
    if(!m->crop_lock)return;
    uint32_t w=readout_w(m),h=readout_h(m),rw=raster_w(m),rh=raster_h(m);
    if(contain)from_w=w*rh<=h*rw;
    uint32_t frac=from_w?udiv(w*10000u,rw):udiv(h*10000u,rh);
    uint32_t minw=32u*m->bin_h,minh=12u*m->bin_v;
    if(minw<64u)minw=64u;if(minh<64u)minh=64u;
    uint32_t a=udiv(minw*10000u+rw-1u,rw),b=udiv(minh*10000u+rh-1u,rh);
    if(frac<a)frac=a;if(frac<b)frac=b;if(frac>10000u)frac=10000u;
    m->crop_w=udiv(rw*(10000u-frac),10000u)&~15u;
    m->crop_h=udiv(rh*(10000u-frac),10000u)&~1u;
}
#endif
static uint32_t crop_key(struct sl_menu *m, uint32_t key) {
    uint32_t k = key - K_CROP, mult = key_mult(m, key, k == K_UP || k == K_DOWN);
    int32_t dir = 0, n, v;
    switch (k) {
    case K_EDIT: m->crop_editing = 1u; return 1;
    case K_DONE: m->crop_editing = 0u; return 1;
    case K_LEFT: case K_RIGHT:
#if defined(SL_CALC_ONLY)
        m->crop_field=k==K_RIGHT?(m->crop_field+1u)%3u:(m->crop_field+2u)%3u;
#else
        m->crop_field ^= 1u;
#endif
        return 1;
    case K_UP: dir = 1; break;
    case K_DOWN: dir = -1; break;
    case K_DIAL_UP: dir = 1; mult = 10u; break;
    case K_DIAL_DOWN: dir = -1; mult = 10u; break;
    default: return 0;
    }
    n = dir * (int32_t)mult;
#if defined(SL_CALC_ONLY)
    if(m->crop_field==2u){
        m->crop_lock^=1u;post_int(m->names[51],m->crop_lock);lock_crop(m,1u,1u);
        m->out_w=max_w(m,m->bin_h);m->out_h=max_h(m,m->bin_v);fit(m,1u);return 1;
    }
    n=-n; /* The sidebar edits retained pixels, not removed pixels. */
#endif
    if (m->crop_field == 0u) {
        v = (int32_t)m->crop_w + n * (int32_t)W_STEP;
        if (v < 0) v = 0;
        if ((uint32_t)v > raster_w(m) - CROP_KEEP) v = (int32_t)((raster_w(m) - CROP_KEEP) & ~(W_STEP - 1u));
        m->crop_w = (uint32_t)v;
    } else {
        v = (int32_t)m->crop_h + n * (int32_t)H_STEP;
        if (v < 0) v = 0;
        if ((uint32_t)v > raster_h(m) - CROP_KEEP) v = (int32_t)((raster_h(m) - CROP_KEEP) & ~(H_STEP - 1u));
        m->crop_h = (uint32_t)v;
    }
#if defined(SL_CALC_ONLY)
    lock_crop(m,m->crop_field==0u,0u);
    m->out_w=max_w(m,m->bin_h);m->out_h=max_h(m,m->bin_v);fit(m,1u);
#else
    {
        uint32_t num, den, held;
        ratio_of(m, m->ratio, &num, &den);
        held = num != 0u;
        if (held) {                          /* the other side follows: start it uncut */
            if (m->crop_field == 0u) m->crop_h = 0;
            else m->crop_w = 0;
        }
        m->out_w = max_w(m, m->bin_h);       /* the resolution follows the cut (the user) */
        m->out_h = max_h(m, m->bin_v);
        fit(m, m->crop_field == 0u || !held);
        if (held) {
            /* the side being edited keeps the cut asked for; only the side that follows
             * the ratio is what is left = the output + its margins.  It used to rebuild
             * both from the output -- the fit rounds the output down to a legal size, so
             * a smaller cut came back as the old one and the cut never went back to 0
             * (the user 2026-10-04).  The edited side at 0 = no cut at all. */
            uint32_t lw = (m->out_w + MARGIN_W) * m->bin_h, lh = (m->out_h + MARGIN_H) * m->bin_v;
            uint32_t asked = m->crop_field == 0u ? m->crop_w : m->crop_h;
            if (!asked) m->crop_w = m->crop_h = 0;
            else if (m->crop_field == 0u) m->crop_h = raster_h(m) > lh ? raster_h(m) - lh : 0;
            else m->crop_w = raster_w(m) > lw ? raster_w(m) - lw : 0;
        }
    }
#endif
    return 1;
}

static uint32_t panel_key(struct sl_menu *m, uint32_t key) {
    int32_t dir = 0, big = 0;
    uint32_t mult, num, den, held;
    if (key > K_CROP) return crop_key(m, key);
    ratio_of(m, m->ratio, &num, &den);
    held = num != 0u || m->ratio == R_RAW;    /* W:H fixed (not Free) */
    mult = key_mult(m, key, key == K_UP || key == K_DOWN);
    switch (key) {
    case K_EDIT: m->editing = 1u; break;
    case K_DONE: m->editing = 0u; break;
    case K_LEFT: m->edit_field = m->edit_field ? m->edit_field - 1u : 3u; break;
    case K_RIGHT: m->edit_field = m->edit_field < 3u ? m->edit_field + 1u : 0u; break;
    case K_UP: dir = 1; break;
    case K_DOWN: dir = -1; break;
    case K_DIAL_UP: dir = 1; big = 1; break;
    case K_DIAL_DOWN: dir = -1; big = 1; break;
    default: return 0;
    }
    if (dir) {
        int32_t n = dir * (int32_t)mult * (big ? 10 : 1);
        /* a ratio held: the height steps by the width's x16 and follows it -- a
         * bare 2 px step left the width (x16) behind and broke the ratio (the user) */
        uint32_t hs = 0, ws = exact_step(num, den, &hs);
        if (!ws) ws = W_STEP;                /* nearest legal shape: the width x16 */
        if (m->edit_field == 0u || (m->edit_field == 1u && held)) m->out_w = (uint32_t)((int32_t)m->out_w + n * (int32_t)ws);
        else if (m->edit_field == 1u) m->out_h = (uint32_t)((int32_t)m->out_h + n * (int32_t)H_STEP);
        else if (m->edit_field == 2u) bin_step(&m->bin_h, &m->bin_kh, &m->bin_mode, dir);
        else bin_step(&m->bin_v, &m->bin_kv, &m->bin_mode, dir);
        if ((int32_t)m->out_w < 16) m->out_w = 16u;
        if ((int32_t)m->out_h < 2) m->out_h = 2u;
        if (m->edit_field >= 2u) {           /* binning: the largest output it allows (the user) */
            m->out_w = max_w(m, m->bin_h);
            m->out_h = max_h(m, m->bin_v);
        }
    }
    fit(m, m->edit_field != 1u || held);     /* Free: the edited side leads; else the width */
    return 1;
}

/* A mode chosen: the largest output at AUTO, binning 1 x 1 (the user
 * 2026-10-03); the Ratio row shows AUTO again.  The readout is the whole
 * sensor until the mode list is real. */
static void mode_reset(struct sl_menu *m) {
    m->crop_w = m->crop_h = 0;                 /* a mode chosen: no cut (the user) */
    m->crop_editing = 0;
    m->bin_h = m->bin_v = 1u;
    m->bin_kh = m->bin_kv = 0;                 /* (1,1,1), record 0: the cleanest (camera A001_028) */
    m->bin_mode = 0;
#if defined(SL_CALC_ONLY)
    m->output_policy=0;m->lock_num=m->lock_den=0;
    m->small_edit=m->editing=0;m->crop_field=0;
#endif
    m->ratio = R_AUTO;
    m->out_w = max_w(m, 1u);
    m->out_h = max_h(m, 1u);
    fit(m, 1u);
#if defined(SL_CALC_ONLY)
    if(m->ro_sx==m->ro_sy){m->output_policy=1u;m->ratio=R_RAW;}
    m->lock_num=m->out_w;m->lock_den=m->out_h;
    post_int(m->names[V_SCALE],m->output_policy);
#else
    post_int(m->names[V_SCALE], R_AUTO);
#endif
}

/* The readout moved under the panel (a shorter list, the first boot's list):
 * as if that mode were chosen */
static uint32_t readout_apply(struct sl_menu *m) {
    if (!m->ro_changed) return 0;
    m->ro_changed = 0;
    mode_reset(m);
    return 1;
}

/* the write callback: MV_SLScale (the Squeeze row) or SL_O_Key (the panel's keys);
 * the variable is already written.  The key is posted back to 0 so the same key
 * again is a change (our own posts do not call this). */
#if defined(SL_CALC_ONLY)
static uint32_t sl_menu_export(struct sl_menu *m);
static uint32_t sl_menu_apply(struct sl_menu *m);
static void sl_menu_auto(struct sl_menu *m);
static void small_key(struct sl_menu *m,uint32_t key) {
    uint32_t base=key>=50u?50u:key>=40u?40u:30u,k=key-base;
    if(k==K_EDIT){m->small_edit=base;m->editing=1;m->edit_field=base==40u?2u:0u;return;}
    if(k==K_DONE){m->small_edit=0;m->editing=0;return;}
    if(base==50u){
        int32_t n=m->lens_factor?m->lens_factor:133u;
        if(k==K_UP)n++;if(k==K_DOWN)n--;if(k==K_DIAL_UP)n+=10;if(k==K_DIAL_DOWN)n-=10;
        if(n<101)n=101;if(n>400)n=400;m->lens_factor=n;
        m->out_w=max_w(m,m->bin_h);m->out_h=max_h(m,m->bin_v);fit(m,1u);return;
    }
    if(k==K_LEFT||k==K_RIGHT){
        if(base==30u){
            uint32_t f=m->edit_field==4u?2u:m->edit_field;
            f=k==K_RIGHT?(f+1u)%3u:(f+2u)%3u;m->edit_field=f==2u?4u:f;
        }else m->edit_field^=1u;
        return;
    }
    if(base==30u && m->edit_field==4u){
        uint32_t warp=m->ro_sx!=m->ro_sy,p=m->output_policy;
        if(k==K_UP||k==K_DIAL_UP)p=p==2u?(warp?0u:1u):p+1u;
        else if(k==K_DOWN||k==K_DIAL_DOWN)p=p==(warp?0u:1u)?2u:p-1u;
        else return;
        m->output_policy=p;m->lock_num=m->out_w;m->lock_den=m->out_h;
        m->ratio=p==0u?R_AUTO:p==1u?R_RAW:R_FREE;
        post_int(m->names[V_SCALE],p);
        if(p==0u){m->out_w=max_w(m,m->bin_h);m->out_h=max_h(m,m->bin_v);fit(m,1u);}
        return;
    }
    panel_key(m,k);
    if(base==40u){lock_crop(m,1u,1u);m->out_w=max_w(m,m->bin_h);m->out_h=max_h(m,m->bin_v);fit(m,1u);}
}
#endif
static uint32_t panel_changed(uintptr_t desc, uintptr_t unused) {
    struct sl_menu *m = the_menu();
    (void)desc; (void)unused;
    if (!m || m->result != SL_MENU_INSTALLED) return 0;
#if defined(SL_CALC_ONLY)
    /* SAVE is geometry-neutral: do not run policy reconciliation, fitting or
     * automatic commit while editing a filename or writing a saved recipe. */
    uint32_t save_key=value_of(m,V_KEY);
    if(save_key==20u || (save_key>=61u && save_key<=68u)) {
        if(save_key==20u)sl_menu_export(m);else save_name_key(m,save_key);
        post_int(m->names[V_KEY],0u);return 0;
    }
#endif
    m->axis_armed = 1u;                      /* the user acted: the panel drives AXIS from now */
    {
        uint32_t key = value_of(m, V_KEY), row = value_of(m, V_SCALE), sel = value_of(m, V_MODE);
#if defined(SL_CALC_ONLY)
        uint32_t policy=row<=2u?row:0u;
        if(!policy && m->ro_sx==m->ro_sy)policy=1u;
        if(policy!=m->output_policy){
            m->output_policy=policy;m->lock_num=m->out_w;m->lock_den=m->out_h;
        }
        row=policy==0u?R_AUTO:policy==1u?R_RAW:R_FREE;
        uint32_t lock=value_of(m,51u),lens=value_of(m,52u);
        if(lock!=m->crop_lock){m->crop_lock=lock==1u;lock_crop(m,1u,1u);m->out_w=max_w(m,m->bin_h);m->out_h=max_h(m,m->bin_v);fit(m,1u);}
        if(lens!=m->lens_on){
            m->lens_on=lens<=9u?lens:0u;
            m->lens_factor=lens==1u?125u:lens==2u?130u:lens==3u?133u:lens==4u?150u:
                lens==5u?155u:lens==6u?160u:lens==7u?165u:lens==8u?180u:lens==9u?200u:100u;
            /* A preset refits once; subsequent unlocked edits remain free. */
            m->output_policy=0;m->ratio=R_AUTO;
            m->out_w=max_w(m,m->bin_h);m->out_h=max_h(m,m->bin_v);fit(m,1u);
            m->lock_num=m->out_w;m->lock_den=m->out_h;m->output_policy=policy;m->ratio=row;
        }
#endif
        if (row >= R_ROWS) row = R_AUTO;
        if (row != m->ratio) {               /* the Ratio row moved: the largest output at it */
            m->ratio = row;                  /* (the user 2026-10-04: was keep W, refit H) */
            m->out_w = max_w(m, m->bin_h);
            m->out_h = max_h(m, m->bin_v);
            fit(m, 1u);
        }
        if (key) {
#if defined(SL_CALC_ONLY)
            if (key == 20u || key == 21u) {
                panel_post(m);
                if (key==21u) sl_menu_apply(m); else sl_menu_export(m);
                post_int(m->names[V_KEY], 0u);
                return 0;
            }
#endif
#if defined(SL_CALC_ONLY)
            if(key>=30u&&key<=58u)small_key(m,key);else
#endif
            panel_key(m, key);
            post_int(m->names[V_KEY], 0u);
        }
        if (filter_now(m) != m->filter_key) {   /* FILTER moved: the list again, the choice may go */
            modes(m);
            readout_apply(m);
            sel = m->mode_sel;                   /* mode_post may have moved it back to the first */
            excl_update(m);
        }
        if (sel != m->mode_sel) {            /* after the ratio: it sets the row back to AUTO */
            m->mode_sel = sel;
            mode_post(m);                    /* the readout first: the reset sizes to it */
            m->ro_changed = 0;
            mode_reset(m);
            excl_update(m);                      /* the record settings' rows follow the mode */
        }
    }
    panel_post(m);
#if defined(RL_VIRTUAL_RCD)
    sl_menu_auto(m);
#endif
    return 0;
}

uint32_t sl_menu_ui(struct sl_menu *m, uint32_t custom) {
    (void)custom;   /* the MODE list is kept right whatever the resolution, so a
                     * switch to CUSTOM inside the page shows a current one */
    if (!m || m->result != SL_MENU_INSTALLED) return SL_MODES_NOT_INSTALLED;
    if (m->pages && m->pages_state == PAGES_NONE) {                    /* once, whatever happens */
        if (register_pages(m) == PAGES_OK) {
            subscribe(m->names[V_SCALE], panel_changed);
            subscribe(m->names[V_KEY], panel_changed);
            subscribe(m->names[V_MODE], panel_changed);
#if defined(SL_CALC_ONLY)
            subscribe(m->names[V_RFPS], rate_changed);
#else
            subscribe(m->names[V_RFPS], panel_changed);          /* panel_post: the rate */
#endif
            subscribe(m->names[V_FBIT], panel_changed);          /* FILTER: the MODE list again */
            subscribe(m->names[V_FFPS], panel_changed);
            subscribe(m->names[V_FWIDTH], panel_changed);
            subscribe(m->names[V_FPROP], panel_changed);
            subscribe(m->names[V_FCROP], panel_changed);
#if defined(SL_CALC_ONLY)
            subscribe(m->names[51],panel_changed);subscribe(m->names[52],panel_changed);
            m->lens_factor=133u;
#endif
            m->edit_field = m->editing = 0u;
            m->mode_sel = value_of(m, V_MODE);
            mode_reset(m);                                   /* as if the mode were just chosen */
            panel_post(m);
        }
    }
    {
        uint32_t r = modes(m);
        if (m->pages_state == PAGES_OK) {                    /* the list is written now */
            if (readout_apply(m)) panel_post(m);
            else diagram_post(m);
            excl_update(m);
        }
        return r;
    }
}

/* After the frame-rate / bit-depth GUI setter callbacks (sl_excl.S ROLE 12-14,
 * UI thread, the setting already committed): bit changes can rebuild MODE;
 * FPS changes refresh dependent UI without removing MODE rows. */
uint32_t sl_menu_live(struct sl_menu *m) {
    uint32_t r = modes(m);
    if (m && m->result == SL_MENU_INSTALLED && m->pages_state == PAGES_OK) {   /* bits / fps moved */
        readout_apply(m);                      /* the list may have moved under the choice */
        panel_post(m);                         /* the rate, the diagram, the panel */
        excl_update(m);
    }
    return r;
}

uint32_t sl_menu_modes(struct sl_menu *m) { return modes(m); }
uint32_t sl_menu_scan_modes(uint32_t bit, uint32_t ridx, uint8_t *ids) { return scan_modes(the_menu(), bit, ridx, ids); }
uint32_t sl_menu_panel(struct sl_menu *m) { return panel_post(m); }
#ifdef SL_MENU_HOST_TEST
/* the host tests' way to refit a size they set (the Ratio row now maximizes) */
void slm_fit(uint32_t from_w) { struct sl_menu *m = the_menu(); if (m) { fit(m, from_w); panel_post(m); } }
#endif
