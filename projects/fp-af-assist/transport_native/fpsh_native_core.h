#ifndef FPSH_NATIVE_CORE_H
#define FPSH_NATIVE_CORE_H

#include <stdint.h>

/* Offline candidate: no firmware addresses, USB calls, installer or motor API.
 * The eventual adapter must provide ONE complete, stable native OUT transfer.
 * A successful read(64) alone does not satisfy this contract. */
#define FPSH_FRAME_SIZE 64u
#define FPSH_PAYLOAD_SIZE 44u
#define FPSH_REPLY_CAP 128u
#define FPSH_STATE_MAGIC 0x314e5346u

enum fpsh_phase { FPSH_READY = 1, FPSH_ACTIVE = 2, FPSH_FAULTED = 3 };
enum fpsh_result {
    FPSH_OK = 0, FPSH_BAD_STATE = -1, FPSH_BOUNDARY = -2,
    FPSH_FORMAT = -3, FPSH_CRC = -4, FPSH_SEQUENCE = -5,
    FPSH_DENIED = -6, FPSH_COMMAND_FAILED = -7, FPSH_SEND_FAILED = -8,
    FPSH_INVALIDATED = -9, FPSH_REENTRANT = -10
};
enum fpsh_wire_status { FPSH_STATUS_OK = 0, FPSH_STATUS_DENIED = 1,
                        FPSH_STATUS_COMMAND_FAILED = 2 };

struct fpsh_native_state {
    uint32_t magic, phase, generation, last_sequence;
    int32_t fault;
    uint32_t version_calls, commands_completed, frames_sent;
    /* Persistent until every synchronous send returns; never DMA this cached
     * storage directly. The adapter owns copying to its verified DMA buffer. */
    uint8_t output[FPSH_REPLY_CAP];
    uint8_t reply[FPSH_FRAME_SIZE];
};

struct fpsh_native_ops {
    /* Only the fixed read-only version operation may be bound here.
     * Must be synchronous, return 0 on success, write at most cap bytes and
     * report actual length. No arbitrary shell dispatch is exposed. */
    int (*version)(void *opaque, uint8_t *out, uint32_t cap, uint32_t *length);
    /* Synchronous COMPLETE send: 0 means the buffer is no longer referenced.
     * Queue/submit success is insufficient. Failure invalidates the session;
     * the core will not resend or reuse storage on a later request. */
    int (*send_frame)(void *opaque, const uint8_t *frame, uint32_t length);
    void *opaque;
};

/* Call once on zero-initialized storage at a reviewed cold-start boundary.
 * This refuses to reset an existing state, including after disconnect/fault.
 * FPSH v1 has no wire session nonce: one cold boot, one daemon, sequence 1..
 * without wrap. Generation is a local lifecycle witness, not authentication. */
int fpsh_native_init(struct fpsh_native_state *state, uint32_t generation);
void fpsh_native_invalidate(struct fpsh_native_state *state);

/* Serialize in ONE owning task. Reentrancy is detected, but this is not a
 * cross-core mutex. complete_transfer must come from native receive metadata,
 * never from a host assertion. packet may be unaligned and is not modified.
 * Generation changes, malformed input and any uncertain operation latch fault.
 * Every structurally valid accepted sequence is consumed BEFORE execution. */
int fpsh_native_process(struct fpsh_native_state *state,
                        const struct fpsh_native_ops *ops,
                        const uint8_t *packet, uint32_t length,
                        int complete_transfer, uint32_t generation);

#endif
