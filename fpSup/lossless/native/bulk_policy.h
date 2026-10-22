#ifndef FPLOSSLESS_BULK_POLICY_H
#define FPLOSSLESS_BULK_POLICY_H
#include <stdint.h>

#define FPL_BULK_BYTES 0x04000000u
#define FPL_BULK_POOL_SLOTS 96u
#define FPL_BULK_WINDOW 32u

/* Two batches share the stock pool. Four further slots cover the codec /
 * writer handoff, in addition to arrivals during a writer return. The initial
 * 100 ms allowance is a conservative starting assumption, not a measured
 * device guarantee. A longer observed return only tightens this take's cap.
 * The native free-slot watermark remains an independent early trigger. */
struct fpl_bulk_policy {
    uint32_t enabled, fps_ceil, start_free, latency_us;
    uint32_t arrival_reserve, frame_limit, free_watermark, budget_exhausted;
    uint32_t checks, count_flushes, pressure_flushes, unknown_pool;
    uint32_t submitted, compressed, raw, failed_returns;
    uint32_t window_frames, window_compressed, window_bytes;
    uint32_t sample_frames, sample_compressed, sample_bytes;
    uint32_t mean_bytes, predicted_frames;
};

void fpl_bulk_reset(struct fpl_bulk_policy *);
void fpl_bulk_begin(struct fpl_bulk_policy *, uint32_t fps_num, uint32_t fps_den,
                    uint32_t free_slots);
/* pending excludes the current file: its data is already in the native
 * batch, but its cookie is appended only AFTER this decision. */
uint32_t fpl_bulk_should_flush(struct fpl_bulk_policy *, uint32_t pending,
                               uint32_t free_slots);
/* Native submission return, not proof of DMA completion / durable storage.
 * Mixed compressed + RAW sizes are observed rather than guessed from ON. */
void fpl_bulk_observe(struct fpl_bulk_policy *, uint32_t low, uint32_t high,
                       uint32_t compressed, uint32_t elapsed_us);
#endif
