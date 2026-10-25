.syntax unified
.arm
.text
/* bufa_grab -- steer BUFA0 into a buffer for one whole frame, camera-side (2026-10-24).
 * The host used to write NEXT, then poll a sentinel at the buffer's tail ~100 times a frame over USB, then write NEXT
 * back ~30 ms late; here the BUFA0 completion flag (the ISR sets [0xC2F14C98] bit 0 per frame) is waited on, and NEXT
 * goes back the moment the frame lands -- before the next frame can latch the buffer (the DMA latches 0x30182180 at
 * frame start).
 *   r0 = flag id   r1 = buffer (DMA word: physical >> 2)   r2 = scratch (DMA word)   r3 = timeout ms per completion
 * Steps: NEXT = buffer; completion 1 (the frame in flight -- it may have latched the old address); completion 2 (a
 * whole frame in the buffer); NEXT = scratch.  Returns 0, or the failing tk_wai_flg code (NEXT is put back either way).
 */
    .global bufa_grab
bufa_grab:
    push    {r4, r5, r6, r7, r8, lr}
    mov     r8, sp
    bic     sp, sp, #7
    sub     sp, sp, #8
    mov     r4, r0
    mov     r5, r1
    mov     r6, r2
    mov     r7, r3
    ldr     r0, =0x30182180
    str     r5, [r0]                    @ NEXT = buffer
    bl      wait_one
    cmp     r0, #0
    bne     9f
    bl      wait_one
9:  ldr     r1, =0x30182180
    str     r6, [r1]                    @ NEXT = scratch, at once
    mov     sp, r8
    pop     {r4, r5, r6, r7, r8, pc}

/* clear bit 0, wait for the next completion; r4 = flag id, r7 = timeout; returns tk_wai_flg's code */
wait_one:
    push    {lr}
    sub     sp, sp, #12                 @ 8-aligned with the push: [sp] = timeout, [sp+4] = out
    mov     r0, r4
    mvn     r1, #1
    ldr     ip, =0xC00169C8             @ tk_clr_flg(id, ~1)
    blx     ip
    str     r7, [sp]
    add     r3, sp, #4
    mov     r2, #1                      @ TWF_ORW
    mov     r1, #1
    mov     r0, r4
    ldr     ip, =0xC0016C08             @ tk_wai_flg
    blx     ip
    add     sp, sp, #12
    pop     {pc}
    .ltorg
