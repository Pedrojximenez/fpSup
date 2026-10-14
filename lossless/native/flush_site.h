#ifndef FPLOSSLESS_FLUSH_SITE_H
#define FPLOSSLESS_FLUSH_SITE_H
#include "frame_hold.h"
#include "header_tag.h"

/* The writer's final flush, C03A5490: BL C069ADE0 with r0 = the writer, a
 * 148-byte STACK object (never retained; §10.3). Its single node is at
 * writer+0x0C: writer+0x8C is the head and must point there, writer+0x90 is
 * the node count and must be 1, node+4 is the file buffer, node+8 the length.
 * Measured and used live 2026-09-29 (inline_compress_probe.S): a node length
 * set here is the length the card gets.
 *
 * For a file buffer with a promise from the frame adapter, and ONLY if the
 * node still carries that frame's stock length: complete the IFD its header
 * already holds (header_tag.h), then set the length, then read it back, then
 * consume the promise. Anything else -- no promise, another shape, another
 * length -- is left exactly as it is. */
struct fpl_flush_stats {
    uint32_t calls, applied, shape, no_promise, length_mismatch, tag_failed;
    uint32_t last_length;
};

#if defined(FPL_FLUSH_SITE_HOST_TEST)
struct fpl_flush_natives {
    uint32_t (*read)(uintptr_t);
    void (*write)(uintptr_t, uint32_t);
    uintptr_t (*uncached)(uintptr_t);
    void (*barrier)(void);
};
extern const struct fpl_flush_natives fpl_flush_test_natives;
#endif

/* The promise may be in either hold (two lanes); the second may be NULL.
 * `tag` is the take's prepared IFD. A frame is only ever held when its take
 * has one (frame_hold.h require_head), so a promise it does not fit is a
 * fault: counted, consumed, not retried. */
uint32_t fpl_flush_before(uintptr_t writer, struct fpl_frame_hold *,
                          struct fpl_frame_hold *, const struct fpl_header_tag *tag,
                          struct fpl_flush_stats *);
#endif
