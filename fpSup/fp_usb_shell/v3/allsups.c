/* Loader v3's optional fpSup management area.
 * Built with sloader.c and uishare in one position-independent compilation
 * unit. The loader enters it last, so it can list the other Sups' outcomes.
 * UI data lives in \fpSup\UI\ALLSUPS.BIN (build_ft6.py); FT6Z includes
 * five visible slots with separate name, version and status fields.
 *
 * The loader owns navigation and next-boot Enable/Disable. Sups own their
 * More Settings callback and persistence. No file renames or live unload.
 * Claims/string layers and the FT_ page-id hook follow the camera-proven
 * r3g mechanism; navigation and popup callbacks are camera-validated.
 */

#define FT6_MAGIC   0x5A365446u        /* "FT6Z" (= sloader.c ALLSUPS_MAGIC) */
#define GUI_SITE    0xC056461Cu
#define GUI_NEXT0   0xC0564638u
#define GUI_OBJECT_AT 0xC37B7048u
#define NBR_LOAD    0xC05E84D9u        /* Thumb */
#define NBU_BASE_AT 0xC18C0460u
#define VAR_REGISTER 0xC05DB309u       /* Thumb: (app, n, {type, name, first value}) */
#define VAR_SUBSCRIBE 0xC0560FB0u      /* ARM: (GUI object, name, fn) -- fn(descriptor) on the UI thread */
#define POST_INT    0xC0593F30u        /* ARM: (0, name, value) queued to the GUI */
#define POST_STR    0xC0593FE0u        /* ARM: (0, name, text) -- the GUI keeps the pointer */
#define FILE_OBJECT_BYTES 0x1000u
#define DESC_VALUE  0x08u

#define APP_SCREENS_N   0x80u
#define APP_SCREENS_CAP 0x84u
#define APP_SCREENS     0x8Cu
#define APP_MACH_N      0xF8u
#define APP_MACH_CAP    0xFCu
#define APP_MACH        0x104u
#define SCREEN_READER   0x24u
#define READER_APP      0x08u
#define READER_POOL_LEN 0x10u
#define READER_POOL     0x14u
#define READER_BASE     0x24u
#define MACH_NAME       0x08u

#define FT6_ROWS    32u                /* stored rows, independent of visible slots */
#define FT6_VISIBLE 5u
#define FT6_PAGES   5u
enum { T_UNLOAD, T_LOAD, T_FAILED, T_ERROR, T_DIR, T_BIN, T_OFF_EXT, T_BLANK,
       T_I_OK, T_I_AEL, T_I_MENU, T_SP, T_W_UNINSTALL, T_W_INSTALL, T_POPUP_FOOTER, T_VERSION, T_FOOTER,
       T_MORE_HINT, T_PAGE_HINT, T_COUNT };
enum { P_NAME, P_GREY, P_VER, P_RED, P_GREEN, P_COUNT };   /* ft6_page.CELL_PARTS */
enum { BOOT_ON, BOOT_OFF, BOOT_FAILED };

/* status: 0 ok; 1 claim refused; 2 no cave; 10+r uia_apply refused with r;
 * 3 no app; 4 no stock reader; 5 no room; 6 loader refused; 7 bad reader;
 * 8 machine count did not grow by one; 9 last machine is not ours;
 * 90+ a variable would not register */
struct ft6_row {
    char base[24];                     /* "10LOSS": the file's name without .BIN / .OFF */
    char disp[24];                     /* "Lossless": the product's name -- the GUI keeps the pointer */
    uint32_t ver;                      /* "v0.2.0test" (data offset), 0 = none known  */
    uint32_t boot, bin, err;           /* this boot; on at the next (not on the list); the write failed */
    uint32_t id, legacy;               /* its sup_id (0: none read); a NAME.OFF file (not switchable) */
    uint32_t sup;                      /* 1 + its index in the books when it loaded, else 0 */
    uint32_t version_x;                /* inline version's native position binding */
    char reserved[192];                /* 272-byte row stride retained */
};
struct ft6_tab {                       /* build_ft6.py data_file(): the same words  */
    uint32_t magic, pack_off, pack_len;
    uint32_t ui_off, n_ui;             /* FPUI blocks: {offset, bytes, first string#} */
    uint32_t n_str, soff_off;          /* STRBASE fills soff[string#]               */
    uint32_t n_refs, refs_off;         /* {pack offset, string#}: BE fields         */
    uint32_t n_vars, vars_off;         /* {type, name}: FT_Key, FT_<part><k> by part, FT_Focus */
    uint32_t txt[T_COUNT];             /* data offsets of the fixed texts           */
    uint32_t rows_off;                 /* FT6_ROWS x struct ft6_row, zero in the file */
    uint32_t n_prod, prod_off;         /* {sup_id, name, version, version_x}         */
    uint32_t logo_off, logo_len;       /* own NBR reader: retain its image filename pool */
    uint32_t stock[4];                 /* GUI site, then the three string sites     */
    char machine[12];                  /* "TransFtTab": no .rodata here             */
    uint32_t status, ven, rd, app, mach, ui_result, ui_op;
    uint32_t n_rows, fobj, keys;       /* run time                                  */
    uint32_t st, path;                 /* the loader's state; "\fpSup\LOADER.BIN"     */
    uint32_t page;                     /* zero-based, focus stays on the title */
    char pager[64];                    /* persistent: POST_STR borrows its pointer */
    uint32_t popup, selected[FT6_VISIBLE], header;
};

