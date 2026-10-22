#include "raw_false_color_runtime.h"

static void rfc_barrier(void)
{
#if defined(__arm__) || defined(__thumb__)
    __asm__ volatile("dmb ish" ::: "memory");
#else
    __asm__ volatile("" ::: "memory");
#endif
}

void rfc_mailbox_publish(struct rfc_frame_mailbox *mailbox,
                         uintptr_t raw_address, uint32_t descriptor_address)
{
    uint32_t next;

    if (!mailbox)
        return;
    next = mailbox->sequence + 1u;
    if ((next & 1u) == 0)
        ++next;
    mailbox->sequence = next;
    rfc_barrier();
    mailbox->raw_address = raw_address;
    mailbox->descriptor_address = descriptor_address;
    rfc_barrier();
    mailbox->sequence = next + 1u;
}

int rfc_mailbox_take_latest(const struct rfc_frame_mailbox *mailbox,
                            uint32_t *last_sequence,
                            struct rfc_frame_snapshot *snapshot)
{
    uint32_t before;
    uint32_t after;

    if (!mailbox || !last_sequence || !snapshot)
        return -1;
    before = mailbox->sequence;
    if ((before & 1u) != 0 || before == *last_sequence)
        return 0;
    rfc_barrier();
    snapshot->raw_address = mailbox->raw_address;
    snapshot->descriptor_address = mailbox->descriptor_address;
    rfc_barrier();
    after = mailbox->sequence;
    if (before != after || (after & 1u) != 0)
        return 0;
    snapshot->sequence = after;
    *last_sequence = after;
    return 1;
}
