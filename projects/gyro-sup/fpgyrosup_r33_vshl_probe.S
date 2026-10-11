/* r33 r32-base producer diagnostics.
 *
 * The existing logger reads the hardware ring head and only then calls
 * TickTimer.  A preemption in that narrow window delays the raw-block anchor
 * even if no sample was dropped.  Read the same clock immediately before the
 * existing ring-head load, retain the original post-head TickTimer result as
 * the batch anchor, and keep the unsigned before/after delta.  Only a callback
 * that actually starts a new raw block contributes to the reported maximum,
 * because only that callback's timestamp can become a GCSV block anchor.
 *
 * S_DROPPED at state+0x14 remains the original r17/r29 counter.  The only new
 * resident words are state+0x1E4 (last delta) and state+0x1E8 (maximum relevant
 * block-start delta), cleared together with S_DROPPED at take start.
 */
    .syntax unified
    .arm

    .section .text

    /* Exact end of the r29/r32 resident logger. */
    .org 0xE24

    /* Replaces `str r0,[sl,#0x14]`; r0 is already zero. */
    .global probe_reset
probe_reset:
    str     r0, [sl, #0x14]
    str     r0, [sl, #0x1E4]
    str     r0, [sl, #0x1E8]
    bx      lr

    /* Replaces `ldr r5,[r8]`, the actual hardware-head snapshot.  r4 is dead on
     * this path and the original code resets it immediately after the post-head
     * timer.  Replay the displaced load before returning. */
    .global probe_before_head
probe_before_head:
    push    {r3, lr}
    movw    ip, #0xB6E0
    movt    ip, #0xC002
    blx     ip
    mov     r4, r0
    ldr     r5, [r8]
    pop     {r3, pc}

    /* Replaces `mov sb,r0` after the original TickTimer call.  Preserve that
     * exact anchor, then update the diagnostic maximum without another call. */
    .global probe_after_head_tick
probe_after_head_tick:
    mov     sb, r0
    sub     r1, sb, r4
    str     r1, [sl, #0x1E4]
    bx      lr

    /* Replaces `lsr r2,r3,#3` after a producer slot has been selected.  r0 is
     * that slot's current gyro-byte count.  Zero means this callback supplies
     * the timestamp that PGEN will later use as the raw-block anchor. */
    .global probe_block_start
probe_block_start:
    mov     r2, r3, lsr #3
    cmp     r0, #0
    bxne    lr
    ldr     ip, [sl, #0x1E4]
    ldr     r2, [sl, #0x1E8]
    cmp     ip, r2
    strhi   ip, [sl, #0x1E8]
    mov     r2, r3, lsr #3
    bx      lr
