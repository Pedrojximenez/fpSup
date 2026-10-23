/* IMXL fork of rec-core/writer/wr.c (ULWR, sha256 2e83816d...): see ix_wr.h.
 * Changes: wr_init stamps the sink, wr_service writes through ix_sink. */
#include "ix_wr.h"

#ifdef WR_HOST                                   /* test_wr.py: a fake 32-bit space */
volatile uint32_t *wr_host_mem(uint32_t a);
#define RD(a)     (*wr_host_mem(a))
#define WRW(a, v) (*wr_host_mem(a) = (uint32_t)(v))
#define TOKEN(b)  ((uint32_t)((uintptr_t)(b) | 1u))   /* only ever tested for 0 */
#define WORDS(a)  ((const uint32_t *)wr_host_mem(a))
#define RD8(a)    ((RD((a) & ~3u) >> (((a) & 3u) * 8u)) & 0xFFu)
#else
#define RD8(a)    (*(volatile uint8_t *)(uintptr_t)(a))
#define RD(a)     (*(volatile uint32_t *)(uintptr_t)(a))
#define WRW(a, v) (*(volatile uint32_t *)(uintptr_t)(a) = (uint32_t)(v))
#define TOKEN(b)  ((uint32_t)(uintptr_t)(b))
#define WORDS(a)  ((const uint32_t *)(uintptr_t)(a))
#endif

static const uint32_t SLOT[6] = { V_CB, V_ACQ, V_ADD, V_CKPT, V_RB, V_REL };

static uint32_t lock(wr_t *w) { return w->fw.irq_off(); }
static void unlock(wr_t *w, uint32_t s) { w->fw.irq_restore(s); }

void wr_init(wr_t *w, const wr_fw *fw, int flag, const uint32_t veneer[6],
             uint32_t block_bytes, uint32_t maxdesc_at) {
    uint8_t *p = (uint8_t *)w;
    for (uint32_t i = 0; i < sizeof *w; i++) p[i] = 0;
    w->magic = WR_MAGIC;
    w->fw = *fw;
    w->flag = flag;
    for (int i = 0; i < 6; i++) w->veneer[i] = veneer[i];
    w->block_bytes = block_bytes;
    w->maxdesc_at = maxdesc_at;
    w->cur = BQ_BLOCKS;
    w->cap.magic = IX_CAP_MAGIC;
    w->cap.version = 1;
}

static uint32_t shift_of(uint32_t v) {           /* v is a power of two        */
    uint32_t s = 0;
    while (s < 31 && (1u << s) != v) s++;
    return (1u << s) == v ? s : 32;
}

/* stock C063F220 returned 1: the vol holds the driver arena, threshold set */
void wr_installed(wr_t *w, uint32_t vol) {
    if (w->vol || !vol || !RD(vol + V_THRESH) || !RD(vol + V_ARENA)) { w->n_refuse++; return; }
    uint32_t acq = RD(vol + V_ACQ);
    bq_limits lim = { 0x400u, 0, 0 };
    if (acq == WR_SD_ACQ) {
        lim.max_heads = 0x100u;
        lim.max_desc = w->maxdesc_at ? RD(w->maxdesc_at) : 0x10000u;
        if (!lim.max_desc) { w->n_refuse++; return; }
    } else if (acq != WR_SSD_ACQ) {
        w->n_refuse++;                           /* a driver we have not read  */
        return;
    }
    uint32_t ss = RD(vol + V_SECTOR), cluster = RD(vol + V_SPC) * ss;
    w->sector_shift = shift_of(ss);
    if (w->sector_shift < 9 || w->sector_shift > 12 || shift_of(cluster) > 25) {
        w->n_refuse++;                           /* exFAT: both powers of two  */
        return;
    }
    for (int i = 0; i < 6; i++) w->saved[i] = RD(vol + SLOT[i]);
#ifndef WR_HOST                                  /* the host fixture supplies them */
    w->fw.drv_acquire = (uint32_t (*)(void))(uintptr_t)w->saved[1];
    w->fw.drv_add = (int (*)(uint32_t, uint32_t))(uintptr_t)w->saved[2];
    w->fw.drv_release = (void (*)(void))(uintptr_t)w->saved[5];
    w->fw.stock_cb = (void (*)(uint32_t, uint32_t))(uintptr_t)w->saved[0];
#endif
    w->fw.drv_release();                         /* our writer acquires per chunk */
    uint32_t s = lock(w);
    bq_init(&w->q, &lim);
    bq_block *b = bq_open(&w->q);
    unlock(w, s);
    if (w->block_bytes) {                        /* stock rounds up to a cluster too */
        WRW(vol + V_THRESH, (w->block_bytes + cluster - 1) & ~(cluster - 1));
    }
    for (int i = 0; i < 6; i++) WRW(vol + SLOT[i], w->veneer[i]);
    WRW(vol + V_ARENA, TOKEN(b));
    w->vol = w->wvol = vol;
    w->n_install++;
}

