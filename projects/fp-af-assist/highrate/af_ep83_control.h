#ifndef FP_AF_EP83_CONTROL_H
#define FP_AF_EP83_CONTROL_H
#include "af_ep83_camera.h"

#define AF_EP83_CONTROL_OFFSET 0x64a00u
#define AF_EP83_CONTROL_MAGIC 0x314e4641u /* AFN1 */

/* Cold-boot initialized, retained through the entire boot. Not stack storage:
 * the terminal may remain DMA-owned after its only Start. No retry or free.
 */
struct af_ep83_control_state {
    uint32_t magic, schema, phase;
    int32_t read_rc, camera_rc, terminal_start_rc;
    uint32_t terminal_trb, terminal_bus;
    uint32_t reserved[24];
    uint8_t frame[64], terminal[64];
};

struct af_ep83_control_snapshot {
    uint32_t mode, pending, out_armed, out_active, out_bytes;
    uint32_t partial_mode, partial_offset, bulk_gate, usb_state;
    uint32_t shadow_enabled, hardware_enabled, out_mps;
    uint32_t out_mode, out_direction, out_endpoint;
    uint32_t in_mode, in_direction, in_endpoint;
    uint32_t out_buffer, out_trb_pointer, out_trb_bus;
    uint32_t trb_word0, trb_word1, trb_word2, trb_word3;
};

int32_t af_ep83_control_snapshot_ok(const struct af_ep83_control_snapshot *);

/* Candidate native mode-5 callsite ABI: mode in r0; a small near veneer supplies
 * runtime pool in r1 and config in r2. Only native usbTask may call this entry.
 * This is NOT a second USB worker and does not run the original PTP parser.
 * The caller's dedicated boot image must exclude legacy workers and other
 * high-level bulk producers; this module cannot establish that by inspection.
 */
int32_t af_ep83_control_entry(uint32_t mode, uint32_t runtime_pool,
                             struct af_ep83_camera_config *);

_Static_assert(sizeof(struct af_ep83_control_state) == 256, "control state ABI");
#endif
