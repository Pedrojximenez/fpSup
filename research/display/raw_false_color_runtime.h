#ifndef SIGMA_FP_RAW_FALSE_COLOR_RUNTIME_H
#define SIGMA_FP_RAW_FALSE_COLOR_RUNTIME_H

#include <stdint.h>

/*
 * Single-producer/single-consumer mailbox for the movie RAW completion path.
 * The completion callback only publishes metadata. The analysis worker may
 * drop an older frame; it must never make the SigProcess callback wait.
 */
struct rfc_frame_mailbox {
    volatile uint32_t sequence;
    volatile uintptr_t raw_address;
    volatile uint32_t descriptor_address;
};

struct rfc_frame_snapshot {
    uint32_t sequence;
    uintptr_t raw_address;
    uint32_t descriptor_address;
};

void rfc_mailbox_publish(struct rfc_frame_mailbox *mailbox,
                         uintptr_t raw_address, uint32_t descriptor_address);
int rfc_mailbox_take_latest(const struct rfc_frame_mailbox *mailbox,
                            uint32_t *last_sequence,
                            struct rfc_frame_snapshot *snapshot);

#endif
