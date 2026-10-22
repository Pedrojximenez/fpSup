#include "sl_menu.h"
#include "ui_pool.h"      /* fpSup/uishare: the shared string pool convention */

/* Sensor Lab: the private B2_5 page (sl_b25_page.py) with the MODE / SIZE
 * rows.  A copy of fpSup/lossless/native/menu_page.c (proven on the camera
 * 2026-10-01 for MainB2); what differs: the page replaced is B2_5, found by
 * name in the same shared reader (reached through the MainB2 screen, as
 * there), the file block is "SLMP", and six private integers are registered.
 *
 * Ver.5.02 runtime layout, read from the camera 2026-09-30:
 *   C37B7048              the GUI object (C055F0F0); its word +0 is the UI app
 *   app+7C                screen vector: +4 count, +10 array (C05E04D8/E0)
 *   screen+04/+08/+24     app, name, the shared NBU reader
 *   reader+10/+14         string pool length / address
 *   reader+24             NBU base C18C0460
 *   reader+A8/+AC         44-byte runtime entries: +04 name, +08 page offset
 *   app+888 -> +60        the variable registry (C05D9EB0)
 * Firmware facts: MainB2 page C2030364. The string pool belongs to no sup:
 * private strings go through uis_intern() (fpSup/uishare/ui_pool.h). */
#define GUI_OBJECT      0xC37B7048u
#define SCREENS_COUNT   0x80u
#define SCREENS_ARRAY   0x8Cu
#define SCREEN_APP      0x04u
#define SCREEN_NAME     0x08u
#define SCREEN_READER   0x24u
#define READER_POOL_LEN 0x10u
#define READER_POOL     0x14u
#define READER_SOURCE   0x24u
#define READER_ENTRIES  0xA8u
#define READER_TABLE    0xACu
#define ENTRY_BYTES     44u
#define ENTRY_NAME      0x04u
#define ENTRY_OFFSET    0x08u
#define APP_REGISTRY    0x888u
#define REGISTRY_OFF    0x60u
#define NBU_BASE        0xC18C0460u
#define B25_OFFSET      0x19C130u     /* B2_5 entry+08, read on camera 2026-10-02 */
#define MAX_SCREENS     512u
#define FILE_OBJECT     0x1000u       /* the native file object, ~3 KiB */
#define VOLUME_SD       1u
#define VARIABLE_INT    0u
#define VARIABLE_TEXT   2u            /* a string: C05DB308 copies the initial one */
#define DESC_TYPE       0x00u
#define DESC_NAME       0x04u
#define DESC_VALUE      0x08u
#ifndef SL_LAB_FOCUS0
#define SL_LAB_FOCUS0   0u            /* the builder passes the tab bar's object id */
#endif

/* Strings are spelled in words: the camera build links .text alone. */
static void spell(uint32_t *to, uint32_t a, uint32_t b, uint32_t c, uint32_t d, uint32_t e) {
    volatile uint32_t *v = to;
    v[0] = a; v[1] = b; v[2] = c; v[3] = d; v[4] = e;
}
#define PATH_WORDS(w) spell(w, 0x5370665Cu, 0x422E7075u, 0x00004E49u, 0u, 0u)    /* \fpSup.BIN */
#define SCREEN_WORDS(w) spell(w, 0x6E69614Du, 0x00003242u, 0u, 0u, 0u)           /* MainB2 */
#define PAGE_WORDS(w) spell(w, 0x355F3242u, 0u, 0u, 0u, 0u)                        /* B2_5 */
static void name_words(struct sl_menu *m) {
    spell(m->names[0], 0x4F5F4C53u, 0x0000575Fu, 0u, 0u, 0u);    /* SL_O_W */
    spell(m->names[1], 0x4F5F4C53u, 0x0000485Fu, 0u, 0u, 0u);    /* SL_O_H */
    spell(m->names[2], 0x4F5F4C53u, 0x006E495Fu, 0u, 0u, 0u);    /* SL_O_In */
    spell(m->names[3], 0x4F5F4C53u, 0x0048425Fu, 0u, 0u, 0u);    /* SL_O_BH */
    spell(m->names[4], 0x4F5F4C53u, 0x0056425Fu, 0u, 0u, 0u);    /* SL_O_BV */
    spell(m->names[5], 0x4F5F4C53u, 0x0057535Fu, 0u, 0u, 0u);    /* SL_O_SW */
    spell(m->names[6], 0x4D5F4C53u, 0x4365646Fu, 0x746E756Fu, 0u, 0u);                   /* SL_ModeCount */
    spell(m->names[7], 0x535F564Du, 0x6163534Cu, 0x0000656Cu, 0u, 0u);    /* MV_SLScale */
    spell(m->names[8], 0x4F5F4C53u, 0x0048535Fu, 0u, 0u, 0u);    /* SL_O_SH */
    spell(m->names[9], 0x535F564Du, 0x6E69424Cu, 0u, 0u, 0u);    /* MV_SLBin */
    spell(m->names[10], 0x535F564Du, 0x7A77524Cu, 0x0000006Du, 0u, 0u);    /* MV_SLRwzm */
    spell(m->names[11], 0x4C5F4C53u, 0x6F466261u, 0x00737563u, 0u, 0u);    /* SL_LabFocus */
    spell(m->names[12], 0x465F4C53u, 0x7469425Fu, 0u, 0u, 0u);    /* SL_F_Bit */
    spell(m->names[13], 0x465F4C53u, 0x7370465Fu, 0u, 0u, 0u);    /* SL_F_Fps */
    spell(m->names[14], 0x465F4C53u, 0x6469575Fu, 0x00006874u, 0u, 0u);    /* SL_F_Width */
    spell(m->names[15], 0x465F4C53u, 0x6F72505Fu, 0x00000070u, 0u, 0u);    /* SL_F_Prop */
    spell(m->names[16], 0x4D5F4C53u, 0x6C65535Fu, 0u, 0u, 0u);    /* SL_M_Sel */
    spell(m->names[17], 0x4C5F4C53u, 0x61546261u, 0x00000062u, 0u, 0u);    /* SL_LabTab */
    spell(m->names[18], 0x4F5F4C53u, 0x79654B5Fu, 0u, 0u, 0u);    /* SL_O_Key */
    spell(m->names[19], 0x4F5F4C53u, 0x0030415Fu, 0u, 0u, 0u);    /* SL_O_A0 */
    spell(m->names[20], 0x4F5F4C53u, 0x0031415Fu, 0u, 0u, 0u);    /* SL_O_A1 */
    spell(m->names[21], 0x4F5F4C53u, 0x0032415Fu, 0u, 0u, 0u);    /* SL_O_A2 */
    spell(m->names[22], 0x4F5F4C53u, 0x0033415Fu, 0u, 0u, 0u);    /* SL_O_A3 */
    spell(m->names[23], 0x4F5F4C53u, 0x7461525Fu, 0x00000065u, 0u, 0u);   /* SL_O_Rate */
    spell(m->names[24], 0x4D5F4C53u, 0x4D65646Fu, 0x00007861u, 0u, 0u);   /* SL_ModeMax */
    spell(m->names[25], 0x4D5F4C53u, 0x7865545Fu, 0x00000074u, 0u, 0u);   /* SL_M_Text */
    spell(m->names[26], 0x4F5F4C53u, 0x7046525Fu, 0x00000073u, 0u, 0u);   /* SL_O_RFps */
    /* the MODE tab's diagram (sl_modes.c diagram_post): green / red frames in
     * screen pixels, their labels, the mode's rate and rolling shutter */
    spell(m->names[27], 0x445F4C53u, 0x0058475Fu, 0u, 0u, 0u);   /* SL_D_GX */
    spell(m->names[28], 0x445F4C53u, 0x0059475Fu, 0u, 0u, 0u);   /* SL_D_GY */
    spell(m->names[29], 0x445F4C53u, 0x0057475Fu, 0u, 0u, 0u);   /* SL_D_GW */
    spell(m->names[30], 0x445F4C53u, 0x0048475Fu, 0u, 0u, 0u);   /* SL_D_GH */
    spell(m->names[31], 0x445F4C53u, 0x0058525Fu, 0u, 0u, 0u);   /* SL_D_RX */
    spell(m->names[32], 0x445F4C53u, 0x0059525Fu, 0u, 0u, 0u);   /* SL_D_RY */
    spell(m->names[33], 0x445F4C53u, 0x0057525Fu, 0u, 0u, 0u);   /* SL_D_RW */
    spell(m->names[34], 0x445F4C53u, 0x0048525Fu, 0u, 0u, 0u);   /* SL_D_RH */
    spell(m->names[35], 0x445F4C53u, 0x7854475Fu, 0x00000074u, 0u, 0u);   /* SL_D_GTxt */
    spell(m->names[36], 0x445F4C53u, 0x7854525Fu, 0x00000074u, 0u, 0u);   /* SL_D_RTxt */
    spell(m->names[37], 0x445F4C53u, 0x7370465Fu, 0u, 0u, 0u);   /* SL_D_Fps */
    spell(m->names[38], 0x445F4C53u, 0x0073525Fu, 0u, 0u, 0u);   /* SL_D_Rs */
    spell(m->names[39], 0x465F4C53u, 0x6F72435Fu, 0x00000070u, 0u, 0u);   /* SL_F_Crop: FILTER's crop row */
    spell(m->names[40], 0x4D5F4C53u, 0x6261545Fu, 0u, 0u, 0u);   /* SL_M_Tab: the MODES tab's caption */
    spell(m->names[41], 0x435F4C53u, 0x7865545Fu, 0x00000074u, 0u, 0u);   /* SL_C_Text: the Crop row */
    spell(m->names[42], 0x445F4C53u, 0x0058435Fu, 0u, 0u, 0u);   /* SL_D_CX: the diagram's crop frame */
    spell(m->names[43], 0x445F4C53u, 0x0059435Fu, 0u, 0u, 0u);   /* SL_D_CY */
    spell(m->names[44], 0x445F4C53u, 0x0057435Fu, 0u, 0u, 0u);   /* SL_D_CW */
    spell(m->names[45], 0x445F4C53u, 0x0048435Fu, 0u, 0u, 0u);   /* SL_D_CH */
    spell(m->names[46], 0x445F4C53u, 0x7854435Fu, 0x00000074u, 0u, 0u);   /* SL_D_CTxt */
    spell(m->names[47], 0x4E5F4C53u, 0x6C65535Fu, 0u, 0u, 0u);   /* SL_N_Sel: the NAME tab's preset */
    spell(m->names[48], 0x4F5F4C53u, 0x7854425Fu, 0x00000074u, 0u, 0u);   /* SL_O_BTxt: the bin field's caption */
#if defined(SL_CALC_ONLY)
    spell(m->names[49], 0x455F4C53u, 0x7865545Fu, 0x00000074u, 0u, 0u); /* SL_E_Text */
    /* A button's native value controller must never observe command codes. */
    spell(m->names[50], 0x455F4C53u, 0x7475425Fu, 0x006e6f74u, 0u, 0u); /* SL_E_Button */
    spell(m->names[51], 0x4f5f4c53u, 0x636f4c5fu, 0x6bu, 0u, 0u); /* SL_O_Lock */
    spell(m->names[52], 0x4f5f4c53u, 0x6e654c5fu, 0x73u, 0u, 0u); /* SL_O_Lens */
    spell(m->names[53], 0x4f5f4c53u, 0x6c6f505fu, 0x00796369u, 0u, 0u); /* SL_O_Policy */
    spell(m->names[54], 0x4f5f4c53u, 0x7261575fu, 0x70u, 0u, 0u); /* SL_O_Warp */
    spell(m->names[55], 0x4f5f4c53u, 0x6461505fu, 0u, 0u, 0u);
    spell(m->names[56], 0x4f5f4c53u, 0x6461505fu, 0x32u, 0u, 0u);
    spell(m->names[57], 0x4f5f4c53u, 0x7a69535fu, 0x65u, 0u, 0u); /* SL_O_Size */
    spell(m->names[58], 0x4f5f4c53u, 0x6e69425fu, 0x73u, 0u, 0u); /* SL_O_Bins */
    spell(m->names[59], 0x4f5f4c53u, 0x6361465fu, 0x726f74u, 0u, 0u); /* SL_O_Factor */
    spell(m->names[60], 0x445f4c53u, 0x6e69465fu, 0x6c61u, 0u, 0u); /* SL_D_Final */
    for (uint32_t k=0;k<4u;k++) {
        uint32_t a=k==0?'X':k==1?'Y':k==2?'W':'H';
        spell(m->names[61+k],0x445f4c53u,0x465fu|(a<<16),0u,0u,0u);
    }
    for (uint32_t k=0;k<64u;k++) for (uint32_t a=0;a<2u;a++) {
        spell(m->names[65+k*2+a],0x445f4c53u,0x4c5fu|(('0'+k/10u)<<16)|(('0'+k%10u)<<24),a?'Y':'X',0u,0u);
    }
    spell(m->names[193],0x435f4c53u,0x65704f5fu,0x6eu,0u,0u); /* SL_C_Open */
    spell(m->names[194],0x4f5f4c53u,0x7475415fu,0x6fu,0u,0u); /* SL_O_Auto */
    spell(m->names[195],0x4f5f4c53u,0x736c435fu,0u,0u,0u); /* SL_O_Cls */
    spell(m->names[196],0x4f5f4c53u,0x65704f5fu,0x6eu,0u,0u); /* SL_O_Open */
    spell(m->names[197],0x455f4c53u,0x6d614e5fu,0x65u,0u,0u); /* SL_E_Name */
#endif
}

#if defined(SL_MENU_HOST_TEST)
#define N (&sl_menu_test_natives)
#define peek(a) N->read(a)
#define poke(a, v) N->write(a, v)
#define peek8(a) N->read_byte(a)
#define poke8(a, v) N->write_byte(a, v)
#define f_ctor(o, v) N->f_ctor(o, v)
#define f_open(o, p, m) N->f_open(o, p, m)
#define f_read(o, b, l, a) N->f_read(o, b, l, a)
#define f_close(o) N->f_close(o)
#define f_dtor(o, m) N->f_dtor(o, m)
#define lookup(r, n, d) N->lookup(r, n, d)
#define reg(a, c, d) N->reg(a, c, d)
#define publish() N->publish()
#elif defined(__arm__) && UINTPTR_MAX == UINT32_MAX
#define peek(a) (*(volatile const uint32_t *)(a))
#define poke(a, v) (*(volatile uint32_t *)(a) = (v))
#define peek8(a) (*(volatile const uint8_t *)(a))
#define poke8(a, v) (*(volatile uint8_t *)(a) = (uint8_t)(v))
static void f_ctor(uintptr_t o, uint32_t v) {
    typedef void (*fn)(uintptr_t, uint32_t); ((fn)0xC0365E90u)(o, v);
}
static uint32_t f_open(uintptr_t o, const char *p, uint32_t m) {
    typedef uint32_t (*fn)(uintptr_t, const char *, uint32_t); return ((fn)0xC0365FB0u)(o, p, m);
}
static uint32_t f_read(uintptr_t o, uintptr_t b, uint32_t l, uint32_t *a) {
    typedef uint32_t (*fn)(uintptr_t, uintptr_t, uint32_t, uint32_t *);
    return ((fn)0xC0366060u)(o, b, l, a);
}
static void f_close(uintptr_t o) { typedef void (*fn)(uintptr_t); ((fn)0xC0366020u)(o); }
static void f_dtor(uintptr_t o, uint32_t m) {
    typedef void (*fn)(uintptr_t, uint32_t); ((fn)0xC0365ED0u)(o, m);
}
static uint32_t lookup(uintptr_t r, const char *n, uintptr_t *d) {   /* Thumb */
    typedef uint32_t (*fn)(uintptr_t, const char *, uintptr_t *); return ((fn)0xC05DB419u)(r, n, d);
}
static uint32_t reg(uintptr_t a, uint32_t c, const uint32_t *d) {    /* Thumb */
    typedef uint32_t (*fn)(uintptr_t, uint32_t, const uint32_t *); return ((fn)0xC05DB309u)(a, c, d);
}
static void publish(void) {       /* D-cache clean+invalidate, barriers */
    typedef void (*fn)(void); ((fn)0xC000E91Cu)();
}
#else
#error "ARM32 native menu ABI required; host tests must explicitly substitute it"
#endif

static uint32_t aligned(uintptr_t a) { return a && !(a & 3u); }
/* The NUL-terminated native string at `a` equals `s` (bounded by s). */
static uint32_t same(uintptr_t a, const char *s) {
    if (!a) return 0;
    for (uint32_t n = 0;; ++n) {
        uint32_t c = peek8(a + n);
        if (c != (uint8_t)s[n]) return 0;
        if (!c) return 1;
    }
}
static uint32_t fnv(uintptr_t a, uint32_t n, uint32_t h) {
    for (uint32_t i = 0; i < n; ++i) h = (h ^ peek8(a + i)) * 16777619u;
    return h;
}
/* A big-endian word in the page, as the NBU reader sees it. */
static void put_be(uintptr_t a, uint32_t v) {
    poke8(a, v >> 24); poke8(a + 1, v >> 16); poke8(a + 2, v >> 8); poke8(a + 3, v);
}
static uint32_t fail(struct sl_menu *m, uint32_t why) { m->result = why; return why; }

/* The registered variable's descriptor (of that type), or 0. */
static uintptr_t variable_of(uintptr_t app, const char *NAME, uint32_t type) {
    uintptr_t d = 0, registry;
    if (!aligned(app) || !aligned(peek(app + APP_REGISTRY))) return 0;
    registry = peek(app + APP_REGISTRY) + REGISTRY_OFF;
    if (lookup(registry, NAME, &d) != 0 || !aligned(d)) return 0;
    if (peek(d + DESC_TYPE) != type || !same(peek(d + DESC_NAME), NAME)) return 0;
    return d;
}

