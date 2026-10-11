/* Offline candidate native-task CMD4 adapter, no independent endpoint loop.
 * Boot integration/other bulk-writer exclusion remain mandatory external
 * obligations. Configuration files alone cannot make this deployable.
 */
#include "af_ep83_control.h"
#include "af_ep83_memory.h"

int32_t af_ep83_control_snapshot_ok(const struct af_ep83_control_snapshot *s) {
    return s && s->mode == 5 && s->pending == 1 && s->out_armed == 0 &&
        s->out_active == 0 && s->out_bytes == 64 && s->partial_mode == 0 &&
        s->partial_offset == 0 && s->bulk_gate == 0 && s->usb_state != 4 &&
        (s->shadow_enabled & 0xa4u) == 0xa4u &&
        s->hardware_enabled == s->shadow_enabled &&
        (s->out_mps == 64 || s->out_mps == 512 || s->out_mps == 1024) &&
        s->out_mode == 1 && s->out_direction == 0 && s->out_endpoint == 1 &&
        s->in_mode == 1 && s->in_direction == 1 && s->in_endpoint == 2 &&
        s->out_buffer == 0x442f71c0u && s->out_trb_pointer == 0x431e32d0u &&
        s->out_trb_bus == 0x031e32d0u && s->trb_word0 == 0x042f71c0u &&
        s->trb_word1 == 0 && s->trb_word2 == s->out_mps - 64u &&
        s->trb_word3 == 0x812u;
}

#if defined(__arm__)
static uint32_t control_read(uint32_t address) {
    return *(const volatile uint32_t *)(uintptr_t)address;
}

static int32_t control_pending_ok(uint32_t mode) {
    struct af_ep83_control_snapshot s;
    s.mode = mode;
    s.pending = control_read(0xc31e3a08u);
    s.out_armed = control_read(0xc31e3974u);
    s.out_active = control_read(0xc31e3914u);
    s.out_bytes = control_read(0xc31e3a68u);
    s.partial_mode = control_read(0xc31e39fcu);
    s.partial_offset = control_read(0xc31e3a00u);
    s.bulk_gate = control_read(0xc31e38fcu);
    s.usb_state = control_read(0xc31e3748u);
    s.shadow_enabled = control_read(0xc31e398cu);
    s.hardware_enabled = control_read(0x2100c720u);
    s.out_mode = control_read(0xc31e3898u);
    s.out_direction = control_read(0xc31e389cu);
    s.out_endpoint = control_read(0xc31e38a0u);
    s.in_mode = control_read(0xc31e38a8u);
    s.in_direction = control_read(0xc31e38acu);
    s.in_endpoint = control_read(0xc31e38b0u);
    s.out_buffer = control_read(0xc3025744u);
    s.out_trb_pointer = control_read(0xc31e3268u);
    s.out_trb_bus = control_read(0xc31e323cu);
    if (s.out_buffer != 0x442f71c0u || s.out_trb_pointer != 0x431e32d0u ||
        !af_ep83_noncache_span_ok(s.out_buffer, 1024) ||
        !af_ep83_noncache_span_ok(s.out_trb_pointer, 16)) return 0;
    s.trb_word0 = control_read(s.out_trb_pointer);
    s.trb_word1 = control_read(s.out_trb_pointer + 4);
    s.trb_word2 = control_read(s.out_trb_pointer + 8);
    s.trb_word3 = control_read(s.out_trb_pointer + 12);
    /* Native getter selects the configured MPS; no parameter-changing ioctl. */
    s.out_mps = ((uint32_t (*)(uint32_t))(uintptr_t)0xc01e6099u)(1);
    return af_ep83_control_snapshot_ok(&s);
}

