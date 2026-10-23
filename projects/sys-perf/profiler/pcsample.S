.syntax unified
.arm
.text
/* ============================================================================
 * pcsample — PC-sampling profiler, one record per timer interrupt.
 * ============================================================================
 *
 * Called by the timer ISR C0016000 as a channel handler (`blx r0`, r0 = this
 * entry), in IRQ mode (0xD2), interrupts off, on the IRQ stack.  Static
 * evidence: research/firmware/notes/PC_SAMPLER_HOOKPOINTS.md.
 *
 * Two ways in, chosen by the host through C_ORIG:
 *   A  channel 0's handler pointer 0xC303380C is swapped for pcs_tick and
 *      C_ORIG = C0016978 (the OS tick).  We tail-call it with r0 = C_ORIG,
 *      exactly what the ISR would have passed it.
 *   B  pcs_tick is registered on an idle channel through C0016210, C_ORIG = 0,
 *      and we simply return.
 *
 * Record, 16 bytes, at ring + (idx & mask) * 16:
 *   +0  interrupted PC                  [C_FRAME]       (0xC42F1FBC)
 *   +4  interrupted mode's banked LR    SVC/SYS/USR only, else 0
 *   +8  (tid << 8) | (SPSR & 0xFF)      SPSR at [C_FRAME - 8]; tid 0 = idle
 *   +12 current_time low word (ms)      0xC301EAE4
 * The record is written first, then `dmb`, then C_IDX: a reader that sees an
 * index sees the records below it.
 *
 * Touches only r0-r3, ip and r4/r5 (saved).  Calls nothing.  Stack: two words,
 * so an 8-aligned sp stays 8-aligned (C0016000 pushed four).
 *
 * The banked LR is read by switching CPSR.M to the interrupted mode and back.
 * Only SVC (0x13) and SYS (0x1F, also used for USR) are ever switched to: a
 * garbage SPSR (wrong C_FRAME) must not put the core in an invalid mode.
 * ========================================================================== */

.equ C_MAGIC,  0x00     /* 'PCS1' */
.equ C_RING,   0x04     /* ring base */
.equ C_MASK,   0x08     /* records - 1, records a power of two */
.equ C_IDX,    0x0C     /* records written since start (monotonic) */
.equ C_LIMIT,  0x10     /* stop writing at idx == limit; 0xFFFFFFFF = wrap */
.equ C_ORIG,   0x14     /* handler to tail-call; 0 = return */
.equ C_EN,     0x18     /* 0 = count calls only */
.equ C_OVER,   0x1C     /* calls dropped because idx reached limit */
.equ C_FRAME,  0x20     /* address of the interrupted PC on the IRQ stack */
.equ C_CALLS,  0x24     /* every entry, enabled or not */
.equ C_SKIP,   0x28     /* enabled calls to ignore before the first record */
.equ C_SEEN,   0x2C     /* enabled calls since start (compared with C_SKIP) */

.equ CTXTSK,   0xC3000098
.equ CURTIME,  0xC301EAE4

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm


ctl:
    .word   0x31534350      /* C_MAGIC */
    .word   0               /* C_RING */
    .word   0               /* C_MASK */
    .word   0               /* C_IDX */
    .word   0               /* C_LIMIT */
    .word   0               /* C_ORIG */
    .word   0               /* C_EN */
    .word   0               /* C_OVER */
    .word   0xC42F1FBC      /* C_FRAME */
    .word   0               /* C_CALLS */
    .word   0               /* C_SKIP */
    .word   0               /* C_SEEN */
    .word   0, 0, 0, 0      /* spare, keeps pcs_tick at +0x40 */

.global pcs_tick
pcs_tick:
    push    {r4, r5}
    adr     r3, ctl
    ldr     r1, [r3, #C_CALLS]
    add     r1, r1, #1
    str     r1, [r3, #C_CALLS]

    ldr     r1, [r3, #C_EN]
    cmp     r1, #0
    beq     out

    ldr     r1, [r3, #C_SEEN]
    add     r1, r1, #1
    str     r1, [r3, #C_SEEN]
    ldr     r2, [r3, #C_SKIP]
    cmp     r1, r2
    bls     out                     /* still inside the skip window */

    ldr     r1, [r3, #C_IDX]
    ldr     r2, [r3, #C_LIMIT]
    cmp     r1, r2
    bhs     full

    ldr     r2, [r3, #C_MASK]
    and     r2, r1, r2
    ldr     r4, [r3, #C_RING]
    add     r4, r4, r2, lsl #4

    ldr     r0, [r3, #C_FRAME]
    ldr     r2, [r0]                /* interrupted PC */
    str     r2, [r4]
    ldr     r5, [r0, #-8]           /* interrupted CPSR (SPSR_irq copy) */

    and     r2, r5, #0x1F
    cmp     r2, #0x10
    moveq   r2, #0x1F               /* USR registers are SYS registers */
    mov     ip, #0
    cmp     r2, #0x13
    cmpne   r2, #0x1F
    bne     nolr
    mrs     r0, cpsr
    bic     ip, r0, #0x1F
    orr     ip, ip, r2
    msr     cpsr_c, ip              /* I/F stay set: r0 has them */
    mov     r2, lr
    msr     cpsr_c, r0
    mov     ip, r2
nolr:
    str     ip, [r4, #4]

    LDA     r0, CTXTSK
    ldr     r0, [r0]
    cmp     r0, #0
    ldrne   r0, [r0, #8]            /* tid */
    and     r5, r5, #0xFF
    orr     r5, r5, r0, lsl #8
    str     r5, [r4, #8]

    LDA     r0, CURTIME
    ldr     r0, [r0]
    str     r0, [r4, #12]

    dmb     sy
    ldr     r1, [r3, #C_IDX]
    add     r1, r1, #1
    str     r1, [r3, #C_IDX]
    b       out

full:
    ldr     r1, [r3, #C_OVER]
    add     r1, r1, #1
    str     r1, [r3, #C_OVER]

out:
    pop     {r4, r5}
    ldr     r0, [r3, #C_ORIG]
    cmp     r0, #0
    bxeq    lr
    bx      r0                      /* tail call, r0 = handler as the ISR passes */
