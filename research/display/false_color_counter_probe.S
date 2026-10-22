.syntax unified
.arm
.text

/* SIGMA fp 5.02, loaded at 0xC072DE64. */
.equ STATE,       0xC072E500
.equ RAW_RETURN,  0xC0429F1C
.equ DRAW_RETURN, 0xC057DB9C

.global raw_probe
.type raw_probe, %function
raw_probe:
    /* Reproduce the instruction replaced at 0xC0429F18. */
    push    {r4-r7, r11, lr}
    movw    r12, #:lower16:STATE
    movt    r12, #:upper16:STATE
    ldr     r1, [r12, #4]
    add     r1, r1, #1
    str     r1, [r12, #4]
    str     r0, [r12, #8]
    mov     r1, r0, lsl #2
    mov     r2, #0x40000000
    add     r1, r1, r2
    str     r1, [r12, #12]
    ldr     r2, [r12, #16]
    cmp     r1, r2
    strlo   r1, [r12, #16]
    ldr     r2, [r12, #20]
    cmp     r1, r2
    strhi   r1, [r12, #20]
    movw    r12, #:lower16:RAW_RETURN
    movt    r12, #:upper16:RAW_RETURN
    bx      r12

/* Keep the second hook at a stable offset for the AutoRun generator. */
.balign 128
.global draw_probe
.type draw_probe, %function
draw_probe:
    /* Reproduce the instruction replaced at 0xC057DB98. */
    push    {r4-r7, r9-r11, lr}
    movw    r12, #:lower16:STATE
    movt    r12, #:upper16:STATE
    str     r3, [r12, #40]
    ldr     r3, [r12, #24]
    add     r3, r3, #1
    str     r3, [r12, #24]
    str     r0, [r12, #28]
    str     r1, [r12, #32]
    str     r2, [r12, #36]
    ldr     r3, [r12, #40]
    movw    r12, #:lower16:DRAW_RETURN
    movt    r12, #:upper16:DRAW_RETURN
    bx      r12
