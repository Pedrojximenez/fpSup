@ waveform.S — faster, bit-identical replacement for the brightness waveform
@ drawer (HistogramDrawerWaveForm).  Stock method C05A3728 is reached through
@ three vtable slots (0xC2DF8F4C, 0xC2DF8FE4, 0xC2DF9220); wf_method replaces it.
@
@ Stock method (ARM):
@   C0529D98(ctx, this+8, [this+0x18]); memcpy(tab, 0xC2DF8954, 0x528);
@   if (C05A34B8(this, img, tab)) C05A35A0(this, ctx, tab);
@ C05A34B8 samples V=[this+0x74] rows x 330 luma bytes into [this+0x30].
@ C05A35A0 builds, per screen column, a 256-bin histogram of one sample column
@ and calls C0529D10(ctx, &pt, level+16) for every display row whose bin count
@ is non-zero (level = first j with thr[j] >= count, thr = [this+0x34..0x70]).
@
@ What is faster here (output and the C0529D10 call sequence are identical):
@  - sampling: 4 samples per iteration (ldm of indices), no per-element movw/cmp
@  - counting: two interleaved histograms (no load/store dependency chain)
@  - per-point level search memoised per call (count <= V <= 256)
@  - histogram clear inline NEON (q0 only), dead 1 KiB template memcpy dropped
@ Guards: V outside 1..256 or H > 330 (stock would index outside its own buffers) or
@ the enable word 0 -> tail-call the stock method.
@
@ VFP/NEON: only s0-s3 / q0 (d0-d1), like the stock code; d16-d31 never touched.
@ Mutations (test only): MUT_HB, MUT_LEVEL, MUT_Y, MUT_TAIL, MUT_MEMO, MUT_STEP,
@ MUT_ODD.

        .syntax unified
        .arm
        .fpu    neon
        .arch_extension idiv
        .text

        .global wf_ctl, wf_method, wf_sample, wf_draw

        .equ    F_GETADDR, 0xC0023030
        .equ    F_SETUP,   0xC0529D98
        .equ    F_MEMCPY,  0xC001510C
        .equ    F_POINT,   0xC0529D10
        .equ    F_STOCK,   0xC05A3728
        .equ    TAB_SRC,   0xC2DF8954

@ ---------------------------------------------------------------------------
@ control block: +0 'WAVE', +4 enable, +8 calls (fast), +12 fallbacks
        .align  3
wf_ctl:
.Lctl:
        .ascii  "WAVE"
        .word   1
        .word   0
        .word   0

