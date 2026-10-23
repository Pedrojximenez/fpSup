/* wq -- the writer's block queue (pure logic, no firmware calls).
 *
 * WRITER_SPEC.md §5.1 / §5.4c.  The submitter (stock task, FS lock held) feeds
 * the take's data as one LBA-contiguous stream of segments; wq cuts that stream
 * into blocks of exactly `block_bytes` (a multiple of the RU, 512 KB), so every
 * write the writer task issues is RU-aligned and an RU multiple.  A segment that
 * crosses a block edge is split; a frame may therefore span two blocks, and its
 * cookie belongs to the block holding its last byte (as stock C063F380 does).
 *
 * Blocks: FREE -> FILLING -> QUEUED -> WRITING -> FREE.  One producer (submitter),
 * one consumer (writer task).  wq is NOT thread-safe: the native adapter holds a
 * lock around every call.  Completion hands each cookie back exactly once, in
 * the order the frames were submitted.
 */
#ifndef REC_CORE_WQ_H
#define REC_CORE_WQ_H
#include <stdint.h>

#define WQ_BLOCKS     4u        /* filling + writing + two queued: absorbs a stall */
#define WQ_MAX_SEG  256u        /* stock C069ADE0 sends <= 8 segments per frame   */
#define WQ_MAX_COOKIE 128u      /* stock batch limit is 0x80 cookies (C063F380)   */
#define WQ_SECTOR   512u

enum { WQ_FREE = 0, WQ_FILLING, WQ_QUEUED, WQ_WRITING };

enum {                          /* return codes */
    WQ_OK = 0,
    WQ_FULL = -1,               /* no free block: caller must wait for the writer */
    WQ_BADARG = -2,
    WQ_SEGS = -3,               /* segment table of the filling block exhausted   */
    WQ_COOKIES = -4,
};

/* why a block left FILLING (diagnostics; also tells the writer whether it is a
 * full RU-aligned block) */
enum { WQ_CLOSE_FULL = 1, WQ_CLOSE_GAP = 2, WQ_CLOSE_FLUSH = 3, WQ_CLOSE_LIMIT = 4 };

typedef struct { uint32_t addr, len; } wq_seg;

typedef struct {
    uint32_t state, close_reason, status;
    uint32_t lba;               /* first sector of this block on the medium        */
    uint32_t bytes;
    uint32_t nseg, ncookie;
    uint32_t seq;               /* order in which blocks were queued               */
    wq_seg   seg[WQ_MAX_SEG];
    uint32_t cookie[WQ_MAX_COOKIE];
} wq_block;

typedef struct {
    uint32_t block_bytes;       /* multiple of ru_bytes                            */
    uint32_t ru_bytes;
    uint32_t fill;              /* index of the FILLING block, or WQ_BLOCKS        */
    uint32_t last_closed;       /* index of the block queued most recently         */
    uint32_t next_seq, done_seq;/* queue order; done_seq = next block to complete  */
    uint32_t stream_lba;        /* sector where the next byte of the stream goes   */
    uint32_t stream_valid;
    uint32_t pending_tail;      /* bytes of the current frame already added        */
    uint32_t hold;              /* block closed at its edge that may hold the open  */
                                /* frame's last byte; WQ_BLOCKS if none            */
    /* counters for tests and the on-camera status block */
    uint32_t n_blocks, n_split, n_gap, n_cookies_done, n_full;
    wq_block blk[WQ_BLOCKS];
} wq_t;

typedef void (*wq_done_fn)(void *ctx, uint32_t cookie, uint32_t status);

int  wq_init(wq_t *q, uint32_t block_bytes, uint32_t ru_bytes);
/* Append `len` bytes at memory `addr` that belong at sector `lba` of the medium.
 * `len` must be a multiple of WQ_SECTOR (stock pads to the sector, C063F048).
 * WQ_FULL: only *taken bytes were queued (a whole number of sectors); wait for
 * the writer to free a block, then add the remainder at lba + *taken/512. */
int  wq_add(wq_t *q, uint32_t lba, uint32_t addr, uint32_t len, uint32_t *taken);
/* The current frame is complete: its cookie goes with its last byte. */
int  wq_frame_end(wq_t *q, uint32_t cookie);
/* Close the filling block even if short (stop, or before an unrelated write). */
int  wq_flush(wq_t *q);
/* Writer side: the oldest QUEUED block, now WRITING; 0 if none. */
wq_block *wq_take(wq_t *q);
/* Writer side: the block finished with `status`; every cookie is handed back. */
int  wq_complete(wq_t *q, wq_block *b, uint32_t status, wq_done_fn fn, void *ctx);
/* Nothing filling, queued or writing. */
int  wq_idle(const wq_t *q);

#endif