typedef uint32_t (*fn3)(uint32_t, uint32_t, uint32_t);
typedef uint32_t (*fn4)(uint32_t, uint32_t, uint32_t, uint32_t);

static inline uint32_t rd32(uintptr_t a) { return *(volatile uint32_t *)a; }
static inline void wr32(uintptr_t a, uint32_t v) { *(volatile uint32_t *)a = v; }
static inline int bad(uintptr_t p) { return !p || (p & 3u); }

/* The page-id layer, ARM, called by `bl` through the veneer: r0 = the
 * CustomScreenLoader, r1 = the page name.  Only ip is touched on the way in.
 * ft6_next / ft6_ctx: words in .text (RAM), written at load. */
__asm__(
    ".text\n"
    ".balign 4\n"
    ".arm\n"
    "ft6_layer:\n"
    "    cmp     r1, #0\n"
    "    beq     1f\n"
    "    ldrb    ip, [r1]\n"
    "    cmp     ip, #0x46\n"              /* 'F' */
    "    ldrbeq  ip, [r1, #1]\n"
    "    cmpeq   ip, #0x54\n"              /* 'T' */
    "    ldrbeq  ip, [r1, #2]\n"
    "    cmpeq   ip, #0x5F\n"              /* '_' */
    "    moveq   r0, #21\n"                /* MainY5's GUI id (build_ft6.GUI_ID) */
    "    bxeq    lr\n"
    "1:  ldr     ip, ft6_next\n"
    "    bx      ip\n"
    "ft6_next:\n"
    "    .word   0\n"
    "ft6_ctx:\n"
    "    .word   0\n"
    ".thumb\n");
extern const uint8_t ft6_layer[];
extern const uint32_t ft6_next;      /* const: -fropi addresses it PC-relative */
extern const uint32_t ft6_ctx;       /* the data block, for allsups_key */

/* the FPUI block's hash (ui_apply.c fnv, FNV-1a) */
static uint32_t ft6_fnv(uintptr_t p, uint32_t n)
{
    uint32_t h = 2166136261u;
    for (uint32_t i = 0; i < n; ++i) h = (h ^ *(const volatile uint8_t *)(p + i)) * 16777619u;
    return h;
}

static uint32_t ft6_be(uint32_t v)
{
    return (v >> 24) | ((v >> 8) & 0xFF00u) | ((v << 8) & 0xFF0000u) | (v << 24);
}

static int ft6_same(uintptr_t a, const char *b)
{
    for (;; ++a, ++b) {
        if (*(const volatile uint8_t *)a != (uint8_t)*b) return 0;
        if (!*b) return 1;
    }
}

static char *ft6_cat(char *p, const char *s)
{
    while (*s) *p++ = *s++;
    *p = 0;
    return p;
}

static const char *ft6_text(uint8_t *block, uint32_t i)
{
    return (const char *)(block + ((struct ft6_tab *)block)->txt[i]);
}

static struct ft6_row *ft6_rows(uint8_t *block)
{
    return (struct ft6_row *)(block + ((struct ft6_tab *)block)->rows_off);
}

static const char *ft6_var(uint8_t *block, uint32_t i)
{
    struct ft6_tab *t = (struct ft6_tab *)block;
    return (const char *)(block + rd32((uintptr_t)(block + t->vars_off + 8u * i + 4u)));
}

/* variable index of cell k's part p (build_ft6.variables) */
/* the variables are registered red, green, name, grey, version (build_ft6
 * .VAR_PARTS): the posted ones first */
static uint32_t ft6_slot(uint32_t p)
{
    return p == P_RED ? 0u : p == P_GREEN ? 1u : p == P_NAME ? 2u : p == P_GREY ? 3u : 4u;
}
static uint32_t ft6_part_of(uint32_t slot)
{
    return slot == 0u ? P_RED : slot == 1u ? P_GREEN : slot == 2u ? P_NAME : slot == 3u ? P_GREY : P_VER;
}
/* 0 FT_Key, 1 FT_OK, then the cells' parts, FT_Focus last (build_ft6.variables) */
#define VAR_OK 1u
static uint32_t ft6_vi(uint32_t p, uint32_t k) { return 2u + ft6_slot(p) * FT6_VISIBLE + (k - 1u); }

/* What cell part p shows (the user 2026-10-07): the product's name white when
 * it loaded this boot, grey when not; small, its version; red "Unload on
 * restart" / "Load failed" / "Write failed", green "Load on restart" (the
 * texts: build_ft6.TEXTS).  A part not shown is " ". */