static void restore(wr_t *w) {
    uint32_t vol = w->vol;
    for (int i = 0; i < 6; i++) WRW(vol + SLOT[i], w->saved[i]);
    WRW(vol + V_ARENA, 0);                       /* C063F310 then skips release */
    w->vol = 0;
    w->ended_vol = vol;
}

void wr_take_start(wr_t *w) { w->ended_vol = 0; }

/* The stop task can run C063F310 between C03A5348 marking a frame 0xC and that
 * frame's write: C069ADE0 opens, writes and closes under three separate holds
 * of the FS lock, so a stop queued on the lock while SRecFile blocked gets it
 * at the open's release.  The write then finds +0x4828 == 0 and C063F380
 * (F816) skips the cookie, while C03A5348 (mgr+0xD != 0) waits for one: the
 * frame never completes.  Such a frame was written synchronously, as with
 * aggregation off, so let stock take its own aggregation-off branch.  Any frame
 * that did reach the vol was completed (0xD) by the drain before the restore. */
int wr_late_frame(wr_t *w, uint32_t mgr, uint32_t node) {
#ifdef WR_MUTANT_NO_LATE
    return 0;
#endif
    uint32_t vol = w->ended_vol;
    if (!vol || !mgr || !node) return 0;
    if (!RD8(mgr + M_AGGREGATE) || RD(node + N_STATE) != N_HANDED || RD(vol + V_THRESH)) return 0;
    w->n_late_frame++;
    return 1;
}

static void wait_bits(wr_t *w, uint32_t bits) {
    uint32_t got;
    w->fw.flg_wait(w->flag, bits, TWF_ORW_BITCLR, &got, 1000);
}

/* C063F140(vol), called with the FS lock held */
int wr_send(wr_t *w, uint32_t vol, uint32_t lr) {
    if (!w->vol || vol != w->vol) { w->n_stock_send++; return 1; }
    if (!RD(vol + V_ARENA)) return 0;            /* stock: nothing to do        */
    uint32_t n = RD(vol + V_NCOOKIE);
    if (n > BQ_MAX_COOKIE) n = BQ_MAX_COOKIE;
    uint32_t s = lock(w);
    int r = bq_seal(&w->q, RD(vol + V_CL), RD(vol + V_BYTES),
                    WORDS(vol + V_COOKIES), n);
    unlock(w, s);
    if (r == BQ_MISMATCH) w->n_mismatch++;
    if (r == BQ_STATE) {                         /* no open block: cannot happen; */
        const uint32_t *ck = WORDS(vol + V_COOKIES);
        w->n_mismatch++;                         /* never strand a frame          */
        for (uint32_t i = 0; i < n; i++) w->fw.stock_cb(ck[i], (uint32_t)-4);
    }
    w->n_send++;
    WRW(vol + V_NCOOKIE, 0);
    WRW(vol + V_CL, 0);
    WRW(vol + V_BYTES, 0);
    w->fw.flg_set(w->flag, WR_F_WORK);
    if (lr == WR_LR_STOP) {                      /* C063F310: all written on return */
        uint32_t tries = 0;
#ifdef WR_MUTANT_NO_DRAIN
        tries = 1000;
#endif
        for (;;) {
            s = lock(w);
            int idle = bq_idle(&w->q);
            unlock(w, s);
            if (idle) break;
            if (++tries > 30) { if (tries < 1000) w->n_drain_timeout++; break; }
            wait_bits(w, WR_F_IDLE);
        }
        w->n_drain++;
        restore(w);
        return 0;
    }
    bq_block *b;
    for (;;) {
        s = lock(w);
        b = bq_open(&w->q);
        unlock(w, s);
        if (b) break;
        w->n_wait_free++;                        /* the writer needs no FS lock */
        wait_bits(w, WR_F_FREE);
    }
    WRW(vol + V_ARENA, TOKEN(b));
    return 0;
}

