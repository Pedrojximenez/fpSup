#include "trailer.h"

/* Every callback access below is an ALIGNED word read/write. Only span
 * boundaries need read-modify-write. On 2026-09-29 an unaligned stm into this
 * very trailer was a Data Abort on the writer's thread, three times. Nothing
 * here can repeat that: the only accesses the callbacks see are word-aligned. */

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
#define LOSSLESS_JPEG 7u
#define TIFF_LE_MAGIC 0x002a4949u         /* "II*\0" */

/* Caller-owned scratch is CPU-written only. Source/destination addresses
 * still refer to the actual file; only bounded IFD spans are staged. */
struct fpl_trailer_io {
    fpl_trailer_read reader;
    fpl_trailer_write writer;
    uintptr_t source_first, destination_first;
    uint32_t source_words, destination_words;
    uint32_t *source_data, *destination_data;
};
static uint32_t io_read(const struct fpl_trailer_io *io, uintptr_t a) {
    if (io->source_data && a >= io->source_first &&
        a - io->source_first < 4u * io->source_words)
        return io->source_data[(a - io->source_first) >> 2];
    if (io->destination_data && a >= io->destination_first &&
        a - io->destination_first < 4u * io->destination_words)
        return io->destination_data[(a - io->destination_first) >> 2];
    return io->reader(a);
}
static void io_write(struct fpl_trailer_io *io, uintptr_t a, uint32_t v) {
    if (io->destination_data && a >= io->destination_first &&
        a - io->destination_first < 4u * io->destination_words)
        io->destination_data[(a - io->destination_first) >> 2] = v;
    else io->writer(a, v);
}

static uint32_t rd8(const struct fpl_trailer_io *io, uintptr_t a) {
    return (io_read(io, a & ~(uintptr_t)3) >> (8u * (uint32_t)(a & 3u))) & 0xffu;
}
static uint32_t rd16(const struct fpl_trailer_io *io, uintptr_t a) {
    uint32_t shift = 8u * (uint32_t)(a & 3u), word = io_read(io, a & ~(uintptr_t)3);
    if (shift <= 16u) return (word >> shift) & 0xffffu;
    return (word >> 24) | ((io_read(io, (a & ~(uintptr_t)3) + 4u) & 0xffu) << 8);
}
static uint32_t rd32(const struct fpl_trailer_io *io, uintptr_t a) {
    uintptr_t word = a & ~(uintptr_t)3;
    uint32_t shift = 8u * (uint32_t)(a & 3u), value = io_read(io, word);
    return shift ? (value >> shift) | (io_read(io, word + 4u) << (32u - shift)) : value;
}
static void wr8(struct fpl_trailer_io *io, uintptr_t a, uint32_t v) {
    uintptr_t word = a & ~(uintptr_t)3;
    uint32_t shift = 8u * (uint32_t)(a & 3u);
    io_write(io, word, (io_read(io, word) & ~(0xffu << shift)) | ((v & 0xffu) << shift));
}
static void wr16(struct fpl_trailer_io *io, uintptr_t a, uint32_t v) {
    uint32_t shift = 8u * (uint32_t)(a & 3u);
    if (shift <= 16u) {
        uintptr_t word = a & ~(uintptr_t)3;
        io_write(io, word, (io_read(io, word) & ~(0xffffu << shift)) | ((v & 0xffffu) << shift));
    } else {
        wr8(io, a, v); wr8(io, a + 1, v >> 8);
    }
}
static void wr32(struct fpl_trailer_io *io, uintptr_t a, uint32_t v) {
    uintptr_t word = a & ~(uintptr_t)3;
    uint32_t shift = 8u * (uint32_t)(a & 3u);
    if (!shift) { io_write(io, word, v); return; }
    /* Two ALIGNED word writes; preserve bytes before/after the value. */
    io_write(io, word, (io_read(io, word) & ((1u << shift) - 1u)) | (v << shift));
    io_write(io, word + 4u, (io_read(io, word + 4u) & (UINT32_MAX << shift)) | (v >> (32u - shift)));
}
static void copy_span(struct fpl_trailer_io *io,
                       uintptr_t to, uintptr_t from, uint32_t left) {
    while ((to & 3u) && left) {
        wr8(io, to++, rd8(io, from++)); --left;
    }
    while (left >= 4u) {
        io_write(io, to, rd32(io, from)); to += 4u; from += 4u; left -= 4u;
    }
    while (left--) wr8(io, to++, rd8(io, from++));
}
static uint32_t replaced_tag(uint32_t tag) {
    return tag == TAG_COMPRESSION || tag == TAG_STRIP_OFFSETS ||
           tag == TAG_ROWS_PER_STRIP || tag == TAG_STRIP_COUNTS;
}
static void put_table(struct fpl_trailer_io *io, uintptr_t at,
                       const uint32_t *lengths, uint32_t count, uint32_t offsets) {
    uint32_t position = FPL_TRAILER_PIXELS, shift = 8u * (uint32_t)(at & 3u);
    uintptr_t word = at & ~(uintptr_t)3;
    uint32_t previous = offsets ? position : lengths[0];
    position += lengths[0];
    if (!shift) {
        io_write(io, word, previous);
        for (uint32_t n = 1; n < count; ++n) {
            io_write(io, word + 4u * n, offsets ? position : lengths[n]);
            position += lengths[n];
        }
        return;
    }
    /* One boundary RMW at each end; all shared interior words written once. */
    io_write(io, word, (io_read(io, word) & ((1u << shift) - 1u)) | (previous << shift));
    for (uint32_t n = 1; n < count; ++n) {
        uint32_t next = offsets ? position : lengths[n];
        io_write(io, word + 4u * n, (previous >> (32u - shift)) | (next << shift));
        previous = next; position += lengths[n];
    }
    word += 4u * count;
    io_write(io, word, (io_read(io, word) & (UINT32_MAX << shift)) | (previous >> (32u - shift)));
}