static const char *ft6_part(uint8_t *block, const struct ft6_row *r, uint32_t p)
{
    uint32_t t = T_BLANK;
    if (!r->base[0]) return ft6_text(block, T_BLANK);
    if (p == P_NAME) return r->boot == BOOT_ON ? r->disp : ft6_text(block, T_BLANK);
    if (p == P_GREY) return r->boot != BOOT_ON ? r->disp : ft6_text(block, T_BLANK);
    uint32_t red = r->err ? T_ERROR : r->boot == BOOT_ON && !r->bin ? T_UNLOAD
                 : r->boot == BOOT_FAILED && r->bin ? T_FAILED : T_BLANK;
    uint32_t green = !r->err && r->boot == BOOT_OFF && r->bin ? T_LOAD : T_BLANK;
    if (p == P_VER) return r->ver ? (const char *)(block + r->ver) : ft6_text(block, T_BLANK);
    if (p == P_RED)
        t = red;
    if (p == P_GREEN)
        t = green;
    return ft6_text(block, t);
}

/* The product's name and version by the sup_id in the file's header; a sup
 * the table does not know: its file name without the load-order digits. */
static void ft6_name(uint8_t *block, struct ft6_row *r, uint32_t id)
{
    struct ft6_tab *t = (struct ft6_tab *)block;
    const char *n = r->base;
    r->version_x = 49u;
    for (uint32_t i = 0; id && i < t->n_prod; i++) {
        uintptr_t e = (uintptr_t)(block + t->prod_off) + 16u * i;
        if (rd32(e) != id) continue;
        n = (const char *)(block + rd32(e + 4));
        r->ver = rd32(e + 8);
        r->version_x = rd32(e + 12);
        copy(r->disp, n, slen(n) + 1);
        return;
    }
    while (*n >= '0' && *n <= '9' && n[1]) n++;
    copy(r->disp, n, slen(n) + 1);
}

/* "\fpSup" + '\\' + base + ".BIN" / ".OFF" */
static void ft6_path(uint8_t *block, char *p, const struct ft6_row *r, uint32_t bin)
{
    p = ft6_cat(p, ft6_text(block, T_DIR));
    *p++ = 0x5C;
    p = ft6_cat(p, r->base);
    ft6_cat(p, ft6_text(block, bin ? T_BIN : T_OFF_EXT));
}

/* LOADER.BIN's disabled list (sloader.c DS_*): put `id` on it or take it off,
 * then write the file back whole -- the same length, so mode 7's no-truncate
 * cannot leave a tail.  1 = written. */
static uint32_t ft6_disable(struct ft6_tab *t, uint32_t id, uint32_t off)
{
    struct state *st = (struct state *)(uintptr_t)t->st;
    u32 *d = st ? st->dis : 0, n, i, ok, was[DS_MAX + 2];
    if (!d) return 2;
    if (!id) return 3;
    copy(was, d, DS_BYTES);
    n = d[1];
    for (i = 0; i < n && d[2 + i] != id; i++) {}
    if (off && i == n) {
        if (n == DS_MAX) return 4;
        d[2 + n] = id;
        d[1] = n + 1u;
    } else if (!off && i < n) {
        d[2 + i] = d[1 + n];
        d[1 + n] = 0;
        d[1] = n - 1u;
    }
    f_ctor((void *)(uintptr_t)t->fobj, DRIVE_SD);
    ok = f_create((void *)(uintptr_t)t->fobj, (const char *)(uintptr_t)t->path) ? 1u : 5u;
    if (ok == 1u) {
        ok = f_write((void *)(uintptr_t)t->fobj, st->file, st->file_len) != 0 ? 1u : 6u;
        f_close((void *)(uintptr_t)t->fobj);
    }
    f_dtor((void *)(uintptr_t)t->fobj);
    if (ok != 1u) copy(d, was, DS_BYTES);       /* the list stays what the card has */
    return ok;                                  /* 1 written; 2 no list, 3 no id, 4 full, 5 open, 6 write */
}

/* Variable layout shared with build_ft6.variables(). */
#define VAR_PAGE (2u + P_COUNT * FT6_VISIBLE)
#define VAR_VERSION (VAR_PAGE + 1u)
#define VAR_VISIBLE (VAR_VERSION + 1u)
#define VAR_LOCK (VAR_VISIBLE + FT6_VISIBLE)
#define VAR_SELECTED (VAR_LOCK + FT6_VISIBLE)
#define VAR_MORE (VAR_SELECTED + FT6_VISIBLE)
#define VAR_DEFAULT (VAR_MORE + FT6_VISIBLE)
#define VAR_CHOICE (VAR_DEFAULT + FT6_VISIBLE)
#define VAR_FOCUS (VAR_CHOICE + FT6_VISIBLE)
#define VAR_RIGHT_FOOTER (VAR_FOCUS + 3u)
#define VAR_VERSION_X (VAR_RIGHT_FOOTER + 1u)
#define FT6_TABS ((FT6_ROWS + FT6_VISIBLE - 1u) / FT6_VISIBLE)
#define VAR_TAB_VISIBLE (VAR_VERSION_X + FT6_VISIBLE)
#define VAR_TAB_ACTIVE (VAR_TAB_VISIBLE + FT6_TABS)
#define VAR_TAB_X (VAR_TAB_ACTIVE + FT6_TABS)
#define VAR_TAB_WIDTH (VAR_TAB_X + FT6_TABS)
#define HEADER_FOCUS 3451u

