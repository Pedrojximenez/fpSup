#include "header_tag.h"

/* Byte and halfword accesses are built from ALIGNED word reads and
 * read-modify-write word writes: the frame buffer is uncached memory where an
 * unaligned access aborts (a Data Abort on the writer's thread, 2026-09-29). */

#define TAG_COMPRESSION 259u
#define TAG_STRIP_OFFSETS 273u
#define TAG_ROWS_PER_STRIP 278u
#define TAG_STRIP_COUNTS 279u
#define TAG_TILE_WIDTH 322u
#define TAG_TILE_LENGTH 323u
#define TAG_TILE_OFFSETS 324u
#define TAG_TILE_COUNTS 325u
#define TYPE_SHORT 3u
#define TYPE_LONG 4u
#define TYPE_UNDEFINED 7u
#define LOSSLESS_JPEG 7u
#define TIFF_LE_MAGIC 0x002a4949u         /* "II*\0" */

static uint32_t rd8(fpl_header_tag_read read, uintptr_t a) {
    return (read(a & ~(uintptr_t)3) >> (8u * (uint32_t)(a & 3u))) & 0xffu;
}
static uint32_t rd16(fpl_header_tag_read read, uintptr_t a) {
    return rd8(read, a) | (rd8(read, a + 1) << 8);
}
static uint32_t rd32(fpl_header_tag_read read, uintptr_t a) {
    if (!(a & 3u)) return read(a);
    return rd16(read, a) | (rd16(read, a + 2) << 16);
}
static void wr8(fpl_header_tag_read read, fpl_header_tag_write write, uintptr_t a, uint32_t v) {
    uintptr_t word = a & ~(uintptr_t)3;
    uint32_t shift = 8u * (uint32_t)(a & 3u);
    write(word, (read(word) & ~(0xffu << shift)) | ((v & 0xffu) << shift));
}
static void wr16(fpl_header_tag_read r, fpl_header_tag_write w, uintptr_t a, uint32_t v) {
    if (!(a & 1u)) {                                    /* one word RMW */
        uintptr_t word = a & ~(uintptr_t)3;
        uint32_t shift = 8u * (uint32_t)(a & 3u);
        w(word, (r(word) & ~(0xffffu << shift)) | ((v & 0xffffu) << shift));
        return;
    }
    wr8(r, w, a, v); wr8(r, w, a + 1, v >> 8);
}
static void wr32(fpl_header_tag_read r, fpl_header_tag_write w, uintptr_t a, uint32_t v) {
    if (!(a & 3u)) { w(a, v); return; }
    wr16(r, w, a, v); wr16(r, w, a + 2, v >> 16);
}
static uintptr_t put_entry(fpl_header_tag_read r, fpl_header_tag_write w, uintptr_t at,
                           uint32_t tag, uint32_t type, uint32_t count, uint32_t value) {
    wr16(r, w, at, tag);
    wr16(r, w, at + 2, type);
    wr32(r, w, at + 4, count);
    wr32(r, w, at + 8, value);
    return at + 12;
}

