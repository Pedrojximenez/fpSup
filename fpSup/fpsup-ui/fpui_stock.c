/* fpsup-ui: rows added to a STOCK menu page (SHOOT 2, TOOLS, ...), loader v4.
 *
 * uishare's ui_apply.c (the FPUI block format, uishare/ui/fpui.py, and its
 * composition rules) with the sharing of strings taken out: a private string's
 * id is its own address at the uncached alias, as fpsup_ui.c's are, so there
 * is no string layer, no pool and no hook of our own.  Two sups that add rows
 * to the same stock page still compose -- each serves the page from a copy of
 * whatever it is now (stock, or the copy another sup made, "FSPG" header) --
 * so a sup's row never needs to know who else is there.  Not here: QS_OPTION
 * (Quick Set is a container's job: res-custom brings its own).
 *
 *     struct uia_outcome o;
 *     if (fpui_stock_apply(svc, block, len, &o) == UIA_OK) ...   // from the entry
 *
 * `block` is the FPUI block at the cached alias (in the sup's own block when
 * SL_F_CACHED_OK); it is borrowed first (svc->borrow) and must stay resident.
 * #include it next to fpsup_ui.c: one -fropi unit, no data section. */
#ifndef FPUI_STOCK_LIB
#define FPUI_STOCK_LIB
#include <stdint.h>
#include "sloader4.h"

#define UIA_MAGIC     0x47505346u      /* "FSPG" */
#define UIA_VERSION   1u
#define UIA_HEADER    128u
#define UIA_COUNTERS  8u
#define UIA_MAX_SLOTS 8u

enum uia_result {
    UIA_OK = 0, UIA_BLOCK = 1,        /* not an FPUI v1 block, or damaged */
    UIA_NO_UI = 2,                    /* no reader / no such page entry */
    UIA_PAGE = 3,                     /* the page is neither stock nor a convention copy */
    UIA_GUARD = 4,                    /* the page does not hold what the block expects */
    UIA_NO_MEMORY = 5, UIA_STRING = 6, UIA_OP = 7, UIA_FULL = 8,
    UIA_HOOK = 9,                     /* the file-redirect site holds someone else's code */
    UIA_CONFLICT = 10                 /* two sups replace the same whole file */
};

struct uia_outcome {
    uint32_t result, op;              /* which op failed (index) */
    uint32_t first_id;                /* the block's first object id (last page) */
    uint32_t slots[UIA_MAX_SLOTS];    /* what ALLOC handed out, in order */
    uint32_t n_slots;
    uintptr_t page;                   /* the copy switched in (last page) */
};

/* Ver.5.02 runtime layout (fp-native-ui §8a, read from the camera):
 *   reader+A8 = number of runtime page entries, reader+AC = the entries,
 *   44 bytes each: +04 name (C string), +08 page offset from the NBU base. */
#define READER_ENTRIES 0xA8u
#define READER_TABLE   0xACu
#define ENTRY_BYTES    44u
#define ENTRY_NAME     0x04u
#define ENTRY_OFFSET   0x08u
#define NBU_BASE       0xC18C0460u
#define MAX_ENTRIES    512u

#define OP_PAGE        1u
#define OP_GUARD       2u
#define OP_INSERT      3u
#define OP_ADD32       4u
#define OP_ADDF        5u
#define OP_ALLOC       6u
#define OP_DONE        7u
#define OP_HOOK_FV     8u
#define OP_FILE        9u
#define OP_CSV_ADD     10u
#define OP_CSV_CELL    11u
#define OP_FILE_SET    12u
#define OP_FILE_DONE   13u
#define OP_EXPECT      14u
#define OP_SETSTR_SLOT 15u
#define OP_STRBASE     16u
/* 2026-10-06, QS_SHARE.md §9 (ui/fpui.py has the same numbers in one place) */
#define OP_QS_OPTION   17u
#define OP_IF_SLOT     18u
#define QS_OPTION_ARGS 16u
/* STRBASE returns string offsets, independently of the eight CSV row slots.
 * A text layout may need one offset for every string in the block. */
#define MAX_STRBASE    MAX_STRINGS
#define R_LOCAL_ID 1u
#define R_STRING   2u
#define R_SLOT_F32 3u
#define R_SLOT_U32 4u
#define NAME_STRING 0xFFFFFFFEu
#define MAX_STRINGS 64u
#define MAX_ARGS    24u
#define MAX_PAGES   4u
#define MAX_FILES   8u
#define FSHK        0x4B485346u          /* "FSHK": the shared file-redirect handler */
#define FSFV        0x56465346u          /* "FSFV": its table */

/* Firmware structures through volatile accesses; our own copies are ordinary
 * cached memory and are published (D-cache clean) before the switch. */
#define fst_peek(a) (*(volatile const uint32_t *)(a))
#define fst_poke(a, v) (*(volatile uint32_t *)(a) = (v))
#define fst_peek8(a) (*(const uint8_t *)(a))
#define fst_poke8(a, v) (*(uint8_t *)(a) = (uint8_t)(v))
/* The firmware allocator hands out the uncached alias; every copy is used at
 * the cached one (pages there are read ~50x faster, sup-code-runs-uncached)
 * and published before anyone is pointed at it. */