static uint32_t ft6_tabvalue(struct ft6_tab *t, uint32_t i)
{
    uint32_t n = 1u + (t->n_rows ? (t->n_rows - 1u) / FT6_VISIBLE : 0u);
    /* Cortex-A9's standalone loader has no runtime division library. */
    uint32_t width = n == 1u ? 1024u : n == 2u ? 512u : n == 3u ? 341u
                   : n == 4u ? 256u : n == 5u ? 204u : n == 6u ? 170u : 146u;
    uint32_t group = (i - VAR_TAB_VISIBLE) / FT6_TABS;
    uint32_t k = (i - VAR_TAB_VISIBLE) % FT6_TABS;
    return group == 0u ? k < n
         : group == 1u ? k == t->page
         : group == 2u ? width * k
         : k + 1u == n ? 1024u - width * k : width;
}

static struct ft6_row *ft6_visible(uint8_t *block, uint32_t k)
{
    struct ft6_tab *t = (struct ft6_tab *)block;
    uint32_t i = t->page * FT6_VISIBLE + k - 1u;
    return k && k <= FT6_VISIBLE && i < t->n_rows ? &ft6_rows(block)[i] : 0;
}

static uint32_t ft6_more(struct ft6_tab *t, struct ft6_row *r)
{
    struct state *st = (struct state *)(uintptr_t)t->st;
    return r && r->bin && r->boot == BOOT_ON && r->sup && st->btn_fn[r->sup - 1u];
}

static uint32_t ft6_meta(uint8_t *block, uint32_t group, uint32_t k)
{
    struct ft6_tab *t = (struct ft6_tab *)block;
    struct ft6_row *r = ft6_visible(block, k);
    return group == VAR_VISIBLE ? !!r
         : group == VAR_LOCK ? (!r || !r->id || r->legacy)
         : group == VAR_MORE ? !!ft6_more(t, r)
         : (r && !r->bin ? 1u : 0u);
}

/* Audio's two choices: only enabled+loaded providers get a Right hint. */
static void ft6_hint(uint8_t *block)
{
    struct ft6_tab *t = (struct ft6_tab *)block;
    uint32_t more = 0;
    for (uint32_t k = 1; k <= FT6_VISIBLE; k++) {
        uint32_t eligible = !!ft6_more(t, ft6_visible(block, k));
        if (t->popup == k) {
            eligible = eligible && t->selected[k - 1u] == 0u;
            more = eligible;
        }
        FW(POST_INT, fn3)(0, (uint32_t)(uintptr_t)ft6_var(block, VAR_MORE + k - 1u), eligible);
    }
    FW(POST_STR, fn3)(0, (uint32_t)(uintptr_t)ft6_var(block, VAR_OK),
        (uint32_t)(uintptr_t)ft6_text(block, t->popup ? T_POPUP_FOOTER : t->header ? T_PAGE_HINT : T_FOOTER));
    FW(POST_STR, fn3)(0, (uint32_t)(uintptr_t)ft6_var(block, VAR_RIGHT_FOOTER),
        (uint32_t)(uintptr_t)ft6_text(block, more ? T_MORE_HINT : T_BLANK));
    FW(POST_STR, fn3)(0, (uint32_t)(uintptr_t)ft6_var(block, VAR_VERSION),
        (uint32_t)(uintptr_t)ft6_text(block, more ? T_BLANK : T_VERSION));
}

static uint32_t ft6_selected(uintptr_t desc, uint32_t k)
{
    uint8_t *block = (uint8_t *)(uintptr_t)ft6_ctx;
    if (!block) return 0;
    struct ft6_tab *t = (struct ft6_tab *)block;
    t->selected[k - 1u] = rd32(desc + DESC_VALUE);
    ft6_hint(block);
    return 0;
}
static uint32_t allsups_selected1(uintptr_t d) { return ft6_selected(d, 1); }
static uint32_t allsups_selected2(uintptr_t d) { return ft6_selected(d, 2); }
static uint32_t allsups_selected3(uintptr_t d) { return ft6_selected(d, 3); }
static uint32_t allsups_selected4(uintptr_t d) { return ft6_selected(d, 4); }
static uint32_t allsups_selected5(uintptr_t d) { return ft6_selected(d, 5); }

static uint32_t allsups_focus(uintptr_t desc)
{
    uint8_t *block = (uint8_t *)(uintptr_t)ft6_ctx;
    if (!block) return 0;
    ((struct ft6_tab *)block)->header = rd32(desc + DESC_VALUE) == HEADER_FOCUS;
    ft6_hint(block);
    return 0;
}

static void ft6_pager(struct ft6_tab *t)
{
    char *p = t->pager;
    if (t->n_rows <= FT6_VISIBLE) {
        *p++ = ' '; *p = 0;
        return;
    }
    *p++ = '1' + t->page; *p++ = ' '; *p++ = '/'; *p++ = ' ';
    *p++ = '1' + (t->n_rows ? (t->n_rows - 1u) / FT6_VISIBLE : 0u);
    *p = 0;
}

