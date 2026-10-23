@ filldma.S -- whole-layer fills through the stock Fill DMA driver.
@
@ fd_layer_fill(r0 = layer, r1 = value)  -- same arguments as the layer
@ vtable's fill C0721480 (vtable 0xC2E38E5C / 0xC2EF6280, slot +0x20).
@ Called by the sys-perf dispatcher that owns that slot; this file patches
@ nothing itself.
@
@   r0 == 0   the layer buffer has been filled (by DMA, or -- if the driver
@             failed after we had started -- by our own CPU loop).
@   r0 != 0   not taken: nothing was written and no cache line was touched.
@             1 disabled, 2 not 16bpp, 3 layer invalid, 4 below threshold,
@             5 driver never initialised, 6 alignment / not DRAM / too big,
@             7 recording (unless fd_rec_ok).
@
@ What the stock fill does for a 16bpp layer ([layer+0x1C] == 1):
@   if (!layer->vt[+0x30](layer)) return;
@   base = layer->vt[+0x10](layer)->[+4];  size = ((w*16)>>3) * h
@   w = [layer+4], h = [layer+8];  strh value to every halfword of [base, base+size)
@ Both virtuals are pure reads for these two classes (C0698C08 / C0721F98
@ return 1; C0721328 -> C0721CC8 returns [layer+0x4C]).
@
@ Position independent; the only writable words are the header below.

        .syntax unified
        .arm
        .text

        .equ    FW_FILLDMA,     0xC00DB189      @ Thumb: C00DB188(desc) -> 0 ok
        .equ    FW_DCIMVAC,     0xC000EB28      @ ARM: invalidate [r0, r1] by line, IRQs off
        .equ    FW_SYSSTAT,     0xC00178D8      @ ARM: system status object
        .equ    FILL_INITED,    0xC31D25B4      @ ==1 once C00DBC80 has run (boot, LCD init)
        .equ    CHUNK,          0x10000         @ bytes invalidated per call
        .equ    ROWW,           0x2000          @ words per DMA row (driver needs < 0x4000)

@ ---------------------------------------------------------------- header
fd_base:
        .word   0x414D4446                      @ +00 'FDMA'
        .word   2                               @ +04 version
fd_enable:
        .word   1                               @ +08 0 = never take
fd_thresh:
        .word   0x4000                          @ +0C bytes; smaller -> not taken
fd_rec_ok:
        .word   0                               @ +10 1 = also while recording
fd_calls:
        .word   0                               @ +14
fd_dma_ok:
        .word   0                               @ +18 fills done by DMA
fd_dma_bytes:
        .word   0                               @ +1C bytes (mod 2^32)
fd_declined:
        .word   0                               @ +20 returned non-zero
fd_cpu_done:
        .word   0                               @ +24 driver failed, we filled by CPU
fd_last_code:
        .word   0                               @ +28 last return code
fd_last_base:
        .word   0                               @ +2C last DMA range (cache-clean on return)
fd_last_size:
        .word   0                               @ +30
        .space  0x0C                            @ +34 reserved

@ ---------------------------------------------------------------- entry (+0x40)
        .global fd_layer_fill
