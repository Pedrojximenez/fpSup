@ dirtyclean -- replace the whole-cache flush after each UI redraw round.
@
@ Stock: C0528700 (DrawController redraw round) calls C000E91C once if any of
@ its 4 slots drew: L1+L2 set/way clean+invalidate with IRQ and FIQ masked.
@ Here: when every drawn slot holds only UIC drawers, clean (DCCMVAC, IRQs
@ left on) just the rows UIC rendered into that slot's back buffer.  Any
@ other case tail-calls C000E91C exactly as stock.  See README.md.
@
@ Three entries, reached through 8-byte veneers in the cave (BL range):
@   dc_clean       replaces  bl C000E91C  at C0528954
@   dc_clear_hook  replaces  bl C0528B40  at C05287F4  (slot = r5)
@   dc_copy_hook   replaces  bl C0528BA0  at C0528AE0  (slot = r6)
@ Position independent; control block at offset 0.

        .syntax unified
        .arm
        .text

        .equ MAGIC,        0x434C4344      @ 'DCLC'
        .equ FW_FLUSH,     0xC000E91C
        .equ FW_CLEAR,     0xC0528B40
        .equ FW_COPY,      0xC0528BA0
        .equ FW_BYTES,     0xC0721110      @ (pixels, fmt) -> bytes
        .equ RET_SITE,     0xC0528958      @ lr when called from C0528954
        .equ UIC_MGR,      0xC37B7048      @ C055F0F0() = 0xC37B7034+0x14 (was 0xC37B7034: wrong)
        .equ UIC_RECS,     0x18            @ 10 records x 0x20: +4 base, +8 x,y,w,h
        .equ UIC_NREC,     10
        .equ MAX_BYTES,    0x00800000

        @ control block offsets
        .equ C_EN,     0x04
        .equ C_CLEAR,  0x08     @ slots cleared (C0528B40) this round
        .equ C_COPY,   0x0C     @ slots whose back buffer was memcpy'd (C0528BA0)
        .equ C_CALLS,  0x10
        .equ C_FAST,   0x14
        .equ C_FALL,   0x18
        .equ C_LINES,  0x1C
        .equ C_WHY,    0x20     @ last fallback reason
        .equ C_FULLS,  0x24     @ slots cleaned whole (need_full) on the fast path

        .global dc_ctl
dc_ctl:
ctl:
        .word MAGIC
        .word 1                 @ C_EN
        .word 0, 0, 0, 0, 0, 0, 0, 0
        .space 0x40 - 0x28

@ -------------------------------------------------- mark-and-forward hooks
@ Only r3 and ip are scratch: r0-r2 are the forwarded arguments.
        .global dc_clear_hook
dc_clear_hook:
        adr     ip, ctl
        ldr     r3, [ip, #C_CLEAR]
        cmp     r5, #0
        orreq   r3, r3, #1
        cmp     r5, #1
        orreq   r3, r3, #2
        cmp     r5, #2
        orreq   r3, r3, #4
        cmp     r5, #3
        orreq   r3, r3, #8
        str     r3, [ip, #C_CLEAR]
        ldr     pc, 1f
1:      .word FW_CLEAR

        .global dc_copy_hook
dc_copy_hook:
        adr     ip, ctl
        ldr     r3, [ip, #C_COPY]
        cmp     r6, #0
        orreq   r3, r3, #1
        cmp     r6, #1
        orreq   r3, r3, #2
        cmp     r6, #2
        orreq   r3, r3, #4
        cmp     r6, #3
        orreq   r3, r3, #8
        str     r3, [ip, #C_COPY]
        ldr     pc, 1f
1:      .word FW_COPY


@ ---------------------------------------------------------------- dc_clean
@ in:  r4 = DrawController (callee-saved in C0528700), lr = RET_SITE,
@      [sp+0x18..0x1B] = per-slot "drew" bytes of C0528700's frame.
        .global dc_clean
dc_clean:
        push    {r4-r11, lr}
        mov     r11, sp                 @ caller sp = r11 + 36
        bic     sp, sp, #7
        sub     sp, sp, #16             @ [sp]=height [sp+4]=stride [sp+8]=fmt [sp+12]=width
        adr     r10, ctl
        ldr     r0, [r10, #C_CALLS]
        add     r0, r0, #1
        str     r0, [r10, #C_CALLS]

        mov     r0, #1
        ldr     r1, [r10, #C_EN]
        cmp     r1, #0
        beq     fallback
        mov     r0, #2
        ldr     r1, [r11, #32]          @ saved lr
        ldr     r2, =RET_SITE
        cmp     r1, r2
        bne     fallback
        add     r9, r11, #36            @ C0528700's sp

        @ pass 1: only UIC drawers and a SurfacePixel layer in every drawn slot
        mov     r5, #0
1:      add     r0, r9, #0x18
        ldrb    r0, [r0, r5]
        cmp     r0, #0
        beq     3f
        add     r6, r5, r5, lsl #1
        add     r6, r4, r6, lsl #2      @ ctrl + s*12: three drawer pointers
        mov     r7, #0
2:      ldr     r0, [r6, r7, lsl #2]
        cmp     r0, #0
        beq     21f
        ldr     r0, [r0]
        ldr     r1, =0xC0D17780
        cmp     r0, r1
        ldrne   r1, =0xC2E45DF8
        cmpne   r0, r1
        movne   r0, #3
        bne     fallback
21:     add     r7, r7, #1
        cmp     r7, #3
        blt     2b
        add     r6, r4, #0x58
        ldr     r6, [r6, r5, lsl #3]    @ layer
        mov     r0, #4
        cmp     r6, #0
        beq     fallback
        ldr     r1, [r6]
        ldr     r2, =0xC2EF6280
        cmp     r1, r2
        ldrne   r2, =0xC2E38E5C
        cmpne   r1, r2
        bne     fallback
3:      add     r5, r5, #1
        cmp     r5, #4
        blt     1b

        @ line size from CTR.DminLine
        mrc     p15, 0, r0, c0, c0, 1
        ubfx    r0, r0, #16, #4
        mov     r7, #4
        lsl     r7, r7, r0

        @ pass 2: clean
        mov     r5, #0
10:     add     r0, r9, #0x18
        ldrb    r0, [r0, r5]
        cmp     r0, #0
        beq     19f
        add     r6, r4, #0x58
        ldr     r6, [r6, r5, lsl #3]
        mov     r0, r6
        ldr     r1, [r6]
        ldr     r1, [r1, #0x10]         @ getBuffer -> desc
        blx     r1
        mov     r1, r0
        mov     r0, #5
        cmp     r1, #0
        beq     fallback
        ldr     r8, [r1, #4]            @ back-buffer base
        ldr     r2, [r1, #8]
        cmp     r2, #0
        beq     fallback
        ldr     r2, [r2, #4]            @ height
        str     r2, [sp]
        mov     r0, #6
        cmp     r8, #0xC0000000         @ cached view only
        blo     fallback
        mov     r0, r6
        mov     r1, #0
        ldr     r2, [r6]
        ldr     r2, [r2, #0x28]         @ stride = pixelsToBytes(width)
        blx     r2
        str     r0, [sp, #4]
        ldr     r1, [sp]
        mul     r2, r0, r1              @ size
        mov     r0, #7
        cmp     r2, #0
        beq     fallback
        cmp     r2, #MAX_BYTES
        bhi     fallback
        ldr     r0, [r6, #0x1c]
        str     r0, [sp, #8]
        ldr     r0, [r6, #4]
        str     r0, [sp, #12]

        @ need_full if this slot was cleared or memcpy'd
        ldr     r0, [r10, #C_CLEAR]
        ldr     r1, [r10, #C_COPY]
        orr     r0, r0, r1
        lsr     r0, r0, r5
        tst     r0, #1
        bne     15f

        @ UIC record for this buffer
        ldr     r3, =UIC_MGR + UIC_RECS
        mov     r2, #UIC_NREC
11:     ldr     r0, [r3, #4]
        cmp     r0, r8
        beq     12f
        add     r3, r3, #0x20
        subs    r2, r2, #1
        bne     11b
        b       15f
12:     ldr     r0, [r3, #8]            @ x
        ldr     r1, [r3, #12]           @ y
        ldr     r2, [r3, #16]           @ w
        ldr     r3, [r3, #20]           @ h
        cmp     r2, #0
        ble     15f
        cmp     r3, #0
        ble     15f
        cmp     r0, #0                  @ clamp x
        addlt   r2, r2, r0
        movlt   r0, #0
        cmp     r1, #0                  @ clamp y
        addlt   r3, r3, r1
        movlt   r1, #0
        ldr     ip, [sp, #12]
        sub     ip, ip, r0
        cmp     r2, ip
        movgt   r2, ip
        ldr     ip, [sp]
        sub     ip, ip, r1
        cmp     r3, ip
        movgt   r3, ip
        cmp     r2, #0
        ble     15f
        cmp     r3, #0
        ble     15f
        @ rows y .. y+h-1, bytes [bx0, bx1+1)
        push    {r1, r3}                @ y, h  (sp stays 8-aligned)
        add     r2, r0, r2              @ x+w
        push    {r0, r2}
        ldr     r1, [sp, #16 + 8]       @ fmt
        bl      call_bytes              @ r0 = bytes(x)
        mov     r6, r0
        ldr     r0, [sp, #4]
        ldr     r1, [sp, #16 + 8]
        bl      call_bytes              @ r0 = bytes(x+w)
        add     r3, r0, #1
        pop     {r0, r2}
        pop     {r1, r2}                @ r1 = y, r2 = h
        ldr     ip, [sp, #4]            @ stride
        mla     r1, r1, ip, r8          @ row base
        sub     r0, r3, r6              @ row span >= half the stride: one range
        cmp     ip, r0, lsl #1
        bhi     13f
        add     r0, r1, r6
        sub     r2, r2, #1
        mla     r1, r2, ip, r1          @ last row base
        add     r1, r1, r3
        bl      clean_range
        b       19f
13:     add     r0, r1, r6
        push    {r1, r2}
        add     r1, r1, r3
        bl      clean_range
        pop     {r1, r2}
        ldr     ip, [sp, #4]
        add     r1, r1, ip
        subs    r2, r2, #1
        bne     13b
        b       19f

15:     ldr     r0, [r10, #C_FULLS]
        add     r0, r0, #1
        str     r0, [r10, #C_FULLS]
        mov     r0, r8
        ldr     r1, [sp]
        ldr     ip, [sp, #4]
        mla     r1, r1, ip, r8
        bl      clean_range

19:     add     r5, r5, #1
        cmp     r5, #4
        blt     10b

        dsb     sy
        @ consume: clear marks of this round; memcpy marks of slots just cleaned
        mov     r0, #0
        str     r0, [r10, #C_CLEAR]
        mov     r5, #0
        mov     r1, #0
16:     add     r0, r9, #0x18
        ldrb    r0, [r0, r5]
        cmp     r0, #0
        movne   r0, #1
        orrne   r1, r1, r0, lsl r5
        add     r5, r5, #1
        cmp     r5, #4
        blt     16b
        ldr     r0, [r10, #C_COPY]
        bic     r0, r0, r1
        str     r0, [r10, #C_COPY]
        ldr     r0, [r10, #C_FAST]
        add     r0, r0, #1
        str     r0, [r10, #C_FAST]
        mov     sp, r11
        pop     {r4-r11, pc}

fallback:                               @ r0 = reason; stock flush covers everything
        str     r0, [r10, #C_WHY]
        ldr     r0, [r10, #C_FALL]
        add     r0, r0, #1
        str     r0, [r10, #C_FALL]
        mov     r0, #0
        str     r0, [r10, #C_CLEAR]
        str     r0, [r10, #C_COPY]
        mov     sp, r11
        pop     {r4-r11, lr}
        ldr     pc, =FW_FLUSH

@ r0 = pixels, r1 = fmt -> r0 = bytes   (clobbers r0-r3, ip)
call_bytes:
        push    {r4, lr}
        ldr     ip, =FW_BYTES
        blx     ip
        pop     {r4, pc}

@ clean [r0, r1) by MVA; r7 = line size, r10 = ctl.  Clobbers r0, r2.
clean_range:
        sub     r2, r7, #1
        bic     r0, r0, r2
        cmp     r0, r1
        bhs     2f
1:      mcr     p15, 0, r0, c7, c10, 1  @ DCCMVAC
        add     r0, r0, r7
        ldr     r2, [r10, #C_LINES]
        add     r2, r2, #1
        str     r2, [r10, #C_LINES]
        cmp     r0, r1
        blo     1b
2:      bx      lr

        .ltorg
