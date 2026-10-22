/* EP83 one-shot event wait.  No heap, EndTransfer, C01E7780 or endpoint re-arm. */
#include "af_ep83_wait.h"

#include <stddef.h>

#define MAX_WAIT_MS 2000u

static int valid_ops(const struct af_ep83_wait_ops *o) {
    return o && o->clear_flags && o->critical_enter && o->critical_exit &&
        o->interest_load && o->interest_store && o->irq_reenable && o->wait_flags;
}

static int32_t claim_interest(const struct af_ep83_wait_ops *o) {
    uint32_t token = o->critical_enter(o->ctx);
    uint32_t value = o->interest_load(o->ctx);
    if (value & AF_EP83_LOCAL_WAIT_MASK) {
        o->critical_exit(o->ctx, token);
        return AF_EP83_WAIT_E_BUSY;
    }
    o->interest_store(o->ctx, value | AF_EP83_LOCAL_WAIT_MASK);
    o->critical_exit(o->ctx, token);
    return 0;
}

static void release_interest(const struct af_ep83_wait_ops *o) {
    uint32_t token = o->critical_enter(o->ctx);
    uint32_t value = o->interest_load(o->ctx);
    o->interest_store(o->ctx, value & ~AF_EP83_LOCAL_WAIT_MASK);
    o->critical_exit(o->ctx, token);
    /* C01E3660 deliberately leaves IRQ 0x34 masked while an interested waiter
     * owns the delivered bit.  This mirrors C01E71E0's final C01E5E78 call.
     */
    o->irq_reenable(o->ctx);
}

static int32_t fault(struct af_ep83_wait_state *s, int32_t rc) {
    s->phase = AF_EP83_WAIT_FAULT;
    s->kernel_rc = rc;
    s->quarantine = 1;
    return rc;
}

int32_t af_ep83_wait_start(struct af_ep83_wait_state *s,
                          const struct af_ep83_wait_ops *o, uint32_t reference,
                          af_ep83_native_start_fn native_start, void *start_ctx) {
    if (!s || !valid_ops(o) || !native_start || !reference ||
        s->phase != AF_EP83_WAIT_FRESH)
        return AF_EP83_WAIT_E_ARGS;
    s->reference = reference;
    s->observed = 0;
    s->kernel_rc = 0;
    s->quarantine = 0;

    int32_t rc = claim_interest(o);
    if (rc != 0) return fault(s, rc);

    /* tk_clr_flg(id, keep_mask): remove only stale EP83 local events.  Global
     * reset/device bits and every other endpoint event remain untouched.
     */
    rc = o->clear_flags(o->ctx, ~AF_EP83_LOCAL_WAIT_MASK);
    if (rc != 0) {
        release_interest(o);
        return fault(s, rc);
    }
    o->irq_reenable(o->ctx);

    rc = native_start(start_ctx);
    if (rc != 0) {
        /* Start failure is still an uncertain transfer outcome.  Dropping our
         * waiter interest is not DMA reclamation; upper layers quarantine it.
         */
        release_interest(o);
        return fault(s, rc);
    }
    s->phase = AF_EP83_WAIT_ARMED;
    return 0;
}

int32_t af_ep83_wait_once(struct af_ep83_wait_state *s,
                         const struct af_ep83_wait_ops *o, uint32_t reference,
                         uint32_t timeout_ms) {
    if (!s || !valid_ops(o)) return AF_EP83_WAIT_E_ARGS;
    if (s->phase != AF_EP83_WAIT_ARMED || !reference ||
        reference != s->reference) {
        if (s->phase == AF_EP83_WAIT_ARMED) release_interest(o);
        return fault(s, AF_EP83_WAIT_E_REFERENCE);
    }
    if (!timeout_ms || timeout_ms > MAX_WAIT_MS) {
        release_interest(o);
        return fault(s, AF_EP83_WAIT_E_ARGS);
    }

    uint32_t observed = 0;
    int32_t rc = o->wait_flags(o->ctx, AF_EP83_LOCAL_WAIT_MASK,
                               AF_EP83_TWF_ORW_BITCLR, &observed, timeout_ms);
    s->observed = observed;
    release_interest(o);
    if (rc != 0) return fault(s, rc);

    /* p_flgptn may contain unrelated shared-object bits.  BITCLR consumes only
     * our wait mask, so classify only our two bits.  NotReady, or Complete and
     * NotReady together, is an unknown/fault outcome and never success.
     */
    if ((observed & AF_EP83_LOCAL_WAIT_MASK) != AF_EP83_COMPLETE_BIT)
        return fault(s, AF_EP83_WAIT_E_EVENT);
    s->phase = AF_EP83_WAIT_EVENT;
    s->kernel_rc = 0;
    return 0;
}

