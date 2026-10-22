/* Host harness for header_tag.c: the template or the frame lives in a
 * caller-owned byte buffer mapped at a fake word-aligned address. Every access
 * is checked to be word aligned and inside the buffer. */
#include <stdint.h>
#include <string.h>
#include "header_tag.h"

#define BASE 0x50000000u
static uint8_t *buffer;
static uint32_t size, unaligned, outside, reads, writes;
static uintptr_t last_write;
static uint32_t first_root_write;
static struct fpl_header_tag tag;

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
static void reset(uint8_t *buf, uint32_t buf_size) {
    buffer = buf; size = buf_size;
    unaligned = outside = reads = writes = first_root_write = 0;
    last_write = 0;
}
static void stats(uint32_t *out) {
    out[0] = unaligned; out[1] = outside; out[2] = reads; out[3] = writes;
    out[4] = last_write ? (uint32_t)(last_write - BASE) : 0xffffffffu;
    out[5] = first_root_write;
}

/* out: [0..5] stats, [6] ifd_at, [7] entries, [8] tables_at, [9] counts_at,
 * [10] max_tiles */
uint32_t fpl_fixture_prepare(uint8_t *buf, uint32_t buf_size, uint32_t head, uint32_t *out) {
    reset(buf, buf_size);
    memset(&tag, 0xA5, sizeof(tag));
    uint32_t r = fpl_header_tag_prepare(&tag, BASE, head, rd, wr);
    stats(out);
    out[6] = tag.ifd_at; out[7] = tag.entries; out[8] = tag.tables_at;
    out[9] = tag.counts_at; out[10] = tag.max_tiles;
    return r;
}
uint32_t fpl_fixture_complete(uint8_t *buf, uint32_t buf_size, uint32_t payload,
                              const uint32_t *tiles, uint32_t count, uint32_t tw,
                              uint32_t th, uint32_t capacity, uint32_t *out) {
    uint32_t bytes = 0;
    reset(buf, buf_size);
    uint32_t r = fpl_header_tag_complete(&tag, BASE, payload, tiles, count, tw, th,
                                         capacity, rd, wr, &bytes);
    stats(out);
    out[6] = bytes;
    return r;
}
