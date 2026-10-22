/* fp 5.02 one-shot EP83 synthetic camera adapter.
 *
 * This is a freestanding, fail-closed component for the first cold-boot
 * transport trial.  It does not install the AF recorder, move the lens, open
 * USB, send an EP82 reply, retry, drain, EndTransfer, or recover an uncertain
 * endpoint.  Its caller already owns one complete FPSH CMD4 frame and is
 * responsible for transporting the returned same-sequence terminal frame.
 */
#include "af_ep83_camera.h"
#include "af_ep83_memory.h"

#define FP_PUBLICATION_CALLSITE       0xC022C858u
#define FP_PUBLICATION_ORIGINAL       0xEB00485Cu
#define FP_NATIVE_SENDER_PATCH        0xC01E5880u
#define FP_NATIVE_SENDER_STUB         0x47702000u
#define FP_CTX3_DEFAULT               0xC07E2800u
#define FP_POOL_DESCRIPTOR            0xC3757A7Cu
#define FP_EVENT_FLAG_ID_ADDRESS      0xC31E3210u
#define FP_CTX3_TRB_POINTER           0xC31E3270u
#define FP_CTX3_TRB_BUS_POINTER       0xC31E3244u
#define FP_CTX3                       0xC31E38B8u
#define FP_MODE1_START_GATE           0xC31E38FCu
#define FP_USB_STATE                  0xC31E3748u
#define FP_WAIT_INTEREST              0xC31E3884u
#define FP_ACTIVE                     0xC31E391Cu
#define FP_DALEPENA_SHADOW            0xC31E398Cu
#define FP_IRQ_GATE                   0xC31E3A1Cu
#define FP_RESOURCE_INDEX             0xC31E3A4Cu
#define FP_NATIVE_PTP_INFLIGHT        0xC31E3AC4u
#define FP_DALEPENA_HARDWARE          0x2100C720u
#define FP_CORE_STATUS                0x300B0000u
#define FP_NATIVE_START_THUMB         0xC01E6B81u

#define FP_CTX3_TRB_CPU               0x431E32F0u
#define FP_CTX3_TRB_BUS               0x031E32F0u
#define FP_PHYSICAL_EP7_BIT           0x00000080u
#define FP_CORE_ALIVE_BIT             0x00000010u
#define FP_TRB_ARMED_CONTROL          0x00000813u

#define AF_CAPTURE_MAGIC              0x31464841u
/* Capture schema 2 adds the staged level and the re-entrancy counters; see
 * af_batch.py and af_publication.S. A synthetic capture presents itself as a
 * completed record-level run so the host decoder applies the same rules. */
#define AF_CAPTURE_SCHEMA             2u
#define AF_CAPTURE_LEVEL_RECORD       3u
#define AF_CAPTURE_HEADER_BYTES       64u
#define AF_RECORD_BYTES               128u
#define AF_MAX_RECORDS                256u
#define AF_BATCH_HEADER_BYTES         64u
#define AF_BATCH_MAGIC                0x31424641u
#define AF_CALLSITE                   0xC022C858u
#define AF_PRODUCER                   0xC023E9D0u
#define AF_CONTINUATION               0xC022C85Cu

struct af_ep83_camera_runtime {
    struct af_ep83_camera_config config;
    const volatile struct af_ep83_camera_config *live_config;
    const struct af_ep83_camera_private *evidence;
    const struct af_tx_request *request;
    const struct af_tx_result *result;
    struct af_ep83_wait_ops wait_ops;
    struct af_ep83_wait_state wait_state;
    struct af_ep83_receipt receipt;
    uint32_t owned_trb;
    uint32_t requested_bytes;
    uint32_t reference;
    int32_t wait_rc;
    af_ep83_native_start_fn native_start;
};

static uint16_t af_cam_rd16(const uint8_t *p) {
    return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}

static uint32_t af_cam_rd32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static void af_cam_wr16(uint8_t *p, uint16_t value) {
    p[0] = (uint8_t)value;
    p[1] = (uint8_t)(value >> 8);
}

static void af_cam_wr32(uint8_t *p, uint32_t value) {
    p[0] = (uint8_t)value;
    p[1] = (uint8_t)(value >> 8);
    p[2] = (uint8_t)(value >> 16);
    p[3] = (uint8_t)(value >> 24);
}

static void af_cam_zero(void *pointer, uint32_t bytes) {
    uint8_t *p = (uint8_t *)pointer;
    for (uint32_t i = 0; i < bytes; ++i) p[i] = 0;
}

static void af_cam_copy(void *destination, const void *source, uint32_t bytes) {
    uint8_t *d = (uint8_t *)destination;
    const volatile uint8_t *s = (const volatile uint8_t *)source;
    for (uint32_t i = 0; i < bytes; ++i) d[i] = s[i];
}

