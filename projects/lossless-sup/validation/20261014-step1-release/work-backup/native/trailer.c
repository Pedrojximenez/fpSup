#include "trailer.h"

/* Every access below is a byte built from ALIGNED word reads and
 * read-modify-write word writes. On 2026-09-29 an unaligned stm into this
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

static uint32_t rd8(fpl_trailer_read read, uintptr_t a) {
    return (read(a & ~(uintptr_t)3) >> (8u * (uint32_t)(a & 3u))) & 0xffu;
}
static uint32_t rd16(fpl_trailer_read read, uintptr_t a) {
    return rd8(read, a) | (rd8(read, a + 1) << 8);
}
static uint32_t rd32(fpl_trailer_read read, uintptr_t a) {
    return rd16(read, a) | (rd16(read, a + 2) << 16);
}
static void wr8(fpl_trailer_read read, fpl_trailer_write write, uintptr_t a, uint32_t v) {
    uintptr_t word = a & ~(uintptr_t)3;
    uint32_t shift = 8u * (uint32_t)(a & 3u);
    write(word, (read(word) & ~(0xffu << shift)) | ((v & 0xffu) << shift));
}
static void wr16(fpl_trailer_read r, fpl_trailer_write w, uintptr_t a, uint32_t v) {
    wr8(r, w, a, v); wr8(r, w, a + 1, v >> 8);
}
static void wr32(fpl_trailer_read r, fpl_trailer_write w, uintptr_t a, uint32_t v) {
    wr16(r, w, a, v); wr16(r, w, a + 2, v >> 16);
}

uint32_t fpl_trailer_plan(uintptr_t file, uint32_t payload, uint32_t tiles,
                          fpl_trailer_read read, struct fpl_trailer *out) {
    uint32_t root, count, previous = 0, seen = 0;
    if (!file || !read || !out || !payload || !tiles || tiles > 160u ||
        payload > 0x7fffffffu)
        return FPL_INVALID;
    if (read(file) != TIFF_LE_MAGIC) return FPL_UNSUPPORTED;
    root = rd32(read, file + 4);
    if (root < 8 || (root & 1u) || root > FPL_TRAILER_PIXELS - 6) return FPL_UNSUPPORTED;
    count = rd16(read, file + root);
    if (count < 4 || count + 1u > FPL_TRAILER_MAX_ENTRIES ||
        root + 2u + 12u * count + 4u > FPL_TRAILER_PIXELS)
        return FPL_UNSUPPORTED;
    for (uint32_t n = 0; n < count; ++n) {
        uintptr_t e = file + root + 2u + 12u * n;
        uint32_t tag = rd16(read, e);
        if (n && tag <= previous) return FPL_UNSUPPORTED;       /* must be sorted */
        previous = tag;
        if (tag >= TAG_TILE_WIDTH && tag <= TAG_TILE_COUNTS) return FPL_UNSUPPORTED;
        if (tag == TAG_COMPRESSION) {
            if (rd16(read, e + 2) != TYPE_SHORT || rd32(read, e + 4) != 1 ||
                rd16(read, e + 8) != 1)
                return FPL_UNSUPPORTED;                         /* not uncompressed */
            seen |= 1u;
        }
        if (tag == TAG_STRIP_OFFSETS) seen |= 2u;
        if (tag == TAG_ROWS_PER_STRIP) seen |= 4u;
        if (tag == TAG_STRIP_COUNTS) seen |= 8u;
    }
    if (seen != 15u) return FPL_UNSUPPORTED;
    out->entries = count - 3u + 4u;
    out->ifd_at = FPL_TRAILER_PIXELS + payload;
    out->ifd_size = 2u + 12u * out->entries + 4u;
    out->offset_table = out->ifd_at + out->ifd_size;
    out->count_table = out->offset_table + 4u * tiles;
    out->file_bytes = out->count_table + 4u * tiles;
    return FPL_OK;
}

static uintptr_t put_entry(fpl_trailer_read r, fpl_trailer_write w, uintptr_t at,
                           uint32_t tag, uint32_t type, uint32_t count, uint32_t value) {
    wr16(r, w, at, tag);
    wr16(r, w, at + 2, type);
    wr32(r, w, at + 4, count);
    wr32(r, w, at + 8, value);
    return at + 12;
}

