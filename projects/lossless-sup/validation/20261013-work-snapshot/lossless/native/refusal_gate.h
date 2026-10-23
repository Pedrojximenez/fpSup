#ifndef FPLOSSLESS_REFUSAL_GATE_H
#define FPLOSSLESS_REFUSAL_GATE_H
#include <stdint.h>

/* Stop submitting frames that keep coming back without a smaller file.
 *
 * A frame the engine refuses (pattern 4) or that does not shrink still costs
 * the hold, the job and the engine, and then goes to the card as it was. On
 * the camera (2026-10-13) every HS280 / M12240 frame was refused, about
 * 2.3 ms of engine plus the hold per frame, ~8 points of CPU at 119.88p,
 * for nothing. FHD in the same boot compressed 274 of 275.
 *
 * After FPL_GATE_STREAK such frames in a row with no compressed one, later
 * arrivals go RAW at admission, except one probe every FPL_GATE_PROBE
 * arrivals. A probe that compresses opens the gate again. The gate only ever
 * withholds a frame from the engine: the file is the stock file, exactly as
 * with LOSS off, so no output can be wrong because of it. Per take. */
#define FPL_GATE_STREAK 8u
#define FPL_GATE_PROBE 120u

struct fpl_refusal_gate {
    uint32_t streak_limit, probe_every;
    uint32_t seen_compressed, seen_failed;  /* lane totals at the last look */
    uint32_t streak, closed, since_probe;
    uint32_t closes, reopens, probes, skipped;
};

/* At the take's start, with the lanes' current totals. */
void fpl_gate_begin(struct fpl_refusal_gate *, uint32_t compressed, uint32_t failed);
/* At each arrival, before admission: the lanes' running totals of compressed
 * and of failed (no smaller file: refused or no benefit) frames. Returns 1 if
 * this arrival may go to the engine, 0 if it goes RAW. */
uint32_t fpl_gate_allow(struct fpl_refusal_gate *, uint32_t compressed, uint32_t failed);
#endif