static uintptr_t fst_alloc(uint32_t n) {
    typedef void (*get_fn)(uint32_t *, uint32_t, uint32_t, uint32_t);
    typedef uintptr_t (*addr_fn)(uint32_t *);
    uint32_t desc[4] = {0, 0, 0, 0};
    uintptr_t p;
    ((get_fn)0xC001D740u)(desc, 0, n, 0);
    p = ((addr_fn)0xC001D7F0u)(desc);
    return p >= 0x40000000u && p < 0x80000000u ? p + SL_ALIAS : p;
}
static void fst_publish(void) { typedef void (*fn)(void); ((fn)0xC000E91Cu)(); }
static void fst_icache(void) { typedef void (*fn)(void); ((fn)0xC000EABCu)(); }

/* The UI's page reader (uishare ui_pool.c uis_reader). */
#define FST_GUI_OBJECT    0xC37B7048u
#define FST_SCREENS_COUNT 0x80u
#define FST_SCREENS_ARRAY 0x8Cu
#define FST_SCREEN_READER 0x24u
#define FST_READER_BASE   0x24u
#define FST_MAX_SCREENS   512u
static uintptr_t fst_reader(void) {
    uintptr_t app = fst_peek(FST_GUI_OBJECT), screens, screen, reader;
    uint32_t count;
    if (!app || (app & 3u)) return 0;
    count = fst_peek(app + FST_SCREENS_COUNT);
    screens = fst_peek(app + FST_SCREENS_ARRAY);
    if (!count || count > FST_MAX_SCREENS || !screens || (screens & 3u)) return 0;
    screen = fst_peek(screens);
    if (!screen || (screen & 3u)) return 0;
    reader = fst_peek(screen + FST_SCREEN_READER);
    if (!reader || (reader & 3u) || fst_peek(reader + FST_READER_BASE) != NBU_BASE) return 0;
    return reader;
}

/* ---- small helpers ------------------------------------------------------ */
static uint32_t fst_le(uintptr_t a) {
    return fst_peek8(a) | fst_peek8(a + 1) << 8 | fst_peek8(a + 2) << 16 | (uint32_t)fst_peek8(a + 3) << 24;
}
static uint32_t fst_be(uintptr_t a) {
    return (uint32_t)fst_peek8(a) << 24 | fst_peek8(a + 1) << 16 | fst_peek8(a + 2) << 8 | fst_peek8(a + 3);
}
static void fst_put_be(uintptr_t a, uint32_t v) {
    fst_poke8(a, v >> 24); fst_poke8(a + 1, v >> 16); fst_poke8(a + 2, v >> 8); fst_poke8(a + 3, v);
}
/* memmove, a word at a time wherever source and destination share their
 * alignment (pages are copied to the same alignment as their source, and the
 * firmware's records insert in whole words): a byte loop over 160 KB of page
 * costs a noticeable part of a second at boot. */
static void fst_move(uintptr_t to, uintptr_t from, uint32_t n) {
    if (to == from || !n) return;
    if (to < from || to >= from + n) {                  /* forward */
        if (!((to ^ from) & 3u)) {
            while (n && (to & 3u)) { fst_poke8(to, fst_peek8(from)); ++to; ++from; --n; }
            for (; n >= 4u; n -= 4u, to += 4u, from += 4u) fst_poke(to, fst_peek(from));
        }
        for (uint32_t i = 0; i < n; ++i) fst_poke8(to + i, fst_peek8(from + i));
    } else {                                            /* backward, overlapping */
        if (!((to ^ from) & 3u)) {
            while (n && ((to + n) & 3u)) { --n; fst_poke8(to + n, fst_peek8(from + n)); }
            for (; n >= 4u; n -= 4u) fst_poke(to + n - 4u, fst_peek(from + n - 4u));
        }
        while (n--) fst_poke8(to + n, fst_peek8(from + n));
    }
}
static uint32_t fst_fnv(uintptr_t p, uint32_t n) {
    uint32_t h = 2166136261u;
    for (uint32_t i = 0; i < n; ++i) h = (h ^ fst_peek8(p + i)) * 16777619u;
    return h;
}
static uint32_t fst_cstr_eq(uintptr_t a, uintptr_t b, uint32_t n) {
    for (uint32_t i = 0; i < n; ++i) if (fst_peek8(a + i) != fst_peek8(b + i)) return 0;
    return fst_peek8(a + n) == 0;
}

/* Integer-valued IEEE single floats, without float arithmetic. */
static uint32_t fst_f32_to_int(uint32_t w, int32_t *v) {
    uint32_t e = (w >> 23) & 0xFFu, m = (w & 0x7FFFFFu) | 0x800000u;
    int32_t r;
    if (!(w & 0x7FFFFFFFu)) { *v = 0; return 1; }
    if (e < 127u || e > 127u + 23u) return 0;                /* fraction or too big */
    if (m & ((1u << (23u - (e - 127u))) - 1u)) return 0;     /* not an integer */
    r = (int32_t)(m >> (23u - (e - 127u)));
    *v = (w & 0x80000000u) ? -r : r;
    return 1;
}
static uint32_t fst_int_to_f32(int32_t v, uint32_t *w) {
    uint32_t s = 0, m, e = 150u;
    if (v <= -(1 << 24) || v >= (1 << 24)) return 0;
    if (!v) { *w = 0; return 1; }
    if (v < 0) { s = 0x80000000u; m = (uint32_t)-v; } else m = (uint32_t)v;
    while (m < 0x800000u) { m <<= 1; --e; }
    *w = s | e << 23 | (m & 0x7FFFFFu);
    return 1;
}
static uint32_t fst_name_hash(uintptr_t s, uint32_t n) { uint32_t h = fst_fnv(s, n); return h ? h : 1u; }

