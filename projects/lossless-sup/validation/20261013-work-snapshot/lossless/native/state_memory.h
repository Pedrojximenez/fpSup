#ifndef FPLOSSLESS_STATE_MEMORY_H
#define FPLOSSLESS_STATE_MEMORY_H
#include <stdint.h>

/* These owned state objects are word-aligned and word-sized. Preserve the
 * full-zero contract, including padding and inactive metadata. Bulk word
 * operations avoid millions of byte transactions on the USER noncache block.
 * may_alias permits object-representation access through this word type.
 * No DMA, guessed cache aliases, native memset or IRQ masking is involved. */
typedef uint32_t fpl_state_word __attribute__((__may_alias__));
static inline void fpl_state_clear(void *object, uint32_t bytes) {
    fpl_state_word *p = (fpl_state_word *)object;
    uint32_t words = bytes / 4u;
    while (words >= 8u) {
        p[0] = p[1] = p[2] = p[3] = 0;
        p[4] = p[5] = p[6] = p[7] = 0;
        p += 8; words -= 8;
    }
    while (words--) *p++ = 0;
}
static inline uint32_t fpl_state_is_zero(const void *object, uint32_t bytes) {
    const fpl_state_word *p = (const fpl_state_word *)object;
    uint32_t words = bytes / 4u;
    while (words >= 8u) {
        uint32_t a = p[0] | p[1] | p[2] | p[3];
        uint32_t b = p[4] | p[5] | p[6] | p[7];
        if (a | b) return 0;
        p += 8; words -= 8;
    }
    while (words--) if (*p++) return 0;
    return 1;
}
#endif