uint32_t fpl_trailer_write_all(uintptr_t file, uint32_t payload,
                               const uint32_t *tile_bytes, uint32_t tiles,
                               uint32_t tile_width, uint32_t tile_height,
                               uint32_t capacity, fpl_trailer_read read,
                               fpl_trailer_write write, struct fpl_trailer *out) {
    struct fpl_trailer plan;
    uint32_t result, root, count, sum = 0, added = 0, position;
    uintptr_t at;
    /* The four new tags are consecutive, 322..325: computed, not tabled, so
     * the code carries no read-only data section and no relocation. */

    if (!tile_bytes || !write) return FPL_INVALID;
    if ((result = fpl_trailer_plan(file, payload, tiles, read, &plan)) != FPL_OK)
        return result;
    for (uint32_t n = 0; n < tiles; ++n) {
        if (!tile_bytes[n] || tile_bytes[n] > payload - sum) return FPL_INVALID;
        sum += tile_bytes[n];
    }
    if (sum != payload) return FPL_INVALID;          /* tiles must reach the IFD */
    if (plan.file_bytes > capacity || plan.file_bytes < plan.ifd_at) return FPL_UNSUPPORTED;

    root = rd32(read, file + 4);
    count = rd16(read, file + root);
    at = file + plan.ifd_at;
    wr16(read, write, at, plan.entries);
    at += 2;
    for (uint32_t n = 0; n <= count; ++n) {
        uint32_t tag = n < count ? rd16(read, file + root + 2u + 12u * n) : 0x10000u;
        /* the four new tags, each where it sorts */
        while (added < 4 && TAG_TILE_WIDTH + added < tag) {
            uint32_t t = TAG_TILE_WIDTH + added++;
            uint32_t value = t == TAG_TILE_WIDTH ? tile_width :
                             t == TAG_TILE_LENGTH ? tile_height :
                             t == TAG_TILE_OFFSETS ? plan.offset_table : plan.count_table;
            at = put_entry(read, write, at, t, TYPE_LONG,
                           t >= TAG_TILE_OFFSETS ? tiles : 1u, value);
        }
        if (n == count) break;
        if (tag == TAG_STRIP_OFFSETS || tag == TAG_ROWS_PER_STRIP ||
            tag == TAG_STRIP_COUNTS)
            continue;
        if (tag == TAG_COMPRESSION) {
            at = put_entry(read, write, at, tag, TYPE_SHORT, 1, LOSSLESS_JPEG);
            continue;
        }
        for (uint32_t b = 0; b < 12; ++b)                 /* as it was */
            wr8(read, write, at + b, rd8(read, file + root + 2u + 12u * n + b));
        at += 12;
    }
    wr32(read, write, at, 0);                            /* no next IFD */
    at += 4;
    if (at != file + plan.offset_table) return FPL_FAULT;  /* cannot be */

    position = FPL_TRAILER_PIXELS;
    for (uint32_t n = 0; n < tiles; ++n) {
        wr32(read, write, file + plan.offset_table + 4u * n, position);
        wr32(read, write, file + plan.count_table + 4u * n, tile_bytes[n]);
        position += tile_bytes[n];
    }
    /* Last: the one byte of the original header that moves. Until now the
     * file still describes its original strips. */
    wr32(read, write, file + 4, plan.ifd_at);
    *out = plan;
    return FPL_OK;
}

/* ---- the prepared trailer ------------------------------------------------
 * The image and the snapshot are the card's own memory (cached since
 * 2026-10-13): plain byte access is fine there. Only `read`/`write` touch
 * the frame, always aligned words. */
static uint32_t tr_snap_read(uintptr_t a) { return *(const uint32_t *)a; }
static uint32_t tr_get16(const uint8_t *p, uint32_t at) {
    return p[at] | ((uint32_t)p[at + 1] << 8);
}
static void tr_put16(uint8_t *p, uint32_t at, uint32_t v) {
    p[at] = (uint8_t)v; p[at + 1] = (uint8_t)(v >> 8);
}
static void tr_put32(uint8_t *p, uint32_t at, uint32_t v) {
    tr_put16(p, at, v); tr_put16(p, at + 2, v >> 16);
}
static void tr_saturate(uint32_t *v) { if (*v != UINT32_MAX) ++*v; }

/* The compressed IFD from the snapshot, entry for entry what
 * fpl_trailer_write_all writes; the two table positions are left for the
 * frame. 1 = built. */
static uint32_t prep_build(struct fpl_trailer_prep *p, uint32_t tiles,
                           uint32_t tile_width, uint32_t tile_height) {
    const uint8_t *h = (const uint8_t *)p->header;
    uint8_t *img = (uint8_t *)p->image;
    struct fpl_trailer plan;
    uint32_t root, count, at = 2, added = 0;

    p->valid = 0;
    /* the same checks, over the snapshot; the payload only places the IFD */
    if (fpl_trailer_plan((uintptr_t)p->header, 1024u, tiles, tr_snap_read, &plan) != FPL_OK ||
        plan.ifd_size + 8u * tiles > 4u * FPL_PREP_IMAGE_WORDS)
        return 0;
    root = p->header[1];
    count = tr_get16(h, root);
    if (root + 2u + 12u * count + 4u > 4u * p->words) return 0;
    for (uint32_t n = 0; n < FPL_PREP_IMAGE_WORDS; ++n) p->image[n] = 0;
    tr_put16(img, 0, plan.entries);
    for (uint32_t n = 0; n <= count; ++n) {
        uint32_t tag = n < count ? tr_get16(h, root + 2u + 12u * n) : 0x10000u;
        while (added < 4 && TAG_TILE_WIDTH + added < tag) {
            uint32_t t = TAG_TILE_WIDTH + added++;
            tr_put16(img, at, t);
            tr_put16(img, at + 2, TYPE_LONG);
            tr_put32(img, at + 4, t >= TAG_TILE_OFFSETS ? tiles : 1u);
            tr_put32(img, at + 8, t == TAG_TILE_WIDTH ? tile_width :
                               t == TAG_TILE_LENGTH ? tile_height : 0u);
            if (t == TAG_TILE_OFFSETS) p->offsets_value = at + 8;
            if (t == TAG_TILE_COUNTS) p->counts_value = at + 8;
            at += 12;
        }
        if (n == count) break;
        if (tag == TAG_STRIP_OFFSETS || tag == TAG_STRIP_COUNTS || tag == TAG_ROWS_PER_STRIP)
            continue;
        if (tag == TAG_COMPRESSION) {
            tr_put16(img, at, tag);
            tr_put16(img, at + 2, TYPE_SHORT);
            tr_put32(img, at + 4, 1);
            tr_put32(img, at + 8, LOSSLESS_JPEG);
        } else {
            for (uint32_t b = 0; b < 12; ++b) img[at + b] = h[root + 2u + 12u * n + b];
        }
        at += 12;
    }
    tr_put32(img, at, 0);                                   /* no next IFD */
    at += 4;
    if (at != plan.ifd_size || added != 4) return 0;
    p->ifd_size = plan.ifd_size;
    p->tiles = tiles;
    p->tile_width = tile_width;
    p->tile_height = tile_height;
    p->valid = 1;
    tr_saturate(&p->built);
    return 1;
}