static void ft6_refresh(uint8_t *block)
{
    struct ft6_tab *t = (struct ft6_tab *)block;
    ft6_pager(t);
    FW(POST_STR, fn3)(0, (uint32_t)(uintptr_t)ft6_var(block, VAR_PAGE), (uint32_t)(uintptr_t)t->pager);
    for (uint32_t i = VAR_TAB_VISIBLE; i < VAR_TAB_WIDTH + FT6_TABS; i++)
        FW(POST_INT, fn3)(0, (uint32_t)(uintptr_t)ft6_var(block, i), ft6_tabvalue(t, i));
    for (uint32_t k = 1; k <= FT6_VISIBLE; k++) {
        struct ft6_row *r = ft6_visible(block, k);
        FW(POST_INT, fn3)(0, (uint32_t)(uintptr_t)ft6_var(block, VAR_VERSION_X + k - 1u),
                         r ? r->version_x : 49u);
        for (uint32_t p = 0; p < P_COUNT; p++)
            FW(POST_STR, fn3)(0, (uint32_t)(uintptr_t)ft6_var(block, ft6_vi(p, k)),
                             (uint32_t)(uintptr_t)(r ? ft6_part(block, r, p) : ft6_text(block, T_BLANK)));
        for (uint32_t g = VAR_VISIBLE; g <= VAR_DEFAULT; g += FT6_VISIBLE)
            FW(POST_INT, fn3)(0, (uint32_t)(uintptr_t)ft6_var(block, g + k - 1u), ft6_meta(block, g, k));
        t->selected[k - 1u] = ft6_meta(block, VAR_SELECTED, k);
    }
    ft6_hint(block);
}

/* Only title Left/Right writes FT_Key. Sup Right/OK opens a native popup. */
static uint32_t allsups_key(uintptr_t desc)
{
    uint8_t *block = (uint8_t *)(uintptr_t)ft6_ctx;
    if (!block) return 0;
    struct ft6_tab *t = (struct ft6_tab *)block;
    uint32_t key = rd32(desc + DESC_VALUE);
    uint32_t last = t->n_rows ? (t->n_rows - 1u) / FT6_VISIBLE : 0u;
    if (key == 30u || key == 31u) {
        t->header = key == 31u;
        t->popup = 0;
        ft6_hint(block);
        FW(POST_INT, fn3)(0, (uint32_t)(uintptr_t)ft6_var(block, 0), 0);
        return 0;
    }
    if (key >= 20u && key <= 20u + FT6_VISIBLE) {
        t->popup = key - 20u;
        ft6_hint(block);
        FW(POST_INT, fn3)(0, (uint32_t)(uintptr_t)ft6_var(block, 0), 0);
        return 0;
    }
    if (key != 10u && key != 11u) return 0;
    if (key == 10u && t->page) t->page--;
    if (key == 11u && t->page < last) t->page++;
    ft6_refresh(block);
    FW(POST_INT, fn3)(0, (uint32_t)(uintptr_t)ft6_var(block, 0), 0);
    return 0;
}

static uint32_t ft6_choice(uintptr_t desc, uint32_t k)
{
    uint8_t *block = (uint8_t *)(uintptr_t)ft6_ctx;
    if (!block) return 0;
    struct ft6_tab *t = (struct ft6_tab *)block;
    struct ft6_row *r = ft6_visible(block, k);
    uint32_t choice = rd32(desc + DESC_VALUE), rc = 0;
    if (r && r->id && !r->legacy) {
        if (choice <= 1u) {                  /* explicit Enable / Disable, never toggle */
            if (r->bin == choice || r->err) {
                rc = ft6_disable(t, r->id, choice);
                r->err = rc != 1u;
                if (!r->err) r->bin = !choice;
                t->keys++;
            }
        } else if (choice == 2u && t->selected[k - 1u] == 0u && ft6_more(t, r)) {
            struct state *st = (struct state *)(uintptr_t)t->st;
            int ret = st->btn_fn[r->sup - 1u](st->btn_arg[r->sup - 1u]);
            rc = 2000u + t->page * FT6_VISIBLE + k + (uint32_t)(ret * 100);
        }
    }
    ft6_refresh(block);
    FW(POST_INT, fn3)(0, (uint32_t)(uintptr_t)ft6_var(block, VAR_CHOICE + k - 1u), 255u);
    FW(POST_INT, fn3)(0, (uint32_t)(uintptr_t)ft6_var(block, 0), rc);
    return 0;
}
static uint32_t allsups_choice1(uintptr_t d) { return ft6_choice(d, 1); }
static uint32_t allsups_choice2(uintptr_t d) { return ft6_choice(d, 2); }
static uint32_t allsups_choice3(uintptr_t d) { return ft6_choice(d, 3); }
static uint32_t allsups_choice4(uintptr_t d) { return ft6_choice(d, 4); }
static uint32_t allsups_choice5(uintptr_t d) { return ft6_choice(d, 5); }

/* Every *.BIN and *.OFF in \fpSup but this loader, sorted, at most FT6_ROWS.
 * Visible UI slots are independent of this storage bound. */
