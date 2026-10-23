#include "refusal_gate.h"

static void saturate(uint32_t *v) { if (*v != UINT32_MAX) ++*v; }

void fpl_gate_begin(struct fpl_refusal_gate *g, uint32_t compressed, uint32_t failed) {
    if (!g) return;
    g->streak_limit = FPL_GATE_STREAK;
    g->probe_every = FPL_GATE_PROBE;
    g->seen_compressed = compressed;
    g->seen_failed = failed;
    g->streak = g->closed = g->since_probe = 0;
    g->closes = g->reopens = g->probes = g->skipped = 0;
}

uint32_t fpl_gate_allow(struct fpl_refusal_gate *g, uint32_t compressed, uint32_t failed) {
    uint32_t won, lost;
    if (!g || !g->streak_limit || !g->probe_every) return 1;
    /* Counters only grow within a take; a smaller value is a reset lane:
     * start counting again from it rather than read a huge difference. */
    won = compressed >= g->seen_compressed ? compressed - g->seen_compressed : 0;
    lost = failed >= g->seen_failed ? failed - g->seen_failed : 0;
    g->seen_compressed = compressed;
    g->seen_failed = failed;
    if (won) {
        g->streak = 0;
        if (g->closed) {
            g->closed = 0;
            saturate(&g->reopens);
        }
    } else if (lost) {
        g->streak = g->streak + lost < g->streak ? UINT32_MAX : g->streak + lost;
        if (!g->closed && g->streak >= g->streak_limit) {
            g->closed = 1;
            g->since_probe = 0;
            saturate(&g->closes);
        }
    }
    if (!g->closed) return 1;
    if (++g->since_probe >= g->probe_every) {
        g->since_probe = 0;
        saturate(&g->probes);
        return 1;
    }
    saturate(&g->skipped);
    return 0;
}
