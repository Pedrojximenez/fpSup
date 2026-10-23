@ alphalut.S — NEON replacement for C0563BA8, the ARGB4444 "un-premultiply"
@ pass the UIC drawer (C0561198) runs over the union of each round's dirty
@ rects (call site C0561734).  Output is bit-identical to stock; see README.md
@ and test_alphalut.py.
@
@ Stock ABI (ARM):  r0 = layer buffer (u16 pixels), r1 = rect {x, y, w, h},
@                   r2 = stride in pixels.  No return value.
@ Stock per pixel p = A<<12 | R<<8 | G<<4 | B:
@   out = A<<12 | T[A][R]<<8 | T[A][G]<<4 | T[A][B],  T = table 0xC0D0D684,
@   T[a][c] = a ? min(15, 15*c / a) : 0   (verified for all 256 entries).
@ Here, 8 pixels at a time: T[a][c] = min(15, (c * K[a]) >> 8), K below
@ (build.py and the test check K against the image's table for all 256 cells).
@ The stock "same word as last time" shortcut is only a speed path: the map is
@ a pure function with f(0) = 0, so computing every pixel gives the same bytes.
@
@ w <= 0 or h <= 0 (stock then does odd things: an unaligned w=0 row touches two
@ pixels) and enable = 0 go to the stock function unchanged.
@
@ VFP/NEON: TK-OS saves only d0-d15 + FPSCR per task switch / IRQ, so this file
@ uses d0-d15 only and saves the AAPCS callee-saved d8-d15.  No saturating ops.
@
@ Test-only mutations: MUT_K, MUT_MIN, MUT_TAIL, MUT_ZERO, MUT_STRIDE, MUT_SAVE.

        .syntax unified
        .arm
        .fpu    neon
        .text

        .global al_ctl, al_unpremul

        .equ    STOCK_FN,  0xC0563BA8
        .equ    STOCK_TBL, 0xC0D0D684

@ ---- control block (+0) ---------------------------------------------------
al_ctl:
ctl:
        .ascii  "ALUT"          @ +00 magic
        .word   1               @ +04 version
        .word   1               @ +08 enable (0 = always stock)
        .word   0               @ +0C calls taken here
        .word   0               @ +10 8-pixel NEON blocks
        .word   0               @ +14 blocks skipped (all-zero, unchanged)
        .word   0               @ +18 fallbacks to stock
        .word   0               @ +1C reserved

        .equ    C_EN,    0x08
        .equ    C_CALLS, 0x0C
        .equ    C_BLK,   0x10
        .equ    C_ZERO,  0x14
        .equ    C_FALL,  0x18

ktab:   @ K[a] low bytes, then high bytes (K = 0,3840,1920,1280,960,768,640,549,
        @ 480,427,384,350,320,296,275,256)
#ifdef MUT_K
        .byte   0,0,128,0,192,0,128,37,0,171,128,94,64,40,19,0
#else
        .byte   0,0,128,0,192,0,128,37,224,171,128,94,64,40,19,0
#endif
        .byte   0,15,7,5,3,3,2,2,1,1,1,1,1,1,1,1

@ ---- entry ----------------------------------------------------------------
al_unpremul:
        push    {r4-r11, lr}
        sub     sp, sp, #4              @ 9 regs + 4 = 40: keep sp 8-aligned
        adr     r12, ctl
        ldr     r3, [r12, #C_EN]
        cmp     r3, #0
        beq     fallback
        ldm     r1, {r4, r5, r6, r7}    @ x, y, w, h
        cmp     r6, #0
        ble     fallback
        cmp     r7, #0
        ble     fallback
        ldr     r3, [r12, #C_CALLS]
        add     r3, r3, #1
        str     r3, [r12, #C_CALLS]

        mul     r3, r2, r5
        add     r0, r0, r3, lsl #1
        add     r8, r0, r4, lsl #1      @ first row (same 32-bit wrap as stock)
#ifdef MUT_STRIDE
        lsl     r9, r2, #2
#else
        lsl     r9, r2, #1              @ row step in bytes
#endif
#ifdef MUT_SAVE
        vpush   {d9-d15}
#else
        vpush   {d8-d15}
#endif
        adr     r3, ktab
        vld1.8  {d12-d15}, [r3]         @ d12:d13 = K low bytes, d14:d15 = K high bytes
        vmov.i8 d11, #15
        movw    r10, #(STOCK_TBL & 0xFFFF)
        movt    r10, #(STOCK_TBL >> 16)
        mov     lr, #0                  @ NEON blocks this call
        mov     r5, #0                  @ zero blocks this call

row:
        mov     r0, r8
        mov     r1, r6
blocks:
        cmp     r1, #8
        blt     scalar
        vld2.8  {d0, d1}, [r0]          @ d0 = G<<4|B bytes, d1 = A<<4|R bytes
        vorr    d2, d0, d1
        vmov    r2, r3, d2
        orrs    r2, r2, r3
        beq     zero
        vshr.u8 d2, d1, #4              @ A
        vtbl.8  d4, {d12, d13}, d2          @ K low byte per lane
        vtbl.8  d5, {d14, d15}, d2          @ K high byte per lane
        vzip.8  d4, d5                  @ q2 = K as u16 lanes 0..7

        vand    d3, d1, d11             @ R
        vmovl.u8 q3, d3
        vmul.i16 q3, q3, q2
        vshrn.u16 d10, q3, #8
#ifndef MUT_MIN
        vmin.u8 d10, d10, d11
#endif
        vsli.8  d10, d2, #4             @ hi byte = A<<4 | R'

        vshr.u8 d3, d0, #4              @ G
        vmovl.u8 q3, d3
        vmul.i16 q3, q3, q2
        vshrn.u16 d8, q3, #8
        vmin.u8 d8, d8, d11

        vand    d3, d0, d11             @ B
        vmovl.u8 q3, d3
        vmul.i16 q3, q3, q2
        vshrn.u16 d9, q3, #8
        vmin.u8 d9, d9, d11
        vsli.8  d9, d8, #4              @ lo byte = G'<<4 | B'

        vst2.8  {d9, d10}, [r0]!
        add     lr, lr, #1
        sub     r1, r1, #8
        b       blocks
zero:                                   @ eight 0x0000 pixels map to themselves
#ifdef MUT_ZERO
        add     r0, r0, #8
#else
        add     r0, r0, #16
#endif
        add     r5, r5, #1
        sub     r1, r1, #8
        b       blocks

scalar:                                 @ the stock per-pixel code, same table
#ifdef MUT_TAIL
        cmp     r1, #1
        ble     rowend
#else
        cmp     r1, #0
        beq     rowend
#endif
        ldrh    r2, [r0]
        lsr     r3, r2, #8
        and     r4, r3, #0xF0
        add     r11, r10, r4
        and     r3, r3, #0xF
        ldrb    r3, [r11, r3]
        ubfx    r12, r2, #4, #4
        ldrb    r12, [r11, r12]
        and     r2, r2, #0xF
        ldrb    r2, [r11, r2]
        orr     r4, r4, r3
        orr     r4, r12, r4, lsl #4
        orr     r4, r2, r4, lsl #4
        strh    r4, [r0], #2
        sub     r1, r1, #1
        b       scalar

rowend:
        add     r8, r8, r9
        subs    r7, r7, #1
        bne     row

#ifdef MUT_SAVE
        vpop    {d9-d15}
#else
        vpop    {d8-d15}
#endif
        adr     r12, ctl
        ldr     r3, [r12, #C_BLK]
        add     r3, r3, lr
        str     r3, [r12, #C_BLK]
        ldr     r3, [r12, #C_ZERO]
        add     r3, r3, r5
        str     r3, [r12, #C_ZERO]
        add     sp, sp, #4
        pop     {r4-r11, pc}

fallback:                               @ r0-r2 untouched: stock gets the call as-is
        ldr     r3, [r12, #C_FALL]
        add     r3, r3, #1
        str     r3, [r12, #C_FALL]
        add     sp, sp, #4
        pop     {r4-r11, lr}
        ldr     pc, =STOCK_FN
        .ltorg