static uint32_t trailer_plan_io(uintptr_t file, uint32_t payload, uint32_t tiles,
                          const struct fpl_trailer_io *io, struct fpl_trailer *out) {
    uint32_t root, count, previous = 0, seen = 0;
    if (!file || !io->reader || !out || !payload || !tiles || tiles > 160u ||
        payload > 0x7fffffffu)
        return FPL_INVALID;
    if (io_read(io, file) != TIFF_LE_MAGIC) return FPL_UNSUPPORTED;
    root = rd32(io, file + 4);
    if (root < 8 || (root & 1u) || root > FPL_TRAILER_PIXELS - 6) return FPL_UNSUPPORTED;
    count = rd16(io, file + root);
    if (count < 4 || count + 1u > FPL_TRAILER_MAX_ENTRIES ||
        root + 2u + 12u * count + 4u > FPL_TRAILER_PIXELS)
        return FPL_UNSUPPORTED;
    for (uint32_t n = 0; n < count; ++n) {
        uintptr_t e = file + root + 2u + 12u * n;
        uint32_t tag = rd16(io, e);
        if (n && tag <= previous) return FPL_UNSUPPORTED;       /* must be sorted */
        previous = tag;
        if (tag >= TAG_TILE_WIDTH && tag <= TAG_TILE_COUNTS) return FPL_UNSUPPORTED;
        if (tag == TAG_COMPRESSION) {
            if (rd16(io, e + 2) != TYPE_SHORT || rd32(io, e + 4) != 1 ||
                rd16(io, e + 8) != 1)
                return FPL_UNSUPPORTED;                         /* not uncompressed */
            seen |= 1u;
        }
        if (tag == TAG_STRIP_OFFSETS) seen |= 2u;
        if (tag == TAG_ROWS_PER_STRIP) seen |= 4u;
        if (tag == TAG_STRIP_COUNTS) seen |= 8u;
    }
    if (seen != 15u) return FPL_UNSUPPORTED;
    out->cache_used = 0;
    out->entries = count - 3u + 4u;
    out->ifd_at = FPL_TRAILER_PIXELS + payload;
    out->ifd_size = 2u + 12u * out->entries + 4u;
    out->offset_table = out->ifd_at + out->ifd_size;
    out->count_table = out->offset_table + 4u * tiles;
    out->file_bytes = out->count_table + 4u * tiles;
    return FPL_OK;
}

