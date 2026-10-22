.syntax unified
.arm
.text
#include "og_pic.inc"
/* Diagnostic: log every CRCT path-selector run (XC_ImageSensorIMX410::v37,
 * FUN_c0325228, imager0; r1 = geometry in 0x38 B, r2 = path out 0x4C B).
 * Stock runs first, unchanged; then both structs are copied into an 8-slot ring
 * at LOG: +0 count, slot i at LOG + 0x10 + i * 0x90 = {lr, in[14], out[19]}.
 * Writes only LOG (our USER memory). */
.macro LDA reg, value
#ifdef OG_V3
    OGLDA   \reg, \value
#else
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
#endif
.endm
.macro RETURN_TO address
    ldr     pc, [pc, #-4]
    .word   \address
.endm
.global entry
entry:
    push    {r4, r5, r6, lr}
    mov     r4, r1
    mov     r5, r2
    bl      stock
#ifdef FLAG
    /* Branch C with a binned record (2026-10-05 camera, M3 bin 3x3: in rec bin
     * 3/3 -> out a7 mux 4 Hbin2 + main bin 3/3; the DNG came out 6048 -> 672
     * wide, x3 twice).  Hbin2 already bins horizontally: the main pipeline's
     * hbin goes to 1, vbin stays.  CUSTOM only; stock never bins the record. */
    LDA     r3, FLAG
    ldr     r3, [r3]
    cmp     r3, #1
    bne     3f
    ldr     r3, [r5, #8]            @ a7 mux
    cmp     r3, #4
    ldreq   r3, [r4, #0x10]         @ record hbin taps
    cmpeq   r3, #3
    ldreq   r3, [r5, #0x24]         @ main hbin
    cmpeq   r3, #3
    moveq   r3, #1
    streq   r3, [r5, #0x24]
#ifdef BINFILT
    /* record mode r1 (imx410_binfilt BINFILT bit 8): stock reduction record 1,
     * whose control bits (0x300F0800 / 0840 bit16) carry its sharpness */
    bne     3f
    LDA     r3, BINFILT
    ldr     r3, [r3]
    tst     r3, #0x100              @ imx410_binfilt: record mode r1
    movne   r3, #1
    strne   r3, [r5, #0x48]
#endif
3:
#endif
    LDA     r6, LOG
    ldr     r0, [r6]
    and     r1, r0, #7
    add     r0, r0, #1
    str     r0, [r6]
    mov     r2, #0x90
    mla     r1, r1, r2, r6
    add     r1, r1, #0x10
    ldr     r2, [sp, #12]           @ our caller
    str     r2, [r1], #4
    mov     r3, #14
1:  ldr     r2, [r4], #4
    str     r2, [r1], #4
    subs    r3, r3, #1
    bne     1b
    mov     r3, #19
2:  ldr     r2, [r5], #4
    str     r2, [r1], #4
    subs    r3, r3, #1
    bne     2b
    pop     {r4, r5, r6, pc}
stock:
    push    {r4, r5, r6, r7}        @ the displaced instruction
    RETURN_TO 0xC032522C