/* Struct copies word by word: an assignment becomes a memcpy call, and the
 * camera build links nothing. */
static void fst_copy_words(void *to, const void *from, uint32_t bytes) {
    uint32_t *t = (uint32_t *)to;
    const uint32_t *f = (const uint32_t *)from;
    for (uint32_t i = 0; i < bytes / 4u; ++i) { volatile uint32_t v = f[i]; t[i] = v; }
}

/* ---- a page being built ---------------------------------------------------- */
struct uia_work {
    uintptr_t entry, page, deltas;        /* entry word owner; new page; its table */
    uint32_t len, cap, stock_len, next_id, n_deltas, max_deltas;
    uint32_t counters[UIA_COUNTERS][2];
    uint32_t first_id, active;
};

static uint32_t fst_current(const struct uia_work *w, uint32_t pos, uint32_t *at) {
    uint32_t c = pos;
    if (pos > w->stock_len) return 0;
    for (uint32_t i = 0; i < w->n_deltas; ++i)
        if (fst_peek(w->deltas + 8u * i) <= pos) c += fst_peek(w->deltas + 8u * i + 4u);
    if (c + 4u > w->len && c != w->len) return 0;
    *at = c;
    return 1;
}

/* The page's runtime entry, by name. */
static uintptr_t fst_find_entry(uintptr_t reader, uintptr_t name, uint32_t n) {
    uint32_t count = fst_peek(reader + READER_ENTRIES);
    uintptr_t table = fst_peek(reader + READER_TABLE);
    if (!count || count > MAX_ENTRIES || !table || (table & 3u)) return 0;
    for (uint32_t i = 0; i < count; ++i) {
        uintptr_t e = table + ENTRY_BYTES * i, s = fst_peek(e + ENTRY_NAME);
        if (s && fst_cstr_eq(s, name, n)) return e;
    }
    return 0;
}

static uint32_t fst_open_page(struct uia_work *w, uintptr_t name, uint32_t name_n, const uint32_t *a) {
    uintptr_t reader = fst_reader(), e, old, block, hdr;
    uint32_t old_len, old_next, old_n = 0, deltas_cap;
    if (!reader || !(e = fst_find_entry(reader, name, name_n))) return UIA_NO_UI;
    old = NBU_BASE + fst_peek(e + ENTRY_OFFSET);
    hdr = (old & ~3u) - UIA_HEADER;                      /* a copy's header, word-aligned */
    if (fst_peek(e + ENTRY_OFFSET) == a[1]) {                       /* the stock page */
        old_len = a[2]; old_next = a[3];
        for (uint32_t i = 0; i < UIA_COUNTERS; ++i) w->counters[i][0] = w->counters[i][1] = 0;
    } else if (fst_peek(hdr) == UIA_MAGIC && fst_peek(hdr + 4) == UIA_VERSION &&
               fst_peek(hdr + 16) == a[2]) {                       /* a convention copy */
        old_len = fst_peek(hdr + 12);
        old_next = fst_peek(hdr + 20);
        old_n = fst_peek(hdr + 24);
        if (old_next < a[3]) old_next = a[3];
        for (uint32_t i = 0; i < UIA_COUNTERS; ++i) {
            w->counters[i][0] = fst_peek(hdr + 36 + 8 * i);
            w->counters[i][1] = fst_peek(hdr + 40 + 8 * i);
        }
    } else {
        return UIA_PAGE;
    }
    if (old_next + a[4] > 0x10000u || old_n + a[6] < old_n) return UIA_FULL;
    deltas_cap = old_n + a[6];
    w->cap = old_len + a[5];
    block = fst_alloc(8u * deltas_cap + UIA_HEADER + 4u + w->cap);
    if (!block || (block & 7u)) return UIA_NO_MEMORY;
    w->deltas = block;
    w->page = block + 8u * deltas_cap + UIA_HEADER + (old & 3u);   /* the source's alignment */
    if (old_n) fst_move(w->deltas, fst_peek(hdr + 32), 8u * old_n);
    fst_move(w->page, old, old_len);
    w->entry = e;
    w->len = old_len;
    w->stock_len = a[2];
    w->first_id = old_next;
    w->next_id = old_next + a[4];
    w->n_deltas = old_n;
    w->max_deltas = deltas_cap;
    w->active = 1;
    return UIA_OK;
}

