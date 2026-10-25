.syntax unified
.arm
.text
/* bufa_grabcb -- a BUFA0 completion callback that steers one whole frame into a buffer (2026-10-24).
 * FUN_c0630620 calls [0xC37CF8CC](arg, done_addr) from the completion interrupt; the DMA latches NEXT (0x30182180)
 * when a frame starts, before that interrupt runs, so a NEXT written in completion j lands frame j+2 (IMXB frame_cb's
 * rule).  Stages, one per completion:
 *   0: NEXT = target            (frame j+2 will be ours)
 *   1: NEXT = scratch           (frame j+2 already latched target; j+3 goes back to scratch)
 *   2: got = done_addr, done = 1   (frame j+2 finished: the host checks got == target's address)
 * Nothing the firmware waits on is touched (bufa_grab.S consumed the completion flag: 14-bit sessions wedged).
 * Words at the end: stage, target, scratch, done, got (offsets from the build).
 */
    .global bufa_grabcb
bufa_grabcb:
    ldr     r2, stage
    ldr     r3, =0x30182180
    cmp     r2, #0
    bne     1f
    ldr     r0, target
    str     r0, [r3]
    mov     r2, #1
    str     r2, stage
    bx      lr
1:  cmp     r2, #1
    bne     2f
    ldr     r0, scratch
    str     r0, [r3]
    mov     r2, #2
    str     r2, stage
    bx      lr
2:  cmp     r2, #2
    bxne    lr
    str     r1, got
    mov     r2, #1
    str     r2, done
    mov     r2, #3
    str     r2, stage
    bx      lr
    .ltorg
stage:      .word 3
target:     .word 0
scratch:    .word 0
done:       .word 0
got:        .word 0