@ ---------------------------------------------------------------------------
wf_method:
        adr     ip, .Lctl
        ldr     r3, [ip, #4]
        cmp     r3, #0
        beq     .Lfb
        ldr     r3, [r0, #0x74]
        sub     r3, r3, #1
        cmp     r3, #255                @ V in 1..256
        bhi     .Lfb_cnt
        ldr     r3, [r0, #0x28]
        movw    ip, #330
        cmp     r3, ip
        adr     ip, .Lctl
        bhi     .Lfb_cnt
        ldr     r3, [ip, #8]
        add     r3, r3, #1
        str     r3, [ip, #8]

        push    {r4, r5, r6, lr}
        movw    ip, #0x528
        sub     sp, sp, ip
        mov     r4, r0
        mov     r5, r1
        mov     r6, r2
        ldr     r2, [r0, #0x18]
        mov     r0, r1
        add     r1, r4, #8
        ldr     ip, =F_SETUP
        blx     ip
        ldr     r1, =TAB_SRC
        movw    r2, #0x528
        mov     r0, sp
        ldr     ip, =F_MEMCPY
        blx     ip
        mov     r2, sp
        mov     r1, r6
        mov     r0, r4
        bl      wf_sample
        cmp     r0, #0
        beq     7f
        mov     r2, sp
        mov     r1, r5
        mov     r0, r4
        bl      wf_draw
7:
        movw    r0, #0x528              @ stock returns 0x528 (sp adjust left in r0)
        add     sp, sp, r0
        pop     {r4, r5, r6, pc}

.Lfb_cnt:
        ldr     r3, [ip, #12]
        add     r3, r3, #1
        str     r3, [ip, #12]
.Lfb:
        ldr     ip, =F_STOCK
        bx      ip

@ ---------------------------------------------------------------------------
@ wf_sample(r0 = this, r1 = img, r2 = tab[330])  == C05A34B8
wf_sample:
.Lsample:
        push    {r4-r11, lr}
        sub     sp, sp, #4
        mov     r5, r0
        mov     r4, r1
        mov     r6, r2
        ldr     r0, [r1, #0x1c]
        ldr     ip, =F_GETADDR
        blx     ip
        mov     r3, r0
        ldr     r0, [r4, #0x1c]
        cmp     r0, #0
        beq     .Lws_ret                @ r0 = 0
        ldr     r0, [r4, #0x10]
        ldr     r1, =0x634C0635
        lsl     r0, r0, #16
        umull   r1, r2, r0, r1
        lsr     r2, r2, #8
#ifdef MUT_STEP
        add     r2, r2, #1
#endif
        mov     r0, #0
        mov     r1, r6
        movw    ip, #(330 * 4)
        add     ip, r6, ip
1:      lsr     lr, r0, #16
        str     lr, [r1], #4
        add     r0, r0, r2
        cmp     r1, ip
        blo     1b

        ldr     r1, [r4]
        ldr     r0, [r4, #0xc]
        ldr     r2, [r4, #8]
        mla     r0, r1, r0, r2
        lsr     r0, r0, #1
        add     r7, r3, r0, lsl #2      @ r7 = first pixel pair
        ldr     r1, [r5, #0x74]         @ V
        ldr     r2, [r5, #0x30]         @ destination rows
        mov     r0, #0
.Lws_row:
        cmp     r0, r1
        bhs     .Lws_done
        ldr     r3, [r4, #0x14]
        mul     r3, r0, r3
        udiv    r1, r3, r1
        ldr     ip, [r4]
        lsr     ip, ip, #1
        mul     ip, ip, r1
        add     ip, r7, ip, lsl #2      @ source row
        mov     r3, r2                  @ dst
        mov     lr, r6                  @ index table
        add     r1, r6, #(328 * 4)      @ 82 groups of 4, then 2
2:      ldm     lr!, {r8, r9, r10, r11}
        ldrb    r8, [ip, r8, lsl #2]
        ldrb    r9, [ip, r9, lsl #2]
        ldrb    r10, [ip, r10, lsl #2]
        ldrb    r11, [ip, r11, lsl #2]
        cmp     lr, r1
        strb    r8, [r3], #1
        strb    r9, [r3], #1
        strb    r10, [r3], #1
        strb    r11, [r3], #1
        blo     2b
#ifndef MUT_TAIL
        ldm     lr!, {r8, r9}
        ldrb    r8, [ip, r8, lsl #2]
        ldrb    r9, [ip, r9, lsl #2]
        strb    r8, [r3], #1
        strb    r9, [r3], #1
#endif
        ldr     r1, [r5, #0x74]
        add     r2, r2, #0x148
        add     r2, r2, #2
        add     r0, r0, #1
        b       .Lws_row
.Lws_done:
        mov     r0, #1
.Lws_ret:
        add     sp, sp, #4
        pop     {r4-r11, pc}

@ ---------------------------------------------------------------------------
@ wf_draw(r0 = this, r1 = ctx, r2 = tab)  == C05A35A0
@ frame: [sp] pt.x, [sp+4] pt.y, [sp+8..] memo[257] (0xFF = unknown),
@        [sp+272] histogram A (256 words), [sp+1296] histogram B (256 words)
        .equ    MEMO, 8
        .equ    HA, 272
        .equ    HB, 1296
        .equ    FRAME, 2320
wf_draw:
.Ldraw_fn:
        push    {r4-r11, lr}
        sub     sp, sp, #FRAME
        mov     r4, r0
        mov     r6, r1
        mov     r5, r2
        @ display row -> bin table, exactly as stock (VFP s0-s3)
        ldr     r1, [r0, #0x28]
        ldr     r0, [r0, #0x74]
        sub     r0, r0, #1
        vmov    s0, r0
        sub     r0, r1, #1
        vmov    s2, r0
        vcvt.f32.u32 s0, s0
        vcvt.f32.s32 s2, s2
        mov     r0, #0
        cmp     r0, r1
        vmov    s1, r0                  @ +0.0
        vdiv.f32 s0, s0, s2
        bge     2f
1:      vcvt.u32.f32 s3, s1
        vmov    r2, s3
        vadd.f32 s1, s1, s0
        str     r2, [r5, r0, lsl #2]
        ldr     r1, [r4, #0x28]
        add     r0, r0, #1
        cmp     r0, r1
        blt     1b
2:
        @ memo := 0xFF (257 bytes)
#ifndef MUT_MEMO
        vmov.i8 q0, #0xff
        add     r1, sp, #MEMO
        mov     r2, #16
3:      vst1.8  {d0, d1}, [r1]!
        subs    r2, r2, #1
        bne     3b
        mvn     r2, #0
        strb    r2, [r1]
#endif

        add     r8, sp, #HA
        add     r9, sp, #HB
        ldr     r0, [r4, #0x24]         @ W
        mov     sl, #0
        cmp     sl, r0
        bge     .Ldone
.Lcol:
        movw    r1, #0x149
        mul     r1, sl, r1
        sub     r2, r0, #1
        udiv    r7, r1, r2
        @ clear both histograms (2 KiB)
        vmov.i32 q0, #0
        mov     r1, r8
        mov     r2, #16
4:      vst1.32 {d0, d1}, [r1]!
        vst1.32 {d0, d1}, [r1]!
        vst1.32 {d0, d1}, [r1]!
        vst1.32 {d0, d1}, [r1]!
        vst1.32 {d0, d1}, [r1]!
        vst1.32 {d0, d1}, [r1]!
        vst1.32 {d0, d1}, [r1]!
        vst1.32 {d0, d1}, [r1]!
        subs    r2, r2, #1
        bne     4b
        @ count one sample column
        ldr     r1, [r4, #0x74]
        ldr     r0, [r4, #0x30]
        cmp     r1, #0
        add     r2, r7, r0
        beq     .Lcnt_done
        movw    r3, #0x14a
.Lcnt2:
        subs    r1, r1, #2
        blo     .Lcnt_odd
        ldrb    r0, [r2], r3
        ldrb    ip, [r2], r3
        ldr     lr, [r8, r0, lsl #2]
#ifdef MUT_HB
        ldr     r11, [r8, ip, lsl #2]
#else
        ldr     r11, [r9, ip, lsl #2]
#endif
        add     lr, lr, #1
        add     r11, r11, #1
        str     lr, [r8, r0, lsl #2]
#ifdef MUT_HB
        str     r11, [r8, ip, lsl #2]
#else
        str     r11, [r9, ip, lsl #2]
#endif
        b       .Lcnt2
.Lcnt_odd:
#ifndef MUT_ODD
        tst     r1, #1
        beq     .Lcnt_done
        ldrb    r0, [r2], r3
        ldr     lr, [r8, r0, lsl #2]
        add     lr, lr, #1
        str     lr, [r8, r0, lsl #2]
#endif
.Lcnt_done:
        @ draw this column
        ldr     r0, [r4, #0x1c]
        ldr     r2, [r4, #0x20]
        ldr     r1, [r4, #0x28]
        mov     r7, #0
        add     r0, sl, r0
        stm     sp, {r0, r7}
        add     r0, r1, r2
        cmp     r7, r1
        sub     fp, r0, #1
        bge     .Lcol_next
.Ldraw:
        ldr     r0, [r5, r7, lsl #2]
        ldr     r2, [r8, r0, lsl #2]
        ldr     r3, [r9, r0, lsl #2]
        adds    r0, r2, r3
        bne     .Lpoint
.Ldraw_next:
        add     r7, r7, #1
        cmp     r7, r1
        blt     .Ldraw
.Lcol_next:
        ldr     r0, [r4, #0x24]
        add     sl, sl, #1
        cmp     sl, r0
        blt     .Lcol
.Ldone:
        mov     r0, #1
        add     sp, sp, #FRAME
        pop     {r4-r11, pc}

.Lpoint:                                @ r0 = count (1..V)
        add     r3, sp, #MEMO
        ldrb    r2, [r3, r0]
        cmp     r2, #0xff
        bne     6f
        mov     r2, #0
5:      add     ip, r4, r2, lsl #2
        ldr     ip, [ip, #0x34]
        cmp     ip, r0
#ifdef MUT_LEVEL
        addls   r2, r2, #1
        cmpls   r2, #0x10
        bls     5b
#else
        addlo   r2, r2, #1
        cmplo   r2, #0x10
        blo     5b
#endif
        strb    r2, [r3, r0]
6:
#ifdef MUT_Y
        sub     ip, fp, r7
        add     ip, ip, #1
#else
        sub     ip, fp, r7
#endif
        str     ip, [sp, #4]
        mov     r0, r6
        mov     r1, sp
        add     r2, r2, #0x10
        ldr     ip, =F_POINT
        blx     ip
        ldr     r1, [r4, #0x28]
        b       .Ldraw_next

        .ltorg
wf_end:
