#include "memory_budget.h"
#define FPL_MEMORY_BATCH 0x04000000u
#define FPL_MEMORY_MIN_US 100000u
#define FPL_MEMORY_MAX_US 1000000u

static void memory_inc(uint32_t *v) { if (*v != UINT32_MAX) ++*v; }
/* No compiler division helpers in the freestanding ARM image. */
static uint32_t memory_div(uint32_t n, uint32_t d) {
    uint32_t q = 0, r = 0;
    for (uint32_t i = 32; i; --i) {
        uint32_t carry = r >> 31;
        r = (r << 1) | ((n >> (i - 1u)) & 1u);
        if (carry || r >= d) { r -= d; q |= 1u << (i - 1u); }
    }
    return q;
}
static uint32_t memory_ceil(uint32_t n, uint32_t d) {
    return memory_div(n - 1u, d) + 1u; /* callers prove n,d nonzero */
}
void fpl_memory_reset(struct fpl_memory_budget *p) {
    if (!p) return;
    for (uint32_t i = 0; i < sizeof(*p) / sizeof(uint32_t); ++i)
        ((uint32_t *)p)[i] = 0;
    p->last_free = p->min_free = UINT32_MAX;
}
static void memory_reserve(struct fpl_memory_budget *p, uint32_t us) {
    if (us < FPL_MEMORY_MIN_US) us = FPL_MEMORY_MIN_US;
    if (us <= p->latency_us) return;
    p->latency_us = us;
    if (us > FPL_MEMORY_MAX_US) { p->enabled = 0; return; }
    uint32_t arrivals = memory_ceil(p->fps_ceil * us, 1000000u);
    p->reserve_frames = 2u * p->raw_batch_frames + arrivals + 6u;
    if (p->reserve_frames > memory_div(UINT32_MAX, p->frame_charge)) {
        p->enabled = 0;
        return;
    }
    p->reserve_bytes = p->reserve_frames * p->frame_charge;
}
void fpl_memory_begin(struct fpl_memory_budget *p, uint32_t raster,
                      uint32_t fn, uint32_t fd, uint32_t us) {
    if (!p) return;
    fpl_memory_reset(p);
    /* The firmware's frame request: 0x15400 + align512(raster). Charge
     * the allocator's 64-byte header and spacing to the next 1-KiB payload.
     * File bytes instead start 0x2000 later, at the 0x13400 DNG prefix. */
    if (!raster || raster > 0x10000000u || !fn || !fd) return;
    uint32_t packed = (raster + 511u) & ~511u;
    p->frame_charge = (0x15400u + packed + 64u + 1023u) & ~1023u;
    p->raw_file_bytes = 0x13400u + packed;
    p->raw_batch_frames = memory_ceil(FPL_MEMORY_BATCH, p->raw_file_bytes);
    p->fps_ceil = memory_ceil(fn, fd);
    if (p->fps_ceil > 240u) return;
    p->enabled = 1;
    memory_reserve(p, us);
}
uint32_t fpl_memory_allow(struct fpl_memory_budget *p, uint32_t free_bytes,
                          uint32_t us) {
    if (!p) return 0;
    memory_inc(&p->checks);
    p->last_free = free_bytes;
    if (free_bytes < p->min_free) p->min_free = free_bytes;
    if (p->enabled) memory_reserve(p, us);
    if (!p->enabled || free_bytes == UINT32_MAX) {
        memory_inc(&p->unknown_raw);
        return 0;
    }
    /* Equality also goes RAW: no next compressed arrival is budgeted. */
    if (free_bytes <= p->reserve_bytes) {
        memory_inc(&p->pressure_raw);
        return 0;
    }
    memory_inc(&p->admitted);
    return 1;
}
