/* Host substitutes for sl_modes.c. Never linked into a camera build.
 *
 * Memory is sparse: 4 KiB pages made on first write, so a test can put the
 * real firmware tables (mode metadata / timing, the imager descriptor) and the
 * plan's cave tables (AXIS, RECIPE, RATETAB, TMGTAB) at their real addresses.
 * Reading a page never written counts as out of bounds.
 *
 * The model is a list of rows of five strings with the stock modelCSV
 * semantics sl_modes.c relies on (FUN_c05f5970 / 5978 / 5cf0 / 5990 / 5a58):
 * rows, set-current only inside [0, rows), write a cell of the current row,
 * insert / delete. Every call is logged; `fail_at` makes the n-th native call
 * (1-based) return an error. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sl_menu.h"

#define PAGES 256
static struct { uint32_t base; uint8_t data[4096]; } pages[PAGES];
static uint32_t npages, oob;

static uint8_t *at(uint32_t a, int make) {
    uint32_t base = a & ~0xFFFu;
    for (uint32_t i = 0; i < npages; ++i)
        if (pages[i].base == base) return &pages[i].data[a - base];
    if (!make || npages == PAGES) { oob++; return 0; }
    pages[npages].base = base;
    memset(pages[npages].data, 0, 4096);
    return &pages[npages++].data[a - base];
}
static uint32_t rd(uintptr_t a) {
    uint32_t v = 0;
    for (int i = 3; i >= 0; --i) { uint8_t *p = at((uint32_t)a + i, 0); v = v << 8 | (p ? *p : 0); }
    return v;
}
static void wr(uintptr_t a, uint32_t v) {
    for (int i = 0; i < 4; ++i) { uint8_t *p = at((uint32_t)a + i, 1); if (p) *p = (uint8_t)(v >> (8 * i)); }
}
static uint32_t rd8(uintptr_t a) { uint8_t *p = at((uint32_t)a, 0); return p ? *p : 0; }
static void wr8(uintptr_t a, uint32_t v) { uint8_t *p = at((uint32_t)a, 1); if (p) *p = (uint8_t)v; }

/* ---- the resource / model --------------------------------------------- */
#define RES 0x50000000u
#define INST 0x50001000u
#define MAXROWS 80
static char cells[MAXROWS][6][16];
#define IFACE 0x53000000u                    /* a RAM interface table, as the camera has */
static uint32_t rows, current = 0xFFFFFFFFu, loaded, calls, fail_at, iface = IFACE;
static uint32_t notified, found_ok = 1;
static char log_buf[8192];
static uint32_t log_len;
static void logf_(const char *s) {
    uint32_t n = (uint32_t)strlen(s);
    if (log_len + n + 1 < sizeof log_buf) { memcpy(log_buf + log_len, s, n); log_len += n; log_buf[log_len++] = ';'; }
}
static uint32_t step(const char *what) { logf_(what); return ++calls == fail_at ? 7u : 0u; }

