/* Host fixture for test_bq.py.  Never built for the camera. */
#include <stdint.h>
#include <stdlib.h>
#include "bq.h"

static bq_limits L;
bq_t *fx_new(void) { bq_t *q = malloc(sizeof *q); bq_init(q, &L); return q; }
void  fx_free(bq_t *q) { free(q); }
int   fx_open(bq_t *q) { bq_block *b = bq_open(q); return b ? (int)(b - q->blk) : -1; }
int   fx_ck(bq_t *q) { return bq_checkpoint(q); }
int   fx_add(bq_t *q, uint32_t a, uint32_t n) { return bq_add(q, a, n); }
int   fx_rb(bq_t *q) { return bq_rollback(q); }
int   fx_seal(bq_t *q, uint32_t cl, uint32_t bytes, const uint32_t *c, uint32_t n) { return bq_seal(q, cl, bytes, c, n); }
int   fx_late(bq_t *q, uint32_t c) { uint32_t st; return bq_late_cookie(q, c, &st); }
int   fx_take(bq_t *q) { bq_block *b = bq_take(q); return b ? (int)(b - q->blk) : -1; }
void  fx_limits(uint32_t e, uint32_t h, uint32_t d) { L.max_entries = e; L.max_heads = h; L.max_desc = d; }
static uint32_t g_from, g_bytes;
int   fx_chunk(bq_t *q, int i) { return bq_chunk(q, &q->blk[i], &g_from, &g_bytes); }
void  fx_chunk_reset(void) { g_from = 0; }
uint32_t fx_from(void) { return g_from; }
uint32_t fx_cbytes(void) { return g_bytes; }
uint32_t fx_seg(bq_t *q, int i, uint32_t k, int w) { return w ? q->blk[i].seg[k].len : q->blk[i].seg[k].addr; }
uint32_t fx_blk(bq_t *q, int i, int w) {
    bq_block *b = &q->blk[i];
    switch (w) { case 0: return b->cl; case 1: return b->bytes; case 2: return b->skip;
                 case 3: return b->nseg; default: return b->seq; }
}
int   fx_cbegin(bq_t *q, int i, uint32_t st) { return bq_complete_begin(q, &q->blk[i], st); }
static uint32_t g_c, g_s;
int   fx_cnext(bq_t *q) { return bq_complete_next(q, &g_c, &g_s); }
uint32_t fx_ccookie(void) { return g_c; }
uint32_t fx_cstatus(void) { return g_s; }
int   fx_idle(bq_t *q) { return bq_idle(q); }
uint32_t fx_entries(uint32_t a, uint32_t n) { uint32_t h = 0; return bq_entries(a, n, &L, &h); }
