/* wq -- the writer's block queue.  See wq.h. */
#include "wq.h"

/* A block closed exactly at its edge while a frame is still open may turn out to
 * hold that frame's last byte; the writer must not finish it before the cookie
 * arrives.  `hold` marks it; the next byte of the frame (which lands elsewhere)
 * or the frame's end clears it. */
#define HOLD_NONE WQ_BLOCKS
#define hold_idx (q->hold)              /* only the most recently closed block can be held */

static void zero(void *p, uint32_t n) {
    uint8_t *b = (uint8_t *)p;
    while (n--) *b++ = 0;
}

int wq_init(wq_t *q, uint32_t block_bytes, uint32_t ru_bytes) {
    /* RU is a power of two (512 KB in every SD class): no divide on Cortex-A9 */
    if (!q || !ru_bytes || (ru_bytes & (ru_bytes - 1)) || ru_bytes < WQ_SECTOR ||
        !block_bytes || (block_bytes & (ru_bytes - 1)))
        return WQ_BADARG;
    zero(q, sizeof *q);
    q->block_bytes = block_bytes;
    q->ru_bytes = ru_bytes;
    q->fill = WQ_BLOCKS;
    q->last_closed = WQ_BLOCKS;
    q->hold = HOLD_NONE;
    return WQ_OK;
}

static int open_block(wq_t *q, uint32_t lba) {
    for (uint32_t i = 0; i < WQ_BLOCKS; i++) {
        wq_block *b = &q->blk[i];
        if (b->state == WQ_FREE) {
            b->state = WQ_FILLING;
            b->close_reason = b->status = 0;
            b->lba = lba;
            b->bytes = b->nseg = b->ncookie = 0;
            q->fill = i;
            return WQ_OK;
        }
    }
    q->n_full++;
    return WQ_FULL;
}

static void close_block(wq_t *q, uint32_t reason) {
    wq_block *b = &q->blk[q->fill];
    b->state = WQ_QUEUED;
    b->close_reason = reason;
    b->seq = q->next_seq++;
    q->last_closed = q->fill;
    q->fill = WQ_BLOCKS;
    q->n_blocks++;
}

int wq_add(wq_t *q, uint32_t lba, uint32_t addr, uint32_t len, uint32_t *taken) {
    uint32_t got = 0;
    if (taken) *taken = 0;
    if (!q || !len || len % WQ_SECTOR)
        return WQ_BADARG;
    if (q->stream_valid && lba != q->stream_lba && q->fill != WQ_BLOCKS) {
        close_block(q, WQ_CLOSE_GAP);           /* not contiguous: write what we have */
        q->n_gap++;
    }
    /* bytes of this frame now land after the held block: it is not the last */
#ifndef WQ_MUTANT_NOHOLD
    if (hold_idx != HOLD_NONE)
        hold_idx = HOLD_NONE;
#endif
    while (len) {
        if (q->fill == WQ_BLOCKS) {
            int r = open_block(q, lba);
            if (r) {                            /* partial: `got` bytes are queued;  */
                if (taken) *taken = got;        /* the caller retries the remainder  */
                return r;                       /* after the writer frees a block    */
            }
        }
        wq_block *b = &q->blk[q->fill];
        if (b->nseg == WQ_MAX_SEG) {
            close_block(q, WQ_CLOSE_LIMIT);
            continue;
        }
        uint32_t room = q->block_bytes - b->bytes;
        uint32_t take = len < room ? len : room;
        b->seg[b->nseg].addr = addr;
        b->seg[b->nseg].len = take;
        b->nseg++;
        b->bytes += take;
        q->pending_tail += take;
        got += take;
        addr += take;
        len -= take;
        lba += take / WQ_SECTOR;
        q->stream_lba = lba;
        q->stream_valid = 1;
        if (b->bytes == q->block_bytes) {
            close_block(q, WQ_CLOSE_FULL);
            if (len) q->n_split++;
#ifndef WQ_MUTANT_NOHOLD
            else hold_idx = q->last_closed;     /* may hold the frame's last byte */
#endif
        }
    }
    if (taken) *taken = got;
    return WQ_OK;
}

int wq_frame_end(wq_t *q, uint32_t cookie) {
    if (!q) return WQ_BADARG;
    wq_block *b;
    if (hold_idx != HOLD_NONE)
        b = &q->blk[hold_idx];                  /* last byte closed its block */
    else if (q->fill != WQ_BLOCKS)
        b = &q->blk[q->fill];
    else if (q->last_closed != WQ_BLOCKS && q->blk[q->last_closed].state != WQ_FREE)
        b = &q->blk[q->last_closed];            /* closed by a gap/limit after it */
    else
        return WQ_BADARG;                       /* a frame end with no bytes */
    if (b->ncookie == WQ_MAX_COOKIE) {
        if (b == &q->blk[q->fill]) {            /* stock also flushes at 128 cookies */
            close_block(q, WQ_CLOSE_LIMIT);
        }
        return WQ_COOKIES;
    }
    b->cookie[b->ncookie++] = cookie;
    hold_idx = HOLD_NONE;
    q->pending_tail = 0;
    if (b->state == WQ_FILLING && b->ncookie == WQ_MAX_COOKIE)
        close_block(q, WQ_CLOSE_LIMIT);
    return WQ_OK;
}

int wq_flush(wq_t *q) {
    if (!q) return WQ_BADARG;
    if (q->fill != WQ_BLOCKS && q->blk[q->fill].bytes)
        close_block(q, WQ_CLOSE_FLUSH);
    hold_idx = HOLD_NONE;
    return WQ_OK;
}

wq_block *wq_take(wq_t *q) {
    wq_block *best = 0;
    for (uint32_t i = 0; i < WQ_BLOCKS; i++) {
        wq_block *b = &q->blk[i];
        if (b->state != WQ_QUEUED || i == hold_idx) continue;
        if (!best || (int32_t)(b->seq - best->seq) < 0) best = b;
    }
    /* strict order: never overtake an older block (held or not) */
    for (uint32_t i = 0; best && i < WQ_BLOCKS; i++) {
        wq_block *b = &q->blk[i];
        if (b->state == WQ_QUEUED && (int32_t)(b->seq - best->seq) < 0) return 0;
    }
    if (best) best->state = WQ_WRITING;
    return best;
}

int wq_complete(wq_t *q, wq_block *b, uint32_t status, wq_done_fn fn, void *ctx) {
    if (!q || !b || b->state != WQ_WRITING || b->seq != q->done_seq)
        return WQ_BADARG;
    b->status = status;
    for (uint32_t i = 0; i < b->ncookie; i++) {
        if (fn) fn(ctx, b->cookie[i], status);
        q->n_cookies_done++;
    }
    b->state = WQ_FREE;
    b->nseg = b->ncookie = b->bytes = 0;
    q->done_seq++;
    if ((uint32_t)(b - q->blk) == q->last_closed) q->last_closed = WQ_BLOCKS;
    return WQ_OK;
}

int wq_idle(const wq_t *q) {
    for (uint32_t i = 0; i < WQ_BLOCKS; i++)
        if (q->blk[i].state != WQ_FREE) return 0;
    return 1;
}