/* +0x4834 while installed: only C063F380's "4A58 == 0" path calls it */
void wr_cb_cookie(wr_t *w, uint32_t frame, uint32_t status) {
    w->n_late++;
    uint32_t st = 0;
    for (;;) {
        uint32_t s = lock(w);
        int r = bq_late_cookie(&w->q, frame, &st);
        unlock(w, s);
        if (r == BQ_OK) return;
        if (r == BQ_NONE) break;
        w->n_late_full++;                        /* wait until it drains        */
        wait_bits(w, WR_F_IDLE);
    }
    w->n_late_direct++;
    w->fw.stock_cb(frame, status ? status : st);
}

uint32_t wr_cb_acquire(wr_t *w) {
    for (;;) {
        uint32_t s = lock(w);
        bq_block *b = bq_open(&w->q);
        unlock(w, s);
        if (b) return TOKEN(b);    /* never 0: 0 degrades the take */
        w->n_wait_free++;
        wait_bits(w, WR_F_FREE);
    }
}

int wr_cb_add(wr_t *w, uint32_t addr, uint32_t len) {
    uint32_t s = lock(w);
    int r = bq_add(&w->q, addr, len);
    unlock(w, s);
    return r < 0 ? -1 : 0;
}

void wr_cb_ckpt(wr_t *w)     { uint32_t s = lock(w); bq_checkpoint(&w->q); unlock(w, s); }
void wr_cb_rollback(wr_t *w) { uint32_t s = lock(w); bq_rollback(&w->q); unlock(w, s); }
void wr_cb_release(wr_t *w)  { (void)w; }        /* blocks come back via the writer */

/* ---------------------------------------------------------------- writer */

static uint32_t write_block(wr_t *w, uint32_t vol, bq_block *b) {
    uint32_t from = 0, sent = 0, bytes;
    int n;
    uint32_t spc = RD(vol + V_SPC), heap = RD(vol + V_HEAP_LBA), dev = RD(vol + V_DEV);
    uint64_t base = (uint64_t)(b->cl - 2) * spc + heap;
    while ((n = bq_chunk(&w->q, b, &from, &bytes)) > 0) {
        uint32_t arena, tries = 0;
        while (!(arena = w->fw.drv_acquire())) { /* another user of the one table */
            w->n_acq_retry++;
            if (++tries > 2000) return (uint32_t)-5;
            w->fw.dly(1);
        }
        int ok = 1;
        for (uint32_t i = from - (uint32_t)n; i < from; i++)
            if (w->fw.drv_add(b->seg[i].addr, b->seg[i].len) < 0) { ok = 0; break; }
        int r = 0;
        if (ok) {
            uint64_t lba = base + (sent >> w->sector_shift);
            r = w->fw.dev_write(dev, (uint32_t)lba, (uint32_t)(lba >> 32), bytes >> w->sector_shift, arena);
        }
        w->fw.drv_release();
        w->n_chunk++;
        if (!ok) return (uint32_t)-4;
        if (r != 1) { w->n_dev_err++; return (uint32_t)(r < 0 ? r : -1); }
        sent += bytes;
    }
    if (n < 0) return (uint32_t)n;
    return 0;
}


/* ---------------------------------------------------------------- sink */

#ifdef WR_HOST
#error "the sink runs only on the card build (test_card.py)"
#endif

/* Frame bytes are read through the uncached alias: the SD driver hands the
 * same addresses to its DMA without touching the cache, so whoever produced
 * them has already cleaned them to memory. */
static uint32_t ix_src(uint32_t a) {
#ifdef IX_MUTANT_NO_UNCACHE
    return a;
#endif
    return a >= 0xC0000000u ? a - 0x80000000u : a;
}

static void ix_copy(uint32_t dst, uint32_t src, uint32_t n) {
    while (n && (dst & 3u)) { *(volatile uint8_t *)dst++ = *(const volatile uint8_t *)src++; n--; }
    if (!(src & 3u)) {
        uint32_t *d = (uint32_t *)dst;
        const uint32_t *s = (const uint32_t *)src;
        while (n >= 32u) {
            uint32_t a = s[0], b = s[1], c = s[2], e = s[3], f = s[4], g = s[5], h = s[6], i = s[7];
            d[0] = a; d[1] = b; d[2] = c; d[3] = e; d[4] = f; d[5] = g; d[6] = h; d[7] = i;
            d += 8; s += 8; n -= 32u;
        }
        while (n >= 4u) { *d++ = *s++; n -= 4u; }
        dst = (uint32_t)d;
        src = (uint32_t)s;
    }
    while (n--) *(volatile uint8_t *)dst++ = *(const volatile uint8_t *)src++;
}

