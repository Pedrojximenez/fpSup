#ifndef FPLOSSLESS_MEMORY_BUDGET_H
#define FPLOSSLESS_MEMORY_BUDGET_H
#include <stdint.h>

/* Compression retains a whole RAW allocation even when its file is small.
 * Leave room to reach TWO stock byte batches using uncompressed arrivals,
 * plus arrivals during observed completion latency, four pipeline and two
 * stop frames. This is admission control, never an early-flush predicate.
 * Media latency is a measured budget, not an upper-bound hardware promise. */
struct fpl_memory_budget {
    uint32_t enabled, frame_charge, raw_file_bytes, raw_batch_frames, fps_ceil;
    uint32_t latency_us, reserve_frames, reserve_bytes;
    uint32_t checks, admitted, pressure_raw, unknown_raw, last_free, min_free;
};
void fpl_memory_reset(struct fpl_memory_budget *);
void fpl_memory_begin(struct fpl_memory_budget *, uint32_t raster,
                      uint32_t fps_num, uint32_t fps_den, uint32_t latency_us);
/* UINT32_MAX means unknown headroom. Unknown/invalid budgets go RAW.
 * Sample after the current frame and codec workspaces have been allocated;
 * their memory is already excluded from free_bytes. */
uint32_t fpl_memory_allow(struct fpl_memory_budget *, uint32_t free_bytes,
                          uint32_t latency_us);
/* Ver.5.02 primary class-10 RAW counter only; no linked-pool capacity is
 * added. O(1), read-only, IRQ-masked snapshot; never walks allocation lists.
 * Aggregate headroom is not a proof of a contiguous allocation succeeding. */
uint32_t fpl_raw_headroom(void);
#endif
