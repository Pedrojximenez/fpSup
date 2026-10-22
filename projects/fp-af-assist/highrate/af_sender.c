/* Finite AFB1 camera task sender core. Freestanding, no heap/libc/global state,
 * no hook, IRQ, device access or firmware-address assumptions. The identical C
 * logic is host-tested and cross-compiled for ARM; platform callbacks are NOT
 * a completed firmware binding or deployment authorization.
 */
#include "af_sender.h"

#define HEADER 64u
#define RECORD 128u
#define MAX_RECORDS 256u
#define MAX_DMA (HEADER * 2u + RECORD * MAX_RECORDS)

static uint32_t rd(const volatile uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static void wr(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16); p[3] = (uint8_t)(v >> 24);
}
uint32_t af_crc32(const uint8_t *data, uint32_t size) {
    uint32_t crc = 0xffffffffu;
    for (uint32_t i = 0; i < size; ++i) {
        crc ^= data[i];
        for (uint32_t bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

int32_t af_ep83_completion_ok(const struct af_ep83_receipt *r) {
    if (!r) return 0;
    /* Strict normal-TRB policy: accept only the saved address, high word zero,
     * zero residue/status word and exactly original 0x813 with HWO cleared.
     * Unknown status/control mutations are rejected, not reinterpreted.
     * active==2 (End's synthetic wake) must not pass even with Wait==0.
     */
    return r->wait_rc == 0 && r->active == 0 && r->owned_trb != 0 &&
        !(r->owned_trb & 15u) && r->current_trb == r->owned_trb &&
        r->expected_bus != 0 && !(r->expected_bus & 63u) &&
        r->requested_bytes >= HEADER * 2u + RECORD &&
        r->requested_bytes <= MAX_DMA && !(r->requested_bytes & (RECORD - 1u)) &&
        r->expected_bus <= UINT32_MAX - r->requested_bytes &&
        r->word0 == r->expected_bus && r->word1 == 0 &&
        r->word2 == 0 && r->word3 == 0x812u;
}

static int span(const void *p, uint32_t bytes) {
    return p != 0 && bytes && (uintptr_t)p <= UINTPTR_MAX - bytes;
}
static int overlap(const void *a, uint32_t na, const void *b, uint32_t nb) {
    uintptr_t x = (uintptr_t)a, y = (uintptr_t)b;
    return x < y + nb && y < x + na;
}
/* Capture schema 2: word 12 is the staged level, 13 the producer returns seen,
 * 14 the body mark and 15 the latched re-entry count. A batch is never sent
 * from a producer that was re-entered, nor while a body is still marked. */
#define SCHEMA        2u
#define LEVEL_RECORD  3u
static int header_valid(const volatile uint8_t *s, uint32_t n, uint32_t nonce) {
    return rd(s) == 0x31464841u && rd(s+4) == SCHEMA && rd(s+8) == RECORD &&
        rd(s+12) == n && rd(s+16) == nonce && rd(s+20) == 0 &&
        rd(s+24) == n && rd(s+28) == 1 && rd(s+32) == 0xc022c858u &&
        rd(s+36) == 0xc023e9d0u && rd(s+40) == 0xc022c85cu &&
        rd(s+44) == HEADER && rd(s+48) == LEVEL_RECORD && rd(s+52) >= n &&
        !(rd(s+56) | rd(s+60));
}
static int records_valid(const volatile uint8_t *p, uint32_t n, uint32_t nonce) {
    for (uint32_t i = 0; i < n; ++i, p += RECORD)
        if (rd(p) != i + 1 || rd(p+4) != nonce || rd(p+8) != i + 1 ||
            rd(p+124) != ~(i + 1)) return 0;
    return 1;
}
static int32_t fail(struct af_tx_result *s, int32_t error, int32_t rc,
                    uint32_t phase) {
    s->error = error;
    s->platform_rc = rc;
    s->phase = phase;
    return error;
}

int32_t af_tx_send(const struct af_tx_request *q, struct af_tx_result *s,
                   const struct af_tx_ops *ops) {
    if (!q || !s || !ops) return AF_TX_E_ARGS;
    if (s->phase != AF_TX_FRESH) return AF_TX_E_REUSE;

    /* Check every pointer interval/alias before modifying result or buffers.
     * Runtime accessibility/CPU-bus mapping still belongs to preflight.
     */
    const void *ptrs[6] = { (const void *)q->state, (const void *)q->records,
                            q->dma_cpu, q, s, ops };
    uint32_t sizes[6] = { HEADER, q->records_bytes, q->dma_capacity,
                          sizeof(*q), sizeof(*s), sizeof(*ops) };
    if (!q->nonce || !q->wait_ms || q->wait_ms > 2000 ||
        !q->records_bytes || q->records_bytes % RECORD ||
        q->records_bytes > RECORD * MAX_RECORDS || q->dma_capacity > MAX_DMA ||
        q->dma_capacity < HEADER * 2u + q->records_bytes ||
        !q->dma_bus || (q->dma_bus & 63u) ||
        q->dma_bus > UINT32_MAX - q->dma_capacity ||
        ((uintptr_t)q->dma_cpu & 63u) ||
        !ops->preflight || !ops->publish || !ops->start || !ops->wait || !ops->completion)
        return AF_TX_E_ARGS;
    for (uint32_t i = 0; i < 6; ++i) {
        if (!span(ptrs[i], sizes[i])) return AF_TX_E_ARGS;
        for (uint32_t j = 0; j < i; ++j)
            if (overlap(ptrs[i], sizes[i], ptrs[j], sizes[j])) return AF_TX_E_ARGS;
    }

    s->nonce = q->nonce;
    s->phase = AF_TX_CHECKING;
    s->error = s->platform_rc = 0;
    s->batch_bytes = s->batch_crc = 0;
    s->dma_may_be_owned = s->dma_reclaimable = 0;

    int32_t rc = ops->preflight(ops->ctx, q);
    if (rc != 1) return fail(s, AF_TX_E_PREFLIGHT, rc, AF_TX_REJECTED);
    /* Successful preflight establishes an idle DMA lease, not hook detach. */
    s->dma_reclaimable = 1;
    uint32_t count = q->records_bytes / RECORD;
    if (!header_valid(q->state, count, q->nonce) ||
        !records_valid(q->records, count, q->nonce))
        return fail(s, AF_TX_E_CAPTURE, 0, AF_TX_REJECTED);

    uint8_t *d = q->dma_cpu;
    for (uint32_t i = 0; i < HEADER; ++i) d[i] = 0;
    for (uint32_t i = 0; i < HEADER; ++i) d[HEADER+i] = q->state[i];
    for (uint32_t i = 0; i < q->records_bytes; ++i)
        d[HEADER*2u+i] = q->records[i];
    /* Check the copied image, then exact-match the sources again. This detects
     * visible mutation only; no ABA/IRQ/cache coherence guarantee is claimed.
     */
    if (!header_valid(d+HEADER, count, q->nonce) ||
        !records_valid(d+HEADER*2u, count, q->nonce))
        return fail(s, AF_TX_E_CAPTURE, 0, AF_TX_REJECTED);
    for (uint32_t i = 0; i < HEADER; ++i)
        if (d[HEADER+i] != q->state[i])
            return fail(s, AF_TX_E_CAPTURE, 0, AF_TX_REJECTED);
    for (uint32_t i = 0; i < q->records_bytes; ++i)
        if (d[HEADER*2u+i] != q->records[i])
            return fail(s, AF_TX_E_CAPTURE, 0, AF_TX_REJECTED);

    uint32_t capture_bytes = HEADER + q->records_bytes;
    uint32_t total = HEADER + capture_bytes;
    wr(d, 0x31424641u); wr(d+4, 1); wr(d+8, HEADER); wr(d+12, q->nonce);
    wr(d+16, count); wr(d+20, RECORD); wr(d+24, capture_bytes);
    wr(d+28, af_crc32(d+HEADER, capture_bytes)); wr(d+32, 1);
    wr(d+36, af_crc32(d, HEADER));
    s->batch_bytes = total;
    s->batch_crc = af_crc32(d, total);
    s->phase = AF_TX_PREPARED;

    rc = ops->publish(ops->ctx, d, total);
    if (rc != 1) return fail(s, AF_TX_E_PUBLISH, rc, AF_TX_REJECTED);
    /* A bad/partial Start outcome must never permit reuse or overwrite. Set
     * the quarantine indicators BEFORE allowing any endpoint mutation.
     */
    s->dma_may_be_owned = 1;
    s->dma_reclaimable = 0;
    s->phase = AF_TX_IN_FLIGHT;
    rc = ops->start(ops->ctx, 7, q->dma_bus, total);
    if (rc != 0) return fail(s, AF_TX_E_START, rc, AF_TX_QUARANTINED);
    rc = ops->wait(ops->ctx, 3, q->wait_ms);
    if (rc != 0) return fail(s, AF_TX_E_WAIT, rc, AF_TX_QUARANTINED);
    rc = ops->completion(ops->ctx, q->nonce, total);
    if (rc != 1) return fail(s, AF_TX_E_COMPLETION, rc, AF_TX_QUARANTINED);
    s->dma_may_be_owned = 0;
    s->dma_reclaimable = 1;
    s->phase = AF_TX_COMPLETE;
    return AF_TX_OK;
}