static int32_t control_terminal(struct af_ep83_control_state *state,
                                 uint32_t pool) {
    /* Only after exact EP83 completion. The terminal has its own persistent
     * 64-byte noncached source. There is no Wait2 (and hence no C01E7780), End,
     * global recovery, or buffer release here. Host receipt closes the trial;
     * neither this Start's return nor closing a host handle proves DMA idle.
     */
    if (!af_ep83_memory_ok(pool) || control_read(0xc31e38fcu) != 0 ||
        control_read(0xc31e3918u) != 0 || control_read(0xc31e3748u) == 4 ||
        control_read(0xc31e398cu) != control_read(0x2100c720u) ||
        !(control_read(0x2100c720u) & 0x20u)) return -301;
    uint32_t address = control_read(0xc31e326cu);
    /* C01 USB init derives these exact values from logical2's C31E32E0
     * backing storage; check both pointer slots AND actual noncached mapping.
     */
    if (address != 0x431e32e0u || control_read(0xc31e3240u) != 0x031e32e0u ||
        !af_ep83_noncache_span_ok(address, 16)) return -302;
    volatile uint32_t *trb = (volatile uint32_t *)(uintptr_t)address;
    if (trb[3] & 1u) return -303;
    uint32_t cpu = (uint32_t)(uintptr_t)state->terminal;
    state->terminal_trb = address;
    state->terminal_bus = cpu - 0x40000000u;
    state->phase = 4; /* ownership uncertain BEFORE the first endpoint write */
    __asm__ volatile("dsb sy" ::: "memory");
    trb[0] = state->terminal_bus;
    trb[1] = 0;
    trb[2] = 64;
    trb[3] = 0x813u;
    __asm__ volatile("dsb sy" ::: "memory");
    return ((int32_t (*)(uint32_t))(uintptr_t)0xc01e6b81u)(5);
}
#endif

int32_t af_ep83_control_entry(uint32_t mode, uint32_t pool,
                             struct af_ep83_camera_config *cfg) {
#if defined(__arm__)
    if (mode != 5 || !af_ep83_build_identity_ok() || !af_ep83_memory_ok(pool) ||
        (uintptr_t)cfg != pool + AF_EP83_POOL_CONFIG_OFFSET ||
        cfg->expected_pool_base != pool || cfg->magic != AF_EP83_CAMERA_CONFIG_MAGIC ||
        !cfg->owner_epoch || !cfg->mapping_epoch || !cfg->armed_nonce) return -304;
    struct af_ep83_control_state *state =
        (struct af_ep83_control_state *)(uintptr_t)(pool + AF_EP83_CONTROL_OFFSET);
    if (state->magic != AF_EP83_CONTROL_MAGIC || state->schema != 1 || state->phase)
        return -305;
    state->phase = 1; /* one invocation, including rejected/malformed input */
    if (!control_pending_ok(mode)) {
        state->phase = 3;
        return -306;
    }
    /* Native C01E4ED0: with pending=1, offset=0 and exact cached count=64,
     * C01E7080 skips its arm/wait path; the already-completed packet is copied
     * once and native pending/offset bookkeeping is consumed. No partial mode
     * ioctl, PTP length parsing, old worker, or arbitrary shell command.
     * This remains contingent on single native task ownership across the call.
     */
    state->read_rc = ((int32_t (*)(uint32_t, void *, uint32_t, uint32_t))
        (uintptr_t)0xc00337c8u)(5, state->frame, 64, 200);
    if (state->read_rc != 64) {
        state->phase = 3;
        return -307;
    }
    state->camera_rc = af_ep83_camera_entry(state->frame, state->terminal, pool, cfg);
    if (state->camera_rc != 0) {
        state->phase = 3;
        return state->camera_rc; /* no speculative EP82 send on an EP83 fault */
    }
    state->terminal_start_rc = control_terminal(state, pool);
    if (state->terminal_start_rc == 0) state->phase = 2; /* submitted, NOT delivered */
    return state->terminal_start_rc;
#else
    (void)mode; (void)pool; (void)cfg;
    return -308;
#endif
}
