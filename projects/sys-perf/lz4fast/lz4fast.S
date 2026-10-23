@ lz4fast.S — drop-in replacement for the stock LZ4 block decoder C05A7630
@ (UI icon .xci bitmaps).  Same ABI, same memory effects, word-sized copies
@ instead of one function call per byte.  See README.md / test_lz4fast.py.
@
@ Stock ABI (ARM, called with bl from C05A7EE0, the only caller):
@   r0 = ctx (unused by the stock body), r1 = output stream, r2 = input stream,
@   r3 = pointer to the frame FLG word.  A stream is {base, cur, size}.
@   Returns 0.  Effects: output bytes written forward from out->cur,
@   out->cur and in->cur advanced.  Nothing else (stack locals only).
@
@ Stock semantics reproduced exactly (all 32-bit, wrapping):
@   bs = u32 at in->cur; in->cur += 4; start = pos(in)
@   pos(s) = (int)(cur-base) > 0 ? cur-base : base-cur        (C04D1408)
@   while (pos(in) - start) < bs  (unsigned):
@     t = byte; L = t>>4; if L==15: do b=byte; L+=b while b==255
@     copy L bytes in->cur -> out (byte-forward); in->cur += L
@     if !(bs > pos(in) - start): break
@     off = u16; M = t&15; if M==15: extend as above; M += 4
@     copy M bytes (out->cur - off) -> out (byte-forward)
@   if (*flg & 0x10): in->cur += 4 (u32 read, block checksum ignored)
@   No output bound, no input bound — same as stock.
@
@ Byte-forward copy equivalence: a chunk of n bytes may be moved at once when
@ every byte it reads is final before the chunk starts, i.e. when
@ d = dst - src (unsigned) >= n.  dst < src gives a huge d, so it is always
@ safe.  For 0 < d < 16 the result is periodic with period d; after
@ w >= D - d bytes, where D = smallest multiple of d >= 16, reading from
@ dst - D gives the same bytes, so the rest is copied 16 at a time.
@ d == 0 (off 0, corrupt input) keeps the byte loop.
@
@ Integer registers only (no VFP/NEON: the decoder may run in any task).
@ Unaligned ldr/str/ldrh are used on input/output; the stock decoder itself
@ does unaligned ldr/ldrh on the same buffers (C04D1320, C04D12F8).
@
@ Build-time mutations (test only): MUT_PHASE MUT_EXT MUT_POS MUT_FLAG
@ MUT_TAIL MUT_M4 MUT_D16 MUT_LITADV

        .syntax unified
        .arm
        .text

        .global lz_ctl, lz_block

@ control block (offset 0): enable, calls, output bytes (low 32 bits)
lz_ctl:
        .word   1
lz_calls:
        .word   0
lz_bytes:
        .word   0
        .word   0

@ POS rd: rd = pos(in) using r4 = in->cur, r6 = in->base
        .macro  POS rd
        sub     \rd, r4, r6
#ifndef MUT_POS
        cmp     \rd, #0
        rsble   \rd, \rd, #0
#endif
        .endm

@ EXT rlen: extend a nibble of 15 with 255-run bytes from r4
        .macro  EXT rlen
        cmp     \rlen, #15
        bne     1f
2:      ldrb    r12, [r4], #1
        add     \rlen, \rlen, r12
#ifndef MUT_EXT
        cmp     r12, #255
#else
        cmp     r12, #254
#endif
        beq     2b
1:
        .endm

@ COPY: byte-forward-equivalent copy of r1 bytes from r3 to r5.
@ Advances r5 by r1.  Clobbers r0, r1, r2, r3, r8, r9, r10, r12.
        .macro  COPY
        cmp     r1, #0
        beq     9f
        sub     r12, r5, r3             @ d = dst - src
#ifndef MUT_D16
        cmp     r12, #16
#else
        cmp     r12, #15
#endif
        bhs     5f
        cmp     r12, #0
        beq     7f                      @ d == 0: plain byte loop
        mov     r2, r12                 @ D = smallest multiple of d >= 16
3:      cmp     r2, #16
        addlo   r2, r2, r12
        blo     3b