static uint32_t ft6_list(struct state *st, uint8_t *block, u8 *s)
{
    struct ft6_row *rows = ft6_rows(block);
    const char *self = st->sups[st->cur].name;
    uint32_t n = 0;
    void *holder = s + S_HOLDER;
    u8 *ent = s + S_ENTRY;
    dir_ctor(holder, DRIVE_SD);
    if (!dir_open(holder, ft6_text(block, T_DIR))) { dir_dtor(holder); return 0; }
    for (;;) {
        zero(ent, DIR_ENTRY);
        if (!dir_next(holder, ent)) break;
        if (ent[0x218] & (ATTR_DIR | ATTR_HIDDEN)) continue;
        char name[NAME_MAX];
        u32 i = 0, ok = 1;
        for (;; i++) {
            u16 c = (u16)(ent[2 * i] | (ent[2 * i + 1] << 8));
            if (!c) break;
            if (i == NAME_MAX - 1 || c > 0x7E || c < 0x20 || c == '\\') { ok = 0; break; }
            name[i] = (char)c;
        }
        name[i < NAME_MAX ? i : NAME_MAX - 1] = 0;
        if (!ok || i < 5 || i - 4 >= sizeof rows[0].base || name[0] == '.' || !ncmp(name, self)) continue;
        uint32_t bin = !ncmp(name + i - 4, ft6_text(block, T_BIN));
        if (!bin && ncmp(name + i - 4, ft6_text(block, T_OFF_EXT))) continue;
        if (n == FT6_ROWS) continue;
        struct ft6_row *r = &rows[n++];
        zero(r, sizeof *r);
        copy(r->base, name, i - 4);
        r->bin = bin;
        r->legacy = !bin;
        r->boot = bin ? BOOT_FAILED : BOOT_OFF;
        if (bin)
            for (u32 j = 0; j < st->nsups; j++)
                if (j != st->cur && st->sups[j].state == SL_KEEP && !ncmp(st->sups[j].name, name)) {
                    r->boot = BOOT_ON;
                    r->sup = j + 1u;
                }
    }
    dir_dtor(holder);
    for (u32 i = 1; i < n; i++)                     /* insertion sort, as list_dir */
        for (u32 j = i; j && ncmp(rows[j - 1].base, rows[j].base) > 0; j--) {
            struct ft6_row tmp;
            copy(&tmp, &rows[j], sizeof tmp);
            copy(&rows[j], &rows[j - 1], sizeof tmp);
            copy(&rows[j - 1], &tmp, sizeof tmp);
        }
    /* the names: each file's sup_id, from its header (none open while the
     * directory was listed) */
    for (u32 i = 0; i < n; i++) {
        char path[64];
        struct sl_header *h = (struct sl_header *)(s + S_HDR);
        ft6_path(block, path, &rows[i], rows[i].bin);
        zero(h, sizeof *h);
        u32 got = read_file(s, path, h, sizeof *h);
        rows[i].id = got == sizeof *h && h->magic == SL_MAGIC ? h->sup_id : 0u;
        ft6_name(block, &rows[i], rows[i].id);
        if (rows[i].bin && rows[i].id && st->dis)       /* on the list: off this boot and the next */
            for (u32 j = 0; j < st->dis[1]; j++)
                if (st->dis[2 + j] == rows[i].id) { rows[i].boot = BOOT_OFF; rows[i].bin = 0; }
    }
    for (u32 i = n; i < FT6_ROWS; i++) zero(&rows[i], sizeof rows[i]);    /* past the list: blank */
    return n;
}

/* Fixed slot variables; page changes only replace values, never grow UI objects. */
static uint32_t ft6_variables(uint8_t *block, uintptr_t app)
{
    struct ft6_tab *t = (struct ft6_tab *)block;
    ft6_pager(t);
    for (uint32_t i = 0; i < t->n_vars; i++) {
        uint32_t def[3], value = 0;
        def[0] = rd32((uintptr_t)(block + t->vars_off + 8u * i));
        def[1] = (uint32_t)(uintptr_t)ft6_var(block, i);
        if (i >= 2u && i < VAR_PAGE) {
            struct ft6_row *r = ft6_visible(block, 1u + (i - 2u) % FT6_VISIBLE);
            value = (uint32_t)(uintptr_t)(r ? ft6_part(block, r, ft6_part_of((i - 2u) / FT6_VISIBLE)) : ft6_text(block, T_BLANK));
        } else if (i == VAR_PAGE) value = (uint32_t)(uintptr_t)t->pager;
        else if (i == VAR_VERSION) value = (uint32_t)(uintptr_t)ft6_text(block, T_VERSION);
        else if (i >= VAR_VISIBLE && i < VAR_CHOICE)
            value = ft6_meta(block, VAR_VISIBLE + ((i - VAR_VISIBLE) / FT6_VISIBLE) * FT6_VISIBLE,
                            1u + (i - VAR_VISIBLE) % FT6_VISIBLE);
        else if (i >= VAR_CHOICE && i < VAR_FOCUS) value = 255u;
        else if (i == VAR_RIGHT_FOOTER) value = (uint32_t)(uintptr_t)ft6_text(block, T_BLANK);
        else if (i >= VAR_VERSION_X && i < VAR_VERSION_X + FT6_VISIBLE) {
            struct ft6_row *r = ft6_visible(block, 1u + i - VAR_VERSION_X);
            value = r ? r->version_x : 49u;
        }
        else if (i >= VAR_TAB_VISIBLE && i < VAR_TAB_WIDTH + FT6_TABS)
            value = ft6_tabvalue(t, i);
        else if (i >= VAR_FOCUS) value = HEADER_FOCUS;
        else if (i == VAR_OK) value = (uint32_t)(uintptr_t)ft6_text(block, T_FOOTER);
        if (i >= VAR_SELECTED && i < VAR_SELECTED + FT6_VISIBLE)
            t->selected[i - VAR_SELECTED] = value;
        def[2] = value;
        if (FW(VAR_REGISTER, fn3)((uint32_t)app, 1, (uint32_t)(uintptr_t)def)) return 90u + i;
    }
    FW(VAR_SUBSCRIBE, fn3)(GUI_OBJECT_AT, (uint32_t)(uintptr_t)ft6_var(block, 0), (uint32_t)(uintptr_t)&allsups_key);
    for (uint32_t k = 0; k < FT6_VISIBLE; k++) {
        uintptr_t fn = k == 0 ? (uintptr_t)&allsups_choice1 : k == 1 ? (uintptr_t)&allsups_choice2
                     : k == 2 ? (uintptr_t)&allsups_choice3 : k == 3 ? (uintptr_t)&allsups_choice4
                     : (uintptr_t)&allsups_choice5;
        FW(VAR_SUBSCRIBE, fn3)(GUI_OBJECT_AT, (uint32_t)(uintptr_t)ft6_var(block, VAR_CHOICE + k), fn);
        fn = k == 0 ? (uintptr_t)&allsups_selected1 : k == 1 ? (uintptr_t)&allsups_selected2
           : k == 2 ? (uintptr_t)&allsups_selected3 : k == 3 ? (uintptr_t)&allsups_selected4
           : (uintptr_t)&allsups_selected5;
        FW(VAR_SUBSCRIBE, fn3)(GUI_OBJECT_AT, (uint32_t)(uintptr_t)ft6_var(block, VAR_SELECTED + k), fn);
    }
    FW(VAR_SUBSCRIBE, fn3)(GUI_OBJECT_AT, (uint32_t)(uintptr_t)ft6_var(block, VAR_FOCUS), (uint32_t)(uintptr_t)&allsups_focus);
    return 0;
}