uint32_t fpl_header_tag_prepare(struct fpl_header_tag *t, uintptr_t base, uint32_t head,
                                fpl_header_tag_read read, fpl_header_tag_write write) {
    uint32_t root, count, previous = 0, seen = 0, value = 0, bytes = 0, added = 0;
    uint32_t ifd_at, entries, tables_at, max_tiles, end;
    uintptr_t at;

    if (!t || !base || (base & 3u) || !read || !write) return FPL_INVALID;
    if (head < 0x400u || head > FPL_HEADER_TAG_MAX_HEAD || (head & 3u)) return FPL_UNSUPPORTED;
    if (read(base) != TIFF_LE_MAGIC) return FPL_UNSUPPORTED;
    root = rd32(read, base + 4);
    if (root < 8 || (root & 1u) || root > head - 6) return FPL_UNSUPPORTED;
    count = rd16(read, base + root);
    if (count < 4 || root + 2u + 12u * count + 4u > head) return FPL_UNSUPPORTED;
    for (uint32_t n = 0; n < count; ++n) {
        uintptr_t e = base + root + 2u + 12u * n;
        uint32_t tag = rd16(read, e);
        if (n && tag <= previous) return FPL_UNSUPPORTED;          /* must be sorted */
        previous = tag;
        if (tag >= TAG_TILE_WIDTH && tag <= TAG_TILE_COUNTS) return FPL_UNSUPPORTED;
        if (tag == TAG_COMPRESSION) {
            if (rd16(read, e + 2) != TYPE_SHORT || rd32(read, e + 4) != 1 ||
                rd16(read, e + 8) != 1)
                return FPL_UNSUPPORTED;                            /* not uncompressed */
            seen |= 1u;
        }
        if (tag == TAG_STRIP_OFFSETS) seen |= 2u;
        if (tag == TAG_ROWS_PER_STRIP) seen |= 4u;
        if (tag == TAG_STRIP_COUNTS) seen |= 8u;
        if (tag == FPL_HEADER_TAG) {
            bytes = rd32(read, e + 4);
            if (rd16(read, e + 2) != TYPE_UNDEFINED || bytes < FPL_HEADER_TAG_MIN ||
                bytes > FPL_HEADER_TAG_MAX)
                return FPL_UNSUPPORTED;
            value = rd32(read, e + 8);
            seen |= 16u;
        }
    }
    if (seen != 31u) return FPL_UNSUPPORTED;
    if (value < 8u || value > head || head - value < bytes) return FPL_UNSUPPORTED;
    /* the tag's value must not hold the root IFD itself */
    if (root + 2u + 12u * count + 4u > value && root < value + bytes)
        return FPL_UNSUPPORTED;
    end = value + bytes;
    ifd_at = (value + 3u) & ~3u;
    entries = count - 3u + 4u;
    tables_at = (ifd_at + 2u + 12u * entries + 4u + 3u) & ~3u;
    if (tables_at >= end) return FPL_UNSUPPORTED;
    max_tiles = (end - tables_at) >> 3;
    if (max_tiles < 2u) return FPL_UNSUPPORTED;

    t->head = head;
    t->ifd_at = ifd_at;
    t->entries = entries;
    t->tables_at = tables_at;
    t->counts_at = tables_at + 4u * max_tiles;
    t->max_tiles = max_tiles;

    at = base + ifd_at;
    wr16(read, write, at, entries);
    at += 2;
    for (uint32_t n = 0; n <= count; ++n) {
        uintptr_t e = base + root + 2u + 12u * n;
        uint32_t tag = n < count ? rd16(read, e) : 0x10000u;
        while (added < 4 && TAG_TILE_WIDTH + added < tag) {
            uint32_t k = TAG_TILE_WIDTH + added++;
            uint32_t offset = (uint32_t)(at - base);
            if (k == TAG_TILE_WIDTH) t->width_at = offset;
            if (k == TAG_TILE_LENGTH) t->length_at = offset;
            if (k == TAG_TILE_OFFSETS) t->offsets_at = offset;
            if (k == TAG_TILE_COUNTS) t->bytes_at = offset;
            at = put_entry(read, write, at, k, TYPE_LONG, k >= TAG_TILE_OFFSETS ? 0u : 1u,
                           k == TAG_TILE_OFFSETS ? t->tables_at :
                           k == TAG_TILE_COUNTS ? t->counts_at : 0u);
        }
        if (n == count) break;
        if (tag == TAG_STRIP_OFFSETS || tag == TAG_ROWS_PER_STRIP || tag == TAG_STRIP_COUNTS)
            continue;
        if (tag == TAG_COMPRESSION) {
            at = put_entry(read, write, at, tag, TYPE_SHORT, 1, LOSSLESS_JPEG);
            continue;
        }
        at = put_entry(read, write, at, tag, rd16(read, e + 2), rd32(read, e + 4),
                       rd32(read, e + 8));                      /* as it is */
    }
    wr32(read, write, at, 0);                                    /* no next IFD */
    return FPL_OK;
}

uint32_t fpl_header_tag_complete(const struct fpl_header_tag *t, uintptr_t file,
                                 uint32_t payload, const uint32_t *tile_bytes,
                                 uint32_t tiles, uint32_t tile_width,
                                 uint32_t tile_height, uint32_t capacity,
                                 fpl_header_tag_read read, fpl_header_tag_write write,
                                 uint32_t *file_bytes) {
    uint32_t sum = 0, position;
    if (!t || !file || (file & 3u) || !tile_bytes || !read || !write || !file_bytes)
        return FPL_INVALID;
    if (!tiles || tiles > t->max_tiles || !payload) return FPL_UNSUPPORTED;
    for (uint32_t n = 0; n < tiles; ++n) {
        if (!tile_bytes[n] || tile_bytes[n] > payload - sum) return FPL_INVALID;
        sum += tile_bytes[n];
    }
    if (sum != payload) return FPL_INVALID;
    if (payload > capacity || t->head > capacity - payload) return FPL_UNSUPPORTED;
    /* the frame's header must be the template it was prepared in */
    if (read(file) != TIFF_LE_MAGIC || rd16(read, file + t->ifd_at) != t->entries ||
        rd16(read, file + t->offsets_at) != TAG_TILE_OFFSETS ||
        rd16(read, file + t->bytes_at) != TAG_TILE_COUNTS)
        return FPL_UNSUPPORTED;

    wr32(read, write, file + t->width_at + 8u, tile_width);
    wr32(read, write, file + t->length_at + 8u, tile_height);
    wr32(read, write, file + t->offsets_at + 4u, tiles);
    wr32(read, write, file + t->bytes_at + 4u, tiles);
    if (tiles == 1u) {                                  /* one value: in the entry */
        wr32(read, write, file + t->offsets_at + 8u, t->head);
        wr32(read, write, file + t->bytes_at + 8u, tile_bytes[0]);
    } else {
        wr32(read, write, file + t->offsets_at + 8u, t->tables_at);
        wr32(read, write, file + t->bytes_at + 8u, t->counts_at);
        position = t->head;
        for (uint32_t n = 0; n < tiles; ++n) {
            write(file + t->tables_at + 4u * n, position);
            write(file + t->counts_at + 4u * n, tile_bytes[n]);
            position += tile_bytes[n];
        }
    }
    /* Last: the root pointer. Until now the file still describes its strips. */
    write(file + 4, t->ifd_at);
    *file_bytes = t->head + payload;
    return FPL_OK;
}
