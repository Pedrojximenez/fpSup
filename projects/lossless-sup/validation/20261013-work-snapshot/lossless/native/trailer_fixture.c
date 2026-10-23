/* Host harness for trailer.c: the file lives in a caller-owned byte buffer,
 * mapped at a fake word-aligned address. Every access trailer.c makes is
 * checked to be word aligned and inside the buffer -- the property that
 * keeps the 2026-09-29 Data Abort from coming back. */
#include <stdint.h>
#include <string.h>
#include "trailer.h"

#define BASE 0x50000000u
static uint8_t *buffer;
static uint32_t size, unaligned, outside, reads, writes;
static uintptr_t last_write;
static uint32_t first_root_write;

static uint32_t rd(uintptr_t a) {
    reads++;
    if (a & 3u) unaligned++;
    if (a < BASE || a + 4 > BASE + size) { outside++; return 0; }
    uint32_t v;
    memcpy(&v, buffer + (a - BASE), 4);
    return v;
}
static void wr(uintptr_t a, uint32_t v) {
    writes++;
    last_write = a;
    if (a == BASE + 4 && !first_root_write) first_root_write = writes;
    if (a & 3u) unaligned++;
    if (a < BASE || a + 4 > BASE + size) { outside++; return; }
    memcpy(buffer + (a - BASE), &v, 4);
}

uint32_t fpl_fixture_build(uint8_t *buf, uint32_t buf_size, uint32_t payload,
                           const uint32_t *tiles, uint32_t count, uint32_t tw,
                           uint32_t th, uint32_t capacity, uint32_t *result) {
    struct fpl_trailer t;
    buffer = buf; size = buf_size;
    unaligned = outside = reads = writes = first_root_write = 0;
    uint32_t r = fpl_trailer_write_all(BASE, payload, tiles, count, tw, th,
                                       capacity, rd, wr, &t);
    result[0] = r;
    result[1] = r == FPL_OK ? t.file_bytes : 0;
    result[2] = r == FPL_OK ? t.ifd_at : 0;
    result[3] = r == FPL_OK ? t.entries : 0;
    result[4] = unaligned;
    result[5] = outside;
    result[6] = writes;
    result[7] = (uint32_t)(last_write - BASE);
    result[8] = first_root_write;
    result[9] = reads;
    result[10] = 0;
    result[11] = r == FPL_OK ? t.cache_used : 0;
    return r;
}
uint32_t fpl_fixture_cached(uint8_t *buf, uint32_t buf_size, uint32_t payload,
                            const uint32_t *tiles, uint32_t count, uint32_t tw,
                            uint32_t th, uint32_t capacity, uint32_t *result,
                            uint32_t scratch_words) {
    uint32_t scratch[1026];
    struct fpl_trailer t;
    for (uint32_t n = 0; n < 1026; ++n) scratch[n] = 0xa5a5a5a5u;
    if (scratch_words > 1024) return FPL_INVALID;
    buffer = buf; size = buf_size;
    unaligned = outside = reads = writes = first_root_write = 0;
    uint32_t r = fpl_trailer_write_cached(BASE, payload, tiles, count, tw, th,
                                         capacity, rd, wr, scratch + 1, scratch_words, &t);
    result[0] = r;
    result[1] = r == FPL_OK ? t.file_bytes : 0;
    result[2] = r == FPL_OK ? t.ifd_at : 0;
    result[3] = r == FPL_OK ? t.entries : 0;
    result[4] = unaligned;
    result[5] = outside;
    result[6] = writes;
    result[7] = (uint32_t)(last_write - BASE);
    result[8] = first_root_write;
    result[9] = reads;
    result[10] = scratch[0] != 0xa5a5a5a5u;
    for (uint32_t n = scratch_words + 1u; n < 1026u; ++n)
        if (scratch[n] != 0xa5a5a5a5u) result[10]++;
    result[11] = r == FPL_OK ? t.cache_used : 0;
    return r;
}
uint32_t fpl_fixture_plan(uint8_t *buf, uint32_t buf_size, uint32_t payload, uint32_t count) {
    struct fpl_trailer t;
    buffer = buf; size = buf_size;
    return fpl_trailer_plan(BASE, payload, count, rd, &t);
}
