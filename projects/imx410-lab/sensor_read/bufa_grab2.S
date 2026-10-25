.syntax unified
.arm
.text
/* bufa_grab2 -- one whole frame into a buffer, watching registers only (2026-10-24).
 * bufa_grab.S waited on the BUFA0 completion flag ([0xC2F14C98] bit 0) and had to clear it first; the firmware's own
 * still / record path waits on that flag too, and 14-bit sessions wedged 4 times while we were consuming it.  Here
 * nothing shared is touched: 0x30182184 is the DMA word of the frame being written (it changes when the next frame
 * latches 0x30182180), polled with tk_dly_tsk(1).
 *   r0 = buffer (DMA word)   r1 = scratch (DMA word)   r2 = timeout ms (per phase)
 * NEXT = buffer; wait until CUR == buffer (our frame started); NEXT = scratch at once; wait until CUR != buffer (the
 * next frame started, so ours is complete).  Returns 0, 1 = our frame never started, 2 = it never ended.
 */
    .global bufa_grab2
bufa_grab2:
    push    {r4, r5, r6, r7, r8, lr}
    mov     r8, sp
    bic     sp, sp, #7
    mov     r4, r0
    mov     r5, r1
    mov     r6, r2
    ldr     r7, =0x30182180
    str     r4, [r7]                    @ NEXT = buffer
    mov     r0, #1
    bl      wait_cur                    @ r0 = 1: wait for CUR == buffer
    cmp     r0, #0
    str     r5, [r7]                    @ NEXT = scratch, at once (also on timeout)
    movne   r0, #1
    bne     9f
    mov     r0, #0
    bl      wait_cur                    @ r0 = 0: wait for CUR != buffer
    cmp     r0, #0
    movne   r0, #2
9:  mov     sp, r8
    pop     {r4, r5, r6, r7, r8, pc}

/* r0 = 1: until [0x30182184] == r4, else until it differs.  r6 = timeout ms.  Returns 0 or 1 (timeout).
 * Checks before sleeping, so a fast frame is not missed by a whole tick. */
wait_cur:
    push    {r9, r10, r11, lr}
    mov     r9, r0
    mov     r10, r6
    ldr     r11, =0x30182184
1:  ldr     r0, [r11]
    cmp     r0, r4
    moveq   r1, #1
    movne   r1, #0
    cmp     r1, r9
    moveq   r0, #0
    beq     2f
    subs    r10, r10, #1
    movmi   r0, #1
    bmi     2f
    mov     r0, #1
    ldr     ip, =0xC03705D8             @ sleep 1 ms (tk_dly_tsk, as LOSS uses it)
    blx     ip
    b       1b
2:  pop     {r9, r10, r11, pc}
    .ltorg