/* The copy's header; the entry is switched at commit. */
static void fst_close_page(struct uia_work *w) {
    uintptr_t h = (w->page & ~3u) - UIA_HEADER;
    fst_poke(h + 0, UIA_MAGIC); fst_poke(h + 4, UIA_VERSION); fst_poke(h + 8, w->cap);
    fst_poke(h + 12, w->len); fst_poke(h + 16, w->stock_len); fst_poke(h + 20, w->next_id);
    fst_poke(h + 24, w->n_deltas); fst_poke(h + 28, w->max_deltas); fst_poke(h + 32, w->deltas);
    for (uint32_t i = 0; i < UIA_COUNTERS; ++i) {
        fst_poke(h + 36 + 8 * i, w->counters[i][0]); fst_poke(h + 40 + 8 * i, w->counters[i][1]);
    }
    for (uint32_t o = 36 + 8 * UIA_COUNTERS; o < UIA_HEADER; o += 4) fst_poke(h + o, 0);
    w->active = 0;
}

/* ---- files: the shared redirect table --------------------------------------- */
struct uia_file {
    uintptr_t buf;
    uint32_t stock, len, cap, rows_before, appended, active;
};

/* The table the handler at `site` reads: found if another sup installed it,
 * else installed now from the handler code in the block. a: site, stock word,
 * capacity, fragment offset, length, entry offset, cave bump word, arena end,
 * veneer word, offset of the handler's table word. */
static uint32_t fst_hook_fv(const uint32_t *a, uintptr_t frag, uint32_t nf, uintptr_t *table) {
    uintptr_t site = a[0], block, entry, veneer, bump;
    uint32_t w = fst_peek(site), off, hw1, hw2, s, j1, j2, i1, i2;
    if (w != a[1]) {                                     /* someone's B.W: ours? */
        hw1 = w & 0xFFFFu; hw2 = w >> 16;
        if ((hw1 & 0xF800u) != 0xF000u || (hw2 & 0xD000u) != 0x9000u) return UIA_HOOK;
        s = (hw1 >> 10) & 1u; j1 = (hw2 >> 13) & 1u; j2 = (hw2 >> 11) & 1u;
        i1 = 1u ^ (j1 ^ s); i2 = 1u ^ (j2 ^ s);
        off = s << 24 | i1 << 23 | i2 << 22 | (hw1 & 0x3FFu) << 12 | (hw2 & 0x7FFu) << 1;
        if (s) off |= 0xFE000000u;
        veneer = site + 4u + off;
        if (veneer & 3u || fst_peek(veneer) != a[8]) return UIA_HOOK;
        entry = fst_peek(veneer + 4);
        if ((entry & 3u) || fst_peek(entry - a[5]) != FSHK || fst_peek(entry - a[5] + 4) != 1u)
            return UIA_HOOK;
        *table = fst_peek(entry - a[5] + a[9]);
        if (!*table || (*table & 3u) || fst_peek(*table) != FSFV || fst_peek(*table + 4) != 1u)
            return UIA_HOOK;
        return UIA_OK;
    }
    if (a[3] > nf || a[4] > nf - a[3] || a[4] < 16u || a[5] >= a[4] || a[9] + 4u > a[4] ||
        !a[2] || a[2] > 256u)
        return UIA_OP;
    bump = fst_peek(a[6]);
    if ((bump & 3u) || bump + 8u > a[7] || bump < a[6]) return UIA_FULL;
    block = fst_alloc(((a[4] + 3u) & ~3u) + 16u + 12u * a[2]);
    if (!block || (block & 7u)) return UIA_NO_MEMORY;
    fst_move(block, frag + a[3], a[4]);
    *table = block + ((a[4] + 3u) & ~3u);
    fst_poke(*table, FSFV); fst_poke(*table + 4, 1u); fst_poke(*table + 8, 0u); fst_poke(*table + 12, a[2]);
    fst_poke(block + a[9], *table);
    entry = block + a[5];
    fst_poke(a[6], bump + 8u);                               /* the veneer is ours */
    fst_poke(bump, a[8]); fst_poke(bump + 4, entry);             /* ldr.w pc, [pc, #0]; entry (ARM) */
    fst_publish(); fst_icache();
    off = bump - (site + 4u);
    s = off >> 31; i1 = (off >> 23) & 1u; i2 = (off >> 22) & 1u;
    j1 = (1u ^ i1) ^ s; j2 = (1u ^ i2) ^ s;
    hw1 = 0xF000u | s << 10 | ((off >> 12) & 0x3FFu);
    hw2 = 0x9000u | j1 << 13 | j2 << 11 | ((off >> 1) & 0x7FFu);
    fst_poke(site, hw1 | hw2 << 16);                         /* B.W veneer */
    fst_publish(); fst_icache();
    return UIA_OK;
}

static uint32_t fst_table_find(uintptr_t table, uint32_t stock, uint32_t *copy, uint32_t *size) {
    uint32_t n = fst_peek(table + 8);
    for (uint32_t i = 0; i < n; ++i)
        if (fst_peek(table + 16 + 12 * i) == stock) {
            *copy = fst_peek(table + 20 + 12 * i); *size = fst_peek(table + 24 + 12 * i);
            return 1;
        }
    return 0;
}

/* CSV text: data rows (every non-empty line after the header). */
static uint32_t fst_csv_rows(const struct uia_file *f) {
    uint32_t rows = 0, start = 1;
    for (uint32_t i = 0; i < f->len; ++i) {
        uint32_t c = fst_peek8(f->buf + i);
        if (c == '\n') { start = 1; continue; }
        if (c == '\r') continue;
        if (start) { rows++; start = 0; }
    }
    return rows ? rows - 1u : 0u;                       /* the header is not a row */
}
static uint32_t fst_csv_crlf(const struct uia_file *f) {
    for (uint32_t i = 0; i + 1 < f->len; ++i)
        if (fst_peek8(f->buf + i) == '\r' && fst_peek8(f->buf + i + 1) == '\n') return 1;
    return 0;
}
/* Template expansion: {N} = n, {P} = n - 1, {Q} = n - 2. Returns bytes or 0. */
static uint32_t fst_expand(uintptr_t tpl, uint32_t tn, uint32_t n, char *out, uint32_t cap) {
    uint32_t o = 0;
    for (uint32_t i = 0; i < tn; ++i) {
        uint32_t c = fst_peek8(tpl + i);
        if (c == '{' && i + 2 < tn && fst_peek8(tpl + i + 2) == '}') {
            uint32_t k = fst_peek8(tpl + i + 1), v, d = 1;
            if (k == 'N') v = n; else if (k == 'P') v = n - 1u; else if (k == 'Q') v = n - 2u; else return 0;
            if (v > 9999u) return 0;
            for (uint32_t t = 0, lead = 1; t < 4u; ++t) {     /* no divide on a Cortex-A9 */
                uint32_t digit = 0;
                { uint32_t ten = t == 0u ? 1000u : t == 1u ? 100u : t == 2u ? 10u : 1u;
                  while (v >= ten) { v -= ten; ++digit; } }
                if (lead && digit == 0u && t < 3u) continue;
                lead = 0;
                if (o >= cap) return 0;
                out[o++] = (char)('0' + digit);
            }
            (void)d;
            i += 2;
        } else {
            if (o >= cap) return 0;
            out[o++] = (char)c;
        }
    }
    return o;
}
static uint32_t fst_file_append(struct uia_file *f, const char *s, uint32_t n) {
    if (f->len + n > f->cap) return 0;
    for (uint32_t i = 0; i < n; ++i) fst_poke8(f->buf + f->len + i, (uint8_t)s[i]);
    f->len += n;
    return 1;
}
static uint32_t fst_csv_add(struct uia_file *f, uintptr_t tpl, uint32_t tn, uint32_t *index) {
    char line[96], eol[2] = {'\r', '\n'};             /* no string literal: no .rodata */
    uint32_t rows = fst_csv_rows(f), n, crlf = fst_csv_crlf(f);
    if (!f->appended) { f->rows_before = rows; f->appended = 1; }
    if (f->len && fst_peek8(f->buf + f->len - 1) != '\n')
        if (!(crlf ? fst_file_append(f, eol, 2) : fst_file_append(f, eol + 1, 1))) return UIA_FULL;
    if (!(n = fst_expand(tpl, tn, rows + 1u, line, sizeof line))) return UIA_OP;
    if (!fst_file_append(f, line, n) || !(crlf ? fst_file_append(f, eol, 2) : fst_file_append(f, eol + 1, 1)))
        return UIA_FULL;
    *index = rows;                                      /* the new row, 0-based */
    return UIA_OK;
}
/* Replace column `col` of data row `row` (1-based). */
static uint32_t fst_csv_cell(struct uia_file *f, uint32_t row, uint32_t col, uintptr_t tpl, uint32_t tn) {
    char cell[32];
    uint32_t n, line = 0, start = 1, i = 0, from, to, c, k;
    if (!(n = fst_expand(tpl, tn, fst_csv_rows(f), cell, sizeof cell))) return UIA_OP;
    for (; i < f->len; ++i) {                           /* the start of data row `row` */
        c = fst_peek8(f->buf + i);
        if (c == '\n') { start = 1; continue; }
        if (c == '\r') continue;
        if (start) { if (line == row) break; line++; start = 0; }
    }
    if (i >= f->len) return UIA_OP;
    for (k = 0; k < col; ++k) {                         /* to the column */
        while (i < f->len && fst_peek8(f->buf + i) != ',' && fst_peek8(f->buf + i) != '\r' &&
               fst_peek8(f->buf + i) != '\n') ++i;
        if (i >= f->len || fst_peek8(f->buf + i) != ',') return UIA_OP;
        ++i;
    }
    from = to = i;
    while (to < f->len && fst_peek8(f->buf + to) != ',' && fst_peek8(f->buf + to) != '\r' &&
           fst_peek8(f->buf + to) != '\n') ++to;
    if (f->len - (to - from) + n > f->cap) return UIA_FULL;
    fst_move(f->buf + from + n, f->buf + to, f->len - to);
    for (k = 0; k < n; ++k) fst_poke8(f->buf + from + k, (uint8_t)cell[k]);
    f->len = f->len - (to - from) + n;
    return UIA_OK;
}

/* ---- the block ------------------------------------------------------------ */
/* A stock string where the builder says the stock pool has it (checked, as
 * uishare's uis_stock_has); the reader's pool is the stock one under v4. */
#define FST_READER_LEN   0x10u
#define FST_READER_POOL  0x14u
#define FST_NOT_STOCK    0xFFFFFFFFu
static uint32_t fst_stock_has(uintptr_t s, uint32_t n, uint32_t at) {
    uintptr_t reader = fst_reader(), pool;
    uint32_t len;
    if (!s || !n || !reader || at == FST_NOT_STOCK) return 0;
    pool = fst_peek(reader + FST_READER_POOL);
    len = fst_peek(reader + FST_READER_LEN);
    if (!pool || at >= len || n >= len - at) return 0;
    for (uint32_t k = 0; k < n; ++k) if (fst_peek8(pool + at + k) != fst_peek8(s + k)) return 0;
    return fst_peek8(pool + at + n) == 0;
}

/* svc: only a block with a private string needs it (borrow); 0 refuses one. */
static uint32_t fst_apply(uintptr_t b, uint32_t bytes, struct uia_outcome *out,
                          const struct sl_svc *svc) {
    uintptr_t str_at[MAX_STRINGS], ops, frag, table = 0;
    uint32_t str_n[MAX_STRINGS], str_hint[MAX_STRINGS], str_off[MAX_STRINGS];
    uint32_t sb_at[MAX_STRBASE], sb_off[MAX_STRBASE], n_sb = 0;
    uint32_t total, ns, nw, nf, cur, i, n_pages = 0, n_files = 0;
    struct uia_work w, pages[MAX_PAGES];
    struct uia_file f, files[MAX_FILES];
    uint32_t skip = 0;
    w.active = 0; f.active = 0;
    out->result = UIA_BLOCK; out->op = 0; out->first_id = 0; out->n_slots = 0; out->page = 0;
    if (!b || bytes < 0x20u || fst_le(b) != 0x49555046u || fst_le(b + 4) != 1u || fst_le(b + 28) != 0)
        return UIA_BLOCK;
    total = fst_le(b + 8); ns = fst_le(b + 16); nw = fst_le(b + 20); nf = fst_le(b + 24);
    if (total < 0x20u || total > bytes || fst_fnv(b + 0x20, total - 0x20) != fst_le(b + 12) ||
        ns > MAX_STRINGS)
        return UIA_BLOCK;
    cur = 0x20;
    for (i = 0; i < ns; ++i) {
        uint32_t n;
        if (cur + 8u > total) return UIA_BLOCK;
        str_hint[i] = fst_le(b + cur); n = fst_le(b + cur + 4);
        if (!n || n >= 64u || cur + 8u + n + 1u > total || fst_peek8(b + cur + 8 + n)) return UIA_BLOCK;
        for (uint32_t k = 0; k < n; ++k) if (!fst_peek8(b + cur + 8 + k)) return UIA_BLOCK;
        str_at[i] = b + cur + 8; str_n[i] = n;
        cur += (8u + n + 1u + 3u) & ~3u;
    }
    if (nw > (total - cur) / 4u) return UIA_BLOCK;
    ops = b + cur;
    frag = ops + 4u * nw;
    if (nf > total - cur - 4u * nw) return UIA_BLOCK;

    /* A stock string keeps its stock offset (the builder's hint, checked).
     * Every other string's id is its own address at the uncached alias:
     * LOADER.BIN's resolve hook maps any id in [0x40000000, 0x80000000) back
     * to the cached address (fpsup_ui.c).  No layer, no search.  Such a
     * block must sit at the cached alias and is borrowed (svc->borrow) before
     * any op, so the firmware never frees its strings. */
    {
        uint32_t priv = 0;
        for (i = 0; i < ns; ++i) {
            if (str_hint[i] == NAME_STRING) { str_off[i] = 0xFFFFFFFFu; continue; }
            if (fst_stock_has(str_at[i], str_n[i], str_hint[i])) { str_off[i] = str_hint[i]; continue; }
            str_off[i] = (uint32_t)(str_at[i] - SL_ALIAS);
            priv = 1;
        }
        if (priv && (b < 0xC0000000u || !svc || svc->version < 6u || !svc->borrow ||
                     svc->borrow(svc, (const void *)b, (const void *)(b + total)) != SL_OK))
            return out->result = UIA_STRING;
    }

    for (uint32_t k = 0, index = 0; k < nw; ++index) {
        uint32_t head = fst_le(ops + 4u * k), code = head >> 24, n = head & 0xFFFFFFu, r = UIA_OK;
        uintptr_t a = ops + 4u * (k + 1u);
        uint32_t args[MAX_ARGS];
        out->op = index;
        if (n > nw - k - 1u) return out->result = UIA_BLOCK;
        for (i = 0; i < n && i < MAX_ARGS; ++i) args[i] = fst_le(a + 4u * i);
        if (skip) { skip--; k += 1u + n; continue; }
        if (code == OP_PAGE) {
            if (w.active || f.active || n != 7u || args[0] >= ns || str_hint[args[0]] != NAME_STRING ||
                n_pages >= MAX_PAGES)
                return out->result = UIA_OP;
            r = fst_open_page(&w, str_at[args[0]], str_n[args[0]], args);
        } else if (code == OP_HOOK_FV) {
            if (n != 10u || table) r = UIA_OP;
            else r = fst_hook_fv(args, frag, nf, &table);
        } else if (code == OP_FILE) {
            uint32_t copy = args[0], size = args[1];
            if (w.active || f.active || !table || n != 3u || n_files >= MAX_FILES ||
                args[2] > 0x10000u) { r = UIA_OP; goto done; }
            for (i = 0; i < n_files; ++i) if (files[i].stock == args[0]) { r = UIA_OP; goto done; }
            fst_table_find(table, args[0], &copy, &size);
            f.cap = size + args[2];
            f.buf = fst_alloc(f.cap + 4u);
            if (!f.buf) { r = UIA_NO_MEMORY; goto done; }
            fst_move(f.buf, copy, size);
            f.stock = args[0]; f.len = size; f.appended = 0; f.rows_before = 0; f.active = 1;
        } else if (code == OP_CSV_ADD || code == OP_CSV_CELL || code == OP_FILE_SET ||
                   code == OP_FILE_DONE) {
            if (!f.active) { r = UIA_OP; goto done; }
            if (code == OP_CSV_ADD) {
                uint32_t idx;
                if (n != 1u || args[0] >= ns || out->n_slots >= UIA_MAX_SLOTS) { r = UIA_OP; goto done; }
                if ((r = fst_csv_add(&f, str_at[args[0]], str_n[args[0]], &idx)) == UIA_OK)
                    out->slots[out->n_slots++] = idx;
            } else if (code == OP_CSV_CELL) {
                uint32_t row;
                if (n != 3u || args[2] >= ns || !f.appended) { r = UIA_OP; goto done; }
                row = args[0] == 0u ? 1u : args[0] == 1u ? f.rows_before : 0u;
                if (!row) { r = UIA_OP; goto done; }
                r = fst_csv_cell(&f, row, args[1], str_at[args[2]], str_n[args[2]]);
            } else if (code == OP_FILE_SET) {
                uint32_t copy, size;
                if (n != 2u || args[0] > nf || args[1] > nf - args[0] || args[1] > f.cap)
                    { r = UIA_OP; goto done; }
                if (fst_table_find(table, f.stock, &copy, &size)) { r = UIA_CONFLICT; goto done; }
                fst_move(f.buf, frag + args[0], args[1]);
                f.len = args[1];
            } else {
                if (n) { r = UIA_OP; goto done; }
                fst_copy_words(&files[n_files++], &f, sizeof f);
                f.active = 0;
            }
        } else if (code == OP_STRBASE) {                /* written at commit */
            if (n != 2u || args[0] >= ns || str_hint[args[0]] == NAME_STRING ||
                n_sb >= MAX_STRBASE || (args[1] & 3u)) { r = UIA_OP; goto done; }
            sb_at[n_sb] = args[1]; sb_off[n_sb] = str_off[args[0]]; n_sb++;
        } else if (code == OP_IF_SLOT) {
            if (n != 3u || args[0] >= out->n_slots) r = UIA_OP;
            else if (out->slots[args[0]] != args[1]) skip = args[2];
        } else if (code == OP_QS_OPTION) {
            r = UIA_OP;                                 /* not in v4: QS is a container's */
        } else if (code == OP_EXPECT) {
            if (n != 2u || args[0] >= out->n_slots) r = UIA_OP;
            else if (out->slots[args[0]] != args[1]) r = UIA_GUARD;
        } else if (code == OP_ALLOC) {
            uint32_t h, slot = UIA_COUNTERS;
            if (!w.active || n != 3u || args[0] >= ns || out->n_slots >= UIA_MAX_SLOTS) { r = UIA_OP; goto done; }
            h = fst_name_hash(str_at[args[0]], str_n[args[0]]);
            for (i = 0; i < UIA_COUNTERS && slot == UIA_COUNTERS; ++i)
                if (w.counters[i][0] == h) slot = i;
            for (i = 0; i < UIA_COUNTERS && slot == UIA_COUNTERS; ++i)
                if (!w.counters[i][0]) { slot = i; w.counters[i][0] = h; w.counters[i][1] = 0; }
            if (slot == UIA_COUNTERS) { r = UIA_FULL; goto done; }
            out->slots[out->n_slots++] = args[1] + args[2] * w.counters[slot][1]++;
        } else if (!w.active) {
            r = UIA_OP;
        } else if (code == OP_GUARD) {
            uint32_t at;
            if (n != 2u || !fst_current(&w, args[0], &at) || at + 4u > w.len) r = UIA_OP;
            else if (fst_be(w.page + at) != args[1]) r = UIA_GUARD;
        } else if (code == OP_ADD32 || code == OP_ADDF) {
            uint32_t at, v;
            int32_t x;
            if (n != 2u || !fst_current(&w, args[0], &at) || at + 4u > w.len) r = UIA_OP;
            else if (code == OP_ADD32) fst_put_be(w.page + at, fst_be(w.page + at) + args[1]);
            else if (!fst_f32_to_int(fst_be(w.page + at), &x) ||
                     !fst_int_to_f32(x + (int32_t)args[1], &v)) r = UIA_OP;
            else fst_put_be(w.page + at, v);
        } else if (code == OP_SETSTR_SLOT) {
            uint32_t at, idx;
            if (n < 4u || n > MAX_ARGS || args[0] >= out->n_slots || args[3] >= ns ||
                str_hint[args[3]] == NAME_STRING) { r = UIA_OP; goto done; }
            idx = out->slots[args[0]] - args[1];
            if (idx >= args[2] || idx >= n - 4u || !fst_current(&w, args[4 + idx], &at) ||
                at + 4u > w.len) { r = UIA_OP; goto done; }
            fst_put_be(w.page + at, str_off[args[3]]);
        } else if (code == OP_INSERT) {
            uint32_t pos = args[0], off, len, at;
            if (n < 3u || (n - 3u) % 2u) { r = UIA_OP; goto done; }
            off = args[1]; len = args[2];
            if (!len || off > nf || len > nf - off || w.len + len > w.cap ||
                w.n_deltas >= w.max_deltas || !fst_current(&w, pos, &at)) { r = UIA_OP; goto done; }
            fst_move(w.page + at + len, w.page + at, w.len - at);
            fst_move(w.page + at, frag + off, len);
            for (i = 3; i < n; i += 2) {
                uint32_t rk = fst_le(a + 4u * i), ro = fst_le(a + 4u * i + 4u), kind = rk >> 24,
                         arg = rk & 0xFFFFFFu, v = 0;
                if (ro > len - 4u || len < 4u) { r = UIA_OP; goto done; }
                if (kind == R_LOCAL_ID) v = w.first_id + arg;
                else if (kind == R_STRING) {
                    if (arg >= ns || str_hint[arg] == NAME_STRING) { r = UIA_OP; goto done; }
                    v = str_off[arg];
                } else if (kind == R_SLOT_U32 || kind == R_SLOT_F32) {
                    if (arg >= out->n_slots) { r = UIA_OP; goto done; }
                    v = out->slots[arg];
                    if (kind == R_SLOT_F32 && !fst_int_to_f32((int32_t)v, &v)) { r = UIA_OP; goto done; }
                } else { r = UIA_OP; goto done; }
                fst_put_be(w.page + at + ro, v);
            }
            fst_poke(w.deltas + 8u * w.n_deltas, pos);
            fst_poke(w.deltas + 8u * w.n_deltas + 4u, len);
            w.n_deltas++;
            w.len += len;
        } else if (code == OP_DONE) {
            if (n) { r = UIA_OP; goto done; }
            out->first_id = w.first_id;
            out->page = w.page;
            fst_close_page(&w);
            fst_copy_words(&pages[n_pages++], &w, sizeof w);
        } else {
            r = UIA_OP;
        }
    done:
        if (r != UIA_OK) return out->result = r;
        k += 1u + n;
    }
    if (w.active || f.active || skip) return out->result = UIA_OP;

    /* ---- commit: every copy exists before anyone is pointed at it -------- */
    if (n_files) {
        uint32_t cnt = fst_peek(table + 8), fresh = 0;
        for (i = 0; i < n_files; ++i) {
            uint32_t seen = 0;
            for (uint32_t e = 0; e < cnt; ++e) if (fst_peek(table + 16 + 12 * e) == files[i].stock) seen = 1;
            fresh += !seen;
        }
        if (cnt + fresh > fst_peek(table + 12)) return out->result = UIA_FULL;
    }
    for (i = 0; i < n_sb; ++i) fst_poke(sb_at[i], sb_off[i]);   /* the sup's own data, in order */
    fst_publish();
    for (i = 0; i < n_files; ++i) {
        uint32_t cnt = fst_peek(table + 8), at = cnt;
        for (uint32_t e = 0; e < cnt; ++e) if (fst_peek(table + 16 + 12 * e) == files[i].stock) at = e;
        if (at == cnt) {
            fst_poke(table + 16 + 12 * at, files[i].stock);
            fst_poke(table + 20 + 12 * at, files[i].buf);
            fst_poke(table + 24 + 12 * at, files[i].len);
            fst_publish();
            fst_poke(table + 8, cnt + 1u);
        } else {                                        /* the copy only grows: pointer first */
            fst_poke(table + 20 + 12 * at, files[i].buf);
            fst_publish();
            fst_poke(table + 24 + 12 * at, files[i].len);
        }
    }
    if (n_files) fst_publish();                             /* the table, before any page */
    for (i = 0; i < n_pages; ++i) fst_poke(pages[i].entry + ENTRY_OFFSET, pages[i].page - NBU_BASE);
    fst_publish();
    return out->result = UIA_OK;
}

/* Apply one FPUI block from a sup's entry.  `block` at the cached alias when
 * it has private strings (they are borrowed); UIA_STRING otherwise. */
static uint32_t fpui_stock_apply(const struct sl_svc *svc, const void *block, uint32_t bytes,
                                 struct uia_outcome *out)
{
    return fst_apply((uintptr_t)block, bytes, out, svc);
}

/* The same without a service table, uia_apply's signature, for a launcher in
 * assembly (raw-view): only a block whose strings are all stock or names. */
static uint32_t fpui_stock_apply_plain(uintptr_t block, uint32_t bytes, struct uia_outcome *out)
{
    return fst_apply(block, bytes, out, 0);
}
#endif
