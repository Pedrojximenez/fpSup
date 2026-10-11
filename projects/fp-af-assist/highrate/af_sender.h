#ifndef FP_AF_SENDER_H
#define FP_AF_SENDER_H

#include <stdint.h>
#include <stddef.h>

/* Task context ONLY. No device is opened by this freestanding core. Real
 * platform callbacks remain subject to the EP83 ownership/ABI contract.
 * Fresh nonce and fresh result object for every authorized new capture;
 * never reset a quarantined result to retry. Caller serializes all access and
 * keeps request/ops/result/code and all pointed-to leases alive and unmodified
 * until return. Callbacks may update only their non-aliasing private context
 * and documented endpoint/cache state, never request, ops, result or the
 * source/destination bytes. This core exclusively owns the result structure.
 * Caller supplies valid accessible pointers; integer range checks cannot prove
 * address accessibility. ARM callers must provide 8-byte stack alignment.
 */
enum af_tx_phase {
    AF_TX_FRESH = 0, AF_TX_CHECKING = 1, AF_TX_PREPARED = 2,
    AF_TX_IN_FLIGHT = 3, AF_TX_COMPLETE = 4,
    AF_TX_REJECTED = 5, AF_TX_QUARANTINED = 6
};
enum af_tx_error {
    AF_TX_OK = 0, AF_TX_E_ARGS = -1, AF_TX_E_REUSE = -2,
    AF_TX_E_PREFLIGHT = -3, AF_TX_E_CAPTURE = -4,
    AF_TX_E_PUBLISH = -5, AF_TX_E_START = -6,
    AF_TX_E_WAIT = -7, AF_TX_E_COMPLETION = -8
};

struct af_tx_request {
    const volatile uint8_t *state;   /* exactly 64 accessible bytes */
    const volatile uint8_t *records;
    uint8_t *dma_cpu;               /* exclusive CPU mapping of DMA lease */
    uint32_t records_bytes;         /* exact capacity * 128 */
    uint32_t dma_capacity;
    uint32_t dma_bus;               /* independently verified bus mapping */
    uint32_t nonce;
    uint32_t wait_ms;               /* 1..2000; NOT total native execution bound */
};

struct af_tx_result {
    uint32_t phase;
    uint32_t nonce;
    uint32_t batch_bytes;
    uint32_t batch_crc;             /* CRC32 of entire AFB1 frame */
    int32_t error;
    int32_t platform_rc;
    uint32_t dma_may_be_owned;
    uint32_t dma_reclaimable;       /* DMA lease only, NEVER hook/state */
};

struct af_tx_ops {
    void *ctx;
    /* Return exactly 1 only after checking running build, exclusive code/data/
     * DMA lease and mappings, endpoint enumeration/ownership/idle, no stale
     * completion, capture visibility and task context. Failure changes no
     * endpoint. This is a platform obligation, not proven by a boolean input.
     * Keep ownership until sender outcome has been acknowledged by its owner.
     */
    int32_t (*preflight)(void *, const struct af_tx_request *);
    /* Publish CPU-written DMA bytes with the verified cache/coherence path.
     * No endpoint arm here. Return exactly 1 on success.
     */
    int32_t (*publish)(void *, uint8_t *, uint32_t);
    /* Arm ONE TRB and Start physical endpoint 7. No retries. Native rc=0
     * means Start accepted, not delivery; nonzero is quarantined as uncertain.
     */
    int32_t (*start)(void *, uint32_t physical_ep, uint32_t bus, uint32_t bytes);
    /* One IN completion wait for logical endpoint 3, NOT OUT C01E4E81.
     * The current bulk-mode adapter uses af_ep83_wait_once rather than native
     * C01E56F1: the latter reaches C01E7780 and can re-arm the shared EP01.
     * Success=0. Start has an independent internal DEPCMD wait;
     * wait_ms is not an end-to-end deadline or hard execution-time bound.
     */
    int32_t (*wait)(void *, uint32_t logical_ep, uint32_t timeout_ms);
    /* Return exactly 1 only after proving this nonce's owned transfer completed
     * the exact byte count and DMA is idle. A generic event bit is insufficient.
     * Until the concrete firmware adapter is audited, this must not be stubbed
     * to success. The host additionally validates bytes/CRC and EP82 terminal.
     */
    int32_t (*completion)(void *, uint32_t nonce, uint32_t bytes);
};

/* One camera-side post-Wait snapshot, acquired under the SAME exclusive owner
 * as Start. This data does not create ownership or prove its own freshness.
 * Never assemble it from unsynchronized multi-hop host RAM reads.
 */
struct af_ep83_receipt {
    int32_t wait_rc;
    uint32_t active, owned_trb, current_trb, expected_bus, requested_bytes;
    uint32_t word0, word1, word2, word3;
};

int32_t af_ep83_completion_ok(const struct af_ep83_receipt *);

#if defined(__arm__)
_Static_assert(sizeof(void *) == 4, "ARM32 pointers required");
_Static_assert(sizeof(struct af_tx_request) == 32, "request layout changed");
_Static_assert(sizeof(struct af_tx_result) == 32, "result layout changed");
_Static_assert(sizeof(struct af_tx_ops) == 24, "ops layout changed");
_Static_assert(sizeof(struct af_ep83_receipt) == 40, "receipt layout changed");
_Static_assert(offsetof(struct af_tx_request, dma_bus) == 20, "bus offset changed");
_Static_assert(offsetof(struct af_tx_ops, completion) == 20, "callback offset changed");
#endif

uint32_t af_crc32(const uint8_t *data, uint32_t size);
int32_t af_tx_send(const struct af_tx_request *, struct af_tx_result *,
                   const struct af_tx_ops *);

#endif