/* Lent memory only: the uncached alias, below the firmware image. */
static uint32_t ix_room(const ix_cap *c) {
    if (c->nchunk > IX_MAX_CHUNK || c->ci > c->nchunk) return 0;
    uint32_t total = 0;
    for (uint32_t i = 0; i < c->nchunk; i++) {
        const ix_chunk *k = &c->chunk[i];
        if (k->addr < 0x40000000u || k->len > 0xC0000000u - k->addr) return 0;
        if (i > c->ci) total += k->len;
        else if (i == c->ci) { if (c->coff > k->len) return 0; total += k->len - c->coff; }
    }
    return total;
}

/* `n` bytes from `src` at the cursor (src == 0: leave them as they are). */
static void ix_put(ix_cap *c, uint32_t src, uint32_t n) {
    while (n) {
        const ix_chunk *k = &c->chunk[c->ci];
        uint32_t room = k->len - c->coff;
        if (!room) { c->ci++; c->coff = 0; continue; }
        uint32_t m = n < room ? n : room;
        if (src) { ix_copy(k->addr + c->coff, src, m); src += m; }
        c->coff += m;
        n -= m;
    }
}

static uint32_t ix_capture(wr_t *w, bq_block *b) {
    ix_cap *c = &w->cap;
    uint32_t data = (b->bytes + 3u) & ~3u;
#ifndef IX_MUTANT_NO_ROOM
    if (data < b->bytes || ix_room(c) < data + sizeof(ix_rec)) { c->n_full++; return 0; }
#endif
    uint32_t t0 = w->fw.tick_us();
    uint32_t hci = c->ci, hoff = c->coff;
    ix_put(c, 0, sizeof(ix_rec));               /* the header goes in last  */
    for (uint32_t i = 0; i < b->nseg; i++) ix_put(c, ix_src(b->seg[i].addr), b->seg[i].len);
    ix_put(c, 0, data - b->bytes);
    uint32_t dt = w->fw.tick_us() - t0;
    ix_rec r;
    r.magic = IX_REC_MAGIC; r.seq = b->seq; r.cl = b->cl; r.bytes = b->bytes;
    r.ncookie = b->ncookie; r.t_us = t0; r.copy_us = dt; r.nseg = b->nseg;
    uint32_t eci = c->ci, eoff = c->coff;
    c->ci = hci; c->coff = hoff;
    ix_put(c, (uint32_t)&r, sizeof r);
    c->ci = eci; c->coff = eoff;
    c->used += data + sizeof(ix_rec);
    if (!c->n_rec) c->t_first = t0;
    c->t_last = t0;
    c->n_rec++;
    c->copy_us += dt;
    if (dt > c->copy_max_us) c->copy_max_us = dt;
    return 0;
}

static uint32_t ix_sink(wr_t *w, uint32_t vol, bq_block *b) {
    uint32_t mode = w->cap.mode;
#ifdef IX_MUTANT_ALWAYS_SD
    mode = IX_SD;
#endif
    if (mode == IX_CAPTURE) return ix_capture(w, b);
    if (mode == IX_SD) { w->cap.n_sd++; return write_block(w, vol, b); }
    w->cap.n_discard++;                          /* IX_DISCARD and anything else */
    return 0;
}

void wr_service(wr_t *w) {
    for (;;) {
        uint32_t s = lock(w);
        bq_block *b = bq_take(&w->q);
        uint32_t vol = w->wvol;                  /* survives a drain timeout     */
        unlock(w, s);
        if (!b) break;
        uint32_t st = b->skip ? 0 : ix_sink(w, vol, b);
        w->last_status = st;
        s = lock(w);
        bq_complete_begin(&w->q, b, st);
        unlock(w, s);
        w->fw.flg_set(w->flag, WR_F_FREE);
        uint32_t c, cs;
        for (;;) {
            s = lock(w);
            int got = bq_complete_next(&w->q, &c, &cs);
            unlock(w, s);
            if (!got) break;
            w->fw.stock_cb(c, cs);                   /* C03A55D0, outside any lock */
        }
    }
    uint32_t s = lock(w);
    int idle = bq_idle(&w->q);
    unlock(w, s);
    if (idle) w->fw.flg_set(w->flag, WR_F_IDLE);
}

void wr_task(wr_t *w) {
    for (;;) {
        uint32_t got;
        w->fw.flg_wait(w->flag, WR_F_WORK, TWF_ORW_BITCLR, &got, -1);
        wr_service(w);
    }
}
