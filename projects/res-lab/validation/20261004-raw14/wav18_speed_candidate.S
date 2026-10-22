.syntax unified
.arm
.text
/*
 * Isolated candidate for iXML MASTER_SPEED and CURRENT_SPEED only.
 *
 * The two original BL sites are C0685BF8 and C0685C04.  The preceding
 * C0685BEC call for TIMECODE_RATE must keep calling stock C0685B20 because
 * the current timecode still runs on the native 23.976 carrier.
 *
 * This file is evidence only.  It is not included in r86 or any card.
 * FLAG/RATE18/AXIS/RECIPE are virtual build-time addresses.  A production
 * integration would need USER relocation and the normal cave audit.
 */
#ifndef FLAG
.equ FLAG, 0xC0731C08
#endif
#ifndef RATE18
.equ RATE18, 0xC0731C4C
#endif
#ifndef AXIS
.equ AXIS, 0xC0732490
#endif
#ifndef RECIPE
.equ RECIPE, 0xC07324C0
#endif
.equ STOCK_SPEED, 0xC0685B20

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global entry
entry:
    push    {r4-r8, lr}
    mov     r8, r0                  @ original enum for stock tail-call
    cmp     r0, #1                  @ legal native 23.976 carrier
    bne     stock
    LDA     r4, FLAG
    ldr     r4, [r4]
    cmp     r4, #1
    bne     stock
    LDA     r4, RATE18
    ldr     r4, [r4]
    cmp     r4, #1
    bne     stock
    LDA     r5, AXIS
    ldr     r4, [r5]                @ AXIS bit depth
    cmp     r4, #14
    bne     stock
    ldr     r4, [r5, #4]            @ AXIS private rate index
    cmp     r4, #11
    bne     stock
    LDA     r6, RECIPE
    mov     r7, #9
snapshot:
    ldr     r1, [r5], #4
    ldr     r2, [r6], #4
    cmp     r1, r2
    bne     stock
    subs    r7, r7, #1
    bne     snapshot
    ldr     r1, [r6]                @ RECIPE.valid
    cmp     r1, #1
    bne     stock
    ldr     r1, [r6, #4]            @ RECIPE.mode
    cmp     r1, #0
    cmpne   r1, #141
    bne     stock
    ldr     r1, [r6, #36]           @ RECIPE.nominal FPS
    cmp     r1, #18
    bne     stock
    adr     r0, speed18
    pop     {r4-r8, pc}
stock:
    mov     r0, r8
    pop     {r4-r8, lr}
    LDA     ip, STOCK_SPEED
    bx      ip

.align 2
speed18:
    .asciz "18/1"