static uint32_t ft6_register(uint8_t *block, struct ft6_tab *t)
{
    uintptr_t app = rd32(GUI_OBJECT_AT), screens, screen, reader, rdr = 0, data, last;
    uint32_t n0, n;
    t->app = app;
    if (bad(app)) return 3;
    if (!rd32(app + APP_SCREENS_N)) return 4;
    screens = rd32(app + APP_SCREENS);
    if (bad(screens)) return 4;
    screen = rd32(screens);
    if (bad(screen)) return 4;
    reader = rd32(screen + SCREEN_READER);
    if (bad(reader) || rd32(reader + READER_BASE) != NBU_BASE_AT || rd32(reader + READER_APP) != app)
        return 4;
    /* Image properties are decoded lazily. They must retain their own pool;
     * only the separate page reader below adopts the shared stock pool. */
    if (FW(NBR_LOAD, fn4)((uint32_t)app, (uint32_t)(uintptr_t)(block + t->logo_off), t->logo_len, 0))
        return 6;
    /* The stock NBR registrar grows its screen vector when needed (native
     * UI skill 8g). Reject corrupt bookkeeping, not a normal full vector:
     * the camera's observed 221/224 cannot hold all five pages without growth. */
    if (rd32(app + APP_SCREENS_N) > rd32(app + APP_SCREENS_CAP)) return 5;
    n0 = rd32(app + APP_MACH_N);
    if (n0 > rd32(app + APP_MACH_CAP)) return 5;    /* normal full vector grows natively */
    if (FW(NBR_LOAD, fn4)((uint32_t)app, (uint32_t)(uintptr_t)(block + t->pack_off), t->pack_len,
                          (uint32_t)(uintptr_t)&rdr))
        return 6;
    t->rd = rdr;
    if (bad(rdr)) return 7;
    wr32(rdr + READER_POOL_LEN, rd32(reader + READER_POOL_LEN));
    wr32(rdr + READER_POOL, rd32(reader + READER_POOL));
    n = rd32(app + APP_MACH_N);
    if (n != n0 + 1u) return 8;
    data = rd32(app + APP_MACH);
    last = rd32(data + 4u * (n - 1u));
    t->mach = last;
    if (bad(last) || !ft6_same(rd32(last + MACH_NAME), t->machine)) return 9;
    for (uint32_t i = n - 1u; i; --i) wr32(data + 4u * i, rd32(data + 4u * (i - 1u)));
    wr32(data, last);
    return 0;
}

/* no table: a const array would be .rodata, which LOADER.BIN does not have */
static uint32_t ft6_site(uint32_t i)
{
    return i == 0 ? GUI_SITE : i == 1 ? 0xC05E5B58u : i == 2 ? 0xC05E61C8u : 0xC05E61E0u;
}

static void ft6_report(const struct sl_svc *svc, struct ft6_tab *t, uint32_t s)
{
    char line[12];
    t->status = s;
    line[0] = 'F'; line[1] = 'T'; line[2] = '6'; line[3] = ' '; line[4] = 's'; line[5] = '=';
    line[8] = 0;
    line[6] = (char)('0' + (s / 10u) % 10u);
    line[7] = (char)('0' + s % 10u);
    svc->log(svc, line);
}

