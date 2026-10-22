#include "raw_false_color_runtime.h"

#include <assert.h>
#include <stdio.h>

int main(void)
{
    struct rfc_frame_mailbox mailbox = {0};
    struct rfc_frame_snapshot snapshot = {0};
    uint32_t last = 0;

    assert(rfc_mailbox_take_latest(&mailbox, &last, &snapshot) == 0);
    rfc_mailbox_publish(&mailbox, (uintptr_t)0x41234000u, 0xc375d840u);
    assert(rfc_mailbox_take_latest(&mailbox, &last, &snapshot) == 1);
    assert(snapshot.raw_address == (uintptr_t)0x41234000u);
    assert(snapshot.descriptor_address == 0xc375d840u);
    assert(rfc_mailbox_take_latest(&mailbox, &last, &snapshot) == 0);

    rfc_mailbox_publish(&mailbox, (uintptr_t)0x45678000u, 0xc375d840u);
    rfc_mailbox_publish(&mailbox, (uintptr_t)0x489ab000u, 0xc375d840u);
    assert(rfc_mailbox_take_latest(&mailbox, &last, &snapshot) == 1);
    assert(snapshot.raw_address == (uintptr_t)0x489ab000u);

    puts("raw false-color runtime tests passed");
    return 0;
}