static uintptr_t put_entry(struct fpl_trailer_io *io, uintptr_t at,
                           uint32_t tag, uint32_t type, uint32_t count, uint32_t value) {
    wr16(io, at, tag);
    wr16(io, at + 2, type);
    wr32(io, at + 4, count);
    wr32(io, at + 8, value);
    return at + 12;
}

static uint32_t trailer_write_io(uintptr_t file, uint32_t payload,
                               const uint32_t *tile_bytes, uint32_t tiles,
                               uint32_t tile_width, uint32_t tile_height,
                               uint32_t capacity, struct fpl_trailer_io *io, struct fpl_trailer *out) {
    struct fpl_trailer plan;
    uint32_t result, root, count, sum = 0, added = 0;
    uintptr_t at;
    /* The four new tags are consecutive, 322..325: computed, not tabled, so
     * the code carries no read-only data section and no relocation. */

    if (!tile_bytes || !io->writer || !out) return FPL_INVALID;
    if ((result = trailer_plan_io(file, payload, tiles, io, &plan)) != FPL_OK)
        return result;
    for (uint32_t n = 0; n < tiles; ++n) {
        if (!tile_bytes[n] || tile_bytes[n] > payload - sum) return FPL_INVALID;
        sum += tile_bytes[n];
    }
    if (sum != payload) return FPL_INVALID;          /* tiles must reach the IFD */
    if (plan.file_bytes > capacity || plan.file_bytes < plan.ifd_at) return FPL_UNSUPPORTED;

    root = rd32(io, file + 4);
    count = rd16(io, file + root);
    at = file + plan.ifd_at;
    wr16(io, at, plan.entries);
    at += 2;
    for (uint32_t n = 0; n <= count; ++n) {
        uint32_t tag = n < count ? rd16(io, file + root + 2u + 12u * n) : 0x10000u;
        /* the four new tags, each where it sorts */
        while (added < 4 && TAG_TILE_WIDTH + added < tag) {
            uint32_t t = TAG_TILE_WIDTH + added++;
            uint32_t value = t == TAG_TILE_WIDTH ? tile_width :
                             t == TAG_TILE_LENGTH ? tile_height :
                             t == TAG_TILE_OFFSETS ? plan.offset_table : plan.count_table;
            at = put_entry(io, at, t, TYPE_LONG,
                           t >= TAG_TILE_OFFSETS ? tiles : 1u, value);
        }
        if (n == count) break;
        if (tag == TAG_STRIP_OFFSETS || tag == TAG_ROWS_PER_STRIP ||
            tag == TAG_STRIP_COUNTS)
            continue;
        if (tag == TAG_COMPRESSION) {
            at = put_entry(io, at, tag, TYPE_SHORT, 1, LOSSLESS_JPEG);
            continue;
        }
        uint32_t run = 1;
        while (n + run < count) {
            uint32_t next = rd16(io, file + root + 2u + 12u * (n + run));
            if (replaced_tag(next) || (added < 4u && TAG_TILE_WIDTH + added < next)) break;
            ++run;
        }
        copy_span(io, at, file + root + 2u + 12u * n, 12u * run);
        at += 12u * run;
        n += run - 1u;
    }
    wr32(io, at, 0);                            /* no next IFD */
    at += 4;
    if (at != file + plan.offset_table) return FPL_FAULT;  /* cannot be */

    put_table(io, file + plan.offset_table, tile_bytes, tiles, 1u);
    put_table(io, file + plan.count_table, tile_bytes, tiles, 0u);
    /* Emit the complete staged tail before publishing the root pointer.
     * Only the boundary bytes outside the exact tail are preserved. */
    if (io->destination_data) {
        for (uint32_t n = 0; n < io->destination_words; ++n)
            io->writer(io->destination_first + 4u * n, io->destination_data[n]);
        plan.cache_used = 1;
    }
    /* Last: the root pointer of the original header moves. Until now the
     * file still describes its original strips. */
    wr32(io, file + 4, plan.ifd_at);
    *out = plan;
    return FPL_OK;
}