static uintptr_t variable(uintptr_t app, const char *NAME) { return variable_of(app, NAME, VARIABLE_INT); }

uint32_t sl_menu_install(struct sl_menu *m, uintptr_t area, uint32_t area_bytes) {
    uint32_t screen_words[5], path_words[5], page_words[5];
    const char *SCREEN = (const char *)screen_words, *PATH = (const char *)path_words;
    const char *PAGE = (const char *)page_words;
    uintptr_t screens = 0, screen = 0, app, reader, table, entry = 0;
    uintptr_t fobj, file, page, strings, relocs, d;
    uint32_t count, actual = 0, page_len, strings_len, reloc_count, ok, room, nbr_len, body, nbr_at;
    uint32_t pages_len, pages_at = 0;
    /* one pool search per private string: each costs a whole-pool scan (and,
     * when appended, two cache flushes) -- 64 covers every string both pages have */


    if (!m || m->result) return m ? m->result : SL_MENU_NO_GUI;   /* once */
    SCREEN_WORDS(screen_words);
    PAGE_WORDS(page_words);
    PATH_WORDS(path_words);
    name_words(m);
    /* ---- the native objects, exactly as the stock firmware builds them -- */
    app = peek(GUI_OBJECT);                    /* [C37B7048]: the UI app */
    if (!aligned(app)) return fail(m, SL_MENU_NO_GUI);
    count = peek(app + SCREENS_COUNT);
    screens = peek(app + SCREENS_ARRAY);
    if (!aligned(screens) || !count || count > MAX_SCREENS) return fail(m, SL_MENU_NO_GUI);
    for (uint32_t n = 0; n < count && !screen; ++n) {
        uintptr_t s = peek(screens + 4u * n);
        if (aligned(s) && same(peek(s + SCREEN_NAME), SCREEN)) screen = s;
    }
    if (!screen || peek(screen + SCREEN_APP) != app) return fail(m, SL_MENU_NO_SCREEN);
    reader = peek(screen + SCREEN_READER);
    if (!aligned(reader) || peek(reader + READER_SOURCE) != NBU_BASE ||
        !uis_pool_known(reader))              /* stock, or shared by the convention */
        return fail(m, SL_MENU_READER);
    count = peek(reader + READER_ENTRIES);
    table = peek(reader + READER_TABLE);
    if (!aligned(table) || !count || count > MAX_SCREENS) return fail(m, SL_MENU_READER);
    for (uint32_t n = 0; n < count && !entry; ++n) {
        uintptr_t e = table + ENTRY_BYTES * n;
        if (same(peek(e + ENTRY_NAME), PAGE)) entry = e;
    }
#if defined(SL_PRIVATE_ONLY)
    /* Only private pages are installed. The recording page can already belong
     * to res-custom/uishare, and is never replaced by this producer. */
    if (!entry) return fail(m, SL_MENU_NO_ENTRY);
#else
    if (!entry || peek(entry + ENTRY_OFFSET) != B25_OFFSET) return fail(m, SL_MENU_NO_ENTRY);
#endif

    /* ---- the file, into memory owned for the rest of the boot --------- */
#if defined(SL_MENU_IN_BLOCK)
    if ((area & 7u) || area_bytes < FILE_OBJECT + SL_MENU_FILE_HEADER)
#else
    if ((area & 7u) || area_bytes < FILE_OBJECT + SL_MENU_AT)
#endif
        return fail(m, SL_MENU_ROOM);
    fobj = area;
    file = area + FILE_OBJECT;
    room = area_bytes - FILE_OBJECT;
#if defined(SL_MENU_IN_BLOCK)
    /* Loader v3 (build_v3_reslab.py): the SLMP block rides in the sup's own
     * block, already in memory -- its length at area+0, its bytes at
     * area + FILE_OBJECT.  No file is opened. */
    (void)fobj; (void)PATH;
    actual = peek(area);
    ok = actual != 0;
#else
    f_ctor(fobj, VOLUME_SD);
    ok = f_open(fobj, PATH, 1);
    if (ok) {
        /* The row's data rides in fpSup.BIN past what the loader reads
         * (SL_MENU_AT). Two reads of one open file: the first, into the same
         * buffer, only moves past the loader's part. Should the second not
         * continue from there, the magic below does not match and nothing
         * is installed. */
        ok = f_read(fobj, file, SL_MENU_AT, &actual) && actual == SL_MENU_AT;
        actual = 0;
        if (ok) ok = f_read(fobj, file, room, &actual);
        f_close(fobj);
    }
    f_dtor(fobj, 2);
#endif
    if (!ok) return fail(m, SL_MENU_FILE);
    m->file_len = actual;
#if defined(SL_MENU_IN_BLOCK)
    /* Its declared length comes from the already loaded sup. Exact fit is
     * valid; reject a length beyond the owned area before reading any fields. */
    if (actual > room) return fail(m, SL_MENU_ROOM);
#else
    if (actual >= room) return fail(m, SL_MENU_ROOM);    /* may not be all of it */
#endif
    if (actual < SL_MENU_FILE_HEADER) return fail(m, SL_MENU_FORMAT);
    page_len = peek(file + 0x08);
    strings_len = peek(file + 0x0C);
    reloc_count = peek(file + 0x10);
    nbr_len = peek(file + 0x1C);
    pages_len = peek(file + 0x20);
    if (actual < SL_MENU_FILE_HEADER || peek(file) != SL_MENU_MAGIC ||
        peek(file + 4) != SL_MENU_VERSION || peek(file + 0x14) != B25_OFFSET ||
        !page_len || page_len > actual || strings_len > actual || reloc_count > actual / 8u ||
        nbr_len > actual || pages_len > actual ||
        actual - SL_MENU_FILE_HEADER < page_len + strings_len + 8u * reloc_count)
        return fail(m, SL_MENU_FORMAT);        /* padding after: putfile cannot shorten */
    /* v2: the private NBR (sl_lists.py) follows the references, 4-aligned in
     * the file; the checksum covers everything up to its end. */
    body = page_len + strings_len + 8u * reloc_count;
    nbr_at = (SL_MENU_FILE_HEADER + body + 3u) & ~3u;
    if (nbr_len) {
        if (actual < nbr_at || actual - nbr_at < nbr_len || nbr_len < 20u)
            return fail(m, SL_MENU_FORMAT);
        body = nbr_at - SL_MENU_FILE_HEADER + nbr_len;
    }
    /* v3: the pages pack (sl_pages.py) after that, 4-aligned too */
    if (pages_len) {
        pages_at = (SL_MENU_FILE_HEADER + body + 3u) & ~3u;
        if (actual < pages_at || actual - pages_at < pages_len || pages_len < 20u)
            return fail(m, SL_MENU_FORMAT);
        body = pages_at - SL_MENU_FILE_HEADER + pages_len;
    }
    page = file + SL_MENU_FILE_HEADER;
    strings = page + page_len;
    relocs = strings + strings_len;
    if (fnv(page, body, 2166136261u) != peek(file + 0x18))
        return fail(m, SL_MENU_FORMAT);
    /* "NBR\0" 1.5, as the stock container at C0D22400 */
    if (nbr_len && (peek(file + nbr_at) != 0x0052424Eu || peek8(file + nbr_at + 4) != 1u ||
                    peek8(file + nbr_at + 5) != 5u))
        return fail(m, SL_MENU_FORMAT);
    /* "NBR\0" 1.9: the loader wants NBR's magic; the version is NBU's (sl_pages.py) */
    if (pages_len && (peek(file + pages_at) != 0x0052424Eu || peek8(file + pages_at + 4) != 1u ||
                      peek8(file + pages_at + 5) != 9u))
        return fail(m, SL_MENU_FORMAT);
    /* Every reference first, so a bad file changes nothing.  (v4) A flagged
     * offset is in the pages pack (sl_pages.py), patched before it registers. */
    for (uint32_t r = 0; r < reloc_count; ++r) {
        uint32_t at = peek(relocs + 8u * r), s = peek(relocs + 8u * r + 4u), n = 0;
        uint32_t room = page_len;
        if (at & SL_MENU_PAGES_REF) { at &= ~SL_MENU_PAGES_REF; room = pages_len; }
        if (room < 4u || at > room - 4u || s >= strings_len) return fail(m, SL_MENU_FORMAT);
        while (s + n < strings_len && peek8(strings + s + n)) ++n;
        if (!n || s + n >= strings_len) return fail(m, SL_MENU_FORMAT);
    }
    /* ---- the page's private strings: offsets from the shared pool -------
     * All at once (uis_intern_many): one pair of cache cleans for the lot and
     * no scan of the stock bytes -- the builder only ships strings the stock
     * pool lacks.  r13: a pair per string plus whole-pool scans cost ~20 s. */
    {
        const char *texts[SL_MENU_STRINGS];
        char text[SL_MENU_TEXT];                /* C strings, read through peek8 */
        uint32_t from[SL_MENU_STRINGS], offs[SL_MENU_STRINGS], unique = 0, used = 0, k;
        for (uint32_t r = 0; r < reloc_count; ++r) {
            uint32_t s = peek(relocs + 8u * r + 4u);
            for (k = 0; k < unique && from[k] != s; ++k) {}
            if (k == unique) {
                if (unique == SL_MENU_STRINGS) return fail(m, SL_MENU_FORMAT);
                from[unique] = s;
                texts[unique++] = text + used;
                do {
                    if (used == sizeof text) return fail(m, SL_MENU_FORMAT);
                    text[used] = (char)peek8(strings + s++);
                } while (text[used++]);
            }
        }
        if (unique && uis_intern_many(texts, unique, UIS_NOT_STOCK, offs) != UIS_OK) return fail(m, SL_MENU_POOL);
        for (uint32_t r = 0; r < reloc_count; ++r) {
            uint32_t at = peek(relocs + 8u * r), s = peek(relocs + 8u * r + 4u);
            for (k = 0; from[k] != s; ++k) {}
            if (at & SL_MENU_PAGES_REF) put_be(file + pages_at + (at & ~SL_MENU_PAGES_REF), offs[k]);
            else put_be(page + at, offs[k]);
        }
    }

    /* ---- the variables: registered once, 0, memory only ---------------- */
    for (uint32_t n = 0; n < SL_MENU_VARIABLES; ++n) {
        const char *NAME = (const char *)m->names[n];
        uint32_t type = SL_MENU_IS_TEXT(n) ? VARIABLE_TEXT : VARIABLE_INT;
        d = variable_of(app, NAME, type);
        if (!d) {
            uint32_t def[3];
            def[0] = type;
            def[1] = (uint32_t)(uintptr_t)NAME;
            /* 0, but the lab page's focus; a text starts as "1.00" (C05DB308 copies it) */
            def[2] = type == VARIABLE_TEXT ? (uint32_t)(uintptr_t)m->rwzm_text[0] :
                     n == SL_MENU_LAB_FOCUS ? SL_LAB_FOCUS0 : 0u;
            if (type == VARIABLE_TEXT) {
                m->rwzm_text[0][0] = '1'; m->rwzm_text[0][1] = '.'; m->rwzm_text[0][2] = '0';
                m->rwzm_text[0][3] = '0'; m->rwzm_text[0][4] = 0;
            }
            if (reg(app, 1, def) != 0) return fail(m, SL_MENU_REGISTER);
            m->registered++;
            d = variable_of(app, NAME, type);
        }
        if (!d) return fail(m, SL_MENU_VARIABLE);
    }
    publish();

    /* ---- the two stock variant variables sl_excl.S sets under CUSTOM ------
     * Looked up only (stock registers them); 0 when absent, and the hooks
     * then leave them alone. */
#if !defined(SL_CALC_ONLY)
    {
        uint32_t w[6];
        volatile uint32_t *v = w;
        v[0] = 0x4C435845u; v[1] = 0x6172465Fu; v[2] = 0x6152656Du; v[3] = 0x00006574u;
        v[4] = 0u; v[5] = 0u;                                              /* EXCL_FrameRate */
        m->excl_rate = variable(app, (const char *)w);
        v[0] = 0x4C435845u; v[1] = 0x6E69435Fu; v[2] = 0x44616D65u; v[3] = 0x7551474Eu;
        v[4] = 0x74696C61u; v[5] = 0x00000079u;                            /* EXCL_CinemaDNGQuality */
        m->excl_bit = variable(app, (const char *)w);
    }

#endif

    /* ---- switch B2_5 to the page ----------------------------------------
     * The migrated late launcher publishes the entry only after its page
     * parser/list hooks are journal-proven and armed.  This keeps a concurrent
     * UI parser on the stock page while hooks are still being prepared. */
#if !defined(SL_DYNAMIC_CORE)
    poke(entry + ENTRY_OFFSET, page - NBU_BASE);
    publish();
#endif
    m->app = app; m->reader = reader; m->entry = entry; m->page = page; m->page_len = page_len;
    m->pool = peek(reader + READER_POOL); m->pool_len = peek(reader + READER_POOL_LEN);
    m->nbr = nbr_len ? file + nbr_at : 0;   /* registered later, on the UI thread (sl_excl.S) */
    m->nbr_len = nbr_len;
    m->pages = pages_len ? file + pages_at : 0;   /* registered later, on the UI thread */
    m->pages_len = pages_len;
    m->count_desc = variable(app, (const char *)m->names[6]);
    m->result = SL_MENU_INSTALLED;
    return SL_MENU_INSTALLED;
}

uint32_t sl_menu_value(struct sl_menu *m, uint32_t index, uint32_t *value) {
    uintptr_t d;
    if (!m || m->result != SL_MENU_INSTALLED || index >= SL_MENU_VARIABLES || !value) return 0;
    d = variable(m->app, (const char *)m->names[index]);
    if (!d) return 0;
    *value = peek(d + DESC_VALUE);
    return 1;
}
