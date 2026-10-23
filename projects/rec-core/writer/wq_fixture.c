/* Host fixture for test_wq.py: a flat C API over wq so ctypes need not mirror
 * the struct layout.  Never built for the camera. */
#include <stdint.h>
#include <stdlib.h>
#include "wq.h"

typedef struct { uint32_t cookie, status; } done_rec;
static done_rec g_done[1 << 16];
static uint32_t g_ndone;

static void on_done(void *ctx, uint32_t cookie, uint32_t status) {
    (void)ctx;
    if (g_ndone < sizeof g_done / sizeof g_done[0]) {
        g_done[g_ndone].cookie = cookie;
        g_done[g_ndone].status = status;
    }
    g_ndone++;
}

wq_t *fx_new(uint32_t block_bytes, uint32_t ru) {
    wq_t *q = calloc(1, sizeof *q);
    g_ndone = 0;
    if (wq_init(q, block_bytes, ru)) { free(q); return 0; }
    return q;
}
void     fx_free(wq_t *q) { free(q); }
static uint32_t g_taken;
int      fx_add(wq_t *q, uint32_t lba, uint32_t addr, uint32_t len) { return wq_add(q, lba, addr, len, &g_taken); }
uint32_t fx_taken(void) { return g_taken; }
int      fx_end(wq_t *q, uint32_t cookie) { return wq_frame_end(q, cookie); }
int      fx_flush(wq_t *q) { return wq_flush(q); }
int      fx_idle(wq_t *q) { return wq_idle(q); }
int      fx_take(wq_t *q) { wq_block *b = wq_take(q); return b ? (int)(b - q->blk) : -1; }
int      fx_complete(wq_t *q, int i, uint32_t status) { return wq_complete(q, &q->blk[i], status, on_done, 0); }
uint32_t fx_info(wq_t *q, int i, int what) {
    wq_block *b = &q->blk[i];
    switch (what) {
    case 0: return b->state;   case 1: return b->lba;     case 2: return b->bytes;
    case 3: return b->nseg;    case 4: return b->ncookie; case 5: return b->close_reason;
    default: return b->seq;
    }
}
uint32_t fx_seg(wq_t *q, int i, int k, int what) { return what ? q->blk[i].seg[k].len : q->blk[i].seg[k].addr; }
uint32_t fx_cookie(wq_t *q, int i, int k) { return q->blk[i].cookie[k]; }
uint32_t fx_ndone(void) { return g_ndone; }
uint32_t fx_done(uint32_t k, int what) { return what ? g_done[k].status : g_done[k].cookie; }
uint32_t fx_counter(wq_t *q, int what) {
    switch (what) { case 0: return q->n_blocks; case 1: return q->n_split; case 2: return q->n_gap;
                    case 3: return q->n_cookies_done; default: return q->n_full; }
}
