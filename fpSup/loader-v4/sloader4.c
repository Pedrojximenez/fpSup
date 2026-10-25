/* Loader v4 core (LOADER.BIN).  Design: projects/loader-v4/DESIGN.md.
 *
 * Derived from v3/sloader.c (left untouched): the same entry from loader.S,
 * the same books (claims, journal, power-off write-back), the same cave.
 * What changed is listed in sloader4.h.  Built like v3: clang -fropi, one
 * .text, no relocations, no globals, no string literals.
 *
 * Cached execution: the firmware allocator returns the uncached alias
 * (0x4..., TEX=4 C=B=0).  The core copies itself there, cleans the D-cache,
 * invalidates the I-cache and carries on from block + SL_ALIAS (WBWA, same
 * physical memory).  A sup with SL_F_CACHED_OK is read into a 64-aligned
 * block through the uncached alias and entered at the cached one. */
#include "sloader4.h"

typedef uint32_t u32;
typedef uint16_t u16;
typedef uint8_t u8;

#ifndef CAVE_BUMP
#error "CAVE_BUMP, CAVE_ARENA, CAVE_ARENA_END and LOAD_DONE_US come from build_v4.py"
#endif

/* --- firmware (Ver.5.02, as v3) ------------------------------------------ */
#define FW(addr, type) ((type)(uintptr_t)(addr))
#define tick_us()        FW(0xC002B6E0, u32 (*)(void))()
#define dcache()         FW(0xC000E91C, void (*)(void))()
#define icache()         FW(0xC000EABC, void (*)(void))()
#define mem_heap(c)      FW(0xC001CF78, void *(*)(u32))(c)
#define mem_get(h, n)    FW(0xC001D038, void *(*)(void *, u32, u32, u32, u32))(h, n, 0, 0, 0)
#define mem_free(h, p)   FW(0xC001D2B8, void (*)(void *, void *))(h, p)
#define poff_mgr()       FW(0xC0023A98, void *(*)(void))()
#define poff_add(m, o, f) FW(0xC0024118, u32 (*)(void *, void *, u32))(m, o, f)

#ifdef PWROFF_LOG
/* build_v4.py --pwroff-log (debug, default off): what the last power-off
 * decided, for projects/loader-v4/pwroff_log.py.  Two records:
 *  - early, from this core's own power-off routine (XC_PowerOffMgr's lists run
 *    before the settings flush), into a free 112 B of XC_CommonSaveData
 *    (0xC307523C + 0x210, research/firmware/notes/PERSISTENT_STORE_COMMONSAVE.md):
 *    survives a cold boot;
 *  - late, from a wrapper around the stock veto callback [0xC31D848C] =
 *    C0023B60 that C0122F90 calls just before it writes 0x2D000400: into a
 *    cave block; survives only a warm (self-refresh) restart.
 * The wrapper is armed at power-off (the pointer is BSS, re-registered every
 * boot by C0023A20, so nothing to journal) and returns the stock result. */
#define PL_STORE      0xC307544Cu
#define PL_WORDS      28u
#define PL_MAGIC      0x314C5750u      /* "PWL1" */
#define PL_LMAGIC     0x4C4C5750u      /* "PWLL" */
#define PL_LATE_BYTES 64u
#define PL_MGR        0xC30756C4u      /* XC_PowerOffMgr */
#define PL_PMU        0x2D000280u      /* +0x80..0x8C = wake factors 0x2D000300..30C */
#define PL_CBOBJ      0xC31D848Cu      /* [+0] veto callback, +0x230, +0x234 */
#define PL_CB_STOCK   0xC0023B60u
#define POFF_WORDS    8u               /* X-8, routine, journal, early, wrap, late, calls, boot */
#elif defined(PWROFF_FILE)
#define POFF_WORDS    4u               /* X-8, routine, journal, power-off hook */
#else
#define POFF_WORDS    3u
#endif

#ifdef PWROFF_FILE
/* build_v4.py --pwroff-file (debug, default off): one fixed 128 B record of
 * each power-off in \fpSup\PWROFF.LOG, written from this core's power-off
 * routine while the card is still mounted (XC_PowerOffMgr's lists).  A card
 * file survives the cold boot that wipes RAM and the settings area cannot
 * (it is flushed before the lists run).  Only this one fixed name is ever
 * written; any failure skips, the power-off goes on.  Read by
 * projects/loader-v4/pwroff_file.py. */
#define PF_MAGIC      0x31465750u      /* "PWF1" */
#define PF_WORDS      32u
#define PF_MGR        0xC30756C4u
#define PF_PMU        0x2D000280u      /* +0x80..0x8C wake factors, +0x94 = 0x2D000314 */
#define PF_CBOBJ      0xC31D848Cu
#define PF_BATT       0xC30783D8u      /* [[+4]+0xB8]: external power */
#define PF_BUSY       0xC3075748u
#define PF_NOW_MS     0xC301EAE4u      /* current_time */
#define PF_OBJ_BYTES  0x1100u          /* file object 0x1000, path +0x1000, record +0x1080 */
#endif
#define f_ctor(o, v)     FW(0xC0365E90, void (*)(void *, u32))(o, v)
#define f_open(o, p)     FW(0xC0365FB0, u32 (*)(void *, const char *, u32))(o, p, 1)
#define f_create(o, p)   FW(0xC0365FB0, u32 (*)(void *, const char *, u32))(o, p, 7)
#define f_write(o, b, n) FW(0xC03660E8, u32 (*)(void *, const void *, u32))(o, b, n)
#define f_read(o, b, n, a) FW(0xC0366060, u32 (*)(void *, void *, u32, u32 *))(o, b, n, a)
#define f_close(o)       FW(0xC0366020, void (*)(void *))(o)
#define f_dtor(o)        FW(0xC0365ED0, void (*)(void *, u32))(o, 2)
#define dir_ctor(h, d)   FW(0xC0366918, void *(*)(void *, u32))(h, d)
#define dir_open(h, p)   FW(0xC0366990, u32 (*)(void *, const char *))(h, p)
#define dir_next(h, e)   FW(0xC03669F8, u32 (*)(void *, void *))(h, e)
#define dir_dtor(h)      FW(0xC0366940, void (*)(void *, u32))(h, 2)

#define DRIVE_SD     1u
#define DIR_ENTRY    0x238u
#define ATTR_HIDDEN  0x02u
#define ATTR_DIR     0x10u

#define MAX_SUPS     32u
#define MAX_CLAIMS   768u
#define MAX_LOG      96u
#define MAX_SERVICES 16u
#define NAME_MAX     40u
#define JOURNAL_BYTES 0x8000u
#define MAX_BLOCK    0x01000000u
#define LINE         64u               /* cache line; blocks are aligned to it */

#define S_FOBJ       0x0000u
#define S_HOLDER     0x1000u
#define S_ENTRY      0x1010u
#define S_PATH       0x1300u
#define S_HDR        0x1380u
#define S_CANDS      0x1400u
#define SCRATCH_BYTES (S_CANDS + MAX_SUPS * sizeof(struct cand))

/* Log codes: v3's, plus OLD_FORMAT.  The log is one line per file plus the
 * repairs and refusals; claims are counted on the LOADED line, not listed (v3
 * filled its 4096 bytes with claim lines and lost the later sups). */
enum {
    L_START = 1, L_NO_DIR, L_SKIP_NAME, L_TOO_MANY, L_OPEN_FAIL, L_BAD_HEADER,
    L_DUP_ID, L_NO_MEMORY, L_SHORT_READ, L_LOADED, L_RELEASED, L_REPAIRED,
    L_SUP, L_DONE, L_NO_POFF, L_CONFLICT, L_LISTED, L_CLAIM, L_DISABLED,
    L_OLD_FORMAT,
#ifdef PWROFF_LOG
    L_PWRLOG,
#endif
#ifdef PWROFF_FILE
    L_PWRFILE = 0x31,
#endif
    L_UI = 0x32,                       /* fpsup_home.c: a = 0 hooked / 1 no page / 2 claim / 3 cave / 0x100 + page / 0x300 + string site */
};

#define LOG_FILE_BYTES 8192u                     /* MAX_LOG lines of 62 */
#define DS_MAGIC      0x53445346u      /* "FSDS": the disabled list after the code */
#define DS_MAX        30u
#define DS_BYTES      (8u + 4u * DS_MAX)

struct cand { char name[NAME_MAX]; u32 size; u32 id; u32 magic; };
struct claim { u32 addr, len; u8 kind, sup, res, pad; };
struct sup { char name[NAME_MAX]; u32 id; void *block; u32 state;
             char path[NAME_MAX + 8]; u32 version; u32 status; u32 ublock;
             u32 size; char disp[24]; };
struct logrec { u32 code, a, b; char text[NAME_MAX]; };   /* a whole file name (names_v4: up to 39) */
struct service { u32 id; void *ptr; };
struct prow { const struct sl_row *row; u32 owner; u32 dirty; };

struct strings {          /* from sloader4_entry.S                             */
    const char *dir;      /* "\fpSup"                                          */
    const char *self;     /* "LOADER.BIN"                                      */
    const char *logname;  /* "LOAD.LOG"                                        */
    u32 splash;           /* the four-box completion, ARM; 0 when not built    */
    const char *ui;       /* "\fpSup\UI\FPSUP.BIN" (FPSUP_UI), else 0           */
};

struct state {
    struct sl_svc svc;                 /* FIRST: the table is the state        */
    u32 poff[POFF_WORDS];              /* X-8, routine, journal (+ PWROFF_LOG)  */
    void *heap;
    u32 *jbase, *jcur, *jend;
    u32 nclaims, cur, jmark, cmark;
    struct claim claims[MAX_CLAIMS];
    u32 nsups;
    struct sup sups[MAX_SUPS];
    u32 nlog;
    struct logrec log[MAX_LOG];
    u32 running;
    u8 *file;                          /* LOADER.BIN as read, with its list    */
    u32 file_len;
    u32 *dis;                          /* DS_MAGIC, count, ids (in `file`)     */
    u32 has_smgr;                      /* the list applies only with SupManager */
    u32 nserv;
    struct service serv[MAX_SERVICES];
    u32 nrows;
    struct prow rows[SL_PAGE_MAX];
    const struct strings *str;
#ifdef FPSUP_UI
    u32 ui_sup;                        /* the pseudo-sup LOADER.BIN's index; MAX_SUPS: no hooks */
    u8 *ui_home;                       /* FPSUP.BIN, installed; 0 = no home page */
    u32 ui_page, ui_popup, ui_header;
    u32 ui_hint, ui_head;               /* last footer / header-light posted, + 1 (0: none yet) */
    u32 ui_going;                      /* 1 while a JUMP row's open() runs: svc->ui_go is allowed */
    u32 ui_goseq;                      /* V_GO's last value: each named open posts the next */
    char ui_pager[8];
#endif
#ifdef PWROFF_FILE
    u8 *pf_obj;                        /* preallocated at load: no allocation at power-off */
    u32 pf_seq, pf_calls;
#endif
};

/* --- helpers -------------------------------------------------------------- */
static void zero(void *d, u32 n) { volatile u8 *p = d; while (n--) *p++ = 0; }
static void copy(void *d, const void *s, u32 n)
{
    volatile u8 *a = d; const volatile u8 *b = s;
    while (n--) *a++ = *b++;
}
static int differs(const void *a, const void *b, u32 n)
{
    const volatile u8 *x = a, *y = b;
    while (n--) if (*x++ != *y++) return 1;
    return 0;
}
static u32 slen(const char *s) { u32 n = 0; while (s[n]) n++; return n; }
static char upper(char c) { return (c >= 'a' && c <= 'z') ? (char)(c - 32) : c; }
static int ncmp(const char *a, const char *b)
{
    for (;; a++, b++) {
        char x = upper(*a), y = upper(*b);
        if (x != y) return x < y ? -1 : 1;
        if (!x) return 0;
    }
}
static void publish(void) { dcache(); icache(); }
/* cached alias of an uncached-alias address; anything else is left alone */
static u32 cached(u32 a) { return (a >= 0x40000000u && a < 0x80000000u) ? a + SL_ALIAS : a; }

static void logrec(struct state *st, u32 code, u32 a, u32 b, const char *text)
{
    if (st->nlog >= MAX_LOG) return;
    struct logrec *r = &st->log[st->nlog];
    r->code = code; r->a = a; r->b = b;
    u32 i = 0;
    if (text) for (; i < sizeof r->text - 1 && text[i]; i++) r->text[i] = text[i];
    r->text[i] = 0;
    st->nlog++;
}

/* --- journal (v3, unchanged) ----------------------------------------------- */
static int journal(struct state *st, u32 addr, u32 len, const void *stock)
{
    u32 words = len / 4;
    if (st->jcur + 2 + words + 1 > st->jend) return SL_FULL;
    volatile u32 *e = st->jcur;
    copy((void *)(e + 2), stock, len);
    e[2 + words] = 0;
    e[1] = len;
    e[0] = addr;
    st->jcur = (u32 *)(e + 2 + words);
    return SL_OK;
}

/* --- v3 services ------------------------------------------------------------ */
static int overlaps(const struct claim *c, u32 addr, u32 len)
{
    return addr < c->addr + c->len && c->addr < addr + len;
}

static int svc_claim(const struct sl_svc *svc, u32 addr, u32 len, const void *stock, u32 kind)
{
    struct state *st = (struct state *)svc;
    if (!len || ((addr | len) & 3) || kind < SL_CHAIN || kind > SL_SHARED_UI || !stock)
        return SL_BADARG;
    int shared = 0;
    for (u32 i = 0; i < st->nclaims; i++) {
        struct claim *c = &st->claims[i];
        if (c->res || !overlaps(c, addr, len)) continue;
        if (c->sup == st->cur && c->addr == addr && c->len == len && c->kind == kind)
            return SL_OK;
        if (kind != SL_EXCL && c->kind == kind && c->addr == addr && c->len == len) {
            shared = 1;
            continue;
        }
        logrec(st, L_CONFLICT, addr, st->sups[c->sup].id, st->sups[st->cur].name);
        return SL_CONFLICT;
    }
    if (st->nclaims >= MAX_CLAIMS) return SL_FULL;
    if (!shared) {
        if (st->jcur + 2 + len / 4 + 1 > st->jend) return SL_FULL;
        if (differs((const void *)(uintptr_t)addr, stock, len)) {
            copy((void *)(uintptr_t)addr, stock, len);
            publish();
            logrec(st, L_REPAIRED, addr, len, st->sups[st->cur].name);
        }
        journal(st, addr, len, stock);
    }
    struct claim *c = &st->claims[st->nclaims++];
    c->addr = addr; c->len = len; c->kind = (u8)kind; c->sup = (u8)st->cur;
    c->res = 0; c->pad = 0;
    return SL_OK;
}

static int svc_claim_res(const struct sl_svc *svc, u32 id, u32 kind)
{
    struct state *st = (struct state *)svc;
    if (kind < SL_CHAIN || kind > SL_SHARED_UI) return SL_BADARG;
    for (u32 i = 0; i < st->nclaims; i++) {
        struct claim *c = &st->claims[i];
        if (!c->res || c->addr != id) continue;
        if (c->sup == st->cur) return SL_OK;
        if (kind != SL_EXCL && c->kind == kind) continue;
        logrec(st, L_CONFLICT, id, st->sups[c->sup].id, st->sups[st->cur].name);
        return SL_CONFLICT;
    }
    if (st->nclaims >= MAX_CLAIMS) return SL_FULL;
    struct claim *c = &st->claims[st->nclaims++];
    c->addr = id; c->len = 0; c->kind = (u8)kind; c->sup = (u8)st->cur;
    c->res = 1; c->pad = 0;
    return SL_OK;
}

static u32 svc_chain_next(const struct sl_svc *svc, u32 site, u32 thumb)
{
    (void)svc;
    if (!thumb) {
        u32 w = *(volatile u32 *)(uintptr_t)site;
        if ((w & 0x0E000000u) != 0x0A000000u) return 0;
        int32_t off = (int32_t)(w << 8) >> 6;
        u32 t = site + 8 + (u32)off;
        if ((w >> 28) == 0xF) t |= ((w >> 23) & 2u) | 1u;
        return t;
    }
    u32 h1 = *(volatile u16 *)(uintptr_t)site, h2 = *(volatile u16 *)(uintptr_t)(site + 2);
    if ((h1 & 0xF800u) != 0xF000u) return 0;
    u32 op = h2 & 0xD000u;
    if (op != 0x9000u && op != 0xD000u && op != 0xC000u) return 0;
    u32 s = (h1 >> 10) & 1, j1 = (h2 >> 13) & 1, j2 = (h2 >> 11) & 1;
    u32 i1 = !(j1 ^ s), i2 = !(j2 ^ s);
    u32 imm = (s << 24) | (i1 << 23) | (i2 << 22) | ((h1 & 0x3FFu) << 12) | ((h2 & 0x7FFu) << 1);
    int32_t off = (int32_t)(imm << 7) >> 7;
    u32 t = site + 4 + (u32)off;
    return op == 0xC000u ? (t & ~3u) : (t | 1u);
}

/* unchanged from v3: RESCUS's veneer discovery depends on it */
static u32 svc_cave_alloc(const struct sl_svc *svc, u32 bytes)
{
    (void)svc;
    volatile u32 *bump = (volatile u32 *)(uintptr_t)CAVE_BUMP;
    u32 p = (*bump + 7) & ~7u, n = (bytes + 7) & ~7u;
    if (!n || p < CAVE_ARENA || p + n > CAVE_ARENA_END) return 0;
    *bump = p + n;
    return p;
}

static void svc_publish(const struct sl_svc *svc) { (void)svc; publish(); }

static const char *svc_holder(const struct sl_svc *svc, u32 addr, u32 i)
{
    struct state *st = (struct state *)svc;
    for (u32 k = 0; k < st->nsups; k++) {
        if (st->sups[k].state != SL_KEEP && !(k == st->cur && st->running)) continue;
        for (u32 j = 0; j < st->nclaims; j++) {
            struct claim *c = &st->claims[j];
            if (c->sup != k || (c->res ? c->addr != addr : !overlaps(c, addr, 4))) continue;
            if (!i--) return st->sups[k].path;
            break;
        }
    }
    return 0;
}

static const char *svc_self(const struct sl_svc *svc)
{
    struct state *st = (struct state *)svc;
    return st->running ? st->sups[st->cur].path : 0;
}

static void svc_log(const struct sl_svc *svc, const char *line)
{
    struct state *st = (struct state *)svc;
    logrec(st, L_SUP, st->sups[st->cur].id, 0, line);
}

/* --- v4 services ------------------------------------------------------------ */
static void *svc_uncached(const struct sl_svc *svc, const void *p)
{
    struct state *st = (struct state *)svc;
    u32 a = (u32)(uintptr_t)p;
    for (u32 k = 0; k < st->nsups; k++) {
        struct sup *s = &st->sups[k];
        u32 b = (u32)(uintptr_t)s->block;
        if (b && a >= b && a < b + s->size) return (void *)(uintptr_t)(s->ublock + (a - b));
    }
    return (void *)p;
}

/* The path of the loaded sup whose block (either alias) contains `p`. */
static const char *svc_self_path(const struct sl_svc *svc, const void *p)
{
    struct state *st = (struct state *)svc;
    u32 a = (u32)(uintptr_t)p;
    for (u32 k = 0; k < st->nsups; k++) {
        struct sup *s = &st->sups[k];
        if (!s->block) continue;
        u32 b = (u32)(uintptr_t)s->block, u = s->ublock;
        if ((a >= b && a < b + s->size) || (a >= u && a < u + s->size)) return s->path;
    }
    return 0;
}

static u32 read_file_obj(void *fo, const char *path, void *buf, u32 want)
{
    u32 got = 0;
    f_ctor(fo, DRIVE_SD);
    if (!f_open(fo, path)) { f_dtor(fo); return 0xFFFFFFFFu; }
    f_read(fo, buf, want, &got);
    f_close(fo);
    f_dtor(fo);
    return got;
}

static int svc_file_is(const struct sl_svc *svc, const char *path, const void *expect, u32 n)
{
    struct state *st = (struct state *)svc;
    if (!path || !expect || !n || n > 256) return SL_BADARG;
    u8 *obj = mem_get(st->heap, 0x1000 + 256);
    if (!obj) return SL_IO;
    u8 *buf = obj + 0x1000;
    zero(buf, n);
    u32 got = read_file_obj(obj, path, buf, n);
    int r = (got == 0xFFFFFFFFu || got != n || differs(buf, expect, n)) ? SL_NOT_SELF : SL_OK;
    mem_free(st->heap, obj);
    return r;
}

/* svc->file_read(): up to `want` bytes of a file on the card; the count, or SL_IO. */
static int svc_file_read(const struct sl_svc *svc, const char *path, void *buf, u32 want)
{
    struct state *st = (struct state *)svc;
    if (!path || !buf || !want) return SL_BADARG;
    u8 *obj = mem_get(st->heap, 0x1000);
    if (!obj) return SL_IO;
    u32 got = read_file_obj(obj, path, buf, want);
    mem_free(st->heap, obj);
    return got == 0xFFFFFFFFu ? SL_IO : (int)got;
}

static int svc_provide(const struct sl_svc *svc, u32 id, void *ptr)
{
    struct state *st = (struct state *)svc;
    if (!id || !ptr) return SL_BADARG;
    for (u32 i = 0; i < st->nserv; i++)
        if (st->serv[i].id == id) return SL_CONFLICT;
    if (st->nserv >= MAX_SERVICES) return SL_FULL;
    st->serv[st->nserv].id = id;
    st->serv[st->nserv].ptr = ptr;
    st->nserv++;
    return SL_OK;
}

static void *svc_find(const struct sl_svc *svc, u32 id)
{
    struct state *st = (struct state *)svc;
    for (u32 i = 0; i < st->nserv; i++)
        if (st->serv[i].id == id) return st->serv[i].ptr;
    return 0;
}

/* Rows sorted by title, case-insensitive; SupManager's rows first; equal
 * titles keep their registration order. */
static int row_before(struct state *st, const struct prow *a, const struct prow *b)
{
    u32 sa = st->sups[a->owner].id == SL_SMGR_ID, sb = st->sups[b->owner].id == SL_SMGR_ID;
    if (sa != sb) return sa > sb;
    return ncmp(a->row->title, b->row->title) < 0;
}

static int svc_page_add(const struct sl_svc *svc, const struct sl_row *row)
{
    struct state *st = (struct state *)svc;
    if (!row || !row->title || row->kind < SL_ROW_JUMP || row->kind > SL_ROW_ACTION)
        return SL_BADARG;
    if ((row->kind == SL_ROW_JUMP || row->kind == SL_ROW_ACTION) && !row->open) return SL_BADARG;
    if (row->kind == SL_ROW_TOGGLE && (!row->get || !row->set)) return SL_BADARG;
    if (row->kind == SL_ROW_LIST && (!row->get || !row->set || !row->choices || !row->n_choices
                                     || row->n_choices > SL_LIST_MAX))
        return SL_BADARG;
    if (row->kind == SL_ROW_TOGGLE && row->n_choices && (row->n_choices != 2 || !row->choices))
        return SL_BADARG;
    if (!st->running) return SL_BADARG;                 /* only from an entry */
    if (st->nrows >= SL_PAGE_MAX) return SL_FULL;
    struct prow n = { row, st->cur, 1 };
    u32 i = st->nrows;
    while (i && row_before(st, &n, &st->rows[i - 1])) {
        st->rows[i] = st->rows[i - 1];
        i--;
    }
    st->rows[i] = n;
    st->nrows++;
    return (int)i;
}

#ifdef FPSUP_UI
static void home_dirty(struct state *st, u32 row);
#endif
static void svc_page_refresh(const struct sl_svc *svc, int row)
{
    struct state *st = (struct state *)svc;
    if (row >= 0 && (u32)row < st->nrows) {
        st->rows[row].dirty = 1;
#ifdef FPSUP_UI
        home_dirty(st, (u32)row);
#endif
    }
}

static u32 svc_page_count(const struct sl_svc *svc) { return ((struct state *)svc)->nrows; }

static const struct sl_row *svc_page_row(const struct sl_svc *svc, u32 i)
{
    struct state *st = (struct state *)svc;
    return i < st->nrows ? st->rows[i].row : 0;
}

static int listed(struct state *st, u32 id)
{
    if (!st->dis) return 0;
    for (u32 i = 0; i < st->dis[1] && i < DS_MAX; i++)
        if (st->dis[2 + i] == id) return 1;
    return 0;
}

static int svc_sups_list(const struct sl_svc *svc, u32 i, struct sl_supinfo *out)
{
    struct state *st = (struct state *)svc;
    if (i >= st->nsups || !out) return SL_BADARG;
    struct sup *s = &st->sups[i];
    out->name = s->name;
    out->display = s->disp[0] ? s->disp : s->name;
    out->id = s->id; out->version = s->version; out->status = s->status;
    out->next_boot = s->id && !listed(st, s->id) && s->status != SL_S_OLD_FORMAT
                     && s->status != SL_S_BAD_HEADER;
    return SL_OK;
}

static int svc_disabled_get(const struct sl_svc *svc, u32 id)
{
    return listed((struct state *)svc, id);
}

/* Change the list and write LOADER.BIN back -- only over the file it was read
 * from (same first 64 bytes), never creating one. */
static int svc_disabled_set(const struct sl_svc *svc, u32 id, u32 off)
{
    struct state *st = (struct state *)svc;
    if (!id || id == SL_SMGR_ID) return SL_BADARG;       /* cannot disable itself */
    if (!st->dis || !st->file) return SL_IO;
    u32 n = st->dis[1], at = n;
    for (u32 i = 0; i < n; i++) if (st->dis[2 + i] == id) at = i;
    if (off && at == n) {
        if (n >= DS_MAX) return SL_FULL;
        st->dis[2 + n] = id;
        st->dis[1] = n + 1;
    } else if (!off && at < n) {
        st->dis[2 + at] = st->dis[2 + n - 1];
        st->dis[2 + n - 1] = 0;
        st->dis[1] = n - 1;
    } else {
        return SL_OK;                                    /* already so */
    }
    const struct strings *str = st->str;
    u8 *obj = mem_get(st->heap, 0x1000);
    if (!obj) return SL_IO;
    char *path = (char *)(obj + 0xF00);
    u32 d = slen(str->dir);
    copy(path, str->dir, d);
    path[d] = '\\';
    copy(path + d + 1, str->self, slen(str->self) + 1);
    int r = svc_file_is(svc, path, st->file, 64);
    if (r == SL_OK) {
        f_ctor(obj, DRIVE_SD);
        if (f_create(obj, path)) {
            f_write(obj, st->file, st->file_len);
            f_close(obj);
        } else r = SL_IO;
        f_dtor(obj);
    }
    mem_free(st->heap, obj);
    return r;
}

static void undo_current(struct state *st)
{
    for (u32 *e = (u32 *)(uintptr_t)st->jmark; e < st->jcur && e[0]; e += 2 + e[1] / 4)
        copy((void *)(uintptr_t)e[0], e + 2, e[1]);
    st->jcur = (u32 *)(uintptr_t)st->jmark;
    st->jcur[0] = 0;
    st->nclaims = st->cmark;
    /* rows and services a released sup registered go too */
    u32 k = 0;
    for (u32 i = 0; i < st->nrows; i++)
        if (st->rows[i].owner != st->cur) st->rows[k++] = st->rows[i];
    st->nrows = k;
    publish();
}

/* --- directory ---------------------------------------------------------------- */
static int wanted(const char *name, const char *self)
{
    u32 n = slen(name);
    if (n < 5 || name[0] == '.') return 0;
    const char *ext = name + n - 4;
    if (ext[0] != '.' || upper(ext[1]) != 'B' || upper(ext[2]) != 'I' || upper(ext[3]) != 'N')
        return 0;
    return ncmp(name, self) != 0;
}

/* A file name's version: the "_v<digit>..." before ".BIN" (the user 2026-10-25:
 * the version rides on the file name, Gyro2_v0.1.0.BIN).  Returns where the
 * version starts (after "_v"), 0 if the name carries none. */
static u32 name_ver(const char *n)
{
    u32 len = slen(n), at = 0;
    for (u32 i = 0; i + 2 < len - 4u; i++)
        if (n[i] == '_' && upper(n[i + 1]) == 'V' && n[i + 2] >= '0' && n[i + 2] <= '9') at = i + 2u;
    return at;
}

/* Two versions: numbers part by part, then a bare version above its suffixed
 * one (0.1.0 > 0.1.0test), then the suffixes.  >0: a is newer. */
static int ver_cmp(const char *a, const char *b)
{
    for (;;) {
        u32 x = 0, y = 0;
        int dx = 0, dy = 0;
        while (*a >= '0' && *a <= '9') { x = x * 10u + (u32)(*a++ - '0'); dx = 1; }
        while (*b >= '0' && *b <= '9') { y = y * 10u + (u32)(*b++ - '0'); dy = 1; }
        if (x != y) return x > y ? 1 : -1;
        if (dx != dy) return dx ? 1 : -1;
        if (*a == '.' && *b == '.') { a++; b++; continue; }
        break;
    }
    int ea = *a == '.' && upper(a[1]) == 'B', eb = *b == '.' && upper(b[1]) == 'B';   /* ".BIN": bare */
    if (ea != eb) return ea ? 1 : -1;
    return ncmp(a, b);                                  /* suffixes: the later one is newer */
}

/* Load order: alphabetical; two versions of one name newest first, so the
 * older one is the duplicate sup_id that does not load (the user 2026-10-25,
 * a new file copied in beside the old one). */
static int cand_cmp(const char *a, const char *b)
{
    u32 va = name_ver(a), vb = name_ver(b);
    if (va && va == vb) {
        u32 i = 0;
        while (i < va && upper(a[i]) == upper(b[i])) i++;
        if (i == va) return -ver_cmp(a + va, b + vb);
    }
    return ncmp(a, b);
}

/* Names in alphabetical order (the user 2026-10-20: no numeric prefixes). */
static u32 list_dir(struct state *st, u8 *s, const struct strings *str)
{
    struct cand *cand = (struct cand *)(s + S_CANDS);
    u32 n = 0;
    void *holder = s + S_HOLDER;
    u8 *ent = s + S_ENTRY;
    dir_ctor(holder, DRIVE_SD);
    if (!dir_open(holder, str->dir)) {
        logrec(st, L_NO_DIR, 0, 0, str->dir);
        dir_dtor(holder);
        return 0;
    }
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
        if (!ok || !wanted(name, str->self)) continue;
        u32 size_hi = *(volatile u32 *)(ent + 0x214);
        if (n == MAX_SUPS) { logrec(st, L_TOO_MANY, n, 0, name); continue; }
        copy(cand[n].name, name, i + 1);
        cand[n].size = size_hi ? 0xFFFFFFFFu : *(volatile u32 *)(ent + 0x210);
        cand[n].id = 0; cand[n].magic = 0;
        n++;
    }
    dir_dtor(holder);
    for (u32 i = 1; i < n; i++)
        for (u32 j = i; j && cand_cmp(cand[j - 1].name, cand[j].name) > 0; j--) {
            struct cand t;
            copy(&t, &cand[j], sizeof t);
            copy(&cand[j], &cand[j - 1], sizeof t);
            copy(&cand[j - 1], &t, sizeof t);
        }
    return n;
}

static char *make_path(u8 *s, const struct strings *str, const char *name)
{
    char *p = (char *)(s + S_PATH);
    u32 d = slen(str->dir);
    copy(p, str->dir, d);
    p[d] = '\\';
    copy(p + d + 1, name, slen(name) + 1);
    return p;
}

typedef int (*sup_entry)(void *block, const struct sl_svc *svc, const char *path);

/* A record of a file that did not load, so SupManager can show it. */
static struct sup *seen(struct state *st, const struct cand *c, const char *path, u32 id, u32 status)
{
    if (st->nsups >= MAX_SUPS) return 0;
    struct sup *sp = &st->sups[st->nsups++];
    zero(sp, sizeof *sp);
    copy(sp->name, c->name, slen(c->name) + 1);
    copy(sp->path, path, slen(path) + 1);
    sp->id = id; sp->state = SL_RELEASE; sp->status = status;
    return sp;
}

static int header_ok(const struct sl4_header *h, u32 got, u32 size)
{
    u32 ent = h->entry_off & ~1u;
    return got == sizeof *h && h->magic == SL4_MAGIC && h->header_len == SL4_HEADER_LEN
        && h->file_len == size && h->file_len >= SL4_HEADER_LEN
        && h->block_size >= h->file_len && h->block_size <= MAX_BLOCK
        && ent >= SL4_HEADER_LEN && ent < h->file_len
        && ((h->entry_off & 1) || !(ent & 3)) && h->min_svc <= SL4_SVC_VERSION
        && (!h->dma_len || (h->dma_off + h->dma_len <= h->block_size && h->dma_off + h->dma_len > h->dma_off))
        && (!h->name_off || h->name_off < h->file_len);
}

static void load_one(struct state *st, u8 *s, const struct strings *str, const struct cand *c)
{
    char *path = make_path(s, str, c->name);
    struct sl4_header *h = (struct sl4_header *)(s + S_HDR);
    zero(h, sizeof *h);
    u32 got = read_file_obj(s + S_FOBJ, path, h, sizeof *h);
    if (got == 0xFFFFFFFFu) { logrec(st, L_OPEN_FAIL, 0, 0, c->name); return; }
    if (got >= 4 && h->magic == SL3_MAGIC) {
        logrec(st, L_OLD_FORMAT, h->magic, 0, c->name);
        seen(st, c, path, 0, SL_S_OLD_FORMAT);
        return;
    }
    if (!header_ok(h, got, c->size)) {
        logrec(st, L_BAD_HEADER, h->magic, got, c->name);
        seen(st, c, path, 0, SL_S_BAD_HEADER);
        return;
    }
    if (st->has_smgr && h->sup_id != SL_SMGR_ID && listed(st, h->sup_id)) {
        logrec(st, L_DISABLED, h->sup_id, 0, c->name);
        struct sup *sp = seen(st, c, path, h->sup_id, SL_S_DISABLED);
        if (sp) sp->version = h->version;
        return;
    }
    for (u32 i = 0; i < st->nsups; i++)
        if (st->sups[i].id == h->sup_id && st->sups[i].state == SL_KEEP) {
            logrec(st, L_DUP_ID, h->sup_id, 0, c->name);
            seen(st, c, path, h->sup_id, SL_S_DUP_ID);
            return;
        }
    if (st->nsups >= MAX_SUPS) { logrec(st, L_TOO_MANY, st->nsups, 0, c->name); return; }
    u32 size = h->block_size, len = h->file_len, entry_off = h->entry_off, id = h->sup_id;
    u32 flags = h->flags, ver = h->version, name_off = h->name_off;
    /* 64-aligned and padded to whole lines: no cache line is shared with the
     * allocator's own words */
    u32 asize = ((size + LINE - 1) & ~(LINE - 1)) + 2 * LINE;
    u8 *raw = mem_get(st->heap, asize);
    if (!raw) { logrec(st, L_NO_MEMORY, size, 0, c->name); return; }
    u8 *ub = (u8 *)(uintptr_t)(((u32)(uintptr_t)raw + LINE - 1) & ~(LINE - 1));
    got = read_file_obj(s + S_FOBJ, path, ub, len);
    if (got != len || ((struct sl4_header *)ub)->magic != SL4_MAGIC) {
        logrec(st, L_SHORT_READ, len, got, c->name);
        mem_free(st->heap, raw);
        return;
    }
    zero(ub + len, ((size + LINE - 1) & ~(LINE - 1)) - len);
    /* whatever the cached alias held for these lines (a past boot's block)
     * goes before the sup runs there */
    publish();
    u32 run = (flags & SL_F_CACHED_OK) ? cached((u32)(uintptr_t)ub) : (u32)(uintptr_t)ub;

    struct sup *sp = &st->sups[st->nsups];
    zero(sp, sizeof *sp);
    copy(sp->name, c->name, slen(c->name) + 1);
    copy(sp->path, path, slen(path) + 1);
    if (name_off) {
        const char *dn = (const char *)ub + name_off;
        u32 i = 0;
        for (; i < sizeof sp->disp - 1 && name_off + i < len && dn[i]; i++) sp->disp[i] = dn[i];
        sp->disp[i] = 0;
    }
    sp->id = id; sp->block = (void *)(uintptr_t)run; sp->state = SL_RELEASE;
    sp->version = ver; sp->ublock = (u32)(uintptr_t)ub; sp->size = size;
    st->cur = st->nsups++;
    st->jmark = (u32)(uintptr_t)st->jcur;
    st->cmark = st->nclaims;
    u32 rmark = st->nrows, smark = st->nserv;
    st->running = 1;
    int r = ((sup_entry)(uintptr_t)(run + entry_off))((void *)(uintptr_t)run, &st->svc, sp->path);
    st->running = 0;
    if (r == SL_KEEP) {
        sp->state = SL_KEEP;
        sp->status = SL_S_LOADED;
        u32 nc = 0;
        for (u32 i = st->cmark; i < st->nclaims; i++) nc += !st->claims[i].res;
        logrec(st, L_LOADED, run, nc, c->name);
    } else {
        undo_current(st);
        (void)rmark;
        st->nserv = smark;
        mem_free(st->heap, raw);
        sp->block = 0;
        sp->status = SL_S_RELEASED;
        logrec(st, L_RELEASED, (u32)r, 0, c->name);
    }
    publish();
}

/* --- the log file ------------------------------------------------------------- */
static char *hex(char *p, u32 v, u32 digits)
{
    while (digits--) {
        u32 d = (v >> (4 * digits)) & 15;
        *p++ = (char)(d < 10 ? '0' + d : 'A' + d - 10);
    }
    return p;
}

static void write_log(struct state *st, const struct strings *str)
{
    char *buf = mem_get(st->heap, LOG_FILE_BYTES);
    if (!buf) return;
    char *p = buf, *end = buf + LOG_FILE_BYTES - 64;
    for (u32 i = 0; i < st->nlog && p < end; i++) {
        struct logrec *r = &st->log[i];
        p = hex(p, r->code, 2); *p++ = ' ';
        p = hex(p, r->a, 8); *p++ = ' ';
        p = hex(p, r->b, 8); *p++ = ' ';
        for (u32 j = 0; j < sizeof r->text && r->text[j]; j++) *p++ = r->text[j];
        *p++ = '\n';
    }
    while (p < buf + LOG_FILE_BYTES - 1) *p++ = ' ';
    *p = '\n';
    u8 *obj = mem_get(st->heap, 0x1000);
    if (obj) {
        char *path = (char *)(obj + 0xF00);
        u32 d = slen(str->dir);
        copy(path, str->dir, d);
        path[d] = '\\';
        copy(path + d + 1, str->logname, slen(str->logname) + 1);
        f_ctor(obj, DRIVE_SD);
        if (f_create(obj, path)) {
            f_write(obj, buf, LOG_FILE_BYTES);
            f_close(obj);
        }
        f_dtor(obj);
        mem_free(st->heap, obj);
    }
    mem_free(st->heap, buf);
}

#ifdef PWROFF_LOG
static u32 pl_rd(u32 a) { return *(volatile u32 *)(uintptr_t)a; }

/* Called by the stock C0122F90 through [0xC31D848C]: no arguments, its result
 * decides 0x40 (non-zero) or 0x10.  Records before and after the stock call
 * (the stock one may not return: its reset path) and cleans the D-cache so a
 * self-refresh keeps the record. */
static u32 pl_wrap(void)
{
    volatile u32 *s = (volatile u32 *)(uintptr_t)PL_STORE;
    volatile u32 *l = (volatile u32 *)(uintptr_t)s[2];
    if (l) {
        l[0] = 0;
        l[1] = s[1];
        l[2] = 1;
        l[3] = 0;
        l[4] = tick_us();
        for (u32 i = 0; i < 4; i++) l[5 + i] = pl_rd(PL_PMU + 0x80u + 4u * i);
        l[9] = pl_rd(PL_CBOBJ + 0x230u);
        l[10] = pl_rd(PL_CBOBJ + 0x234u);
        l[11] = pl_rd(PL_PMU);
        l[0] = PL_LMAGIC;
        dcache();
    }
    u32 r = FW(PL_CB_STOCK, u32 (*)(void))();
    if (l) {
        l[3] = r;
        l[2] = 2;
        l[12] = tick_us();
        dcache();
    }
    return r;
}

/* From the power-off routine (sloader4_entry.S `unhook`), before the journal
 * is written back; both lists call it, so possibly twice. */
static void pl_early(u32 *poff, u32 reason)
{
    volatile u32 *s = (volatile u32 *)(uintptr_t)PL_STORE;
    if (s[0] != PL_MAGIC) {
        for (u32 i = 0; i < PL_WORDS; i++) s[i] = 0;
        s[0] = PL_MAGIC;
    }
    poff[6]++;
    s[3] = poff[6];
    if (poff[6] != 1) return;                  /* the second list: count only */
    s[1] = s[1] + 1;
    s[2] = poff[5];
    s[4] = reason;
    s[5] = tick_us();
    s[6] = pl_rd(PL_MGR + 0x08u);
    s[7] = pl_rd(PL_MGR + 0x60u);
    s[8] = pl_rd(PL_MGR + 0x68u);
    s[9] = pl_rd(PL_MGR + 0x6Cu);
    s[10] = pl_rd(PL_MGR + 0x70u);
    for (u32 i = 0; i < 4; i++) s[11 + i] = pl_rd(PL_PMU + 0x80u + 4u * i);
    s[15] = pl_rd(PL_PMU);
    u32 cb = pl_rd(PL_CBOBJ);
    s[16] = cb;
    s[17] = pl_rd(PL_CBOBJ + 0x230u);
    s[18] = pl_rd(PL_CBOBJ + 0x234u);
    if (cb == PL_CB_STOCK) {
        *(volatile u32 *)(uintptr_t)PL_CBOBJ = poff[4];
        s[19] = 1;
    } else {
        s[19] = cb == poff[4] ? 2u : 0u;
    }
    s[20] = poff[7];
}
#endif


#ifdef PWROFF_FILE
static u32 pf_rd(u32 a) { return *(volatile u32 *)(uintptr_t)a; }

/* After the other hooks (so the callback word shows whether it was wrapped).
 * Both lists call the routine: the first writes, the second only counts --
 * a second write would stall the second list on the card for nothing. */
static void pf_write(u32 *poff, u32 reason)
{
    struct state *st = (struct state *)((u8 *)poff - __builtin_offsetof(struct state, poff));
    st->pf_calls++;
    if (st->pf_calls != 1 || !st->pf_obj) return;
    u8 *obj = st->pf_obj;
    u32 *r = (u32 *)(obj + 0x1080);
    for (u32 i = 0; i < PF_WORDS; i++) r[i] = 0;
    r[1] = st->pf_seq + 1;
    r[2] = st->pf_calls;
    r[3] = reason;
    r[4] = tick_us();
    r[5] = pf_rd(PF_NOW_MS);
    r[6] = pf_rd(PF_MGR + 0x08u);
    r[7] = pf_rd(PF_MGR + 0x60u);
    r[8] = pf_rd(PF_MGR + 0x68u);
    r[9] = pf_rd(PF_MGR + 0x6Cu);
    r[10] = pf_rd(PF_MGR + 0x70u);
    for (u32 i = 0; i < 4; i++) r[11 + i] = pf_rd(PF_PMU + 0x80u + 4u * i);
    r[15] = pf_rd(PF_PMU + 0x94u);                 /* 0x2D000314: raw inputs (VBUS = id2) */
    r[16] = pf_rd(PF_PMU);                         /* 0x2D000280 */
    u32 bm = pf_rd(PF_BATT + 4u);
    r[17] = bm ? *(volatile u8 *)(uintptr_t)(bm + 0xB8u) : 0xFFFFFFFFu;
    r[18] = pf_rd(PF_BUSY);
    r[19] = pf_rd(PF_CBOBJ);
    r[20] = pf_rd(PF_CBOBJ + 0x230u);
    r[21] = pf_rd(PF_CBOBJ + 0x234u);
    r[22] = r[23] = 0xFFFFFFFEu;
    r[25] = st->svc.boot_id;
    r[26] = *(volatile u32 *)(uintptr_t)LOAD_DONE_US;
    r[PF_WORDS - 1] = ~PF_MAGIC;
    r[0] = PF_MAGIC;
    f_ctor(obj, DRIVE_SD);
    if (f_create(obj, (const char *)(obj + 0x1000))) {
        f_write(obj, r, 4u * PF_WORDS);
        f_close(obj);
        st->pf_seq++;
    }
    f_dtor(obj);
}
#endif

#if defined(PWROFF_LOG) || defined(PWROFF_FILE)
/* poff[3]: called by sloader4_entry.S `unhook` before the journal write-back. */
static void poff_hook(u32 *poff, u32 reason)
{
#ifdef PWROFF_LOG
    pl_early(poff, reason);
#else
    (void)reason;
#endif
#ifdef PWROFF_FILE
    pf_write(poff, reason);
#endif
}
#endif

#ifdef FPSUP_UI
#include "fpsup_home.c"
#else
static int svc_borrow(const struct sl_svc *svc, const void *lo, const void *hi) { (void)svc; (void)lo; (void)hi; return SL_BADARG; }
static int svc_ui_go(const struct sl_svc *svc, const char *page) { (void)svc; (void)page; return SL_BADARG; }
#endif

/* --- the resident half -------------------------------------------------------- */
static u32 sl_load(struct state *st, const struct strings *str)
{
    *(volatile u32 *)(uintptr_t)CAVE_BUMP = CAVE_ARENA;
#ifdef BOOT_MARKERS
    /* build_autorun --boot-markers put a stamp routine and its array at the
     * arena start before the loader ran.  Take that block first, so nothing
     * the load hands out lands on it, and tag the array: 'MRK1' means this
     * boot's AutoRun wrote it (keep the stamps, mark it seen); anything else
     * is a previous boot's array -- a warm boot runs no AutoRun -- so empty it. */
    /* The arena start is 4 mod 8 and cave_alloc rounds up to 8, so the first
     * block comes back at MARK_AT or MARK_AT + 4.  Either way the bump started
     * at MARK_AT and now sits past MARK_AT + MARK_BYTES: the whole array is ours. */
    u32 mp = svc_cave_alloc(0, MARK_BYTES);
    if (mp >= MARK_AT && mp <= MARK_AT + 7) {
        volatile u32 *md = (volatile u32 *)(uintptr_t)MARK_DATA;
        if (md[0] == MARK_LIVE) md[0] = MARK_SEEN;
        else { md[1] = 0; md[0] = MARK_NONE; }
    }
#endif
    st->str = str;
    st->svc.version = SL4_SVC_VERSION;
    st->svc.boot_id = tick_us();
    st->svc.claim = svc_claim;
    st->svc.claim_res = svc_claim_res;
    st->svc.chain_next = svc_chain_next;
    st->svc.cave_alloc = svc_cave_alloc;
    st->svc.publish = svc_publish;
    st->svc.log = svc_log;
    st->svc.holder = svc_holder;
    st->svc.self = svc_self;
    st->svc.done_at_start = *(volatile u32 *)(uintptr_t)LOAD_DONE_US;
    st->svc.uncached = svc_uncached;
    st->svc.self_path = svc_self_path;
    st->svc.file_is = svc_file_is;
    st->svc.provide = svc_provide;
    st->svc.find = svc_find;
    st->svc.page_add = svc_page_add;
    st->svc.page_refresh = svc_page_refresh;
    st->svc.page_count = svc_page_count;
    st->svc.page_row = svc_page_row;
    st->svc.sups_list = svc_sups_list;
    st->svc.disabled_get = svc_disabled_get;
    st->svc.disabled_set = svc_disabled_set;
    st->svc.file_read = svc_file_read;
    st->svc.borrow = svc_borrow;
    st->svc.ui_go = svc_ui_go;
    logrec(st, L_START, st->svc.boot_id, 0, 0);
#ifdef PWROFF_LOG
    /* not zeroed: after a warm restart it still holds the last power-off's
     * late record (a cold boot reloads the image, so it is zero then) */
    st->poff[5] = svc_cave_alloc(0, PL_LATE_BYTES);
    st->poff[3] = (u32)(uintptr_t)poff_hook;
    st->poff[4] = (u32)(uintptr_t)pl_wrap;
    st->poff[6] = 0;
    st->poff[7] = st->svc.boot_id;
    logrec(st, L_PWRLOG, st->poff[5], pl_rd(PL_STORE + 4u), 0);
#endif
#ifdef PWROFF_FILE
    {
        st->pf_calls = 0;
        st->pf_seq = 0;
        st->pf_obj = mem_get(st->heap, PF_OBJ_BYTES);
        if (st->pf_obj) {
            char *path = (char *)(st->pf_obj + 0x1000);
            u32 d = slen(str->dir);
            copy(path, str->dir, d);
            /* "\PWROFF.LOG" as immediates: no string literal in the resident code */
            char *p = path + d;
            p[0] = '\\'; p[1] = 'P'; p[2] = 'W'; p[3] = 'R'; p[4] = 'O'; p[5] = 'F';
            p[6] = 'F'; p[7] = '.'; p[8] = 'L'; p[9] = 'O'; p[10] = 'G'; p[11] = 0;
            u32 *rec = (u32 *)(st->pf_obj + 0x1080);
            if (read_file_obj(st->pf_obj, path, rec, 4u * PF_WORDS) == 4u * PF_WORDS &&
                rec[0] == PF_MAGIC && rec[PF_WORDS - 1] == ~PF_MAGIC)
                st->pf_seq = rec[1];
            st->poff[3] = (u32)(uintptr_t)poff_hook;
        }
        logrec(st, L_PWRFILE, (u32)(uintptr_t)st->pf_obj, st->pf_seq, 0);
    }
#endif

    st->jbase = mem_get(st->heap, JOURNAL_BYTES);
    if (!st->jbase) { logrec(st, L_NO_MEMORY, JOURNAL_BYTES, 0, 0); return 0; }
    st->jbase = (u32 *)(uintptr_t)cached((u32)(uintptr_t)st->jbase);
    st->jbase[0] = 0;
    st->jcur = st->jbase;
    st->jend = st->jbase + JOURNAL_BYTES / 4;
    st->poff[0] = (u32)(uintptr_t)st->poff - 8;
    st->poff[2] = (u32)(uintptr_t)st->jbase;
    publish();
    void *m = poff_mgr();
    if (!m || !poff_add(m, st->poff, 0)) { logrec(st, L_NO_POFF, 0, 0, 0); return 0; }
    m = poff_mgr();
    if (!m || !poff_add(m, st->poff, 1)) { logrec(st, L_NO_POFF, 1, 0, 0); return 0; }

    u8 *s = mem_get(st->heap, SCRATCH_BYTES);
    if (!s) { logrec(st, L_NO_MEMORY, SCRATCH_BYTES, 0, 0); return 0; }
    zero(s, SCRATCH_BYTES);
    u32 n = list_dir(st, s, str);
    logrec(st, L_LISTED, n, 0, 0);
    /* Is SupManager on the card (a v4 file with its id)?  Without it the
     * disabled list is ignored: whatever is on the card loads. */
    struct cand *cand = (struct cand *)(s + S_CANDS);
    for (u32 i = 0; i < n; i++) {
        struct sl4_header *h = (struct sl4_header *)(s + S_HDR);
        zero(h, sizeof *h);
        u32 got = read_file_obj(s + S_FOBJ, make_path(s, str, cand[i].name), h, sizeof *h);
        if (got != 0xFFFFFFFFu && header_ok(h, got, cand[i].size) && h->sup_id == SL_SMGR_ID)
            st->has_smgr = 1;
    }
#ifdef FPSUP_UI
    ui_early(st, s, str);                        /* the two fixed-rule hooks, before any sup */
#endif
    *(volatile u32 *)(uintptr_t)SL_SVC_AT = (u32)(uintptr_t)&st->svc;
    publish();
    for (u32 i = 0; i < n; i++)
        load_one(st, s, str, &cand[i]);
    *(volatile u32 *)(uintptr_t)SL_SVC_AT = 0;
#ifdef FPSUP_UI
    ui_load(st, s, str);
#endif
    mem_free(st->heap, s);

    u32 kept = 0;
    for (u32 i = 0; i < st->nsups; i++) kept += st->sups[i].state == SL_KEEP;
    publish();
    *(volatile u32 *)(uintptr_t)LOAD_DONE_US = tick_us();
    logrec(st, L_DONE, kept, st->nsups, 0);
    return kept;
}

static u32 sl_run(struct state *st, const struct strings *str)
{
    u32 kept = sl_load(st, str);
    if (!st->svc.boot_id) return kept;
    write_log(st, str);
    if (str->splash) FW(str->splash, void (*)(void))();
    return kept;
}

typedef u32 (*run_fn)(struct state *, const struct strings *);

/* In the staging buffer: copy all of this into a block of its own (64-aligned),
 * then carry on at its cached alias. */
u32 sl_boot(const u8 *vbin, u32 unhook, u32 base, const struct strings *str)
{
    u32 code = *(const u32 *)(uintptr_t)(base - 4u);
    u32 state_at = (code + LINE - 1) & ~(LINE - 1);
    void *heap = mem_heap(0);
    if (!heap) return 0;
    u32 total = state_at + ((sizeof(struct state) + LINE - 1) & ~(LINE - 1));
    u8 *raw = mem_get(heap, total + 2 * LINE);
    if (!raw) return 0;
    u8 *ub = (u8 *)(uintptr_t)(((u32)(uintptr_t)raw + LINE - 1) & ~(LINE - 1));
    copy(ub, (const void *)(uintptr_t)base, code);
    zero(ub + code, total - code);
    publish();                                   /* the copy is code now */
    u8 *res = (u8 *)(uintptr_t)cached((u32)(uintptr_t)ub);
    struct state *st = (struct state *)(res + state_at);
    st->heap = heap;
    st->poff[1] = (u32)(uintptr_t)res + (unhook - base);
    struct strings *rs = (struct strings *)(res + ((u32)(uintptr_t)str - base));
    rs->dir = (const char *)(res + ((u32)(uintptr_t)str->dir - base));
    rs->self = (const char *)(res + ((u32)(uintptr_t)str->self - base));
    rs->logname = (const char *)(res + ((u32)(uintptr_t)str->logname - base));
    rs->splash = str->splash ? (u32)(uintptr_t)res + (str->splash - base) : 0;
    rs->ui = str->ui ? (const char *)(res + ((u32)(uintptr_t)str->ui - base)) : 0;
    /* LOADER.BIN as read, and its disabled list after the code */
    u32 envelope = 16u + 8u * *(const u32 *)(vbin + 4) + *(const u32 *)(vbin + 12);
    st->file_len = envelope + DS_BYTES;
    u8 *f = mem_get(heap, st->file_len);
    if (f) {
        st->file = (u8 *)(uintptr_t)cached((u32)(uintptr_t)f);
        copy(st->file, vbin, st->file_len);
        zero(st->file + ((u32)(uintptr_t)str - (u32)(uintptr_t)vbin), sizeof(struct strings));
        u32 *d = (u32 *)(st->file + envelope);
        if (d[0] == DS_MAGIC && d[1] <= DS_MAX) st->dis = d;
    }
    publish();
    run_fn run = (run_fn)(uintptr_t)((u32)(uintptr_t)res + ((u32)(uintptr_t)sl_run - base));
    return run(st, rs);
}