static __attribute__((used)) uint32_t fpl_trailer_plan(uintptr_t file, uint32_t payload, uint32_t tiles,
                          fpl_trailer_read read, struct fpl_trailer *out) {
    struct fpl_trailer_io io = {0};
    io.reader = read;
    return trailer_plan_io(file, payload, tiles, &io, out);
}
static __attribute__((used)) uint32_t fpl_trailer_write_all(uintptr_t file, uint32_t payload,
                               const uint32_t *tile_bytes, uint32_t tiles,
                               uint32_t tile_width, uint32_t tile_height,
                               uint32_t capacity, fpl_trailer_read read,
                               fpl_trailer_write write, struct fpl_trailer *out) {
    struct fpl_trailer_io io = {0};
    io.reader = read; io.writer = write;
    return trailer_write_io(file, payload, tile_bytes, tiles, tile_width,
                             tile_height, capacity, &io, out);
}

static __attribute__((used)) uint32_t fpl_trailer_write_cached(uintptr_t file, uint32_t payload,
                                  const uint32_t *tile_bytes, uint32_t tiles,
                                  uint32_t tile_width, uint32_t tile_height,
                                  uint32_t capacity, fpl_trailer_read read,
                                  fpl_trailer_write write, uint32_t *scratch,
                                  uint32_t scratch_words, struct fpl_trailer *out) {
    struct fpl_trailer_io io = {0};
    io.reader = read; io.writer = write;
    /* Validate only the source-span bounds here. Full tag/tile validation is
     * done by the SAME core, using staged input, before any file write. */
    if (!file || (file & 3u) || !read || !write || !out || !tile_bytes ||
        !payload || payload > 0x7fffffffu || !tiles || tiles > 160u)
        return FPL_INVALID;
    if (read(file) != TIFF_LE_MAGIC) return FPL_UNSUPPORTED;
    uint32_t root = rd32(&io, file + 4);
    if (root < 8u || (root & 1u) || root > FPL_TRAILER_PIXELS - 6u)
        return FPL_UNSUPPORTED;
    uint32_t count = rd16(&io, file + root);
    if (count < 4u || count + 1u > FPL_TRAILER_MAX_ENTRIES ||
        root + 2u + 12u * count + 4u > FPL_TRAILER_PIXELS)
        return FPL_UNSUPPORTED;
    uint32_t tail = FPL_TRAILER_PIXELS + payload;
    uint32_t end = tail + 2u + 12u * (count + 1u) + 4u + 8u * tiles;
    if (end > capacity || end < tail) return FPL_UNSUPPORTED;
    uint32_t source_words = ((root & 3u) + 2u + 12u * count + 4u + 3u) >> 2;
    uint32_t destination_words = ((tail & 3u) + end - tail + 3u) >> 2;
    if (scratch && !((uintptr_t)scratch & 3u) &&
        source_words + destination_words <= scratch_words) {
        io.source_first = (file + root) & ~(uintptr_t)3u;
        io.destination_first = (file + tail) & ~(uintptr_t)3u;
        io.source_words = source_words; io.destination_words = destination_words;
        io.source_data = scratch; io.destination_data = scratch + source_words;
        for (uint32_t n = 0; n < source_words; ++n)
            scratch[n] = read(io.source_first + 4u * n);
        for (uint32_t n = 0; n < destination_words; ++n) io.destination_data[n] = 0;
        if (tail & 3u) io.destination_data[0] = read(io.destination_first);
        if (end & 3u)
            io.destination_data[destination_words - 1u] = read((file + end) & ~(uintptr_t)3u);
    }
    return trailer_write_io(file, payload, tile_bytes, tiles, tile_width,
                             tile_height, capacity, &io, out);
}
