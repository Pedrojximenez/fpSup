.syntax unified
.arm
.text
#include "og_pic.inc"
/* 14-bit the 240 fps way: the stock bit-depth setting only ever holds a legal
 * 12-bit (eRawBitType 0); "14 was chosen" is the RAM marker BIT14, set by
 * sl_excl ROLE 14 from the chosen bit-depth row and zero after every boot.
 */
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
#if ROLE == 1
/* Entered from the stock getter C005BF28 (push {r4, r5, lr}), r0 = settings.
 * Stock runs first; under CUSTOM + CinemaDNG, with BIT14 set and stock saying
 * 12-bit, report eRawBitType 1 (14-bit) to every caller instead.  Any other
 * stock value (8 / 10 bit) is returned as is, so a stale marker cannot turn
 * an 8/10-bit choice into 14.  Writes nothing. */
    push    {r4, lr}
    bl      stock
    cmp     r0, #0                  @ stock 12-bit only
    bne     done
    LDA     r3, BIT14
    ldr     r3, [r3]
    cmp     r3, #1
    bne     done
    LDA     r3, FLAG
    ldr     r3, [r3]
    cmp     r3, #1                  @ CUSTOM
    bne     done
    LDA     r3, FMTLATCH
    ldr     r3, [r3]
    cmp     r3, #0                  @ CinemaDNG
    moveq   r0, #1                  @ eRawBitType 1 = 14-bit
done:
    pop     {r4, pc}
stock:
    push    {r4, r5, lr}            @ the displaced instruction; stock returns to entry
    RETURN_TO 0xC005BF2C

#elif ROLE == 3
/* The DNG BlackLevel tag (FUN_c02ca190) scales sensor black +0x208 by the
 * bit depth of its own enum copy (*(param_4+0xF0)+8 / +0x24), which stock only
 * refreshes when the setting changes -- 12 <-> "14" never does (camera r90:
 * 14-bit pixels with black ~1024, tag 256 -> pink).  Replaces its two
 * `bl FUN_c02da870` (enum -> bits): enum 0 under CUSTOM + CinemaDNG + BIT14
 * converts as 1 (14 bit).  Tail-calls stock, writes nothing. */
    cmp     r0, #0
    bne     go
    LDA     r3, BIT14
    ldr     r3, [r3]
    cmp     r3, #1
    bne     go
    LDA     r3, FLAG
    ldr     r3, [r3]
    cmp     r3, #1
    bne     go
    LDA     r3, FMTLATCH
    ldr     r3, [r3]
    cmp     r3, #0
    moveq   r0, #1
go:
    RETURN_TO 0xC02DA870

#elif ROLE == 2
/* Called by sl_excl ROLE 14 after stock committed the row, only when BIT14
 * changed.  12 <-> "14" commits 0 -> 0, and stock's setting core (C0075558)
 * notifies only when the value changes -- so the movie parameters and the LV
 * configuration never re-read the getter.  Replay that notification exactly as
 * C00663B0 -> C0075558 would for a change: same busy flag, same context words,
 * the setting's "changed" slot (+0x30) and FUN_c00911a0(obj, ctx, 1).  The
 * stored value is not touched. */
    push    {r4, r5, r6, lr}
    LDA     ip, 0xC0057AE8          @ settings manager
    blx     ip
    ldr     r0, [r0]                @ as C005BEF0
    ldr     r3, [r0, #4]
    ldr     r3, [r3, #0x198]
    blx     r3                      @ r0 = the bit-depth setting object
    mov     r4, r0
    ldrb    r1, [r4, #0x10]
    cmp     r1, #0                  @ stock is inside this setting already
    bne     out
    mov     r1, #1
    strb    r1, [r4, #0x10]
    ldr     r3, [r4, #0xc]
    ldr     r3, [r3, #0x1c]
    blx     r3                      @ r0 = r4: kind
    mov     r2, r0
    mov     r0, r4
    movw    r1, #0xffff
    mov     r3, #0x80000002
    LDA     ip, 0xC00913F8
    blx     ip
    mov     r5, r0                  @ context (C00663B0's uVar1)
    mov     r0, r4
    ldr     r3, [r4, #0xc]
    ldr     r3, [r3, #0x1c]
    blx     r3
    mov     r2, r0
    mov     r0, r4
    mov     r1, r5
    mov     r3, #0x80000001
    LDA     ip, 0xC00913F8
    blx     ip
    mov     r1, r0
    mov     r0, r4
    LDA     ip, 0xC00691E8
    blx     ip                      @ current value index
    mov     r1, r0
    mov     r2, r5
    mov     r0, r4
    ldr     r3, [r4, #0xc]
    ldr     r3, [r3, #0x30]
    blx     r3                      @ "changed"
    mov     r0, r4
    mov     r1, r5
    mov     r2, #1
    LDA     ip, 0xC00911A0
    blx     ip                      @ notify the listeners
    mov     r1, #0
    strb    r1, [r4, #0x10]
out:
    pop     {r4, r5, r6, pc}
#endif