static void af_cam_dmb(void) {
#if defined(__arm__)
    __asm__ volatile("dmb sy" ::: "memory");
#else
    __asm__ volatile("" ::: "memory");
#endif
}

static void af_cam_dsb(void) {
#if defined(__arm__)
    __asm__ volatile("dsb sy" ::: "memory");
#else
    __asm__ volatile("" ::: "memory");
#endif
}

static uint32_t af_cam_frame_crc(const uint8_t frame[64]) {
    uint32_t crc = 0xFFFFFFFFu;
    for (uint32_t i = 0; i < AF_EP83_FPSH_FRAME_BYTES; ++i) {
        uint8_t value = (i >= 16u && i < 20u) ? 0 : frame[i];
        crc ^= value;
        for (uint32_t bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

static uint32_t af_cam_total_bytes(uint32_t count) {
    return AF_BATCH_HEADER_BYTES + AF_CAPTURE_HEADER_BYTES +
           count * AF_RECORD_BYTES;
}

int32_t af_ep83_camera_validate_trigger(const uint8_t frame[64],
                                       uint32_t *sequence, uint32_t *nonce,
                                       uint32_t *count) {
    if (!frame || !sequence || !nonce || !count) return 0;
    if (af_cam_rd32(frame) != AF_EP83_FPSH_MAGIC ||
        frame[4] != AF_EP83_FPSH_VERSION ||
        frame[5] != AF_EP83_FPSH_COMMAND || af_cam_rd16(frame + 6) != 0 ||
        af_cam_rd32(frame + 8) == 0 ||
        af_cam_rd16(frame + 12) != AF_EP83_TRIGGER_BYTES ||
        af_cam_rd16(frame + 14) != 0 ||
        af_cam_rd32(frame + 16) != af_cam_frame_crc(frame)) return 0;
    if (af_cam_rd32(frame + 20) != AF_EP83_TRIGGER_MAGIC ||
        af_cam_rd16(frame + 24) != 1 ||
        af_cam_rd16(frame + 26) != AF_EP83_TRIGGER_BYTES) return 0;
    uint32_t trigger_nonce = af_cam_rd32(frame + 28);
    uint32_t trigger_count = af_cam_rd32(frame + 32);
    if (!trigger_nonce || !trigger_count || trigger_count > AF_MAX_RECORDS ||
        af_cam_rd32(frame + 36) != af_cam_total_bytes(trigger_count) ||
        af_cam_rd32(frame + 40) || af_cam_rd32(frame + 44) ||
        af_cam_rd32(frame + 48)) return 0;
    for (uint32_t i = 52; i < AF_EP83_FPSH_FRAME_BYTES; ++i)
        if (frame[i] != 0) return 0;
    *sequence = af_cam_rd32(frame + 8);
    *nonce = trigger_nonce;
    *count = trigger_count;
    return 1;
}

static int32_t af_cam_offset_ok(const struct af_ep83_camera_config *c,
                                uint32_t offset) {
    return offset && !(offset & 3u) && offset < AF_EP83_POOL_CODE_LIMIT -
           AF_EP83_POOL_CODE_OFFSET && c->code_base <= UINT32_MAX - offset &&
           c->code_base + offset < c->code_limit;
}

static int32_t af_cam_offsets_ok(const struct af_ep83_camera_config *c) {
    return af_cam_offset_ok(c, c->offsets.sender_preflight) &&
        af_cam_offset_ok(c, c->offsets.sender_publish) &&
        af_cam_offset_ok(c, c->offsets.sender_start) &&
        af_cam_offset_ok(c, c->offsets.sender_wait) &&
        af_cam_offset_ok(c, c->offsets.sender_completion) &&
        af_cam_offset_ok(c, c->offsets.native_start) &&
        af_cam_offset_ok(c, c->offsets.wait_clear_flags) &&
        af_cam_offset_ok(c, c->offsets.wait_critical_enter) &&
        af_cam_offset_ok(c, c->offsets.wait_critical_exit) &&
        af_cam_offset_ok(c, c->offsets.wait_interest_load) &&
        af_cam_offset_ok(c, c->offsets.wait_interest_store) &&
        af_cam_offset_ok(c, c->offsets.wait_irq_reenable) &&
        af_cam_offset_ok(c, c->offsets.wait_flags);
}

static int32_t af_cam_config_ok(uint32_t pool,
                                const struct af_ep83_camera_config *c,
                                const struct af_ep83_camera_config *live) {
    if (!c || !live || pool < 0x40000000u ||
        pool > 0x80000000u - AF_EP83_POOL_WINDOW_END || (pool & 0x1FFu) ||
        (uintptr_t)live != (uintptr_t)(pool + AF_EP83_POOL_CONFIG_OFFSET) ||
        c->magic != AF_EP83_CAMERA_CONFIG_MAGIC ||
        c->schema != AF_EP83_CAMERA_SCHEMA ||
        c->bytes != AF_EP83_CAMERA_CONFIG_BYTES ||
        c->expected_pool_base != pool ||
        c->code_base != pool + AF_EP83_POOL_CODE_OFFSET ||
        c->code_limit != pool + AF_EP83_POOL_CODE_LIMIT ||
        c->state_addr != pool + AF_EP83_POOL_STATE_OFFSET ||
        c->records_addr != pool + AF_EP83_POOL_RECORDS_OFFSET ||
        c->dma_cpu != pool + AF_EP83_POOL_DMA_OFFSET ||
        c->config_addr != pool + AF_EP83_POOL_CONFIG_OFFSET ||
        c->private_addr != pool + AF_EP83_POOL_PRIVATE_OFFSET ||
        c->dma_capacity != AF_EP83_DMA_CAPACITY ||
        c->dma_cpu < 0x40000000u || c->dma_bus != c->dma_cpu - 0x40000000u ||
        (c->dma_cpu & 63u) || (c->dma_bus & 63u) ||
        !c->expected_count || c->expected_count > AF_MAX_RECORDS ||
        !c->wait_ms || c->wait_ms > 2000u || !c->armed_nonce ||
        !c->mapping_epoch || !c->owner_epoch ||
        c->expected_trb != FP_CTX3_TRB_CPU ||
        (c->expected_idle_trb[3] & 1u) || !af_cam_offsets_ok(c)) return 0;
    for (uint32_t i = 0; i < 28; ++i)
        if (c->reserved[i] != 0) return 0;
    return 1;
}

static int32_t af_cam_result_zero(const struct af_tx_result *r) {
    return !(r->phase | r->nonce | r->batch_bytes | r->batch_crc |
             (uint32_t)r->error | (uint32_t)r->platform_rc |
             r->dma_may_be_owned | r->dma_reclaimable);
}

static int32_t af_cam_wait_zero(const struct af_ep83_wait_state *s) {
    return !(s->phase | s->reference | s->observed |
             (uint32_t)s->kernel_rc | s->quarantine);
}

static int32_t af_cam_receipt_zero(const struct af_ep83_receipt *r) {
    return !((uint32_t)r->wait_rc | r->active | r->owned_trb |
             r->current_trb | r->expected_bus | r->requested_bytes |
             r->word0 | r->word1 | r->word2 | r->word3);
}

static int32_t af_cam_private_fresh(const struct af_ep83_camera_private *p,
                                    const struct af_ep83_camera_config *c) {
    if (!p || p->magic != AF_EP83_CAMERA_PRIVATE_MAGIC ||
        p->schema != AF_EP83_CAMERA_SCHEMA ||
        p->bytes != AF_EP83_CAMERA_PRIVATE_BYTES ||
        p->phase != AF_EP83_CAMERA_FRESH || p->consumed_nonce ||
        p->owner_epoch != c->owner_epoch ||
        p->mapping_epoch != c->mapping_epoch || p->last_error ||
        !af_cam_result_zero(&p->result) || !af_cam_wait_zero(&p->wait_state) ||
        !af_cam_receipt_zero(&p->receipt) || p->owned_trb ||
        p->requested_bytes || p->reference || p->wait_rc) return 0;
    for (uint32_t i = 0; i < 29; ++i)
        if (p->reserved[i] != 0) return 0;
    return 1;
}

static int32_t af_cam_live_epochs_ok(const struct af_ep83_camera_runtime *r) {
    const volatile struct af_ep83_camera_config *c = r->live_config;
    return c && c->magic == AF_EP83_CAMERA_CONFIG_MAGIC &&
        c->schema == AF_EP83_CAMERA_SCHEMA &&
        c->bytes == AF_EP83_CAMERA_CONFIG_BYTES &&
        c->expected_pool_base == r->config.expected_pool_base &&
        c->armed_nonce == r->config.armed_nonce &&
        c->mapping_epoch == r->config.mapping_epoch &&
        c->owner_epoch == r->config.owner_epoch &&
        c->expected_trb == r->config.expected_trb;
}

static int32_t af_cam_fixed_guards_ok(
        const struct af_ep83_camera_config *c,
        const struct af_ep83_camera_snapshot *s) {
    return c && s && s->publication_callsite == FP_PUBLICATION_ORIGINAL &&
        s->native_sender_patch == FP_NATIVE_SENDER_STUB &&
        s->ctx3_default == 1u && s->pool_base == c->expected_pool_base &&
        s->ctx3_mode == 1u && s->ctx3_direction == 1u &&
        s->ctx3_endpoint == 3u && s->ctx3_fourth == 0u &&
        s->usb_state != 4u &&
        (s->dalepena_shadow & FP_PHYSICAL_EP7_BIT) != 0 &&
        (s->dalepena_hardware & FP_PHYSICAL_EP7_BIT) != 0 &&
        s->active == 0 && !(s->wait_interest & AF_EP83_LOCAL_WAIT_MASK) &&
        s->event_flag_id && s->event_flag_id <= 0x7FFFFFFFu &&
        s->irq_gate == 0 && s->mode1_start_gate == 0 &&
        s->native_ptp_inflight == 0 &&
        (s->core_status & FP_CORE_ALIVE_BIT) != 0 &&
        s->trb_pointer == FP_CTX3_TRB_CPU &&
        s->trb_pointer == c->expected_trb &&
        s->trb_bus_pointer == FP_CTX3_TRB_BUS && s->trb_snapshot_valid == 1u;
}

int32_t af_ep83_camera_snapshot_ok(const struct af_ep83_camera_config *c,
                                  const struct af_ep83_camera_private *p,
                                  const struct af_tx_request *q,
                                  const struct af_ep83_camera_snapshot *s) {
    if (!af_cam_fixed_guards_ok(c, s) || !p || !q ||
        p->phase != AF_EP83_CAMERA_RUNNING ||
        p->consumed_nonce != c->armed_nonce ||
        p->owner_epoch != c->owner_epoch ||
        p->mapping_epoch != c->mapping_epoch ||
        q->state != (const volatile uint8_t *)(uintptr_t)c->state_addr ||
        q->records != (const volatile uint8_t *)(uintptr_t)c->records_addr ||
        q->dma_cpu != (uint8_t *)(uintptr_t)c->dma_cpu ||
        q->records_bytes != c->expected_count * AF_RECORD_BYTES ||
        q->dma_capacity != c->dma_capacity || q->dma_bus != c->dma_bus ||
        q->nonce != c->armed_nonce || q->wait_ms != c->wait_ms ||
        (s->trb[3] & 1u)) return 0;
    for (uint32_t i = 0; i < 4; ++i)
        if (s->trb[i] != c->expected_idle_trb[i]) return 0;
    return 1;
}

#if defined(__arm__)
static uint32_t af_cam_load32(uint32_t address) {
    return *(const volatile uint32_t *)(uintptr_t)address;
}
#endif

static void af_cam_snapshot(struct af_ep83_camera_snapshot *s,
                            uint32_t expected_trb) {
    af_cam_zero(s, (uint32_t)sizeof(*s));
#if defined(__arm__)
    af_cam_dsb();
    s->publication_callsite = af_cam_load32(FP_PUBLICATION_CALLSITE);
    s->native_sender_patch = af_cam_load32(FP_NATIVE_SENDER_PATCH);
    s->ctx3_default = af_cam_load32(FP_CTX3_DEFAULT);
    s->pool_base = af_cam_load32(FP_POOL_DESCRIPTOR);
    s->ctx3_mode = af_cam_load32(FP_CTX3);
    s->ctx3_direction = af_cam_load32(FP_CTX3 + 4u);
    s->ctx3_endpoint = af_cam_load32(FP_CTX3 + 8u);
    s->ctx3_fourth = af_cam_load32(FP_CTX3 + 12u);
    s->usb_state = af_cam_load32(FP_USB_STATE);
    s->dalepena_shadow = af_cam_load32(FP_DALEPENA_SHADOW);
    s->dalepena_hardware = af_cam_load32(FP_DALEPENA_HARDWARE);
    s->active = af_cam_load32(FP_ACTIVE);
    s->resource_index = af_cam_load32(FP_RESOURCE_INDEX);
    s->wait_interest = af_cam_load32(FP_WAIT_INTEREST);
    s->event_flag_id = af_cam_load32(FP_EVENT_FLAG_ID_ADDRESS);
    s->irq_gate = af_cam_load32(FP_IRQ_GATE);
    s->mode1_start_gate = af_cam_load32(FP_MODE1_START_GATE);
    s->native_ptp_inflight = af_cam_load32(FP_NATIVE_PTP_INFLIGHT);
    s->core_status = af_cam_load32(FP_CORE_STATUS);
    s->trb_pointer = af_cam_load32(FP_CTX3_TRB_POINTER);
    s->trb_bus_pointer = af_cam_load32(FP_CTX3_TRB_BUS_POINTER);
    if (s->trb_pointer == expected_trb &&
        expected_trb == FP_CTX3_TRB_CPU &&
        af_ep83_noncache_span_ok(expected_trb, 16u) == 1) {
        const volatile uint32_t *trb =
            (const volatile uint32_t *)(uintptr_t)expected_trb;
        s->trb[0] = trb[0]; s->trb[1] = trb[1];
        s->trb[2] = trb[2]; s->trb[3] = trb[3];
        s->trb_snapshot_valid = 1u;
    }
    af_cam_dmb();
#else
    (void)expected_trb;
#endif
}

void af_ep83_camera_make_synthetic(uint8_t *state, uint8_t *records,
                                   uint32_t nonce, uint32_t count) {
    if (!state || !records || !nonce || !count || count > AF_MAX_RECORDS)
        return;
    af_cam_zero(state, AF_CAPTURE_HEADER_BYTES);
    af_cam_zero(records, count * AF_RECORD_BYTES);
    af_cam_wr32(state, AF_CAPTURE_MAGIC);
    af_cam_wr32(state + 4, AF_CAPTURE_SCHEMA);
    af_cam_wr32(state + 8, AF_RECORD_BYTES);
    af_cam_wr32(state + 12, count);
    af_cam_wr32(state + 16, nonce);
    af_cam_wr32(state + 20, 0);
    af_cam_wr32(state + 24, count);
    af_cam_wr32(state + 28, 0);
    af_cam_wr32(state + 32, AF_CALLSITE);
    af_cam_wr32(state + 36, AF_PRODUCER);
    af_cam_wr32(state + 40, AF_CONTINUATION);
    af_cam_wr32(state + 44, AF_CAPTURE_HEADER_BYTES);
    af_cam_wr32(state + 48, AF_CAPTURE_LEVEL_RECORD);
    af_cam_wr32(state + 52, count);   /* hits: one producer return per record */
    af_cam_wr32(state + 56, 0);       /* no body running */
    af_cam_wr32(state + 60, 0);       /* never re-entered */
    for (uint32_t i = 0; i < count; ++i) {
        uint8_t *record = records + i * AF_RECORD_BYTES;
        uint32_t sequence = i + 1u;
        af_cam_wr32(record + 4, nonce);
        af_cam_wr32(record + 8, sequence);
        af_cam_wr32(record + 12, AF_EP83_CAMERA_STATE_SYNTHETIC);
        af_cam_wr32(record + 124, ~sequence);
        af_cam_dmb();
        af_cam_wr32(record, sequence);
    }
    af_cam_dmb();
    af_cam_wr32(state + 28, 1);
    af_cam_dmb();
}

static void af_cam_terminal(uint8_t terminal[64], uint32_t sequence,
                            uint32_t nonce, uint32_t count,
                            const struct af_tx_result *result) {
    af_cam_zero(terminal, AF_EP83_FPSH_FRAME_BYTES);
    af_cam_wr32(terminal, AF_EP83_FPSH_MAGIC);
    terminal[4] = AF_EP83_FPSH_VERSION;
    terminal[5] = AF_EP83_FPSH_COMMAND;
    af_cam_wr16(terminal + 6, 0);
    af_cam_wr32(terminal + 8, sequence);
    af_cam_wr16(terminal + 12, AF_EP83_TERMINAL_BYTES);
    af_cam_wr16(terminal + 14, 0);
    af_cam_wr32(terminal + 20, AF_EP83_TERMINAL_MAGIC);
    af_cam_wr16(terminal + 24, 1);
    af_cam_wr16(terminal + 26, AF_EP83_TERMINAL_BYTES);
    af_cam_wr32(terminal + 28, nonce);
    af_cam_wr32(terminal + 32, count);
    af_cam_wr32(terminal + 36, result->batch_bytes);
    af_cam_wr32(terminal + 40, result->batch_crc);
    af_cam_wr32(terminal + 44, result->phase);
    af_cam_wr32(terminal + 48, AF_EP83_CAMERA_STATE_SYNTHETIC);
    af_cam_wr32(terminal + 52, (uint32_t)result->error);
    af_cam_wr32(terminal + 56, (uint32_t)result->platform_rc);
    uint32_t flags = 0;
    if (result->dma_reclaimable) flags |= AF_EP83_TERMINAL_DMA_RECLAIMABLE;
    if (result->dma_may_be_owned) flags |= AF_EP83_TERMINAL_DMA_MAY_BE_OWNED;
    af_cam_wr32(terminal + 60, flags);
    af_cam_wr32(terminal + 16, af_crc32(terminal, AF_EP83_FPSH_FRAME_BYTES));
}

static int32_t af_cam_reject(uint8_t terminal[64], uint32_t sequence,
                             uint32_t nonce, uint32_t count, int32_t error,
                             uint32_t phase) {
    struct af_tx_result result;
    af_cam_zero(&result, (uint32_t)sizeof(result));
    result.phase = phase;
    result.nonce = nonce;
    result.error = error;
    af_cam_terminal(terminal, sequence, nonce, count, &result);
    return error;
}

int32_t af_ep83_camera_preflight(void *opaque,
                                const struct af_tx_request *request) {
    struct af_ep83_camera_runtime *r =
        (struct af_ep83_camera_runtime *)opaque;
    if (!r || request != r->request || !af_cam_live_epochs_ok(r) ||
        af_ep83_build_identity_ok() != 1 ||
        af_ep83_memory_ok(r->config.expected_pool_base) != 1 ||
        af_ep83_noncache_span_ok(r->config.expected_trb, 16u) != 1) return 0;
    struct af_ep83_camera_snapshot snapshot;
    af_cam_snapshot(&snapshot, r->config.expected_trb);
    return af_ep83_camera_snapshot_ok(&r->config, r->evidence, request,
                                      &snapshot);
}

int32_t af_ep83_camera_publish(void *opaque, uint8_t *dma, uint32_t bytes) {
    struct af_ep83_camera_runtime *r =
        (struct af_ep83_camera_runtime *)opaque;
    if (!r || !af_cam_live_epochs_ok(r) || dma != r->request->dma_cpu ||
        bytes != af_cam_total_bytes(r->config.expected_count) ||
        bytes > r->config.dma_capacity ||
        af_cam_rd32(dma) != AF_BATCH_MAGIC ||
        af_cam_rd32(dma + 12) != r->config.armed_nonce ||
        af_cam_rd32(dma + 16) != r->config.expected_count) return 0;
    af_cam_dsb();
    return 1;
}

int32_t af_ep83_camera_native_start(void *opaque) {
    struct af_ep83_camera_runtime *r =
        (struct af_ep83_camera_runtime *)opaque;
    if (!r || r->owned_trb != FP_CTX3_TRB_CPU ||
        !r->requested_bytes || r->reference != r->config.armed_nonce)
        return AF_EP83_CAMERA_E_BINDING;
#if defined(__arm__)
    typedef int32_t (*fp_start_fn)(uint32_t);
    return ((fp_start_fn)(uintptr_t)FP_NATIVE_START_THUMB)(7u);
#else
    return AF_EP83_CAMERA_E_BINDING;
#endif
}

int32_t af_ep83_camera_start(void *opaque, uint32_t physical_ep,
                             uint32_t bus, uint32_t bytes) {
    struct af_ep83_camera_runtime *r =
        (struct af_ep83_camera_runtime *)opaque;
    if (!r || !af_cam_live_epochs_ok(r) || physical_ep != 7u ||
        bus != r->config.dma_bus ||
        bytes != af_cam_total_bytes(r->config.expected_count) ||
        !r->result || r->result->phase != AF_TX_IN_FLIGHT ||
        r->result->nonce != r->config.armed_nonce ||
        r->wait_state.phase != AF_EP83_WAIT_FRESH || r->owned_trb ||
        r->requested_bytes || r->reference) return AF_EP83_CAMERA_E_BINDING;

    struct af_ep83_camera_snapshot snapshot;
    af_cam_snapshot(&snapshot, r->config.expected_trb);
    if (af_ep83_camera_snapshot_ok(&r->config, r->evidence, r->request,
                                   &snapshot) != 1)
        return AF_EP83_CAMERA_E_BINDING;

    r->owned_trb = r->config.expected_trb;
    r->requested_bytes = bytes;
    r->reference = r->config.armed_nonce;
    volatile uint32_t *trb =
        (volatile uint32_t *)(uintptr_t)r->owned_trb;
    trb[0] = bus;
    trb[1] = 0;
    trb[2] = bytes;
    af_cam_dsb();
    trb[3] = FP_TRB_ARMED_CONTROL;
    af_cam_dsb();
    return af_ep83_wait_start(&r->wait_state, &r->wait_ops, r->reference,
                              r->native_start, r);
}

int32_t af_ep83_camera_wait(void *opaque, uint32_t logical_ep,
                            uint32_t timeout_ms) {
    struct af_ep83_camera_runtime *r =
        (struct af_ep83_camera_runtime *)opaque;
    if (!r) return AF_EP83_CAMERA_E_BINDING;
    if (!af_cam_live_epochs_ok(r) || logical_ep != 3u ||
        timeout_ms != r->config.wait_ms ||
        r->wait_state.phase != AF_EP83_WAIT_ARMED) {
        if (r->wait_state.phase == AF_EP83_WAIT_ARMED)
            (void)af_ep83_wait_once(&r->wait_state, &r->wait_ops, 0, 1u);
        r->wait_rc = AF_EP83_CAMERA_E_BINDING;
        return AF_EP83_CAMERA_E_BINDING;
    }
    r->wait_rc = af_ep83_wait_once(&r->wait_state, &r->wait_ops,
                                    r->reference, timeout_ms);
    return r->wait_rc;
}

static int32_t af_cam_completion_guards(
        const struct af_ep83_camera_runtime *r,
        const struct af_ep83_camera_snapshot *s) {
    return af_cam_fixed_guards_ok(&r->config, s) &&
        r->evidence->phase == AF_EP83_CAMERA_RUNNING &&
        r->evidence->consumed_nonce == r->config.armed_nonce &&
        r->evidence->owner_epoch == r->config.owner_epoch &&
        r->evidence->mapping_epoch == r->config.mapping_epoch;
}

int32_t af_ep83_camera_completion(void *opaque, uint32_t nonce,
                                  uint32_t bytes) {
    struct af_ep83_camera_runtime *r =
        (struct af_ep83_camera_runtime *)opaque;
    if (!r || !af_cam_live_epochs_ok(r) ||
        nonce != r->config.armed_nonce || bytes != r->requested_bytes ||
        r->reference != nonce || r->wait_rc != 0 ||
        r->wait_state.phase != AF_EP83_WAIT_EVENT ||
        !af_cam_receipt_zero(&r->receipt) ||
        af_ep83_memory_ok(r->config.expected_pool_base) != 1 ||
        af_ep83_noncache_span_ok(r->config.expected_trb, 16u) != 1)
        return 0;
    struct af_ep83_camera_snapshot snapshot;
    af_cam_snapshot(&snapshot, r->config.expected_trb);
    if (!af_cam_completion_guards(r, &snapshot)) return 0;
    r->receipt.wait_rc = r->wait_rc;
    r->receipt.active = snapshot.active;
    r->receipt.owned_trb = r->owned_trb;
    r->receipt.current_trb = snapshot.trb_pointer;
    r->receipt.expected_bus = r->config.dma_bus;
    r->receipt.requested_bytes = r->requested_bytes;
    r->receipt.word0 = snapshot.trb[0];
    r->receipt.word1 = snapshot.trb[1];
    r->receipt.word2 = snapshot.trb[2];
    r->receipt.word3 = snapshot.trb[3];
    return af_ep83_completion_ok(&r->receipt);
}

static void af_cam_copy_evidence(struct af_ep83_camera_private *p,
                                 const struct af_tx_result *result,
                                 const struct af_ep83_camera_runtime *r,
                                 int32_t rc) {
    p->result.phase = result->phase;
    p->result.nonce = result->nonce;
    p->result.batch_bytes = result->batch_bytes;
    p->result.batch_crc = result->batch_crc;
    p->result.error = result->error;
    p->result.platform_rc = result->platform_rc;
    p->result.dma_may_be_owned = result->dma_may_be_owned;
    p->result.dma_reclaimable = result->dma_reclaimable;
    p->wait_state.phase = r->wait_state.phase;
    p->wait_state.reference = r->wait_state.reference;
    p->wait_state.observed = r->wait_state.observed;
    p->wait_state.kernel_rc = r->wait_state.kernel_rc;
    p->wait_state.quarantine = r->wait_state.quarantine;
    p->receipt.wait_rc = r->receipt.wait_rc;
    p->receipt.active = r->receipt.active;
    p->receipt.owned_trb = r->receipt.owned_trb;
    p->receipt.current_trb = r->receipt.current_trb;
    p->receipt.expected_bus = r->receipt.expected_bus;
    p->receipt.requested_bytes = r->receipt.requested_bytes;
    p->receipt.word0 = r->receipt.word0;
    p->receipt.word1 = r->receipt.word1;
    p->receipt.word2 = r->receipt.word2;
    p->receipt.word3 = r->receipt.word3;
    p->owned_trb = r->owned_trb;
    p->requested_bytes = r->requested_bytes;
    p->reference = r->reference;
    p->wait_rc = r->wait_rc;
    p->last_error = rc;
    if (result->phase == AF_TX_COMPLETE && rc == AF_TX_OK)
        p->phase = AF_EP83_CAMERA_COMPLETE;
    else if (result->phase == AF_TX_QUARANTINED || result->dma_may_be_owned)
        p->phase = AF_EP83_CAMERA_QUARANTINED;
    else
        p->phase = AF_EP83_CAMERA_REJECTED;
    af_cam_dsb();
}

int32_t af_ep83_camera_entry(const uint8_t frame[64], uint8_t terminal[64],
                            uint32_t runtime_pool,
                            struct af_ep83_camera_config *live_config) {
    uint32_t sequence = 0, nonce = 0, count = 0;
    if (!frame || !terminal ||
        af_ep83_camera_validate_trigger(frame, &sequence, &nonce, &count) != 1)
        return AF_EP83_CAMERA_E_WIRE;

    _Alignas(8) struct af_ep83_camera_runtime runtime;
    af_cam_zero(&runtime, (uint32_t)sizeof(runtime));
    if (runtime_pool > UINT32_MAX - AF_EP83_POOL_WINDOW_END || !live_config ||
        runtime_pool < 0x40000000u ||
        runtime_pool > 0x80000000u - AF_EP83_POOL_WINDOW_END ||
        (runtime_pool & 0x1FFu) ||
        (uintptr_t)live_config !=
            (uintptr_t)(runtime_pool + AF_EP83_POOL_CONFIG_OFFSET) ||
        af_ep83_build_identity_ok() != 1 ||
        af_ep83_memory_ok(runtime_pool) != 1)
        return af_cam_reject(terminal, sequence, nonce, count,
                             AF_EP83_CAMERA_E_CONFIG, AF_TX_REJECTED);
    af_cam_copy(&runtime.config, live_config,
                (uint32_t)sizeof(runtime.config));
    runtime.live_config = live_config;
    if (!af_cam_config_ok(runtime_pool, &runtime.config, live_config) ||
        runtime.config.armed_nonce != nonce ||
        runtime.config.expected_count != count)
        return af_cam_reject(terminal, sequence, nonce, count,
                             AF_EP83_CAMERA_E_CONFIG, AF_TX_REJECTED);

    struct af_ep83_camera_private *private_state =
        (struct af_ep83_camera_private *)(uintptr_t)runtime.config.private_addr;
    if (!af_cam_private_fresh(private_state, &runtime.config))
        return af_cam_reject(terminal, sequence, nonce, count,
                             AF_EP83_CAMERA_E_REUSE, AF_TX_QUARANTINED);

    /* This persistent consume marker precedes every state/record/DMA/TRB
     * mutation.  A reset or interrupted attempt therefore cannot be retried by
     * merely presenting the same armed config again.
     */
    private_state->consumed_nonce = nonce;
    af_cam_dsb();
    private_state->phase = AF_EP83_CAMERA_RUNNING;
    af_cam_dsb();
    runtime.evidence = private_state;

    uint8_t *state = (uint8_t *)(uintptr_t)runtime.config.state_addr;
    uint8_t *records = (uint8_t *)(uintptr_t)runtime.config.records_addr;
    af_ep83_camera_make_synthetic(state, records, nonce, count);

    _Alignas(8) struct af_tx_request request;
    request.state = state;
    request.records = records;
    request.dma_cpu = (uint8_t *)(uintptr_t)runtime.config.dma_cpu;
    request.records_bytes = count * AF_RECORD_BYTES;
    request.dma_capacity = runtime.config.dma_capacity;
    request.dma_bus = runtime.config.dma_bus;
    request.nonce = nonce;
    request.wait_ms = runtime.config.wait_ms;

    _Alignas(8) struct af_tx_result result;
    af_cam_zero(&result, (uint32_t)sizeof(result));
    _Alignas(8) struct af_tx_ops ops;
    af_cam_zero(&ops, (uint32_t)sizeof(ops));
    runtime.request = &request;
    runtime.result = &result;
    uint32_t base = runtime.config.code_base;
    ops.ctx = &runtime;
    ops.preflight = (int32_t (*)(void *, const struct af_tx_request *))
        (uintptr_t)(base + runtime.config.offsets.sender_preflight);
    ops.publish = (int32_t (*)(void *, uint8_t *, uint32_t))
        (uintptr_t)(base + runtime.config.offsets.sender_publish);
    ops.start = (int32_t (*)(void *, uint32_t, uint32_t, uint32_t))
        (uintptr_t)(base + runtime.config.offsets.sender_start);
    ops.wait = (int32_t (*)(void *, uint32_t, uint32_t))
        (uintptr_t)(base + runtime.config.offsets.sender_wait);
    ops.completion = (int32_t (*)(void *, uint32_t, uint32_t))
        (uintptr_t)(base + runtime.config.offsets.sender_completion);
    runtime.native_start = (af_ep83_native_start_fn)(uintptr_t)
        (base + runtime.config.offsets.native_start);
    runtime.wait_ops.ctx = &runtime;
    runtime.wait_ops.clear_flags =
        (int32_t (*)(void *, uint32_t))(uintptr_t)
        (base + runtime.config.offsets.wait_clear_flags);
    runtime.wait_ops.critical_enter =
        (uint32_t (*)(void *))(uintptr_t)
        (base + runtime.config.offsets.wait_critical_enter);
    runtime.wait_ops.critical_exit =
        (void (*)(void *, uint32_t))(uintptr_t)
        (base + runtime.config.offsets.wait_critical_exit);
    runtime.wait_ops.interest_load =
        (uint32_t (*)(void *))(uintptr_t)
        (base + runtime.config.offsets.wait_interest_load);
    runtime.wait_ops.interest_store =
        (void (*)(void *, uint32_t))(uintptr_t)
        (base + runtime.config.offsets.wait_interest_store);
    runtime.wait_ops.irq_reenable =
        (void (*)(void *))(uintptr_t)
        (base + runtime.config.offsets.wait_irq_reenable);
    runtime.wait_ops.wait_flags =
        (int32_t (*)(void *, uint32_t, uint32_t, uint32_t *, uint32_t))
        (uintptr_t)(base + runtime.config.offsets.wait_flags);

    int32_t rc = af_tx_send(&request, &result, &ops);
    if (rc != AF_TX_OK && result.phase == AF_TX_FRESH) {
        result.phase = AF_TX_REJECTED;
        result.nonce = nonce;
        result.error = rc;
    }
    af_cam_copy_evidence(private_state, &result, &runtime, rc);
    af_cam_terminal(terminal, sequence, nonce, count, &result);
    return rc;
}