#ifndef MUT_PHASE
        sub     r0, r2, r12             @ phase 1: D - d bytes, byte by byte
#else
        mov     r0, #0
#endif
        cmp     r0, r1
        movhi   r0, r1
        sub     r1, r1, r0
        cmp     r0, #0
        beq     4f
6:      ldrb    r8, [r3], #1
        strb    r8, [r5], #1
        subs    r0, r0, #1
        bne     6b
4:      cmp     r1, #0
        beq     9f
        sub     r3, r5, r2              @ read from dst - D from now on
5:      cmp     r1, #16
        blo     8f
10:     ldr     r0, [r3]
        ldr     r2, [r3, #4]
        ldr     r8, [r3, #8]
        ldr     r9, [r3, #12]
        add     r3, r3, #16
        str     r0, [r5]
        str     r2, [r5, #4]
        str     r8, [r5, #8]
        str     r9, [r5, #12]
        add     r5, r5, #16
        sub     r1, r1, #16
        cmp     r1, #16
        bhs     10b
8:      cmp     r1, #4
        blo     7f
11:     ldr     r0, [r3], #4
        str     r0, [r5], #4
        sub     r1, r1, #4
        cmp     r1, #4
        bhs     11b
7:      cmp     r1, #0
        beq     9f
12:     ldrb    r0, [r3], #1
        strb    r0, [r5], #1
#ifndef MUT_TAIL
        subs    r1, r1, #1
#else
        subs    r1, r1, #1
        subsne  r1, r1, #1
#endif
        bne     12b
9:
        .endm

@ ---------------------------------------------------------------------------
lz_block:
        ldr     r12, lz_ctl
        cmp     r12, #0
        ldreq   pc, stock_entry         @ disabled: run the stock decoder
        push    {r1-r11, lr}            @ 12 words: sp keeps its alignment
        sub     sp, sp, #8              @ [sp] = start pos, [sp+4] = out start
        ldr     r6, [r2]                @ in->base
        ldr     r4, [r2, #4]            @ in->cur
        ldr     r5, [r1, #4]            @ out->cur
        str     r5, [sp, #4]
        ldr     r7, [r4], #4            @ bs (unaligned like C04D1320)
        POS     r12
        str     r12, [sp]
        ldr     r11, [sp]
lz_loop:
        POS     r12
        sub     r12, r12, r11
        cmp     r12, r7
        bhs     lz_done
        ldrb    lr, [r4], #1            @ token
        lsr     r1, lr, #4
        EXT     r1
        mov     r3, r4
#ifndef MUT_LITADV
        add     r4, r4, r1
#else
        add     r4, r4, r1
        add     r4, r4, #1
#endif
        COPY
        POS     r12
        sub     r12, r12, r11
        cmp     r7, r12
        bls     lz_done
        ldrh    r2, [r4], #2            @ offset (unaligned like C04D12F8)
        and     r1, lr, #15
        EXT     r1
#ifndef MUT_M4
        add     r1, r1, #4
#else
        add     r1, r1, #3
#endif
        sub     r3, r5, r2
        COPY
        b       lz_loop
lz_done:
        ldr     r12, [sp, #16]          @ saved r3 = FLG pointer
        ldr     r12, [r12]
#ifndef MUT_FLAG
        tst     r12, #0x10
        ldrne   r12, [r4], #4           @ block checksum, read and ignored
#endif
        ldr     r2, [sp, #12]           @ saved r2 = input stream
        str     r4, [r2, #4]
        ldr     r1, [sp, #8]            @ saved r1 = output stream
        str     r5, [r1, #4]
        ldr     r0, [sp, #4]            @ statistics
        sub     r0, r5, r0
        adr     r2, lz_calls
        ldr     r3, [r2]
        add     r3, r3, #1
        str     r3, [r2]
        ldr     r3, [r2, #4]
        add     r3, r3, r0
        str     r3, [r2, #4]
        mov     r0, #0
        add     sp, sp, #8
        pop     {r1-r11, pc}

stock_entry:
        .word   0xC05A7630