/* the menu's own lists, SL_RATE (10 rows) and SL_BIT (4): NO,TEXT,Popup,Enabled,Enabled2 */
#define RES_AUX 0x50010000u
#define INST_AUX 0x50011000u
static struct { uint32_t rows, current, notified; char cells[12][5][8]; } aux[2];
static int aux_of(uintptr_t i) { return i == INST_AUX ? 0 : i == INST_AUX + 0x100u ? 1 : -1; }
static uint32_t res_find(uintptr_t app, const char *name, uintptr_t *out) {
    uint32_t r = step("find");
    *out = 0;
    if (app != rd(0xC37B7048u)) { oob++; return 1; }
    if (!strcmp(name, "SL_RATE") || !strcmp(name, "SL_BIT")) {
        if (!r) *out = RES_AUX + (name[3] == 'B' ? 0x100u : 0u);
        return r;
    }
    if (strcmp(name, "SL_MODE")) { oob++; return 1; }
    if (!r && found_ok) *out = RES;
    return r;
}
static int is_res(uintptr_t r) { return r == RES || r == RES_AUX || r == RES_AUX + 0x100u; }
static uint32_t res_count(uintptr_t r, uint32_t *n) { uint32_t e = step("count"); if (!is_res(r)) oob++; *n = r == RES ? loaded : 1u; return e; }
static uint32_t res_load(uintptr_t r) { uint32_t e = step("load"); if (!is_res(r)) oob++; if (!e) loaded = 1; return e; }
static uint32_t res_get(uintptr_t r, uintptr_t *i) {
    uint32_t e = step("get");
    if (!is_res(r)) oob++;
    *i = r == RES ? (loaded ? INST : 0) : INST_AUX + (r - RES_AUX);
    return e;
}
static uint32_t model_iface(uintptr_t i, uintptr_t *f) { uint32_t e = step("iface"); if (i != INST && aux_of(i) < 0) oob++; *f = iface; return e; }
static uint32_t notify(uintptr_t i, uint32_t *arg) {
    uint32_t e = step("notify");
    int a = aux_of(i);
    if ((i != INST && a < 0) || *arg != 1) oob++;
    if (!e) { if (a >= 0) aux[a].notified++; else notified++; }
    return e;
}
static uint32_t m_rows(uintptr_t i, uint32_t *n) {
    uint32_t e = step("rows");
    int a = aux_of(i);
    if (i != INST && a < 0) oob++;
    *n = a >= 0 ? aux[a].rows : rows;
    return e;
}
static uint32_t m_current(uintptr_t i, uint32_t r) {
    int a = aux_of(i);
    if (a >= 0) { if (r < aux[a].rows) aux[a].current = r; return 0; }
    if (i != INST) oob++;                     /* stock always returns 0: not a step */
    if ((int32_t)r >= 0 && r < rows) current = r;
    return 0;
}
static uint32_t m_string(uintptr_t i, uint32_t c, const char *s) {
    uint32_t e = step("string");
    int a = aux_of(i);
    if (a >= 0) {
        if (c > 4 || aux[a].current >= aux[a].rows || strlen(s) >= 8) { oob++; return 1; }
        if (!e) strcpy(aux[a].cells[aux[a].current][c], s);
        return e;
    }
    if (i != INST || c > 5 || current == 0xFFFFFFFFu || strlen(s) >= 16) { oob++; return 1; }
    if (!e) strcpy(cells[current][c], s);
    return e;
}
const char *slm_aux_cell(uint32_t k, uint32_t r, uint32_t c) { return k < 2 && r < 12 && c < 5 ? aux[k].cells[r][c] : ""; }
uint32_t slm_aux_notified(uint32_t k) { return k < 2 ? aux[k].notified : 0; }
static uint32_t m_insert(uintptr_t i, uint32_t at_, uint32_t n) {
    uint32_t e = step("insert");
    if (i != INST || at_ > rows || rows + n > MAXROWS) { oob++; return 1; }
    if (e) return e;
    memmove(cells[at_ + n], cells[at_], (rows - at_) * sizeof cells[0]);
    memset(cells[at_], 0, n * sizeof cells[0]);
    rows += n;
    return 0;
}
static uint32_t m_delete(uintptr_t i, uint32_t at_, uint32_t n) {
    uint32_t e = step("delete");
    if (i != INST || at_ + n > rows) { oob++; return 1; }
    if (e) return e;
    memmove(cells[at_], cells[at_ + n], (rows - at_ - n) * sizeof cells[0]);
    rows -= n;
    current = 0xFFFFFFFFu;
    return 0;
}