fd_layer_fill:
        push    {r4-r11, lr}
        mov     r4, r0                          @ layer
        mov     r5, r1                          @ value
        mov     r11, sp
        bic     sp, sp, #7
        sub     sp, sp, #0x28                   @ DMA descriptor
        adr     r10, fd_base
        ldr     r0, [r10, #0x14]
        add     r0, r0, #1
        str     r0, [r10, #0x14]

        mov     r9, #1
        ldr     r0, [r10, #0x08]
        cmp     r0, #0
        beq     fd_decline
        mov     r9, #2
        ldr     r0, [r4, #0x1C]
        cmp     r0, #1
        bne     fd_decline
        mov     r9, #3
        mov     r0, r4
        ldr     ip, [r4]
        ldr     ip, [ip, #0x30]
        blx     ip
        cmp     r0, #0
        beq     fd_decline
        mov     r0, r4
        ldr     ip, [r4]
        ldr     ip, [ip, #0x10]
        blx     ip
        ldr     r7, [r0, #4]                    @ r7 = base
        ldr     r0, [r4, #4]
        lsl     r0, r0, #4
        lsr     r0, r0, #3
        ldr     r1, [r4, #8]
        mul     r6, r0, r1                      @ r6 = size, as the stock computes it

        mov     r9, #4
        ldr     r0, [r10, #0x0C]
        cmp     r6, r0
        blo     fd_decline
        cmp     r6, #0
        beq     fd_decline

        mov     r9, #5
        ldr     r0, =FILL_INITED                @ never run the driver's init: it creates a task
        ldr     r0, [r0]
        cmp     r0, #1
        bne     fd_decline

        mov     r9, #6
        orr     r0, r7, r6                      @ whole cache lines only
        tst     r0, #0x3F
        bne     fd_decline
        cmp     r6, #0x20000000                 @ rows stay < 0x4000
        bhs     fd_decline
        mov     r8, #0                          @ r8 = 1 if cached
        cmp     r7, #0xC0000000
        bhs     2f
        cmp     r7, #0x40000000                 @ uncached alias 0x40000000..0x7FFFFFFF
        blo     fd_decline
        sub     r3, r7, #0x40000000
        add     r0, r3, r6
        cmp     r0, #0x40000000
        bhi     fd_decline
        b       3f
2:      mov     r8, #1                          @ cached 0xC0000000..0xFFFFFFFF
        sub     r3, r7, #0xC0000000
        add     r0, r3, r6
        cmp     r0, #0x40000000
        bhi     fd_decline
3:      mov     r10, r3                         @ r10 = DRAM offset

        mov     r9, #7
        ldr     r0, fd_rec_ok
        cmp     r0, #0
        bne     4f
        ldr     ip, =FW_SYSSTAT
        blx     ip
        ldrb    r0, [r0, #0x18 + 0x84]          @ is_recording (same byte as `status get`)
        cmp     r0, #0
        bne     fd_decline
4:
        @ ---- committed from here on: always fill, always return 0
        uxth    r5, r5
        orr     r5, r5, r5, lsl #16             @ r5 = pattern

        cmp     r8, #0
        beq     5f
        mov     r0, r7                          @ drop every line, dirty or not: the DMA
        bl      fd_inval                        @ rewrites all of them, and a dirty line
5:                                              @ evicted mid-DMA would land on top
        lsr     r0, r6, #2                      @ words
        lsrs    r1, r0, #13                     @ full rows of ROWW words
        beq     6f
        mov     r0, r10, lsr #2
        mov     r2, #ROWW
        bl      fd_dma
        cmp     r0, #0
        bne     fd_dma_failed
6:      lsr     r0, r6, #2
        ubfx    r2, r0, #0, #13                 @ remaining words
        cmp     r2, #0
        beq     7f
        lsr     r1, r0, #13
        mov     r0, r10, lsr #2
        add     r0, r0, r1, lsl #13
        mov     r1, #1
        bl      fd_dma
        cmp     r0, #0
        bne     fd_dma_failed
7:      cmp     r8, #0
        beq     8f
        mov     r0, r7                          @ lines speculatively refilled during the
        bl      fd_inval                        @ DMA hold the old bytes: drop them again
8:      adr     r10, fd_base
        ldr     r0, [r10, #0x18]
        add     r0, r0, #1
        str     r0, [r10, #0x18]
        ldr     r0, [r10, #0x1C]
        add     r0, r0, r6
        str     r0, [r10, #0x1C]
        str     r7, [r10, #0x2C]
        str     r6, [r10, #0x30]
        mov     r0, #0
        b       fd_out

fd_dma_failed:                                  @ lines already dropped: finish by CPU
        cmp     r8, #0
        beq     9f
        mov     r0, r7
        bl      fd_inval
9:      mov     r0, r7
        add     r1, r7, r6
        mov     r2, r5
        mov     r3, r5
10:     stmia   r0!, {r2, r3}
        cmp     r0, r1
        bne     10b
        adr     r10, fd_base
        ldr     r0, [r10, #0x24]
        add     r0, r0, #1
        str     r0, [r10, #0x24]
        mov     r0, #0
        b       fd_out

fd_decline:
        adr     r10, fd_base
        ldr     r0, [r10, #0x20]
        add     r0, r0, #1
        str     r0, [r10, #0x20]
        mov     r0, r9
fd_out:
        adr     r1, fd_base
        str     r0, [r1, #0x28]
        mov     sp, r11
        pop     {r4-r11, pc}

@ ---------------------------------------------------------------- helpers
@ fd_inval(r0 = base), size in r6: [base, base+size) in CHUNK pieces so IRQs
@ are never off for more than CHUNK/64 lines at a time.
fd_inval:
        push    {r4, r5, r6, lr}
        mov     r4, r0
        add     r5, r0, r6                      @ end (0 if the range ends at 2^32)
11:     mov     r0, r4
        sub     r2, r5, r4
        cmp     r2, #CHUNK
        movhi   r2, #CHUNK
        add     r1, r4, r2
        sub     r1, r1, #1                      @ inclusive last byte
        add     r4, r4, r2
        ldr     ip, =FW_DCIMVAC
        blx     ip
        cmp     r4, r5
        bne     11b
        pop     {r4, r5, r6, pc}

@ fd_dma(r0 = dst word, r1 = rows, r2 = width words) -> r0 = driver result.
@ The descriptor is the 0x28 bytes fd_layer_fill keeps at its sp.
fd_dma:
        push    {r4, lr}
        add     r4, sp, #8
        mov     r3, #0
        str     r3, [r4, #0x00]
        str     r3, [r4, #0x04]
        str     r3, [r4, #0x08]
        str     r0, [r4, #0x0C]                 @ dst (DRAM offset / 4)
        str     r3, [r4, #0x10]                 @ mode 0 = fill
        str     r2, [r4, #0x14]                 @ width (words)
        str     r1, [r4, #0x18]                 @ rows
        str     r2, [r4, #0x1C]                 @ stride = width: contiguous
        str     r5, [r4, #0x20]                 @ pattern
        str     r5, [r4, #0x24]
        mov     r0, r4
        ldr     ip, =FW_FILLDMA
        blx     ip
        pop     {r4, pc}

        .ltorg
fd_end:
