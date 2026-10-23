/* bq -- block queue between stock C063F380 (the submitter) and our writer task.
 * Pure logic, no firmware calls; the native glue holds a lock around every call.
 * Design: research/storage/notes/WRITER_LOCK_SCOPE.md §5-§7, WRITER_SPEC §5.
 *
 * Stock still decides WHAT goes in a batch (C063F380/C063F048: extents, cluster
 * padding, threshold +0x4828, cookie limit).  We take the arena callbacks
 * vol+0x4834..0x4848 so the batch is collected into one of our blocks instead
 * of the driver's single arena, and C063F140 (the synchronous send) becomes
 * bq_seal: the block is queued and the submitter gets an empty one back.
 *
 *   acquire  -> bq_open     never 0 while a block is free; the glue waits otherwise
 *   checkpoint/add/rollback -> bq_checkpoint / bq_add / bq_rollback (C063F048)
 *   C063F140 -> bq_seal     cl = +0x4A54, bytes = +0x4A58, cookies +0x4854[0..+0x4850)
 *   +0x4834 (frame with no bytes in the open batch: 4A58 == 0) -> bq_late_cookie
 *
 * Writer: bq_take -> bq_chunk (pieces the driver arena can hold, cut only where a
 * C063F048 extent ended, i.e. at a cluster edge) -> bq_complete_begin ->
 * bq_complete_next until 0.  Blocks complete strictly in seal order and every
 * cookie is handed back exactly once, in the order it was given to us.
 */
#ifndef REC_CORE_BQ_H
#define REC_CORE_BQ_H
#include <stdint.h>

#ifndef BQ_BLOCKS
#define BQ_BLOCKS      3u      /* filling + writing + one queued                     */
#endif
#define BQ_MAX_SEG    2048u    /* add() calls per batch; > 128 frames x (8 + 2 pad)  */
#define BQ_MAX_CUT     160u    /* C063F048 extents per batch: <= 128 frames + slack  */
#define BQ_MAX_COOKIE  136u    /* stock 0x80 + late cookies                           */
#define BQ_SECTOR      512u

enum { BQ_FREE = 0, BQ_FILLING, BQ_QUEUED, BQ_WRITING };

enum {
    BQ_OK = 0,
    BQ_NONE = 1,               /* late cookie: nothing in flight, call it directly    */
    BQ_FULL = -1,              /* no free block / table full                          */
    BQ_BADARG = -2,
    BQ_STATE = -3,
    BQ_MISMATCH = -4,          /* stock's byte count != what was added                */
    BQ_TOOBIG = -5,            /* one extent alone exceeds the driver's table         */
};

typedef struct { uint32_t addr, len; } bq_seg;

typedef struct {
    uint32_t max_entries;      /* driver table size (0x400)                           */
    uint32_t max_heads;        /* SD bounce slots for unaligned heads (0x100); 0 = n/a */
    uint32_t max_desc;         /* SD: bytes per descriptor ([0xC2F2E750]); 0 = 1/seg  */
} bq_limits;

typedef struct {
    uint32_t state, seq;
    uint32_t cl;               /* first cluster (vol+0x4A54)                          */
    uint32_t bytes;            /* sum of seg lens                                     */
    uint32_t skip;             /* sealed with cl == 0 or bytes == 0: write nothing    */
    uint32_t status;           /* first failure of any chunk, else 0                  */
    uint32_t nseg, ncut, ncookie;
    uint32_t ck_seg, ck_bytes, ck_cut;   /* checkpoint                                 */
    uint32_t x_ent, x_heads;   /* driver entries of the extent being added            */
    uint32_t cut[BQ_MAX_CUT];  /* seg index where an extent begins                    */
    uint32_t cookie[BQ_MAX_COOKIE];
    bq_seg   seg[BQ_MAX_SEG];
} bq_block;

typedef struct {
    bq_limits lim;             /* an extent that alone exceeds them is refused at add */
    uint32_t next_seq, done_seq;
    uint32_t fill;             /* index of the FILLING block or BQ_BLOCKS              */
    /* completion in progress: cookies copied out of a freed block, handed back one by
     * one outside the lock; late cookies that arrive meanwhile join the tail */
    uint32_t completing, cpos, cn, cstatus;
    uint32_t cfirst;           /* status of clist[0] (a carried failure)              */
    uint32_t carry;            /* a failed block's status, owed to the frame that may */
                               /* span into the next block (stock reports only the    */
                               /* later block: we may over-report one frame, never    */
                               /* under-report)                                       */
    uint32_t last_status;      /* status of the block completed most recently         */
    uint32_t clist[BQ_MAX_COOKIE + 16];
    uint32_t n_sealed, n_skip, n_late, n_late_direct, n_chunks, n_full, n_mismatch;
    bq_block blk[BQ_BLOCKS];
} bq_t;

void      bq_init(bq_t *q, const bq_limits *lim);
bq_block *bq_open(bq_t *q);                         /* acquire; 0 = none free       */
int       bq_checkpoint(bq_t *q);
int       bq_add(bq_t *q, uint32_t addr, uint32_t len);
int       bq_rollback(bq_t *q);
int       bq_seal(bq_t *q, uint32_t cl, uint32_t bytes, const uint32_t *cookies, uint32_t n);
/* BQ_NONE: nothing in flight; call it now with *status (its bytes were in the
 * block completed last, so it gets that block's status). */
int       bq_late_cookie(bq_t *q, uint32_t cookie, uint32_t *status);
bq_block *bq_take(bq_t *q);
/* Next piece of `b` starting at segment *from that fits q->lim; returns its segment
 * count (0 = done) and its bytes in *bytes, advances *from.  Cuts only where an
 * extent began.  BQ_TOOBIG cannot happen for blocks filled through bq_add, which
 * refuses (like the stock arena) an extent that alone would not fit. */
int       bq_chunk(const bq_t *q, const bq_block *b, uint32_t *from, uint32_t *bytes);
int       bq_complete_begin(bq_t *q, bq_block *b, uint32_t status);
/* 1 and *cookie, *status = next to hand back; 0 = completion finished. */
int       bq_complete_next(bq_t *q, uint32_t *cookie, uint32_t *status);
int       bq_idle(const bq_t *q);                   /* nothing queued/writing/completing */
uint32_t  bq_entries(uint32_t addr, uint32_t len, const bq_limits *lim, uint32_t *heads);

#endif
