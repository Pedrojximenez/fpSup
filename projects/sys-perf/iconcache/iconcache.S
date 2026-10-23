@ iconcache -- keep decoded .xci icons and reuse them (same pixels, no decode).
@
@ The UI's image node loads its icon in C0601F98 (Thumb), which decodes the
@ LZ4 frame inline (c06021a0..c060235a) into a buffer from the UIC memory
@ interface [r6] (alloc +0, free +4, user data +0x34).  Every node load
@ decodes again: a page reload, or two nodes showing the same icon.
@
@ Two hooks, each one aligned Thumb32 word (b.w to an 8-byte veneer):
@   H1 C060219C  stock: ldr r1,[r6,#0x34] ; mov r0,fp   (r2 already = alloc)
@        hit  -> buf = alloc(size, ud) exactly as stock, memcpy from the cache,
@                [sp+0x48] = buf, continue at C060235A (ldr.w fp,[sp,#0x48])
@        miss -> remember the key, redo the two stock instructions, continue
@                at C06021A0 (blx r2): the stock decode runs unchanged
@   H2 C060234C  stock: adds r2,#4 ; str r2,[sp,#0x90]   (end of the LZ4 path)
@        if this frame is the remembered miss and the decoder wrote exactly
@        `size` bytes into [sp+0x48], copy them into the cache; then redo the
@        two stock instructions and continue at C0602350.
@
@ Key: frame source address, compressed size (header +4), FNV-1a over the
@ compressed bytes, decoded size.  The arena is a block the installer gives
@ (ARENA/ARENA_SIZE); entries are first-fit in it, evicted least recently
@ used.  Searches run unmasked; each table edit masks IRQ/FIQ and re-checks
@ (O(N)) first; copies run unmasked with the entry pinned.  ARM, position independent, integer only.

        .syntax unified
        .arm
        .text

        .equ MAGIC,     0x48434349      @ 'ICCH'
        .equ EN,        0x04
        .equ ARENA,     0x08
        .equ ARENA_SZ,  0x0C
        .equ MAXENT,    0x10
        .equ HITS,      0x14
        .equ MISSES,    0x18
        .equ INSERTS,   0x1C
        .equ EVICTS,    0x20
        .equ SKIPS,     0x24
        .equ ALLOCFAIL, 0x28
        .equ P_SP,      0x2C
        .equ P_SRC,     0x30
        .equ P_CSZ,     0x34
        .equ P_HASH,    0x38
        .equ P_SIZE,    0x3C
        .equ CLOCK,     0x40
        .equ NENT,      0x44
        .equ REJECTS,   0x48
        .equ TABLE,     0x50

        .equ N_ENT,     128
        .equ E_STATE,   0
        .equ E_SRC,     4
        .equ E_CSZ,     8
        .equ E_HASH,    12
        .equ E_SIZE,    16
        .equ E_OFF,     20
        .equ E_STAMP,   24
        .equ E_PINS,    28
        .equ ST_FREE,   0
        .equ ST_FILL,   1
        .equ ST_READY,  2

        @ the stock frame (sp at the hook sites)
        .equ F_BUF,     0x48
        .equ F_CTYPE,   0x4C
        .equ F_OPOS,    0x98
        .equ F_OBASE,   0x9C
        .equ F_CSZ,     0xB4
        .equ SAVED,     56              @ r0-r12, lr pushed by the hooks

        .global ic_ctl
        .global ic_h1
        .global ic_h2

ic_ctl:
        .word   MAGIC
        .word   0                       @ EN
        .word   0                       @ ARENA (absolute, 8-aligned)
        .word   0                       @ ARENA_SZ
        .word   0x80000                 @ MAXENT: larger icons are not cached
        .space  TABLE - 0x14
        .space  N_ENT * 32

@ ---------------------------------------------------------------- H1
ic_h1:
        push    {r0-r12, lr}
        mov     r11, sp                 @ r11 = saved registers
        bic     sp, sp, #7
        ldr     r10, L_ctl_h1
ctl_h1: sub     r10, pc, r10            @ r10 = ic_ctl (pc reads ctl_h1+8)
        ldr     r0, [r10, #EN]
        cmp     r0, #0
        beq     h1_stock
        add     r8, r11, #SAVED         @ r8 = the stock frame
        ldr     r4, [r11, #9*4]         @ sb = LZ4 frame
        ldr     r5, [r11, #11*4]        @ fp = decoded size
        ldr     r6, [r8, #F_CSZ]        @ compressed size
        cmp     r5, #0
        cmpne   r6, #0
        beq     h1_skip
        mov     r0, r4
        mov     r1, r6
        bl      fnv
        mov     r7, r0                  @ hash
        mrs     r9, cpsr
        cpsid   if
        add     r0, r10, #TABLE
        mov     r1, #N_ENT
1:      ldr     r2, [r0, #E_STATE]
        cmp     r2, #ST_READY
        bne     2f
        ldr     r2, [r0, #E_SRC]
        cmp     r2, r4
        bne     2f
        ldr     r2, [r0, #E_CSZ]
        cmp     r2, r6
        bne     2f
        ldr     r2, [r0, #E_HASH]
        cmp     r2, r7
        bne     2f
        ldr     r2, [r0, #E_SIZE]
        cmp     r2, r5
        beq     h1_hit
2:      add     r0, r0, #32
        subs    r1, r1, #1
        bne     1b
        msr     cpsr_c, r9
        ldr     r0, [r10, #MISSES]
        add     r0, r0, #1
        str     r0, [r10, #MISSES]
        ldr     r0, [r10, #MAXENT]
        cmp     r5, r0
        bhi     h1_skip
        ldr     r0, [r10, #ARENA_SZ]
        cmp     r5, r0
        bhi     h1_skip
        str     r4, [r10, #P_SRC]
        str     r6, [r10, #P_CSZ]
        str     r7, [r10, #P_HASH]
        str     r5, [r10, #P_SIZE]
        str     r8, [r10, #P_SP]
        b       h1_stock
h1_skip:
        ldr     r0, [r10, #SKIPS]
        add     r0, r0, #1
        str     r0, [r10, #SKIPS]
        mov     r0, #0
        str     r0, [r10, #P_SP]
h1_stock:
        mov     sp, r11
        pop     {r0-r12, lr}
        ldr     r1, [r6, #0x34]         @ the two stock instructions
        mov     r0, r11
        ldr     ip, L_h1_ret            @ ip is scratch across blx r2 and reloaded at C06021A4
        bx      ip

h1_hit:                                 @ r0 = entry, IRQ masked (r9 = cpsr)
        ldr     r1, [r0, #E_PINS]
        add     r1, r1, #1
        str     r1, [r0, #E_PINS]
        ldr     r1, [r10, #CLOCK]
        add     r1, r1, #1
        str     r1, [r10, #CLOCK]
        str     r1, [r0, #E_STAMP]
        msr     cpsr_c, r9
        mov     r9, r0                  @ r9 = pinned entry
        mov     r0, #0
        str     r0, [r10, #P_SP]
        ldr     r3, [r11, #6*4]         @ r6 = UIC memory interface
        ldr     r2, [r3]
        ldr     r1, [r3, #0x34]
        mov     r0, r5
        blx     r2                      @ buf = alloc(size, ud), as stock
        movs    r7, r0
        beq     3f
        ldr     r1, [r10, #ARENA]
        ldr     r2, [r9, #E_OFF]
        add     r1, r1, r2
        mov     r2, r5
        ldr     ip, L_memcpy
        blx     ip
3:      mrs     r1, cpsr
        cpsid   if
        ldr     r2, [r9, #E_PINS]
        sub     r2, r2, #1
        str     r2, [r9, #E_PINS]
        msr     cpsr_c, r1
        cmp     r7, #0
        moveq   r1, #ALLOCFAIL
        movne   r1, #HITS
        ldr     r0, [r10, r1]
        add     r0, r0, #1
        str     r0, [r10, r1]
        str     r7, [r8, #F_BUF]        @ [sp+0x48] = buf (0 -> stock error path)
        mov     sp, r11
        pop     {r0-r12, lr}
        ldr     r0, L_join              @ r0 is dead at C060235A
        bx      r0

@ ---------------------------------------------------------------- H2
ic_h2:
        push    {r0-r12, lr}
        mov     r11, sp
        bic     sp, sp, #7
        sub     sp, sp, #16
        ldr     r10, L_ctl_h2
ctl_h2: sub     r10, pc, r10
        ldr     r0, [r10, #EN]
        cmp     r0, #0
        beq     h2_out
        add     r8, r11, #SAVED
        ldr     r0, [r10, #P_SP]
        cmp     r0, r8
        bne     h2_out
        ldr     r4, [r10, #P_SRC]       @ take the key before anything else
        ldr     r6, [r10, #P_CSZ]
        ldr     r9, [r10, #P_HASH]
        ldr     r5, [r10, #P_SIZE]
        mov     r0, #0
        str     r0, [r10, #P_SP]
        ldr     r7, [r8, #F_BUF]
        ldr     r0, [r8, #F_CTYPE]
        cmp     r0, #2
        bne     h2_rej
        cmp     r7, #0
        beq     h2_rej
        ldr     r0, [r8, #F_OBASE]
        cmp     r0, r7
        bne     h2_rej
        ldr     r0, [r8, #F_OPOS]
        cmp     r0, r5
        bne     h2_rej
        stm     sp, {r4, r6, r9}        @ key: src, csz, hash
ins_retry:                              @ search unmasked, then mask and re-check
        mrs     r8, cpsr
        add     r0, r10, #TABLE         @ a free slot
        mov     r1, #N_ENT
4:      ldr     r2, [r0, #E_STATE]
        cmp     r2, #ST_FREE
        beq     5f
        add     r0, r0, #32
        subs    r1, r1, #1
        bne     4b
        b       ins_evict
5:      mov     r9, r0                  @ r9 = slot
        mov     r3, #0                  @ candidate offset 0 first
        bl      fits
        beq     ins_take
        add     r6, r10, #TABLE         @ then the end of every live entry
        mov     r4, #N_ENT
6:      ldr     r2, [r6, #E_STATE]
        cmp     r2, #ST_FREE
        beq     7f
        ldr     r3, [r6, #E_OFF]
        ldr     r2, [r6, #E_SIZE]
        add     r3, r3, r2
        add     r3, r3, #7
        bic     r3, r3, #7
        bl      fits
        beq     ins_take
7:      add     r6, r6, #32
        subs    r4, r4, #1
        bne     6b
ins_evict:                              @ drop the least recently used, unpinned
        cpsid   if
        add     r0, r10, #TABLE
        mov     r1, #N_ENT
        mov     r2, #0                  @ victim
        mvn     r3, #0                  @ its stamp
8:      ldr     ip, [r0, #E_STATE]
        cmp     ip, #ST_READY
        bne     9f
        ldr     ip, [r0, #E_PINS]
        cmp     ip, #0
        bne     9f
        ldr     ip, [r0, #E_STAMP]
        cmp     ip, r3
        movlo   r3, ip
        movlo   r2, r0
9:      add     r0, r0, #32
        subs    r1, r1, #1
        bne     8b
        cmp     r2, #0
        beq     ins_none
        mov     ip, #ST_FREE
        str     ip, [r2, #E_STATE]
        ldr     ip, [r10, #EVICTS]
        add     ip, ip, #1
        str     ip, [r10, #EVICTS]
        msr     cpsr_c, r8
        b       ins_retry
ins_none:
        msr     cpsr_c, r8
        ldr     r0, [r10, #SKIPS]
        add     r0, r0, #1
        str     r0, [r10, #SKIPS]
        b       h2_out
ins_take:                               @ r9 = slot, r3 = offset
        cpsid   if
        ldr     r0, [r9, #E_STATE]      @ still free, and the range still free?
        cmp     r0, #ST_FREE
        bne     ins_lost
        bl      fits
        bne     ins_lost
        ldm     sp, {r0, r1, r2}
        str     r0, [r9, #E_SRC]
        str     r1, [r9, #E_CSZ]
        str     r2, [r9, #E_HASH]
        str     r5, [r9, #E_SIZE]
        str     r3, [r9, #E_OFF]
        mov     r0, #0
        str     r0, [r9, #E_PINS]
        ldr     r0, [r10, #CLOCK]
        add     r0, r0, #1
        str     r0, [r10, #CLOCK]
        str     r0, [r9, #E_STAMP]
        mov     r0, #ST_FILL
        str     r0, [r9, #E_STATE]
        msr     cpsr_c, r8
        ldr     r0, [r10, #ARENA]
        add     r0, r0, r3
        mov     r1, r7
        mov     r2, r5
        ldr     ip, L_memcpy
        blx     ip
        mrs     r1, cpsr
        cpsid   if
        mov     r0, #ST_READY
        str     r0, [r9, #E_STATE]
        ldr     r0, [r10, #INSERTS]
        add     r0, r0, #1
        str     r0, [r10, #INSERTS]
        msr     cpsr_c, r1
        b       h2_out
ins_lost:
        msr     cpsr_c, r8
        b       ins_retry
h2_rej:
        ldr     r0, [r10, #REJECTS]
        add     r0, r0, #1
        str     r0, [r10, #REJECTS]
h2_out:
        mov     sp, r11
        pop     {r0-r12, lr}
        adds    r2, r2, #4              @ the two stock instructions
        str     r2, [sp, #0x90]
        ldr     r1, L_h2_ret            @ r1 is dead from C0602350 to C0602372
        bx      r1

@ fits: r3 = candidate offset, r5 = size.  Z set when [r3, r3+r5) is inside
@ the arena and overlaps no live entry.  Clobbers r0-r2, ip.
fits:
        ldr     r0, [r10, #ARENA_SZ]
        add     r1, r3, r5
        cmp     r1, r0
        bhi     11f
        add     r0, r10, #TABLE
        mov     ip, #N_ENT
10:     ldr     r2, [r0, #E_STATE]
        cmp     r2, #ST_FREE
        beq     12f
        ldr     r2, [r0, #E_OFF]
        cmp     r2, r1                  @ e.off < c+size ?
        bhs     12f
        ldr     r1, [r0, #E_SIZE]
        add     r2, r2, r1
        add     r1, r3, r5              @ restore c+size
        cmp     r3, r2                  @ c < e.off+e.size ?
        blo     11f
12:     add     r0, r0, #32
        subs    ip, ip, #1
        bne     10b
        cmp     r0, r0                  @ Z = fits
        bx      lr
11:     movs    r0, #1                  @ Z clear
        bx      lr

@ fnv: r0 = bytes, r1 = length -> r0 = FNV-1a over 32-bit words, then tail bytes
fnv:
        ldr     r2, L_fnv_basis
        ldr     ip, L_fnv_prime
13:     cmp     r1, #4
        blo     14f
        ldr     r3, [r0], #4
        eor     r2, r2, r3
        mul     r2, r2, ip
        sub     r1, r1, #4
        b       13b
14:     cmp     r1, #0
        beq     15f
        ldrb    r3, [r0], #1
        eor     r2, r2, r3
        mul     r2, r2, ip
        sub     r1, r1, #1
        b       14b
15:     mov     r0, r2
        bx      lr

L_h1_ret:    .word 0xC06021A1           @ Thumb, after the hooked word at C060219C
L_join:      .word 0xC060235B           @ Thumb, ldr.w fp,[sp,#0x48]
L_h2_ret:    .word 0xC0602351           @ Thumb, after the hooked word at C060234C
L_memcpy:    .word 0xC001510C           @ ARM memcpy(dst, src, n)
L_fnv_basis: .word 0x811C9DC5
L_fnv_prime: .word 0x01000193
L_ctl_h1:    .word ctl_h1 + 8 - ic_ctl
L_ctl_h2:    .word ctl_h2 + 8 - ic_ctl