/* ---- the stock loader, registering the pages pack ----------------------- */
#define NEW_READER 0x54000000u
static uint32_t reg_calls, reg_result, reg_app, reg_pack, reg_len;
static uint32_t nbr_register(uintptr_t app, uintptr_t pack, uint32_t len, uintptr_t *out) {
    reg_calls++; reg_app = (uint32_t)app; reg_pack = (uint32_t)pack; reg_len = len;
    if (reg_result) return reg_result;
    *out = NEW_READER;
    wr(NEW_READER + 0x10, 0x1234); wr(NEW_READER + 0x14, 0x5678);    /* the pack's own pool */
    wr(app + 0x80, rd(app + 0x80) + 1);                                /* one screen more */
    return 0;
}

/* ---- the settings the menu committed -------------------------------------- */
#define MGR 0x58000000u
static uint32_t set_res = 4, set_bit, set_rate = 1, mgr_ok = 1;
static uintptr_t settings(void) { return mgr_ok ? MGR : 0; }
static uint32_t get_res(uintptr_t m) { if (m != MGR) oob++; return set_res; }
static uint32_t get_bit(uintptr_t m) { if (m != MGR) oob++; return set_bit; }
static uint32_t get_rate(uintptr_t m) { if (m != MGR) oob++; return set_rate; }

/* ---- OUTPUT's info panel: subscriptions and posted integers ------------- */
static uint32_t subs, posts, panel_vals[SL_MENU_VARIABLES];
static char sub_names[16][24], post_log[4096];
static uint32_t (*sub_fn[16])(uintptr_t, uintptr_t);
static uint32_t subscribe(const void *name, uint32_t (*fn)(uintptr_t, uintptr_t)) {
    if (subs < 16) { strncpy(sub_names[subs], name, 23); sub_fn[subs] = fn; }
    subs++;
    return 0;
}
static struct sl_menu menu;
static uint32_t post_int(const void *name, uint32_t v) {
    size_t n = strlen(post_log);
    posts++;
    for (uint32_t i = 0; i < SL_MENU_VARIABLES; ++i)     /* the GUI applies it (a little later) */
        if (menu.names[i][0] && !strcmp((const char *)menu.names[i], name)) panel_vals[i] = v;
    snprintf(post_log + n, sizeof post_log - n, "%s=%u ", (const char *)name, v);
    return 0;
}
static uint32_t post_str(const void *name, const char *t) {
    size_t n = strlen(post_log);
    posts++;
    snprintf(post_log + n, sizeof post_log - n, "%s=%s ", (const char *)name, t);
    return 0;
}
static uint32_t now_ms = 1000;
static uint32_t tick_ms(void) { return now_ms; }
void slm_tick(uint32_t ms) { now_ms = ms; }
struct sl_menu *sl_test_menu;
uint32_t sl_menu_value(struct sl_menu *m, uint32_t index, uint32_t *value) {
    if (!m || index >= SL_MENU_VARIABLES) return 0;
    *value = panel_vals[index];
    return 1;
}

const struct sl_menu_natives sl_menu_test_natives = {
    .read = rd, .write = wr, .read_byte = rd8, .write_byte = wr8,
    .res_find = res_find, .res_count = res_count, .res_load = res_load, .res_get = res_get,
    .model_iface = model_iface, .notify = notify, .m_rows = m_rows, .m_current = m_current,
    .m_string = m_string, .m_insert = m_insert, .m_delete = m_delete,
    .nbr_register = nbr_register,
    .settings = settings, .get_res = get_res, .get_bit = get_bit, .get_rate = get_rate,
    .subscribe = subscribe, .post_int = post_int, .post_str = post_str, .tick_ms = tick_ms,
};

