#include "flush_site.h"

#define WRITER_NODE   0x0cu
#define WRITER_HEAD   0x8cu
#define WRITER_COUNT  0x90u
#define NODE_BUFFER   0x04u
#define NODE_LENGTH   0x08u

#if defined(FPL_FLUSH_SITE_HOST_TEST)
#define F (&fpl_flush_test_natives)
#define peek(a) F->read(a)
#define poke(a, v) F->write(a, v)
#define uncached(a) F->uncached(a)
#define barrier() F->barrier()
#elif defined(__arm__) && UINTPTR_MAX == UINT32_MAX
#define peek(a) (*(volatile const uint32_t *)(a))
#define poke(a, v) (*(volatile uint32_t *)(a) = (v))
#define uncached(a) ((uintptr_t)(a) + 0x40000000u)
#define barrier() __asm__ volatile("dsb sy" ::: "memory")
#else
#error "ARM32 native writer ABI required; host tests must explicitly substitute it"
#endif

static void saturate(uint32_t *v) { if (*v != UINT32_MAX) ++*v; }

uint32_t fpl_flush_before(uintptr_t writer, uintptr_t frame, struct fpl_frame_hold *h,
                          struct fpl_frame_hold *h2, struct fpl_flush_stats *s) {
    const struct fpl_hold_commit *c;
    uintptr_t node, buffer;
    uint32_t length;

    if (!s) return FPL_INVALID;
    saturate(&s->calls);
    /* The shape G3 checked and the 9/29 probe relied on. */
    if (!writer || (writer & 3u) || peek(writer + WRITER_COUNT) != 1 ||
        peek(writer + WRITER_HEAD) != writer + WRITER_NODE) {
        saturate(&s->shape);
        return FPL_OK;
    }
    node = writer + WRITER_NODE;
    buffer = peek(node + NODE_BUFFER);
    length = peek(node + NODE_LENGTH);
    c = buffer && !(buffer & 3u) ? fpl_hold_peek_frame(h, buffer, frame) : 0;
    if (!c && buffer && !(buffer & 3u)) {
        c = fpl_hold_peek_frame(h2, buffer, frame);
        if (c) h = h2;                   /* the second lane's current promise */
    }
    if (!c) {
        saturate(&s->no_promise);
        return FPL_OK;
    }
    if (length != c->stock_bytes) {
        /* Not the whole stock file: some other write of this buffer. The
         * promise stays for the real one. */
        saturate(&s->length_mismatch);
        return FPL_OK;
    }
    if (!c->file_bytes || c->file_bytes >= c->stock_bytes) {
        saturate(&s->invalid_length);
        fpl_hold_consumed(h, c);
        return FPL_FAULT;
    }
    /* DNG bytes were completed before enqueue; this task only fixes length. */
    poke(node + NODE_LENGTH, c->file_bytes);
    barrier();
    s->last_length = peek(node + NODE_LENGTH);
    fpl_hold_consumed(h, c);
    saturate(&s->applied);
    return FPL_OK;
}
