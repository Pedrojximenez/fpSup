@ neonblit.S — NEON replacements for the 1:1 (axis-aligned, unscaled) spans that
@ the UI's software 2D engine uses when the destination is the ARGB4444 OSD
@ layer (driver id 6, record 0xC2EB3EE4, span table 1 at 0xC2EB3F5C), plus the
@ 16bpp layer fill.  Output is bit-identical to the stock Thumb code; see
@ README.md and test_neonblit.py.
@
@ Span ABI (stock, called with blx from C07080D0):
@   r0 = destination row pointer (u16)
@   r1 = source image descriptor copy: [r1+0x24] source row pointer,
@        [r1+0x1c] source stride in source elements
@   r2 = width in pixels
@   r3 = parameter block: [r3+4] 256-entry LUT (8bpp sources only),
@        [r3+8] destination stride in pixels, [r3+0xc] rows
@ No return value.
@
@ VFP/NEON: TK-OS saves only d0-d15 + FPSCR on a task switch (C0000D24) and on
@ IRQ entry (C0000E78).  So this file never touches d16-d31, and saves the
@ AAPCS callee-saved d8-d15 it uses.  No saturating ops, so FPSCR.QC is never
@ written.
@
@ Build-time mutations (test only): MUT_ROUND, MUT_OR_ADD, MUT_TAIL, MUT_OPQ,
@ MUT_565, MUT_LUT, MUT_FILL, MUT_SAVE, MUT_A4, MUT_A4T, MUT_A4S.

        .syntax unified
        .arm
        .fpu    neon
        .text

        .global nb_p32_blend, nb_p32_opaque, nb_565_opaque, nb_lut8_blend
        .global nb_a4_blend, nb_layer_fill

@ ---------------------------------------------------------------------------
@ Shared 8-pixel source-over kernel.
@ in:  d0=R d1=G d2=B d3=A (bytes, premultiplied source), q2 = 8 dst pixels
@ out: q6 = 8 result pixels.  Clobbers q3, q4, q5.
@ Stock per channel: t = s + ((n*17 * ia) >> 8), ia = 256 - (A + (A>>7)),
@ n = destination nibble;  out = (tR>>4)<<8 | tG&~15 | tB>>4 | (tA>>4)<<12,
@ composed with OR (fields can overlap when the source is not premultiplied).
        .macro  CHAN src, lsl1, lsr1
        .if \lsl1
        vshl.u16 q4, q2, #\lsl1
        vshr.u16 q4, q4, #\lsr1
        .else
        vshr.u16 q4, q2, #\lsr1
        .endif
        vsli.16 q4, q4, #4              @ n*17
        vmul.i16 q4, q4, q3             @ * ia   (<= 255*256, fits u16)
#ifdef MUT_ROUND
        vrshr.u16 q4, q4, #8
#else
        vshr.u16 q4, q4, #8
#endif
        vaddw.u8 q4, q4, \src           @ + source byte (<= 510)
        .endm

        .macro  BLEND8
        vmovl.u8 q3, d3                 @ A
        vshr.u16 q4, q3, #7
        vadd.i16 q4, q4, q3
        vmov.i16 q5, #0x100
        vsub.i16 q3, q5, q4             @ ia
        CHAN    d0, 4, 12               @ R nibble = d[11:8]
        vshr.u16 q4, q4, #4
        vshl.i16 q6, q4, #8
        CHAN    d1, 8, 12               @ G nibble = d[7:4]
        vshr.u16 q4, q4, #4
        vshl.i16 q4, q4, #4
#ifdef MUT_OR_ADD
        vadd.i16 q6, q6, q4
#else
        vorr    q6, q6, q4
#endif
        CHAN    d2, 12, 12              @ B nibble = d[3:0]
        vshr.u16 q4, q4, #4
        vorr    q6, q6, q4
        CHAN    d3, 0, 12               @ A nibble = d[15:12]
        vshr.u16 q4, q4, #4
        vshl.i16 q4, q4, #12
        vorr    q6, q6, q4
        .endm