uint32_t fpl_trailer_write_prepared(struct fpl_trailer_prep *p, uintptr_t file,
                                    uint32_t payload, const uint32_t *tile_bytes,
                                    uint32_t tiles, uint32_t tile_width,
                                    uint32_t tile_height, uint32_t capacity,
                                    fpl_trailer_read read, fpl_trailer_write write,
                                    struct fpl_trailer *out) {
    uint32_t root, count, end, words, mask, changed = 0, sum = 0;
    uint32_t ifd_at, image_words, offset_table, count_table, position;
    uint8_t *img;

    if (!p || !file || (file & 3u) || !read || !write || !out || !tile_bytes ||
        !payload || !tiles || tiles > 160u || payload > 0x7fffffffu)
        goto fallback;
    for (uint32_t n = 0; n < tiles; ++n) {
        if (!tile_bytes[n] || tile_bytes[n] > payload - sum) goto fallback;
        sum += tile_bytes[n];
    }
    if (sum != payload) goto fallback;
    if (read(file) != TIFF_LE_MAGIC) goto fallback;
    root = read(file + 4);
    if (root < 8 || (root & 3u) || root > FPL_TRAILER_PIXELS - 6) goto fallback;
    count = read(file + root) & 0xffffu;
    end = root + 2u + 12u * count + 4u;
    if (end > 4u * FPL_PREP_HEADER_WORDS) goto fallback;
    words = (end + 3u) >> 2;
    mask = end & 3u ? (1u << (8u * (end & 3u))) - 1u : UINT32_MAX;

    /* 1. the frame's header against the snapshot */
    if (!p->valid || p->words != words || p->last_mask != mask) changed = 1;
    for (uint32_t n = 0; n < words; ++n) {
        uint32_t v = read(file + 4u * n);
        if (n == words - 1) v &= mask;
        if (v != p->header[n]) { p->header[n] = v; changed = 1; }
    }
    p->words = words;
    p->last_mask = mask;
    if (changed || p->tiles != tiles || p->tile_width != tile_width ||
        p->tile_height != tile_height) {
        if (!prep_build(p, tiles, tile_width, tile_height)) goto fallback;
    } else {
        tr_saturate(&p->reused);
    }

    /* 2. this frame's places */
    ifd_at = FPL_TRAILER_PIXELS + payload;
    image_words = (p->ifd_size + 8u * tiles + 3u) >> 2;
    if ((ifd_at & 3u) || ifd_at + 4u * image_words > capacity ||
        ifd_at + 4u * image_words < ifd_at)
        goto fallback;
    offset_table = ifd_at + p->ifd_size;
    count_table = offset_table + 4u * tiles;
    img = (uint8_t *)p->image;
    tr_put32(img, p->offsets_value, offset_table);
    tr_put32(img, p->counts_value, count_table);
    position = (uint32_t)FPL_TRAILER_PIXELS;
    for (uint32_t n = 0; n < tiles; ++n) {
        tr_put32(img, p->ifd_size + 4u * n, position);
        tr_put32(img, p->ifd_size + 4u * (tiles + n), tile_bytes[n]);
        position += tile_bytes[n];
    }

    /* 3. out, whole words; the root pointer last */
    for (uint32_t n = 0; n < image_words; ++n)
        write(file + ifd_at + 4u * n, p->image[n]);
    write(file + 4, ifd_at);
    out->entries = tr_get16(img, 0);
    out->ifd_at = ifd_at;
    out->ifd_size = p->ifd_size;
    out->offset_table = offset_table;
    out->count_table = count_table;
    out->file_bytes = count_table + 4u * tiles;
    return FPL_OK;

fallback:
    if (p) tr_saturate(&p->fallback);
    return fpl_trailer_write_all(file, payload, tile_bytes, tiles, tile_width, tile_height,
                                 capacity, read, write, out);
}
