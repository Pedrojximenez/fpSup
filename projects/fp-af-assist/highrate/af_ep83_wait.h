#ifndef FP_AF_EP83_WAIT_H
#define FP_AF_EP83_WAIT_H

#include <stdint.h>

#define AF_EP83_COMPLETE_BIT 0x00100000u
#define AF_EP83_NOT_READY_BIT 0x00000100u
#define AF_EP83_LOCAL_WAIT_MASK (AF_EP83_COMPLETE_BIT | AF_EP83_NOT_READY_BIT)
#define AF_EP83_TWF_ORW_BITCLR 0x21u

enum af_ep83_wait_phase {
    AF_EP83_WAIT_FRESH = 0,
    AF_EP83_WAIT_ARMED = 1,
    AF_EP83_WAIT_EVENT = 2,
    AF_EP83_WAIT_FAULT = 3,
};

enum af_ep83_wait_error {
    AF_EP83_WAIT_E_ARGS = -101,
    AF_EP83_WAIT_E_BUSY = -102,
    AF_EP83_WAIT_E_EVENT = -103,
    AF_EP83_WAIT_E_REFERENCE = -104,
};

struct af_ep83_wait_state {
    uint32_t phase;
    uint32_t reference;
    uint32_t observed;
    int32_t kernel_rc;
    uint32_t quarantine;
};

typedef int32_t (*af_ep83_native_start_fn)(void *);

/* All callbacks are task-context only.  interest_load/store execute between
 * critical_enter/critical_exit and must only access the shared waiter mask.
 */
struct af_ep83_wait_ops {
    void *ctx;
    int32_t (*clear_flags)(void *, uint32_t keep_mask);
    uint32_t (*critical_enter)(void *);
    void (*critical_exit)(void *, uint32_t token);
    uint32_t (*interest_load)(void *);
    void (*interest_store)(void *, uint32_t value);
    void (*irq_reenable)(void *);
    int32_t (*wait_flags)(void *, uint32_t mask, uint32_t mode,
                          uint32_t *observed, uint32_t timeout_ms);
};

/* Claim EP83's local completion/not-ready bits before issuing Start.  This is
 * intentionally combined with native_start so a completion cannot be lost in
 * the gap between Start and waiter registration.  TRB publication precedes
 * this call and remains the adapter's responsibility.
 */
int32_t af_ep83_wait_start(struct af_ep83_wait_state *,
                          const struct af_ep83_wait_ops *, uint32_t reference,
                          af_ep83_native_start_fn native_start, void *start_ctx);

/* One bounded kernel wait.  A zero return proves only that the real completion
 * bit won; the caller must still run af_ep83_completion_ok on one owned TRB
 * snapshot.  Every nonzero result requires upper-layer DMA quarantine.
 */
int32_t af_ep83_wait_once(struct af_ep83_wait_state *,
                         const struct af_ep83_wait_ops *, uint32_t reference,
                         uint32_t timeout_ms);

#if defined(__arm__) && defined(AF_EP83_ENABLE_FIXED_BINDING)
/* Fixed fp 5.02 event-flag binding only.  It neither writes a TRB nor calls
 * Start/End/C01E7780.  The build must still prove the boot patch and owner.
 * These callbacks are exported so a relocatable adapter can fill its ops
 * table with code_base + symbol_offset at runtime.  Defining
 * AF_EP83_OMIT_FIXED_OPS_FACTORY suppresses the absolute-pointer table.
 */
int32_t af_ep83_fixed_clear(void *, uint32_t keep_mask);
uint32_t af_ep83_fixed_enter(void *);
void af_ep83_fixed_exit(void *, uint32_t token);
uint32_t af_ep83_fixed_interest_load(void *);
void af_ep83_fixed_interest_store(void *, uint32_t value);
void af_ep83_fixed_irq_reenable(void *);
int32_t af_ep83_fixed_wait(void *, uint32_t mask, uint32_t mode,
                           uint32_t *observed, uint32_t timeout_ms);
#if !defined(AF_EP83_OMIT_FIXED_OPS_FACTORY)
const struct af_ep83_wait_ops *af_ep83_fixed_wait_ops(void);
#endif
#endif

#endif