void slm_reset(void) {
    npages = oob = rows = loaded = calls = fail_at = notified = log_len = 0;
    current = 0xFFFFFFFFu; iface = IFACE; found_ok = 1;
    reg_calls = reg_result = reg_app = reg_pack = reg_len = 0;
    set_res = 4; set_bit = 0; set_rate = 1; mgr_ok = 1;
    memset(cells, 0, sizeof cells); memset(&menu, 0, sizeof menu); log_buf[0] = 0;
    /* stock's parse of the static SL_MODE: one placeholder row */
    rows = 1; strcpy(cells[0][1], "No matching");
    memset(aux, 0, sizeof aux);
    aux[0].rows = 10; aux[1].rows = 4;
    for (uint32_t k = 0; k < 2; ++k)
        for (uint32_t r = 0; r < aux[k].rows; ++r) { strcpy(aux[k].cells[r][3], "1"); strcpy(aux[k].cells[r][4], "2"); }
    subs = posts = 0; memset(sub_names, 0, sizeof sub_names); memset(sub_fn, 0, sizeof sub_fn);
    memset(panel_vals, 0, sizeof panel_vals); post_log[0] = 0;
    sl_test_menu = &menu; now_ms = 1000;
    {   /* the names sl_menu.c spells (sl_menu.h) */
        static const char *const NAMES[SL_MENU_VARIABLES] = {"SL_O_W", "SL_O_H", "SL_O_In", "SL_O_BH",
            "SL_O_BV", "SL_O_SW", "SL_ModeCount", "MV_SLScale", "SL_O_SH", "MV_SLBin", 0, 0,
            "SL_F_Bit", "SL_F_Fps", "SL_F_Width", "SL_F_Prop", "SL_M_Sel", 0,
            "SL_O_Key", "SL_O_A0", "SL_O_A1", "SL_O_A2", "SL_O_A3", "SL_O_Rate", "SL_ModeMax", "SL_M_Text", "SL_O_RFps",
            "SL_D_GX", "SL_D_GY", "SL_D_GW", "SL_D_GH", "SL_D_RX", "SL_D_RY", "SL_D_RW", "SL_D_RH",
            "SL_D_GTxt", "SL_D_RTxt", "SL_D_Fps", "SL_D_Rs", "SL_F_Crop", "SL_M_Tab",
            "SL_C_Text", "SL_D_CX", "SL_D_CY", "SL_D_CW", "SL_D_CH", "SL_D_CTxt", "SL_N_Sel", "SL_O_BTxt"};
        for (uint32_t i = 0; i < SL_MENU_VARIABLES; ++i)
            if (NAMES[i]) strncpy((char *)menu.names[i], NAMES[i], sizeof menu.names[i] - 1);
    }
}
void slm_panel_value(uint32_t index, uint32_t v) { if (index < SL_MENU_VARIABLES) panel_vals[index] = v; }
uint32_t slm_subs(void) { return subs; }
const char *slm_sub_name(uint32_t i) { return i < 16 ? sub_names[i] : ""; }
void slm_panel_size(uint32_t w, uint32_t h) { menu.out_w = w; menu.out_h = h; }   /* a test's start */
void slm_rec_cap(uint32_t w, uint32_t h) { menu.rec_cap_w = w; menu.rec_cap_h = h; }   /* 0 = the shipped envelope */
void slm_readout(uint32_t w, uint32_t h) { menu.ro_w = w; menu.ro_h = h; menu.ro_sx = menu.ro_sy = 1; menu.ro_changed = 0; }
/* Formula audit only: independent cases use the firmware mode's real raster. */
void slm_calc_seed(uint32_t mid, uint32_t w, uint32_t h, uint32_t sx, uint32_t sy,
                   uint32_t bh, uint32_t bv, uint32_t cw, uint32_t ch,
                   uint32_t ratio, uint32_t ow, uint32_t oh) {
    menu.modes_rows = 1; menu.mode_sel = 0; menu.mode_ids[0] = (uint8_t)mid;
    menu.ro_w = w; menu.ro_h = h; menu.ro_sx = sx; menu.ro_sy = sy;
    menu.ro_changed = 0; menu.bin_h = bh; menu.bin_v = bv;
    menu.crop_w = cw; menu.crop_h = ch; menu.ratio = ratio;
    menu.out_w = ow; menu.out_h = oh; menu.axis_armed = 1;
}
uint32_t slm_calc_get(uint32_t f) {
    switch (f) {
    case 0: return menu.out_w; case 1: return menu.out_h;
    case 2: return menu.bin_h; case 3: return menu.bin_v;
    case 4: return menu.crop_w; case 5: return menu.crop_h;
    case 6: return menu.ratio; case 7: return menu.sb_vis_w; case 8: return menu.sb_vis_h;
    case 9: return menu.edit_field; case 10: return menu.crop_field;
#if defined(SL_CALC_ONLY)
    case 11: return menu.canvas_valid;
    default: return f >= 32 && f < 61 ? menu.canvas[f - 32] : 0xFFFFFFFFu;
#else
    default: return 0xFFFFFFFFu;
#endif
    }
}
const char *slm_calc_rate(void) { return menu.rate_text; }
uint32_t slm_fire(uint32_t i) { return (i < 16 && sub_fn[i]) ? sub_fn[i](0x1234u, 0) : 0xFFFFFFFFu; }
const char *slm_posts(void) { return post_log; }
void slm_clear_posts(void) { post_log[0] = 0; posts = 0; }
void slm_word(uint32_t a, uint32_t v) { wr(a, v); }
uint32_t slm_peek(uint32_t a) { return rd(a); }
void slm_bytes(uint32_t a, const uint8_t *b, uint32_t n) { for (uint32_t i = 0; i < n; ++i) wr8(a + i, b[i]); }
void slm_install(uint32_t count_desc) { menu.result = SL_MENU_INSTALLED; menu.count_desc = count_desc; }
void slm_fail_at(uint32_t n) { fail_at = n; }
void slm_iface(uint32_t f) { iface = f; }
void slm_loaded(uint32_t v) { loaded = v; }
void slm_found(uint32_t v) { found_ok = v; }
uint32_t slm_modes(void) { return sl_menu_modes(&menu); }
uint32_t slm_scan(uint32_t bit, uint32_t ridx, uint8_t *ids) { return sl_menu_scan_modes(bit, ridx, ids); }
uint32_t slm_get(uint32_t f) {
    switch (f) {
    case 0: return rows; case 1: return oob; case 2: return notified; case 3: return menu.modes_step;
    case 4: return menu.modes_rows; case 5: return menu.modes_runs; case 6: return menu.modes_key;
    case 7: return calls; case 8: return loaded;
    default: return 0xFFFFFFFFu;
    }
}
const char *slm_cell(uint32_t r, uint32_t c) { return r < MAXROWS && c < 6 ? cells[r][c] : ""; }
const char *slm_log(void) { log_buf[log_len] = 0; return log_buf; }
uint32_t slm_id(uint32_t r) { return r < SL_MODES_MAX ? menu.mode_ids[r] : 0xFFFFFFFFu; }
uint32_t slm_seen_iface(void) { return (uint32_t)menu.modes_iface; }
void slm_pages(uint32_t reader, uint32_t pack, uint32_t len) {
    menu.reader = reader; menu.pages = pack; menu.pages_len = len;
}
void slm_reg_result(uint32_t v) { reg_result = v; }
uint32_t slm_ui(uint32_t custom) { return sl_menu_ui(&menu, custom); }
uint32_t slm_live(void) { return sl_menu_live(&menu); }
/* eRawBitType (1 = 14-bit), frame-rate internal enum; RATE240 lives in memory */
void slm_settings(uint32_t bit_type, uint32_t internal) { set_bit = bit_type; set_rate = internal; }
void slm_no_settings(void) { mgr_ok = 0; }
uint32_t slm_pages_get(uint32_t f) {
    switch (f) {
    case 0: return menu.pages_state; case 1: return (uint32_t)menu.pages_reader;
    case 2: return reg_calls; case 3: return reg_app; case 4: return reg_pack; case 5: return reg_len;
    default: return 0xFFFFFFFFu;
    }
}