/* Every STRBASE's address -> &soff[first + its string#]; then the block's hash. */
static void ft6_relocate(uint8_t *block, struct ft6_tab *t, uintptr_t b, uint32_t first)
{
    uintptr_t p = b + 0x20u;
    uint32_t ns = rd32(b + 16), nw = rd32(b + 20);
    for (uint32_t i = 0; i < ns; i++) {
        uint32_t len = rd32(p + 4);
        p += 8u + ((len + 1u + 3u) & ~3u);
    }
    for (uint32_t i = 0; i < nw;) {
        uint32_t w = rd32(p + 4u * i), n = w & 0xFFFFFFu;
        if ((w >> 24) == 16u && n == 2u)
            wr32(p + 4u * (i + 2u),
                 (uint32_t)(uintptr_t)(block + t->soff_off) + 4u * (first + rd32(p + 4u * (i + 1u))));
        i += 1u + n;
    }
    wr32(b + 12, ft6_fnv(b + 0x20, rd32(b + 8) - 0x20));
}

static int allsups_entry(uint8_t *block, const struct sl_svc *svc)
{
    struct state *st = (struct state *)svc;
    struct ft6_tab *t = (struct ft6_tab *)block;            /* the data file starts with it */
    struct uia_outcome ui;
    uint32_t s, r;
    /* 1 */
    for (uint32_t i = 0; i < 4; ++i)
        if (svc->claim(svc, ft6_site(i), 4, &t->stock[i], i ? SL_SHARED_UI : SL_CHAIN) != SL_OK) {
            ft6_report(svc, t, 1);
            return SL_RELEASE;
        }
    if (!(t->ven = svc->cave_alloc(svc, 8))) {
        ft6_report(svc, t, 2);
        return SL_RELEASE;
    }
    u8 *scratch = mem_get(st->heap, S_CANDS);           /* file object, dir entry, path, header */
    t->fobj = (uint32_t)(uintptr_t)mem_get(st->heap, FILE_OBJECT_BYTES);
    if (!scratch || !t->fobj) {
        if (scratch) mem_free(st->heap, scratch);
        ft6_report(svc, t, 2);
        return SL_RELEASE;
    }
    /* 2: the blocks, one layer each; a block's offsets are in its order and
     * its STRBASE gave the first */
    uintptr_t soff = (uintptr_t)(block + t->soff_off);
    for (uint32_t i = 0; i < t->n_str; i++) wr32(soff + 4u * i, 0);
    for (uint32_t j = 0; j < t->n_ui; j++) {
        uintptr_t e = (uintptr_t)(block + t->ui_off) + 12u * j;
        uint32_t first = rd32(e + 8), end = j + 1u < t->n_ui ? rd32(e + 20) : t->n_str;
        ft6_relocate(block, t, (uintptr_t)(block + rd32(e)), first);
        r = uia_apply((uintptr_t)(block + rd32(e)), rd32(e + 4), &ui);
        t->ui_result = r;
        t->ui_op = ui.op;
        if (r != UIA_OK || !rd32(soff + 4u * first)) {
            mem_free(st->heap, scratch);
            ft6_report(svc, t, r != UIA_OK ? 10u + (r < 79u ? r : 79u) : 89u);
            return j || r == UIA_OK ? SL_KEEP : SL_RELEASE;   /* a layer up: keep it */
        }
        for (uint32_t i = first + 1u; i < end; i++) wr32(soff + 4u * i, rd32(soff + 4u * first) + (i - first));
    }
    /* 3 */
    for (uint32_t i = 0; i < t->n_refs; i++) {
        uintptr_t ref = (uintptr_t)(block + t->refs_off) + 8u * i;
        wr32((uintptr_t)(block + t->pack_off + rd32(ref)), ft6_be(rd32(soff + 4u * rd32(ref + 4))));
    }
    t->st = (uint32_t)(uintptr_t)st;
    t->path = (uint32_t)(uintptr_t)st->sups[st->cur].path;       /* "\fpSup\LOADER.BIN" */
    t->n_rows = ft6_list(st, block, scratch);
    mem_free(st->heap, scratch);
    wr32((uintptr_t)&ft6_ctx, (uint32_t)(uintptr_t)block);
    publish();
    s = ft6_variables(block, rd32(GUI_OBJECT_AT));
    if (!s) s = ft6_register(block, t);
    if (s && s != 8u && s != 9u) {
        ft6_report(svc, t, s);           /* no page: the string layer stays, unused */
        return SL_KEEP;
    }
    /* 5 */
    {
        uint32_t next = svc->chain_next(svc, GUI_SITE, 0);
        wr32((uintptr_t)&ft6_next, next ? next : GUI_NEXT0);
        wr32(t->ven, 0xE51FF004u);                       /* ldr pc, [pc, #-4] */
        wr32(t->ven + 4u, (uint32_t)(uintptr_t)ft6_layer);
        svc->publish(svc);
        wr32(GUI_SITE, 0xEB000000u | (((t->ven - GUI_SITE - 8u) >> 2) & 0x00FFFFFFu));
        svc->publish(svc);
    }
    ft6_report(svc, t, s);
    return SL_KEEP;
}