@ One pixel, scalar, same arithmetic.  in: ip = source word, lr = dst pixel.
@ out: r3.  Clobbers r1, r2, r11.
        .macro  SCH n, s
        ubfx    r11, lr, #\n, #4
        orr     r11, r11, r11, lsl #4
        mul     r11, r2, r11
        ubfx    r1, ip, #\s, #8
        add     r11, r1, r11, lsr #8
        .endm

        .macro  BLEND1
        lsr     r1, ip, #24
        add     r2, r1, r1, lsr #7
        rsb     r2, r2, #256            @ ia
        SCH     8, 0                    @ R
        lsr     r11, r11, #4
        lsl     r3, r11, #8
        SCH     4, 8                    @ G
        bic     r11, r11, #15
        orr     r3, r3, r11
        SCH     0, 16                   @ B
        orr     r3, r3, r11, lsr #4
        SCH     12, 24                  @ A
        lsr     r11, r11, #4
        orr     r3, r3, r11, lsl #12
        .endm

@ Frame used by the blend spans (after push/vpush):
@   [sp+0..31]  gather buffer (LUT span)
@   [sp+32] width   [sp+36] src stride bytes   [sp+40] dst stride bytes
        .equ    F_W,   32
        .equ    F_SS,  36
        .equ    F_DS,  40
        .equ    FRAME, 48

