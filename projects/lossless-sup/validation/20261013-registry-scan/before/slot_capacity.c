#include "slot_capacity.h"
static uint32_t divide(uint32_t n, uint32_t d) {
    uint32_t q = 0, r = 0;
    for (uint32_t bit = 32; bit; --bit) {
        uint32_t carry = r >> 31;
        r = (r << 1) | ((n >> (bit - 1)) & 1u);
        if (carry || r >= d) { r -= d; q |= 1u << (bit - 1); }
    }
    return q;
}
static uint32_t ceil_div(uint32_t n, uint32_t d) {
    return divide(n, d) + (n - divide(n, d) * d != 0);
}
uint32_t fpl_slot_plan(uint32_t w, uint32_t h, uint32_t bits, uint32_t lossless,
                       uint32_t fn, uint32_t fd, uint32_t latency,
                       struct fpl_slot_plan *out) {
    if (!out) return 0;
    *out = (struct fpl_slot_plan){0};
    if (!w || !h || w > 8192 || h > 8192 ||
        (bits != 10 && bits != 12 && bits != 14) || lossless > 1 ||
        !fn || !fd || !latency || latency > 1000000u) return 0;
    uint32_t fps = ceil_div(fn, fd);
    if (fps > 240u) return 0;
    uint32_t pixel_bits = w * h * (lossless ? 1u : bits);
    out->file_floor = FPL_SLOT_HEADER_BYTES + ceil_div(pixel_bits, 8u);
    out->batch_frames = ceil_div(FPL_SLOT_BATCH_BYTES, out->file_floor);
    out->arrival_slots = ceil_div(fps * latency, 1000000u);
    out->slots = (2u * out->batch_frames + out->arrival_slots + 6u + 3u) & ~3u;
    if (out->slots < FPL_SLOT_STOCK) out->slots = FPL_SLOT_STOCK;
    out->descriptor_bytes = 0x1130u + out->slots * 0x1128u;
    return out->slots <= FPL_SLOT_MAX;
}