#if defined(__arm__) && defined(AF_EP83_ENABLE_FIXED_BINDING)

#define FP_EVENT_FLAG_ID (*(volatile int32_t *)(uintptr_t)0xC31E3210u)
#define FP_USB_WAIT_INTEREST (*(volatile uint32_t *)(uintptr_t)0xC31E3884u)

typedef int32_t (*fp_clear_flag_fn)(int32_t, uint32_t);
typedef int32_t (*fp_wait_flag_fn)(int32_t, uint32_t, uint32_t,
                                   uint32_t *, uint32_t);
typedef uint32_t (*fp_irq_save_fn)(void);
typedef void (*fp_irq_restore_fn)(uint32_t);
typedef void (*fp_usb_irq_enable_fn)(void);

int32_t af_ep83_fixed_clear(void *ctx, uint32_t keep_mask) {
    (void)ctx;
    int32_t id = FP_EVENT_FLAG_ID;
    if (id < 1) return AF_EP83_WAIT_E_ARGS;
    return ((fp_clear_flag_fn)(uintptr_t)0xC00169C8u)(id, keep_mask);
}
uint32_t af_ep83_fixed_enter(void *ctx) {
    (void)ctx;
    /* C000EC14 returns CPSR and masks IRQ+FIQ (I/F bits); C000EC24 restores
     * exactly those saved bits.  No syscall or blocking call occurs inside.
     */
    return ((fp_irq_save_fn)(uintptr_t)0xC000EC14u)();
}
void af_ep83_fixed_exit(void *ctx, uint32_t token) {
    (void)ctx;
    ((fp_irq_restore_fn)(uintptr_t)0xC000EC24u)(token);
}
uint32_t af_ep83_fixed_interest_load(void *ctx) {
    (void)ctx;
    return FP_USB_WAIT_INTEREST;
}
void af_ep83_fixed_interest_store(void *ctx, uint32_t value) {
    (void)ctx;
    FP_USB_WAIT_INTEREST = value;
}
void af_ep83_fixed_irq_reenable(void *ctx) {
    (void)ctx;
    ((fp_usb_irq_enable_fn)(uintptr_t)0xC01E5E79u)();
}
int32_t af_ep83_fixed_wait(void *ctx, uint32_t mask, uint32_t mode,
                           uint32_t *observed, uint32_t timeout_ms) {
    (void)ctx;
    int32_t id = FP_EVENT_FLAG_ID;
    if (id < 1) return AF_EP83_WAIT_E_ARGS;
    return ((fp_wait_flag_fn)(uintptr_t)0xC0016C08u)(
        id, mask, mode, observed, timeout_ms);
}

#if !defined(AF_EP83_OMIT_FIXED_OPS_FACTORY)
const struct af_ep83_wait_ops *af_ep83_fixed_wait_ops(void) {
    static const struct af_ep83_wait_ops ops = {
        NULL, af_ep83_fixed_clear, af_ep83_fixed_enter, af_ep83_fixed_exit,
        af_ep83_fixed_interest_load, af_ep83_fixed_interest_store,
        af_ep83_fixed_irq_reenable, af_ep83_fixed_wait
    };
    return &ops;
}
#endif

#endif