@ ---------------------------------------------------------------------------
@ Table 1 idx 0 (stock C06FB9A8): premultiplied RGBA8888 source-over ARGB4444.
nb_p32_blend:
        cmp     r2, #8
        bge     10f
        @ < 8 pixels: scalar only, no VFP save (short runs are the common case)
        push    {r4-r11, lr}
        ldr     r4, [r1, #0x24]
        ldr     r6, [r1, #0x1c]
        lsl     r6, r6, #2
        ldr     ip, [r3, #8]
        lsl     ip, ip, #1
        ldr     r7, [r3, #0xc]
        mov     r5, r2
        str     ip, [sp, #-12]!         @ dst stride; 36 + 12 = 8-aligned
1:      subs    r7, r7, #1
        bmi     9f
        mov     r8, r0
        mov     r9, r4
        movs    r10, r5
        ble     5f
4:      ldr     ip, [r9], #4
        ldrh    lr, [r8]
        BLEND1
        strh    r3, [r8], #2
        subs    r10, r10, #1
        bgt     4b
5:      ldr     ip, [sp]
        add     r0, r0, ip
        add     r4, r4, r6
        b       1b
9:      add     sp, sp, #12
        pop     {r4-r11, pc}
10:     ldr     ip, [r3, #0xc]
        cmp     ip, #0
        bxle    lr                      @ no rows: nothing to do
        push    {r4-r11, lr}
#ifdef MUT_SAVE
        vpush   {d8-d11}
#else
        vpush   {d8-d13}
#endif
        sub     sp, sp, #FRAME
        ldr     r4, [r1, #0x24]         @ src row
        ldr     ip, [r1, #0x1c]
        lsl     ip, ip, #2
        str     ip, [sp, #F_SS]
        ldr     ip, [r3, #8]
        lsl     ip, ip, #1
        str     ip, [sp, #F_DS]
        bic     r2, r2, r2, asr #31     @ width<0 -> 0
        str     r2, [sp, #F_W]
        ldr     r7, [r3, #0xc]          @ rows
1:      subs    r7, r7, #1
        bmi     9f
        mov     r8, r0
        mov     r9, r4
        ldr     r10, [sp, #F_W]
2:      cmp     r10, #8
        blt     3f
        vld4.8  {d0-d3}, [r9]!
        vld1.16 {d4-d5}, [r8]
        BLEND8
        vst1.16 {d12-d13}, [r8]!
        sub     r10, r10, #8
        b       2b
3:
#ifdef MUT_TAIL
        subs    r10, r10, #1
        ble     5f
#else
        cmp     r10, #0
        ble     5f
#endif
4:      ldr     ip, [r9], #4
        ldrh    lr, [r8]
        BLEND1
        strh    r3, [r8], #2
        subs    r10, r10, #1
        bgt     4b
5:      ldr     ip, [sp, #F_DS]
        add     r0, r0, ip
        ldr     ip, [sp, #F_SS]
        add     r4, r4, ip
        b       1b
9:      add     sp, sp, #FRAME
#ifdef MUT_SAVE
        vpop    {d8-d11}
#else
        vpop    {d8-d13}
#endif
        pop     {r4-r11, lr}
        bx      lr

@ ---------------------------------------------------------------------------
@ Table 1 idx 3/6/11-14 (stock C06FBC08): 8-bit index -> 32-bit premultiplied
@ LUT entry, then the same source-over.  The LUT lookup is scalar (no NEON
@ gather); eight entries go through the frame buffer into vld4.
nb_lut8_blend:
        cmp     r2, #8
        bge     10f
        @ < 8 pixels: scalar only, no VFP save
        push    {r4-r11, lr}
        ldr     r4, [r1, #0x24]
        ldr     r6, [r1, #0x1c]         @ stride already in bytes
        ldr     ip, [r3, #8]
        lsl     ip, ip, #1
        ldr     r5, [r3, #4]            @ LUT
        ldr     r7, [r3, #0xc]
        sub     sp, sp, #12
        str     ip, [sp]
        str     r2, [sp, #4]
1:      subs    r7, r7, #1
        bmi     9f
        mov     r8, r0
        mov     r9, r4
        ldr     r10, [sp, #4]
        cmp     r10, #0
        ble     5f
4:      ldrb    ip, [r9], #1
        ldr     ip, [r5, ip, lsl #2]
        ldrh    lr, [r8]
        BLEND1
        strh    r3, [r8], #2
        subs    r10, r10, #1
        bgt     4b
5:      ldr     ip, [sp]
        add     r0, r0, ip
        add     r4, r4, r6
        b       1b
9:      add     sp, sp, #12
        pop     {r4-r11, pc}
10:     ldr     ip, [r3, #0xc]
        cmp     ip, #0
        bxle    lr                      @ no rows: nothing to do
        push    {r4-r11, lr}
        vpush   {d8-d13}
        sub     sp, sp, #FRAME
        ldr     r4, [r1, #0x24]
        ldr     ip, [r1, #0x1c]         @ stride already in bytes
        str     ip, [sp, #F_SS]
        ldr     ip, [r3, #8]
        lsl     ip, ip, #1
        str     ip, [sp, #F_DS]
        bic     r2, r2, r2, asr #31
        str     r2, [sp, #F_W]
        ldr     r5, [r3, #4]            @ LUT
        ldr     r7, [r3, #0xc]
1:      subs    r7, r7, #1
        bmi     9f
        mov     r8, r0
        mov     r9, r4
        ldr     r10, [sp, #F_W]
2:      cmp     r10, #8
        blt     3f
        ldrb    r1, [r9], #1
        ldrb    r2, [r9], #1
        ldrb    r3, [r9], #1
        ldrb    r11, [r9], #1
        ldr     r1, [r5, r1, lsl #2]
        ldr     r2, [r5, r2, lsl #2]
        ldr     r3, [r5, r3, lsl #2]
        ldr     r11, [r5, r11, lsl #2]
        stm     sp, {r1, r2, r3, r11}
        ldrb    r1, [r9], #1
        ldrb    r2, [r9], #1
        ldrb    r3, [r9], #1
        ldrb    r11, [r9], #1
        ldr     r1, [r5, r1, lsl #2]
        ldr     r2, [r5, r2, lsl #2]
        ldr     r3, [r5, r3, lsl #2]
#ifdef MUT_LUT
        ldr     r11, [r5, r3, lsl #2]
#else
        ldr     r11, [r5, r11, lsl #2]
#endif
        add     r6, sp, #16
        stm     r6, {r1, r2, r3, r11}
        vld4.8  {d0-d3}, [sp]
        vld1.16 {d4-d5}, [r8]
        BLEND8
        vst1.16 {d12-d13}, [r8]!
        sub     r10, r10, #8
        b       2b
3:      cmp     r10, #0
        ble     5f
4:      ldrb    ip, [r9], #1
        ldr     ip, [r5, ip, lsl #2]
        ldrh    lr, [r8]
        BLEND1
        strh    r3, [r8], #2
        subs    r10, r10, #1
        bgt     4b
5:      ldr     ip, [sp, #F_DS]
        add     r0, r0, ip
        ldr     ip, [sp, #F_SS]
        add     r4, r4, ip
        b       1b
9:      add     sp, sp, #FRAME
        vpop    {d8-d13}
        pop     {r4-r11, lr}
        bx      lr

@ ---------------------------------------------------------------------------
@ Table 1 idx 7 (stock C06FBCD8): ARGB4444 source (fmt 0x10011, e.g. the
@ font_M_* timecode digits) source-over ARGB4444.  The dispatcher (C06E0A94)
@ puts this one span in BOTH the opaque-run and the blend-run slot, so it also
@ draws every opaque run of a glyph.  Stock expands each nibble to n*17 and
@ blends every pixel (41 instructions/pixel, no shortcuts).  Exact identities
@ of that formula used here:
@   s == 0      -> destination unchanged  ((n*17)>>4 == n, ia = 256)
@   s >= 0xF000 -> destination = s        (ia = 0, (n*17)>>4 == n)
@ Short calls (< NB_A4_NEON pixels) never touch VFP; the scalar blend core is
@ the same 33 instructions as stock, and the skip/copy test costs 3, so a blend
@ pixel costs what stock costs and a transparent/opaque pixel far less.
        .equ    NB_A4_NEON, 16

@ in: r1 = source pixel, lr = destination pixel.  out: r3.
@ clobbers r2, r5, r11, ip.  Same arithmetic as stock C06FBD00..C06FBD86.
        .macro  A4BLEND1
        ubfx    r2, r1, #12, #4
        orr     r2, r2, r2, lsl #4      @ A8
        add     r11, r2, r2, lsr #7
        rsb     r11, r11, #256          @ ia
        ubfx    ip, lr, #8, #4          @ R
        orr     ip, ip, ip, lsl #4
        mul     ip, r11, ip
        ubfx    r5, r1, #8, #4
        orr     r5, r5, r5, lsl #4
        add     ip, r5, ip, lsr #8
        lsr     ip, ip, #4
        lsl     r3, ip, #8
        ubfx    ip, lr, #4, #4          @ G
        orr     ip, ip, ip, lsl #4
        mul     ip, r11, ip
        and     r5, r1, #0xF0
        orr     r5, r5, r5, lsr #4
        add     ip, r5, ip, lsr #8
        bic     ip, ip, #15
        orr     r3, r3, ip
        and     ip, lr, #15             @ B
        orr     ip, ip, ip, lsl #4
        mul     ip, r11, ip
        and     r5, r1, #15
#ifdef MUT_A4T
        orr     r5, r5, r5, lsl #3
#else
        orr     r5, r5, r5, lsl #4
#endif
        add     ip, r5, ip, lsr #8
        orr     r3, r3, ip, lsr #4
        lsr     ip, lr, #12             @ A
        orr     ip, ip, ip, lsl #4
        mul     ip, r11, ip
        add     ip, r2, ip, lsr #8
        lsr     ip, ip, #4
        orr     r3, r3, ip, lsl #12
        .endm

@ One row of the scalar path: r9 src, r8 dst, r10 count (> 0).  Clobbers
@ r1-r3, r5, r11, ip, lr.  Falls out at 5:
        .macro  A4ROW
4:      ldrh    r1, [r9], #2
        cmp     r1, #0xF000             @ C = (s >= 0xF000)
        rsbscc  r2, r1, #0              @ else C = (s == 0)
        bcs     6f
        ldrh    lr, [r8]
        A4BLEND1
        strh    r3, [r8], #2
        subs    r10, r10, #1
        bgt     4b
        b       5f
6:      cmp     r1, #0
#ifdef MUT_A4S
        strh    r1, [r8], #2
#else
        strhne  r1, [r8], #2            @ A == F: copy
        addeq   r8, r8, #2              @ s == 0: keep destination
#endif
        subs    r10, r10, #1
        bgt     4b
5:
        .endm

nb_a4_blend:
        ldr     ip, [r3, #0xc]
        cmp     ip, #0
        bxle    lr                      @ no rows
        push    {r4-r11, lr}
        ldr     r4, [r1, #0x24]         @ src row
        ldr     r6, [r1, #0x1c]
        lsl     r6, r6, #1              @ src stride bytes
        ldr     ip, [r3, #8]
        lsl     ip, ip, #1
        ldr     r7, [r3, #0xc]          @ rows
        bic     r2, r2, r2, asr #31     @ width<0 -> 0
        cmp     r2, #NB_A4_NEON
        bhs     20f
        sub     sp, sp, #12             @ 36 + 12: 8-aligned frame
        str     ip, [sp]                @ dst stride bytes
        str     r2, [sp, #4]
1:      subs    r7, r7, #1
        bmi     9f
        mov     r8, r0
        mov     r9, r4
        ldr     r10, [sp, #4]
        cmp     r10, #0
        ble     2f
        A4ROW
2:      ldr     ip, [sp]
        add     r0, r0, ip
        add     r4, r4, r6
        b       1b
9:      add     sp, sp, #12
        pop     {r4-r11, pc}

@ Wide calls: groups of 8 through NEON.  A group whose 8 source pixels are all
@ 0 is skipped, one whose alphas are all F is copied, else BLEND8.
20:     vpush   {d8-d13}
        sub     sp, sp, #12
        str     ip, [sp]
        str     r2, [sp, #4]
21:     subs    r7, r7, #1
        bmi     29f
        mov     r8, r0
        mov     r9, r4
        ldr     r10, [sp, #4]
22:     cmp     r10, #8
        blt     24f
        vld1.16 {d4-d5}, [r9]!          @ 8 source pixels
        vorr    d6, d4, d5
        vmov    r1, r2, d6
        orrs    r1, r1, r2
        beq     23f                     @ all 0: keep destination
        vshrn.u16 d7, q2, #8            @ hi byte: A<<4 | R
        vmov    r1, r2, d7
        and     r1, r1, r2
        ldr     r2, =0xF0F0F0F0
        bics    r1, r2, r1              @ 0 <=> every alpha nibble is F
        bne     25f
        vst1.16 {d4-d5}, [r8]           @ all A == F: copy
        b       23f
25:     vmovn.u16 d6, q2                @ lo byte: G<<4 | B
        vshl.i8 d2, d6, #4
        vsri.8  d2, d2, #4              @ B*17
        vshr.u8 d1, d6, #4
        vsli.8  d1, d1, #4              @ G*17
        vshl.i8 d0, d7, #4
#ifdef MUT_A4
        vsri.8  d0, d0, #3
#else
        vsri.8  d0, d0, #4              @ R*17
#endif
        vshr.u8 d3, d7, #4
        vsli.8  d3, d3, #4              @ A*17
        vld1.16 {d4-d5}, [r8]
        BLEND8
        vst1.16 {d12-d13}, [r8]
23:     add     r8, r8, #16
        sub     r10, r10, #8
        b       22b
24:     cmp     r10, #0
        ble     26f
        A4ROW
26:     ldr     ip, [sp]
        add     r0, r0, ip
        add     r4, r4, r6
        b       21b
29:     add     sp, sp, #12
        vpop    {d8-d13}
        pop     {r4-r11, lr}
        bx      lr
        .ltorg

@ ---------------------------------------------------------------------------
@ Table 1 idx 1 (stock C06FBBA8): opaque RGBA8888 -> ARGB4444 conversion.
@ out = (G & 0xf0) | (R>>4)<<8 | B>>4 | (A>>4)<<12
nb_p32_opaque:
        push    {r4-r10, lr}
        ldr     r4, [r1, #0x24]
        ldr     r5, [r1, #0x1c]
        lsl     r5, r5, #2
        ldr     r6, [r3, #8]
        lsl     r6, r6, #1
        ldr     r7, [r3, #0xc]
        subs    r7, r7, #1
        bmi     9f                      @ no rows
        cmp     r2, #8
        bge     12f
        cmp     r2, #0                  @ width <= 0: nothing is written
        ble     9f
@ < 8 pixels: scalar rows, loop test at the bottom (stock's row overhead)
1:      mov     r8, r0
        mov     r9, r4
        mov     r10, r2
4:      ldr     ip, [r9], #4
        ubfx    r1, ip, #8, #8
        bic     r1, r1, #15
        ubfx    r3, ip, #4, #4
        orr     r1, r1, r3, lsl #8
        ubfx    r3, ip, #16, #8
        orr     r1, r1, r3, lsr #4
        lsr     r3, ip, #28
        orr     r1, r1, r3, lsl #12
        strh    r1, [r8], #2
        subs    r10, r10, #1
        bgt     4b
        add     r0, r0, r6
        add     r4, r4, r5
8:      subs    r7, r7, #1
        bpl     1b
9:      pop     {r4-r10, pc}
@ >= 8 pixels
11:     subs    r7, r7, #1
        bmi     9b
12:     mov     r8, r0
        mov     r9, r4
        mov     r10, r2
2:      cmp     r10, #8
        blt     3f
        vld4.8  {d0-d3}, [r9]!
        vsri.8  d1, d2, #4              @ lo byte: G&0xf0 | B>>4
#ifdef MUT_OPQ
        vsri.8  d3, d0, #3
#else
        vsri.8  d3, d0, #4              @ hi byte: A&0xf0 | R>>4
#endif
        vst2.8  {d1, d3}, [r8]!
        sub     r10, r10, #8
        b       2b
3:      cmp     r10, #0
        ble     5f
4:      ldr     ip, [r9], #4
        ubfx    r1, ip, #8, #8
        bic     r1, r1, #15
        ubfx    r3, ip, #4, #4
        orr     r1, r1, r3, lsl #8
        ubfx    r3, ip, #16, #8
        orr     r1, r1, r3, lsr #4
        lsr     r3, ip, #28
        orr     r1, r1, r3, lsl #12
        strh    r1, [r8], #2
        subs    r10, r10, #1
        bgt     4b
5:      add     r0, r0, r6
        add     r4, r4, r5
        b       11b

@ ---------------------------------------------------------------------------
@ Table 1 idx 2 (stock C06FC038): RGB565 -> ARGB4444, alpha forced to 0xF.
@ out = 0xF000 | (s>>12)<<8 | ((s>>7)&15)<<4 | (s>>1)&15
nb_565_opaque:
        push    {r4-r10, lr}
        ldr     r4, [r1, #0x24]
        ldr     r5, [r1, #0x1c]
        lsl     r5, r5, #1
        ldr     r6, [r3, #8]
        lsl     r6, r6, #1
        ldr     r7, [r3, #0xc]
        subs    r7, r7, #1
        bmi     9f                      @ no rows
        cmp     r2, #8
        bge     12f
        cmp     r2, #0                  @ width <= 0: nothing is written
        ble     9f
1:      mov     r8, r0
        mov     r9, r4
        mov     r10, r2
4:      ldrh    ip, [r9], #2
        lsr     r3, ip, #12
        lsl     r3, r3, #8
        orr     r3, r3, #0xf000
        lsr     r1, ip, #3
        and     r1, r1, #0xf0
        orr     r3, r3, r1
        ubfx    r1, ip, #1, #4
        orr     r3, r3, r1
        strh    r3, [r8], #2
        subs    r10, r10, #1
        bgt     4b
        add     r0, r0, r6
        add     r4, r4, r5
8:      subs    r7, r7, #1
        bpl     1b
9:      pop     {r4-r10, pc}
11:     subs    r7, r7, #1
        bmi     9b
12:     mov     r8, r0
        mov     r9, r4
        mov     r10, r2
2:      cmp     r10, #8
        blt     3f
        vld1.16 {d0-d1}, [r9]!
        vshl.u16 q1, q0, #11
        vshr.u16 q1, q1, #12            @ B4 = s[4:1]
        vshl.u16 q2, q0, #5
        vshr.u16 q2, q2, #12            @ G4 = s[10:7]
        vsli.16 q1, q2, #4
        vshr.u16 q2, q0, #12            @ R4 = s[15:12]
#ifdef MUT_565
        vorr.i16 q2, #0x70
#else
        vorr.i16 q2, #0xf0
#endif
        vsli.16 q1, q2, #8
        vst1.16 {d2-d3}, [r8]!
        sub     r10, r10, #8
        b       2b
3:      cmp     r10, #0
        ble     5f
4:      ldrh    ip, [r9], #2
        lsr     r3, ip, #12
        lsl     r3, r3, #8
        orr     r3, r3, #0xf000
        lsr     r1, ip, #3
        and     r1, r1, #0xf0
        orr     r3, r3, r1
        ubfx    r1, ip, #1, #4
        orr     r3, r3, r1
        strh    r3, [r8], #2
        subs    r10, r10, #1
        bgt     4b
5:      add     r0, r0, r6
        add     r4, r4, r5
        b       11b

@ ---------------------------------------------------------------------------
@ Layer fill (replaces the vtable slot that holds stock C0721480, ARM).
@ Only the 16bpp case ([layer+0x1c] == 1, stock C0722490) is replaced; every
@ other format tail-calls the stock function untouched.  Mirrors the stock
@ sequence: vcall +0x30 (bail if 0), vcall +0x10, buffer = [ret+4],
@ size = ((16*w) >> 3) * h with w = [layer+4], h = [layer+8], then store the
@ low half of r1 at every halfword from buffer while p < buffer+size
@ (unsigned).  Returns the end pointer in r0 like the stock path.
nb_layer_fill:
        ldr     ip, [r0, #0x1c]
        cmp     ip, #1
        ldrne   pc, =0xC0721480         @ not 16bpp: stock, untouched
        push    {r4-r8, lr}
        mov     r4, r0
        mov     r6, r1
        ldr     ip, [r4]
        ldr     ip, [ip, #0x30]
        blx     ip
        cmp     r0, #0
        beq     9f                      @ stock returns r0 = 0 here
        mov     r0, r4
        ldr     ip, [r4]
        ldr     ip, [ip, #0x10]
        blx     ip
        ldr     r7, [r0, #4]            @ buffer
        ldr     r1, [r4, #4]
        lsl     r1, r1, #4
        lsr     r1, r1, #3              @ (16*w) >> 3
        ldr     r2, [r4, #8]
        mul     r1, r2, r1
        add     r8, r7, r1              @ end
        uxth    r6, r6
        @ halfwords to write = ceil((end - p) / 2) while p < end
        mov     r0, r7
        cmp     r0, r8
        bhs     8f
        sub     r2, r8, r0
        add     r2, r2, #1
        lsr     r2, r2, #1              @ count
#ifdef MUT_FILL
        sub     r2, r2, #1
#endif
        @ scalar head until 16-byte aligned (or done)
1:      tst     r0, #15
        beq     2f
        cmp     r2, #0
        beq     8f
        strh    r6, [r0], #2
        sub     r2, r2, #1
        b       1b
2:      vdup.16 q0, r6
        vmov    q1, q0
3:      cmp     r2, #32
        blt     4f
        vst1.16 {d0-d3}, [r0]!
        vst1.16 {d0-d3}, [r0]!
        sub     r2, r2, #32
        b       3b
4:      cmp     r2, #8
        blt     5f
        vst1.16 {d0-d1}, [r0]!
        sub     r2, r2, #8
        b       4b
5:      cmp     r2, #0
        beq     8f
        strh    r6, [r0], #2
        sub     r2, r2, #1
        b       5b
8:      mov     r0, r8                  @ stock leaves the end pointer in r0
9:      pop     {r4-r8, lr}
        bx      lr
        .ltorg
