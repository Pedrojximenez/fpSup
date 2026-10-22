/* Dev-only diagnostic: log who fetches the frame-rate row<->value table.
 *
 * Entered by a B at C06BDB00 (MenuValueConverterBase::v22, the table getter,
 * stock `str r4,[sp,#-4]!`).  Records into a 16-entry ring at LOG, then runs
 * the displaced instruction and returns to C06BDB04.  No behaviour change.
 * RAM only; never on a card.
 *
 * LOG: +00 call count; 8 entries at +10, 128 B each:
 *   +00 lr (inside the converter wrapper)  +04 r6 (row in C06BDAB0, value in C06BDA58)
 *   +08 sp at entry  +0C RATE240  +10 row of first value-7 pair  +14.. 27 stack words from sp+0x10
 */
    .syntax unified
    .arm
    .global entry
entry:
    push    {r0, r1, r2, r3}
    movw    r2, #:lower16:LOG
    movt    r2, #:upper16:LOG
    ldr     r3, [r2]
    add     r0, r3, #1
    str     r0, [r2]
    and     r3, r3, #7                  /* 8 entries x 128 B */
    add     r2, r2, #0x10
    add     r2, r2, r3, lsl #7
    str     lr, [r2]
    str     r6, [r2, #4]
    add     r0, sp, #16
    str     r0, [r2, #8]
    movw    r1, #:lower16:RATE240       /* row-nine flag and first value-7 row, at this instant */
    movt    r1, #:upper16:RATE240
    ldr     r0, [r1]
    str     r0, [r2, #0x0C]
    movw    r1, #:lower16:PAIRROW
    movt    r1, #:upper16:PAIRROW
    ldr     r0, [r1]
    str     r0, [r2, #0x10]
    mov     r3, #0                      /* 27 words from the caller's sp+0x10 */
1:  add     r1, sp, #16+0x10
    ldr     r0, [r1, r3]
    add     r1, r2, #0x14
    str     r0, [r1, r3]
    add     r3, r3, #4
    cmp     r3, #27*4
    blo     1b
    pop     {r0, r1, r2, r3}
    str     r4, [sp, #-4]!
    ldr     pc, [pc, #-4]
    .word   0xC06BDB04
