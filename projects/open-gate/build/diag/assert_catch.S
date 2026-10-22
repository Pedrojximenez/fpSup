/* Dev-only diagnostic: catch the firmware assert before it halts the camera.
 *
 * C0011100(file, line) is SIGMA's assert: it stops the system (C0016D30(1))
 * and spins at C00111FC, so a freeze leaves nothing to read.  Entered by a
 * B at C0011100 (stock `push {r4,r5,lr}`), this records the first caller
 * and parks only the asserting task in dly_tsk, so the USB shell can read
 * RECORD.  Never returns.  RAM-only, never on a release card.
 *
 * RECORD: +00 magic 0x54525352 (set last)  +04 hits  +08 file ptr  +0C line  +10 lr
 *         +14 sp  +18 cpsr  +1C..+5B sixteen words from sp
 */
    .syntax unified
    .arm
    .global entry
entry:
    movw    ip, #:lower16:RECORD
    movt    ip, #:upper16:RECORD
    ldr     r3, [ip, #4]
    add     r3, r3, #1
    str     r3, [ip, #4]
    cmp     r3, #1
    bne     park                    /* keep the first assert only */
    str     r0, [ip, #8]
    str     r1, [ip, #0xC]
    str     lr, [ip, #0x10]
    str     sp, [ip, #0x14]
    mrs     r3, cpsr
    str     r3, [ip, #0x18]
    add     r2, ip, #0x1C
    mov     r3, #0
1:  ldr     r1, [sp, r3]
    str     r1, [r2, r3]
    add     r3, r3, #4
    cmp     r3, #64
    blt     1b
    movw    r3, #0x5352
    movt    r3, #0x5452
    str     r3, [ip]
park:
    mov     r0, #1000
    movw    ip, #0x05D8
    movt    ip, #0xC037             /* dly_tsk */
    blx     ip
    b       park
