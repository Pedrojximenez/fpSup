/* Loader v4 -- the contract between the core (LOADER.BIN) and a sup.
 *
 * Design: projects/loader-v4/DESIGN.md (finalised 2026-10-20).  Differences
 * from v3 (v3/sloader.h):
 *   - a 48-byte header, magic "FSB4": flags, one DMA range, a display name;
 *     v3 files ("FSB1") are not loaded (LOAD.LOG says why).
 *   - SL_F_CACHED_OK: the core runs the sup from the cached alias of its
 *     block (+0x80000000).  The firmware allocator hands out the uncached
 *     alias (0x4...), where code runs about 50x slower (camera 2026-10-20).
 *   - the fpSup page is a registry: a sup adds rows with page_add(); the
 *     core sorts them by title (SupManager first) and pages them 5 at a time.
 *   - the disabled list is the core's; it applies only when SupManager is on
 *     the card, and SupManager cannot disable itself.
 *   - provide()/find() replace guessing another sup's veneer shape.
 *
 *     int entry(void *block, const struct sl_svc *svc, const char *path);
 *
 * `block` is the alias the sup runs at (cached when SL_F_CACHED_OK), `path`
 * its own file ("\fpSup\RESCUS.BIN"), valid for the whole boot. */
#ifndef SLOADER4_H
#define SLOADER4_H
#include <stdint.h>

#define SL4_MAGIC        0x34425346u      /* "FSB4" */
#define SL3_MAGIC        0x31425346u      /* "FSB1": v3, refused */
#define SL4_HEADER_LEN   48u
#define SL4_SVC_VERSION  7u      /* 6: file_read, borrow (DESIGN.md §14); 7: ui_go */
#define SL_SMGR_ID       0x52474D53u      /* "SMGR": SupManager's sup_id */
#define SL_UI_ID         0x34495546u      /* "FUI4": the core's own UI, listed as LOADER.BIN */
#define SL_ALIAS         0x80000000u      /* uncached 0x4... + this = cached 0xC... */

struct sl4_header {
    uint32_t magic;        /* SL4_MAGIC                                       */
    uint32_t header_len;   /* SL4_HEADER_LEN                                  */
    uint32_t file_len;     /* the whole file, header included                 */
    uint32_t block_size;   /* >= file_len; the rest is zeroed (the sup's BSS) */
    uint32_t entry_off;    /* from the block's first byte; bit 0 = Thumb      */
    uint32_t sup_id;       /* four characters; a second file with it is skipped */
    uint32_t version;
    uint32_t min_svc;      /* the service-table version it needs              */
    uint32_t flags;        /* SL_F_*                                          */
    uint32_t dma_off;      /* [dma_off, dma_off+dma_len) of the block is shared */
    uint32_t dma_len;      /*   with a DMA engine: use svc->uncached() for it  */
    uint32_t name_off;     /* display name, NUL-terminated, in the file; 0 none */
};

enum { SL_F_CACHED_OK = 1u };
enum { SL_KEEP = 0, SL_RELEASE = 1 };
enum { SL_CHAIN = 1, SL_EXCL = 2, SL_SHARED_UI = 3 };
enum { SL_OK = 0, SL_CONFLICT = -1, SL_FULL = -2, SL_BADARG = -3,
       SL_NOT_SELF = -4,    /* file_is: the file is not (or no longer) the sup's */
       SL_IO = -5 };

/* --- the fpSup page -------------------------------------------------------- */
enum { SL_ROW_JUMP = 1, SL_ROW_TOGGLE, SL_ROW_LIST, SL_ROW_ACTION };
#define SL_PAGE_ROWS    5u      /* rows per page (the user 2026-10-20)        */
#define SL_PAGE_MAX     64u     /* rows in total; no per-sup limit            */
#define SL_LIST_MAX     3u      /* LIST choices: MainY5's popup has three     */

/* One row.  The core keeps the pointer: the struct and its strings stay
 * resident in the sup's block.  Callbacks run on the UI thread; return fast. */
struct sl_row {
    uint16_t kind;                          /* SL_ROW_*                        */
    uint16_t n_choices;                     /* LIST: 1..SL_LIST_MAX; TOGGLE: 0, or 2 labels */
    const char *title;                      /* sort key and the row's text     */
    const char *value;                      /* right-hand text, may be 0       */
    int  (*get)(void *arg);                 /* TOGGLE / LIST: current value    */
    int  (*set)(void *arg, int v);          /* TOGGLE / LIST: 0 = accepted     */
    const char *const *choices;             /* LIST; TOGGLE: optional {off, on} labels */
    int  (*open)(void *arg);                /* JUMP: its own page; ACTION: run */
    void *arg;
};

/* What SupManager is shown about each file the core looked at. */
enum { SL_S_LOADED = 1, SL_S_RELEASED, SL_S_DISABLED, SL_S_OLD_FORMAT,
       SL_S_BAD_HEADER, SL_S_DUP_ID, SL_S_FAILED };
struct sl_supinfo {
    const char *name;      /* "RESCUS.BIN"                                   */
    const char *display;   /* the header's display name, or the file name    */
    uint32_t id, version, status;
    uint32_t next_boot;    /* 1: will load next boot (not on the list)       */
};

struct sl_svc {
    /* ---- v3's table, at v3's offsets (patch_sup.S calls +8 .. +28) ---- */
    uint32_t version;                     /* SL4_SVC_VERSION                   */
    uint32_t boot_id;
    int      (*claim)(const struct sl_svc *, uint32_t addr, uint32_t len,
                      const void *stock, uint32_t kind);
    int      (*claim_res)(const struct sl_svc *, uint32_t id, uint32_t kind);
    uint32_t (*chain_next)(const struct sl_svc *, uint32_t site, uint32_t thumb);
    /* unchanged from v3: 8-aligned cave bytes for veneers (RESCUS's 24-byte
     * veneer at C043CCF8 keeps its shape) */
    uint32_t (*cave_alloc)(const struct sl_svc *, uint32_t bytes);
    void     (*publish)(const struct sl_svc *);
    void     (*log)(const struct sl_svc *, const char *line);
    const char *(*holder)(const struct sl_svc *, uint32_t addr, uint32_t i);
    const char *(*self)(const struct sl_svc *);     /* own path while entry runs */
    uint32_t done_at_start;
    /* ---- v4 (version 5) ---- */
    /* The uncached alias of an address in the sup's block (for its DMA range). */
    void    *(*uncached)(const struct sl_svc *, const void *p);
    /* Own file's path at any time (not only during entry); 0 if not a sup. */
    const char *(*self_path)(const struct sl_svc *, const void *block);
    /* SL_OK when `path` exists and its first `n` bytes equal `expect`: check
     * before writing back into a file (mode 7 creates; sup-writeback-must-not-create). */
    int      (*file_is)(const struct sl_svc *, const char *path, const void *expect, uint32_t n);
    /* A named entry point another sup can find without knowing veneer shapes. */
    int      (*provide)(const struct sl_svc *, uint32_t id, void *ptr);
    void    *(*find)(const struct sl_svc *, uint32_t id);
    /* fpSup page. */
    int      (*page_add)(const struct sl_svc *, const struct sl_row *row);  /* row# or <0 */
    void     (*page_refresh)(const struct sl_svc *, int row);
    uint32_t (*page_count)(const struct sl_svc *);                  /* rows      */
    const struct sl_row *(*page_row)(const struct sl_svc *, uint32_t i); /* sorted */
    /* SupManager. */
    int      (*sups_list)(const struct sl_svc *, uint32_t i, struct sl_supinfo *out);
    int      (*disabled_get)(const struct sl_svc *, uint32_t id);
    int      (*disabled_set)(const struct sl_svc *, uint32_t id, uint32_t off);
    /* ---- version 6 (DESIGN.md §14) ---- */
    /* Up to `want` bytes of a file on the card into `buf`: the count, or SL_IO. */
    int      (*file_read)(const struct sl_svc *, const char *path, void *buf, uint32_t want);
    /* [lo, hi) holds strings handed to the firmware by id (fpSup/fpsup-ui):
     * the firmware must never free them.  No limit on how many ranges. */
    int      (*borrow)(const struct sl_svc *, const void *lo, const void *hi);
    /* ---- version 7 ---- */
    /* From a JUMP row's open() only: the fpSup page asks the firmware's state
     * machine for request `page` (fpsup-ui fpui_open), after open()'s own posts
     * are applied.  The page's pack must have the transition (FT_Y6 -> page,
     * request = page: build_fp4.open_transitions) and its screen-enter must write
     * FT_Go = 0 (manage_page.enter_write).  A direct screen set (fpui_show) makes
     * the menu drop fast keys until it is left (camera, 2026-10-25).
     * SL_BADARG outside an open() or for a name of SL_GO_MAX bytes or more. */
    int      (*ui_go)(const struct sl_svc *, const char *page);
};
#define SL_GO_MAX       32u      /* build_fp4.GO_TEXT's length + 1 */

/* While entries run: &svc here, else 0 (v3's SL_SVC_AT, unchanged). */
#define SL_SVC_AT       0xC072F6FCu

#endif
