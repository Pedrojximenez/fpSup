#include "bulk_policy.h"

#define START_LATENCY_US 100000u
#define HANDOFF_SLOTS 4u
#define STOP_HEADROOM 2u

/* ARMv7 build has no compiler division runtime. Bounded 32-bit long division. */
static uint32_t divide(uint32_t n, uint32_t d) {
    uint32_t q = 0, r = 0;
    if (!d) return UINT32_MAX;
    for (uint32_t bit = 32; bit; --bit) {
        uint32_t carry = r >> 31;
        r = (r << 1) | ((n >> (bit - 1)) & 1u);
        if (carry || r >= d) { r -= d; q |= 1u << (bit - 1); }
    }
    return q;
}
static uint32_t ceil_div(uint32_t n, uint32_t d) {
    uint32_t q = divide(n, d);
    return q + (q != UINT32_MAX && n - q * d != 0);
}
static void increment(uint32_t *n) { if (*n != UINT32_MAX) ++*n; }

static void limits(struct fpl_bulk_policy *p) {
    uint32_t reserve, used;
    if (!p->fps_ceil || p->fps_ceil > 240u || p->start_free > FPL_BULK_POOL_SLOTS ||
        p->start_free <= STOP_HEADROOM) {
        p->arrival_reserve = FPL_BULK_POOL_SLOTS;
        p->free_watermark = FPL_BULK_POOL_SLOTS;
        p->frame_limit = 1;
        p->budget_exhausted = 1;
        return;
    }
    /* Clamp before multiplication; a one-second stall already exhausts the
     * frame budget at high rates. Do not overflow into a generous limit. */
    uint32_t us = p->latency_us > 1000000u ? 1000000u : p->latency_us;
    reserve = ceil_div(p->fps_ceil * us, 1000000u);
    if (p->latency_us > 1000000u) reserve = FPL_BULK_POOL_SLOTS;
    p->arrival_reserve = reserve;
    used = STOP_HEADROOM + HANDOFF_SLOTS + reserve;
    p->free_watermark = used < FPL_BULK_POOL_SLOTS ? used : FPL_BULK_POOL_SLOTS;
    p->budget_exhausted = p->start_free <= used + 1u;
    p->frame_limit = p->budget_exhausted ? 1u : (p->start_free - used) / 2u;
}

void fpl_bulk_reset(struct fpl_bulk_policy *p) {
    if (!p) return;
    uint32_t *w = (uint32_t *)p;
    for (uint32_t i = 0; i < sizeof(*p) / sizeof(*w); ++i) w[i] = 0;
}

void fpl_bulk_begin(struct fpl_bulk_policy *p, uint32_t num, uint32_t den,
                    uint32_t free_slots) {
    if (!p) return;
    fpl_bulk_reset(p);
    p->enabled = 1;
    p->fps_ceil = den ? ceil_div(num, den) : 0;
    p->start_free = free_slots;
    p->latency_us = START_LATENCY_US;
    limits(p);
}

uint32_t fpl_bulk_should_flush(struct fpl_bulk_policy *p, uint32_t pending,
                               uint32_t free_slots) {
    if (!p || !p->enabled) return pending == 128u;
    increment(&p->checks);
    if (free_slots > FPL_BULK_POOL_SLOTS) {
        increment(&p->unknown_pool);
        return 1;                       /* unknown pressure: send this file */
    }
    if (free_slots <= p->free_watermark) {
        increment(&p->pressure_flushes);
        return 1;
    }
    if (pending >= p->frame_limit - 1u) {
        increment(&p->count_flushes);
        return 1;
    }
    return 0;
}

void fpl_bulk_observe(struct fpl_bulk_policy *p, uint32_t low, uint32_t high,
                       uint32_t compressed, uint32_t elapsed_us) {
    if (!p || !p->enabled) return;
    if (elapsed_us > p->latency_us) {
        p->latency_us = elapsed_us;
        limits(p);
    }
    if (!low || high || low > FPL_BULK_BYTES * 4u) {
        increment(&p->failed_returns);
        return;
    }
    increment(&p->submitted);
    if (compressed) increment(&p->compressed); else increment(&p->raw);
    /* A short window includes the mandatory first RAW frame and every RAW
     * fallback. Overflow closes the preceding window before adding a file. */
    if (p->window_frames == FPL_BULK_WINDOW ||
        low > UINT32_MAX - p->window_bytes) {
        p->window_frames = p->window_compressed = p->window_bytes = 0;
    }
    ++p->window_frames;
    p->window_compressed += compressed != 0;
    p->window_bytes += low;
    p->sample_frames = p->window_frames;
    p->sample_compressed = p->window_compressed;
    p->sample_bytes = p->window_bytes;
    p->mean_bytes = divide(p->sample_bytes, p->sample_frames);
    p->predicted_frames = ceil_div(FPL_BULK_BYTES, p->mean_bytes);
}
