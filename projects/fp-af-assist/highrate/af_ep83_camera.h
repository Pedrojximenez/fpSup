#ifndef FP_AF_EP83_CAMERA_H
#define FP_AF_EP83_CAMERA_H

#include <stdint.h>
#include <stddef.h>

#include "af_sender.h"
#include "af_ep83_wait.h"

#define AF_EP83_CAMERA_CONFIG_MAGIC 0x31434641u /* bytes "AFC1" */
#define AF_EP83_CAMERA_PRIVATE_MAGIC 0x31504641u /* bytes "AFP1" */
#define AF_EP83_CAMERA_SCHEMA 1u
#define AF_EP83_CAMERA_CONFIG_BYTES 256u
#define AF_EP83_CAMERA_PRIVATE_BYTES 256u

#define AF_EP83_FPSH_MAGIC 0x48535046u /* bytes "FPSH" */
#define AF_EP83_FPSH_VERSION 1u
#define AF_EP83_FPSH_COMMAND 4u
#define AF_EP83_FPSH_FRAME_BYTES 64u
#define AF_EP83_FPSH_PAYLOAD_OFFSET 20u
#define AF_EP83_TRIGGER_MAGIC 0x33384641u /* bytes "AF83" */
#define AF_EP83_TRIGGER_BYTES 32u
#define AF_EP83_TERMINAL_MAGIC 0x31544641u /* bytes "AFT1" */
#define AF_EP83_TERMINAL_BYTES 44u
#define AF_EP83_CAMERA_STATE_SYNTHETIC 0x53594E54u /* explicit u32 "SYNT" */

#define AF_EP83_POOL_CODE_OFFSET 0x50000u
#define AF_EP83_POOL_CODE_LIMIT 0x54000u
#define AF_EP83_POOL_STATE_OFFSET 0x54000u
#define AF_EP83_POOL_RECORDS_OFFSET 0x54080u
#define AF_EP83_POOL_DMA_OFFSET 0x5C400u
#define AF_EP83_POOL_CONFIG_OFFSET 0x64800u
#define AF_EP83_POOL_PRIVATE_OFFSET 0x64900u
#define AF_EP83_POOL_WINDOW_END 0x65000u
#define AF_EP83_DMA_CAPACITY 0x8080u

#define AF_EP83_TERMINAL_DMA_RECLAIMABLE 0x1u
#define AF_EP83_TERMINAL_DMA_MAY_BE_OWNED 0x2u

enum af_ep83_camera_private_phase {
    AF_EP83_CAMERA_FRESH = 0,
    AF_EP83_CAMERA_RUNNING = 1,
    AF_EP83_CAMERA_COMPLETE = 2,
    AF_EP83_CAMERA_REJECTED = 3,
    AF_EP83_CAMERA_QUARANTINED = 4,
};

enum af_ep83_camera_error {
    AF_EP83_CAMERA_E_ARGS = -201,
    AF_EP83_CAMERA_E_WIRE = -202,
    AF_EP83_CAMERA_E_CONFIG = -203,
    AF_EP83_CAMERA_E_REUSE = -204,
    AF_EP83_CAMERA_E_BINDING = -205,
};

/* Every field is an offset from code_base.  Zero is always invalid.  The
 * offline builder fills these from the final single-TU symbol table; no C
 * callback address is emitted as static data or guessed at runtime.
 */
struct af_ep83_camera_offsets {
    uint32_t sender_preflight;
    uint32_t sender_publish;
    uint32_t sender_start;
    uint32_t sender_wait;
    uint32_t sender_completion;
    uint32_t native_start;
    uint32_t wait_clear_flags;
    uint32_t wait_critical_enter;
    uint32_t wait_critical_exit;
    uint32_t wait_interest_load;
    uint32_t wait_interest_store;
    uint32_t wait_irq_reenable;
    uint32_t wait_flags;
};

/* Exact 256-byte runtime configuration at pool+0x64800.  The builder may fill
 * addresses and symbol offsets, but armed_nonce, mapping_epoch, owner_epoch,
 * expected_trb and idle TRB words remain zero in an offline image.  Only the
 * sole runtime owner may arm those fields after independent proof; a nonzero
 * cookie is a guard against accidental use, not proof by itself.
 */
