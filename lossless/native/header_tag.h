#ifndef FPLOSSLESS_HEADER_TAG_H
#define FPLOSSLESS_HEADER_TAG_H
#include <stdint.h>
#include "../control.h"

/* The compressed IFD, prepared once per take INSIDE the firmware's own DNG
 * header template (2026-10-14; research/firmware/notes/cinemadng-header/).
 *
 * At the take's template build (the mode-0 observer notify in FUN_c0378a50)
 * the card's observer adds one private IFD0 tag, FPL_HEADER_TAG, UNDEFINED x
 * FPL_HEADER_TAG_BYTES. The firmware serializes it with the rest. After the
 * serialization (the mode-2 notify, C0378F70) the tag's value bytes are filled
 * with a second IFD: the root IFD's entries minus the strips, Compression 7,
 * the four tile tags, and room for the two tile tables. It is not linked into
 * any IFD chain, so a RAW frame of the take is the stock frame plus an unread
 * tag. The firmware's header DMA (C038C77C) carries it into every frame.
 *
 *   tag value  .. ifd_at        (0..3 bytes to word-align the IFD)
 *   ifd_at     .. +ifd_size     the compressed IFD, next-IFD 0
 *   tables_at  .. +4*max_tiles  TileOffsets
 *              .. +4*max_tiles  TileByteCounts
 *
 * Nothing is done per frame: every root-IFD value the firmware rewrites per
 * frame (time codes, unique ID, black level, opcodes...) is out of line, and
 * the copy points at the same bytes (A001_002, 2026-10-15: all 59 entries of
 * frames 1 and 657 identical; HDR_CDNG.md §2). At the writer's flush only the
 * tile width/height, the two table entries, the tables and -- last -- the
 * root pointer are written.
 *
 * Offsets are file offsets: the template is the file's first `head` bytes. */
#define FPL_HEADER_TAG       0xFD4Cu   /* private; Gyro2 must use another */
/* The tag's size is the take's: room for a compressed IFD of up to
 * FPL_HEADER_TAG_ENTRIES entries (the root IFD is ~59 at FHD) and the two
 * tables of THIS take's tiles, word-aligned twice. Every byte of it is in
 * every frame, and the header reserve leaves all the sups only 7-8 KiB. */
#define FPL_HEADER_TAG_ENTRIES 80u
#define FPL_HEADER_TAG_BYTES(tiles) \
    (((3u + 2u + 12u * FPL_HEADER_TAG_ENTRIES + 4u + 3u) + 8u * (tiles) + 3u) & ~3u)
#define FPL_HEADER_TAG_MIN   FPL_HEADER_TAG_BYTES(2u)
#define FPL_HEADER_TAG_MAX   FPL_HEADER_TAG_BYTES(FPL_TILE_MAX)
#define FPL_HEADER_TAG_MAX_HEAD 0x15400u   /* the frame's header reserve */

struct fpl_header_tag {
    uint32_t head;                      /* template bytes it was prepared for */
    uint32_t ifd_at, entries, tables_at, counts_at, max_tiles;
    uint32_t width_at, length_at, offsets_at, bytes_at;   /* the four entries */
};

typedef uint32_t (*fpl_header_tag_read)(uintptr_t);
typedef void (*fpl_header_tag_write)(uintptr_t, uint32_t);

/* Build the compressed IFD into the template at `base` (`head` bytes) and
 * fill `t`. FPL_OK, or FPL_UNSUPPORTED with nothing written. */
uint32_t fpl_header_tag_prepare(struct fpl_header_tag *t, uintptr_t base, uint32_t head,
                                fpl_header_tag_read read, fpl_header_tag_write write);
/* One compressed frame, its payload at `t->head`: the tile entries, the
 * tables, then the root pointer. FPL_OK and *file_bytes, or nothing written. */
uint32_t fpl_header_tag_complete(const struct fpl_header_tag *t, uintptr_t file,
                                 uint32_t payload, const uint32_t *tile_bytes,
                                 uint32_t tiles, uint32_t tile_width,
                                 uint32_t tile_height, uint32_t capacity,
                                 fpl_header_tag_read read, fpl_header_tag_write write,
                                 uint32_t *file_bytes);
#endif
