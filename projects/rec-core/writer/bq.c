/* bq -- see bq.h. */
#include "bq.h"

static void zero(void *p, uint32_t n) {
    uint8_t *b = (uint8_t *)p;
    while (n--) *b++ = 0;
}

void bq_init(bq_t *q, const bq_limits *lim) {
    zero(q, sizeof *q);
    q->lim = *lim;
    q->fill = BQ_BLOCKS;
}

bq_block *bq_open(bq_t *q) {
    if (q->fill != BQ_BLOCKS)
        return &q->blk[q->fill];                /* stock re-acquires without a send */
    for (uint32_t i = 0; i < BQ_BLOCKS; i++) {
        bq_block *b = &q->blk[i];
        if (b->state == BQ_FREE) {
            b->state = BQ_FILLING;
            b->cl = b->bytes = b->skip = b->status = 0;
            b->nseg = b->ncut = b->ncookie = 0;
            b->ck_seg = b->ck_bytes = b->ck_cut = 0;
            q->fill = i;
            return b;
        }
    }
    q->n_full++;
    return 0;
}

int bq_checkpoint(bq_t *q) {
    if (q->fill == BQ_BLOCKS) return BQ_STATE;
    bq_block *b = &q->blk[q->fill];
    b->ck_seg = b->nseg;
    b->ck_bytes = b->bytes;
    b->ck_cut = b->ncut;
    b->x_ent = b->x_heads = 0;
    if (b->ncut && b->cut[b->ncut - 1] == b->nseg)
        return BQ_OK;                           /* previous extent added nothing      */
    if (b->ncut == BQ_MAX_CUT) return BQ_FULL;  /* add() will fail; stock rolls back  */
    b->cut[b->ncut++] = b->nseg;
    return BQ_OK;
}

int bq_add(bq_t *q, uint32_t addr, uint32_t len) {
    if (q->fill == BQ_BLOCKS) return BQ_STATE;
    bq_block *b = &q->blk[q->fill];
    if (!len) return BQ_OK;                     /* the SD driver also accepts 0       */
    if (b->nseg == BQ_MAX_SEG || !b->ncut || b->cut[b->ncut - 1] > b->nseg)
        return BQ_FULL;
    if (b->ncut == BQ_MAX_CUT && b->cut[b->ncut - 1] != b->ck_seg)
        return BQ_FULL;                         /* checkpoint could not record it     */
    uint32_t h = b->x_heads, e = b->x_ent + bq_entries(addr, len, &q->lim, &h);
    if (e > q->lim.max_entries || (q->lim.max_heads && h > q->lim.max_heads))
        return BQ_FULL;                         /* stock: arena exhausted -> direct   */
    b->x_ent = e;
    b->x_heads = h;
    b->seg[b->nseg].addr = addr;
    b->seg[b->nseg].len = len;
    b->nseg++;
    b->bytes += len;
    return BQ_OK;
}

int bq_rollback(bq_t *q) {
    if (q->fill == BQ_BLOCKS) return BQ_STATE;
    bq_block *b = &q->blk[q->fill];
    b->nseg = b->ck_seg;
    b->bytes = b->ck_bytes;
    b->ncut = b->ck_cut;
    return BQ_OK;
}

int bq_seal(bq_t *q, uint32_t cl, uint32_t bytes, const uint32_t *cookies, uint32_t n) {
    if (q->fill == BQ_BLOCKS) return BQ_STATE;
    bq_block *b = &q->blk[q->fill];
    if (n > BQ_MAX_COOKIE) return BQ_BADARG;
    for (uint32_t i = 0; i < n; i++) b->cookie[i] = cookies[i];
    b->ncookie = n;
    b->cl = cl;
    int r = BQ_OK;
    if (!cl || !bytes) {                        /* stock: no write, cookies status 0 */
        b->skip = 1;
        q->n_skip++;
    } else if (bytes != b->bytes || bytes % BQ_SECTOR) {
        b->skip = 1;                            /* never write what we cannot account */
        b->status = (uint32_t)BQ_MISMATCH;
        q->n_mismatch++;
        r = BQ_MISMATCH;
    }
    b->state = BQ_QUEUED;
    b->seq = q->next_seq++;
    q->fill = BQ_BLOCKS;
    q->n_sealed++;
    return r;
}

/* the most recently sealed block that has not completed */
static bq_block *last_inflight(bq_t *q) {
    bq_block *best = 0;
    for (uint32_t i = 0; i < BQ_BLOCKS; i++) {
        bq_block *b = &q->blk[i];
        if (b->state != BQ_QUEUED && b->state != BQ_WRITING) continue;
        if (!best || (int32_t)(b->seq - best->seq) > 0) best = b;
    }
    return best;
}

int bq_late_cookie(bq_t *q, uint32_t cookie, uint32_t *status) {
    bq_block *b = last_inflight(q);
    q->n_late++;
#ifdef BQ_MUTANT_LATE_DIRECT
    b = 0;
    if (0) {
#else
    if (b) {
#endif
        if (b->ncookie == BQ_MAX_COOKIE) return BQ_FULL;
        b->cookie[b->ncookie++] = cookie;
        return BQ_OK;
    }
#ifndef BQ_MUTANT_NO_TAIL
    if (q->completing) {                        /* behind the cookies being handed back */
        if (q->cn == sizeof q->clist / sizeof q->clist[0]) return BQ_FULL;
        q->clist[q->cn++] = cookie;
        return BQ_OK;
    }
#endif
    q->n_late_direct++;
    *status = q->last_status;
    if (q->carry == q->last_status) q->carry = 0;  /* it was the frame owed the failure */
    return BQ_NONE;
}

bq_block *bq_take(bq_t *q) {
    if (q->completing) return 0;               /* one block at a time, in order       */
    for (uint32_t i = 0; i < BQ_BLOCKS; i++) {
        bq_block *b = &q->blk[i];
        if (b->state == BQ_QUEUED && b->seq == q->done_seq) {
            b->state = BQ_WRITING;
            return b;
        }
    }
    return 0;
}

uint32_t bq_entries(uint32_t addr, uint32_t len, const bq_limits *lim, uint32_t *heads) {
    if (!lim->max_desc) return len ? 1 : 0;    /* SSD: one {addr,len} per add        */
    uint32_t n = 0, h = (0u - addr) & 3;       /* SD C065F060                         */
    if (h > len) h = len;
    if (h) { n++; (*heads)++; }
    uint32_t rest = len - h;
    while (rest) {                             /* no divide on the camera             */
        uint32_t t = rest < lim->max_desc ? rest : lim->max_desc;
        rest -= t;
        n++;
    }
    return n;
}

int bq_chunk(const bq_t *q, const bq_block *b, uint32_t *from, uint32_t *bytes) {
    const bq_limits *lim = &q->lim;
    uint32_t s = *from, ent = 0, heads = 0, sum = 0, end = s;
    *bytes = 0;
    if (s >= b->nseg) return 0;
    uint32_t k = 0;                            /* next extent start after s          */
    while (k < b->ncut && b->cut[k] <= s) k++;
    while (end < b->nseg) {
        uint32_t stop = k < b->ncut ? b->cut[k] : b->nseg;
        k++;
        uint32_t e = 0, h = 0, by = 0;
        for (uint32_t i = end; i < stop; i++) {
            e += bq_entries(b->seg[i].addr, b->seg[i].len, lim, &h);
            by += b->seg[i].len;
        }
#ifdef BQ_MUTANT_NOCUT
        if (stop > end + 1) stop = end + 1, by = b->seg[end].len,
            e = bq_entries(b->seg[end].addr, b->seg[end].len, lim, &h), k--;
#endif
        if (ent + e > lim->max_entries || (lim->max_heads && heads + h > lim->max_heads)) {
            if (end == s) return BQ_TOOBIG;
            break;
        }
        ent += e;
        heads += h;
        sum += by;
        end = stop;
    }
    *from = end;
    *bytes = sum;
    return (int)(end - s);
}

int bq_complete_begin(bq_t *q, bq_block *b, uint32_t status) {
    if (b->state != BQ_WRITING || b->seq != q->done_seq || q->completing)
        return BQ_STATE;
    if (b->status) status = b->status;         /* a mismatch outranks the write      */
    if (b->skip && !b->status) status = 0;     /* stock: nothing written, status 0   */
    for (uint32_t i = 0; i < b->ncookie; i++) q->clist[i] = b->cookie[i];
    q->cn = b->ncookie;
    q->cpos = 0;
    q->cstatus = status;
    q->cfirst = status;
    q->last_status = status;
#ifndef BQ_MUTANT_NO_CARRY
    if (!status && q->carry && q->cn) {        /* the frame that may span from it    */
        q->cfirst = q->carry;
        q->carry = 0;
    }
    if (status) q->carry = status;
#endif
    q->completing = 1;
    b->state = BQ_FREE;                         /* the submitter may refill it now   */
    b->nseg = b->ncut = b->ncookie = b->bytes = 0;
    q->done_seq++;
    return BQ_OK;
}

int bq_complete_next(bq_t *q, uint32_t *cookie, uint32_t *status) {
    if (!q->completing) return 0;
    if (q->cpos == q->cn) {
        q->completing = 0;
        q->cn = q->cpos = 0;
        return 0;
    }
    *status = q->cpos ? q->cstatus : q->cfirst;
    *cookie = q->clist[q->cpos++];
    return 1;
}

int bq_idle(const bq_t *q) {
    if (q->completing) return 0;
    for (uint32_t i = 0; i < BQ_BLOCKS; i++)
        if (q->blk[i].state == BQ_QUEUED || q->blk[i].state == BQ_WRITING) return 0;
    return 1;
}