struct af_ep83_camera_config {
    uint32_t magic, schema, bytes;
    uint32_t expected_pool_base, code_base, code_limit;
    uint32_t state_addr, records_addr, dma_cpu, dma_bus, dma_capacity;
    uint32_t config_addr, private_addr;
    uint32_t expected_count, wait_ms, armed_nonce;
    uint32_t mapping_epoch, owner_epoch, expected_trb;
    uint32_t expected_idle_trb[4];
    struct af_ep83_camera_offsets offsets;
    uint32_t reserved[28];
};

/* Exact 256-byte single-use evidence at pool+0x64900. */
struct af_ep83_camera_private {
    uint32_t magic, schema, bytes, phase;
    uint32_t consumed_nonce, owner_epoch, mapping_epoch;
    int32_t last_error;
    struct af_tx_result result;
    struct af_ep83_wait_state wait_state;
    struct af_ep83_receipt receipt;
    uint32_t owned_trb, requested_bytes, reference;
    int32_t wait_rc;
    uint32_t reserved[29];
};

/* Read-only preflight evidence.  The production callback captures this once
 * from the fixed fp 5.02 addresses; host tests can exercise the pure checker.
 */
struct af_ep83_camera_snapshot {
    uint32_t publication_callsite;
    uint32_t native_sender_patch;
    uint32_t ctx3_default;
    uint32_t pool_base;
    uint32_t ctx3_mode, ctx3_direction, ctx3_endpoint, ctx3_fourth;
    uint32_t usb_state;
    uint32_t dalepena_shadow, dalepena_hardware;
    uint32_t active, resource_index, wait_interest, event_flag_id;
    uint32_t irq_gate, mode1_start_gate, native_ptp_inflight, core_status;
    uint32_t trb_pointer, trb_bus_pointer, trb_snapshot_valid;
    uint32_t trb[4];
};

/* Worker ABI: one complete, already-received 64-byte FPSH CMD4 frame in;
 * exactly one complete 64-byte same-sequence terminal frame out.  No USB or
 * EP82 operation occurs here.  runtime_pool/config must name the fixed layout.
 */
int32_t af_ep83_camera_entry(const uint8_t frame[AF_EP83_FPSH_FRAME_BYTES],
                            uint8_t terminal[AF_EP83_FPSH_FRAME_BYTES],
                            uint32_t runtime_pool,
                            struct af_ep83_camera_config *config);

/* Pure helpers retained for host tests and builder verification. */
int32_t af_ep83_camera_validate_trigger(const uint8_t frame[64],
                                       uint32_t *sequence, uint32_t *nonce,
                                       uint32_t *count);
int32_t af_ep83_camera_snapshot_ok(const struct af_ep83_camera_config *,
                                  const struct af_ep83_camera_private *,
                                  const struct af_tx_request *,
                                  const struct af_ep83_camera_snapshot *);
void af_ep83_camera_make_synthetic(uint8_t *state, uint8_t *records,
                                   uint32_t nonce, uint32_t count);

/* Exported sender callbacks.  Production entry obtains their final addresses
 * only as code_base + audited symbol offsets from config.
 */
int32_t af_ep83_camera_preflight(void *, const struct af_tx_request *);
int32_t af_ep83_camera_publish(void *, uint8_t *, uint32_t);
int32_t af_ep83_camera_start(void *, uint32_t, uint32_t, uint32_t);
int32_t af_ep83_camera_wait(void *, uint32_t, uint32_t);
int32_t af_ep83_camera_completion(void *, uint32_t, uint32_t);
int32_t af_ep83_camera_native_start(void *);

_Static_assert(sizeof(struct af_ep83_camera_offsets) == 52,
               "camera offset table changed");
_Static_assert(sizeof(struct af_ep83_camera_config) == AF_EP83_CAMERA_CONFIG_BYTES,
               "camera config must be 256 bytes");
_Static_assert(sizeof(struct af_ep83_camera_private) == AF_EP83_CAMERA_PRIVATE_BYTES,
               "camera private state must be 256 bytes");

#endif
