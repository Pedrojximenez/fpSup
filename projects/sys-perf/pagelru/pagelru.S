@ pagelru.S — keep the last N UI screen layouts loaded so A -> B -> A does not
@ re-parse A.  See README.md.
@
@ Stock screen switch (uicMgr r7, Thumb, around C05DD540):
@   C05DD5CA  bl C05D90F0(next)      load next   (tree exists -> refcount+1, reuse)
@   C05DD670  bl C05D91A0(current)   unload old  (refcount 1 -> teardown + free)
@ Both sites are redirected (Thumb BLX -> 8-byte ARM veneer -> here).
@
@ pl_unload(O): we may take over the reference instead of releasing it:
@   only when enabled, not recording, O has a tree, the tree's refcount is 1
@   (the stock call would free it) and O's name does not start with "QS_"
@   (QS layouts belong to UicResourceCache / uishare / OG — never touched).
@   Otherwise the stock unload runs unchanged.  Over capacity: evict the
@   oldest with the stock unload.
@ pl_load(L): stock load first (reuse path, refcount 2), then if L is ours,
@   drop our reference with the stock unload (refcount > 1 path) — the same
@   load/unload pair the QS screens take in stock.  Done even when disabled,
@   so a reference is never stranded.
@ Disabled or recording: every held layout is released (stock unload) at the
@   next hook call.  Everything runs in the UI task (the hooks' own context).
@
@ Build-time mutations (test only): MUT_NOQS MUT_NOREF MUT_NODROP MUT_LOADORDER
@ MUT_NOEVICT MUT_NOREC MUT_CAPOFF

        .syntax unified
        .arm
        .text

        .equ    FW_LOAD,    0xC05D90F0          @ Thumb
        .equ    FW_UNLOAD,  0xC05D91A0          @ Thumb
        .equ    FW_SYSSTAT, 0xC00178D8          @ ARM: system status object
        .equ    MAXN,       4

        .equ    P_EN,    0x04
        .equ    P_CAP,   0x08
        .equ    P_CNT,   0x0C
        .equ    P_HIT,   0x10
        .equ    P_KEPT,  0x14
        .equ    P_EVICT, 0x18
        .equ    P_BYP,   0x1C
        .equ    P_WHY,   0x20
        .equ    P_FLUSH, 0x24
        .equ    P_SLOT,  0x28                   @ 4 words, [0] = most recent

        .global pl_ctl, pl_load, pl_unload
pl_ctl:
ctl:
        .ascii  "PLRU"
        .word   0                               @ +04 enable (0 = stock)
        .word   2                               @ +08 capacity (0..4)
        .word   0, 0, 0, 0, 0, 0, 0             @ +0C count hits kept evict bypass why flush
        .word   0, 0, 0, 0                      @ +28 slots

@ ------------------------------------------------------------ helpers
@ all helpers: r10 = ctl; may clobber r0-r3, ip

@ r0 = 1 while recording
is_rec:
        push    {r4, lr}
        ldr     ip, =FW_SYSSTAT
        blx     ip
        ldrb    r0, [r0, #0x18 + 0x84]
        pop     {r4, pc}

@ release every held layout (oldest first)
flush_all:
        push    {r4, lr}
1:      ldr     r4, [r10, #P_CNT]
        cmp     r4, #0
        popeq   {r4, pc}
        sub     r4, r4, #1
        str     r4, [r10, #P_CNT]
        add     r1, r10, #P_SLOT
        ldr     r0, [r1, r4, lsl #2]
        mov     r2, #0
        str     r2, [r1, r4, lsl #2]
        ldr     r2, [r10, #P_FLUSH]
        add     r2, r2, #1
        str     r2, [r10, #P_FLUSH]
        ldr     ip, =FW_UNLOAD | 1
        blx     ip
        b       1b

@ r0 = layout -> r0 = index or -1
find:
        ldr     r1, [r10, #P_CNT]
        add     r2, r10, #P_SLOT
        mov     r3, #0
1:      cmp     r3, r1
        mvnhs   r0, #0
        bxhs    lr
        ldr     ip, [r2, r3, lsl #2]
        cmp     ip, r0
        moveq   r0, r3
        bxeq    lr
        add     r3, r3, #1
        b       1b

@ r0 = index: remove it, keep order
remove:
        ldr     r1, [r10, #P_CNT]
        sub     r1, r1, #1
        str     r1, [r10, #P_CNT]
        add     r2, r10, #P_SLOT
1:      cmp     r0, r1
        bhs     2f
        add     r3, r0, #1
        ldr     ip, [r2, r3, lsl #2]
        str     ip, [r2, r0, lsl #2]
        mov     r0, r3
        b       1b
2:      mov     ip, #0
        str     ip, [r2, r1, lsl #2]
        bx      lr

@ ------------------------------------------------------------ pl_load
@ in: r0 = layout to load (Thumb caller via BLX + veneer); out: stock result
pl_load:
        push    {r4-r11, lr}
        mov     r11, sp
        bic     sp, sp, #7
        mov     r4, r0
        adr     r10, ctl
#ifdef MUT_LOADORDER
        bl      find
        cmp     r0, #0
        blt     8f
        bl      remove
        add     r1, r10, #P_HIT
        ldr     r0, [r1]
        add     r0, r0, #1
        str     r0, [r1]
        mov     r0, r4
        ldr     ip, =FW_UNLOAD | 1
        blx     ip
8:      mov     r0, r4
        ldr     ip, =FW_LOAD | 1
        blx     ip
        mov     r5, r0
        b       9f
#endif
        ldr     ip, =FW_LOAD | 1
        blx     ip
        mov     r5, r0
        cmp     r5, #0                          @ failed load: our reference stays held
        bne     9f
        mov     r0, r4
        bl      find
        cmp     r0, #0
        blt     9f
        bl      remove
        ldr     r0, [r10, #P_HIT]
        add     r0, r0, #1
        str     r0, [r10, #P_HIT]
#ifndef MUT_NODROP
        mov     r0, r4                          @ refcount >= 2 here: no teardown
        ldr     ip, =FW_UNLOAD | 1
        blx     ip
#endif
9:      mov     r0, r5
        mov     sp, r11
        pop     {r4-r11, pc}

@ ------------------------------------------------------------ pl_unload
@ in: r0 = old current layout; return value is ignored by the caller
pl_unload:
        push    {r4-r11, lr}
        mov     r11, sp
        bic     sp, sp, #7
        mov     r4, r0
        adr     r10, ctl

        mov     r9, #1
        ldr     r0, [r10, #P_EN]
        cmp     r0, #0
        beq     flushbyp
#ifndef MUT_NOREC
        mov     r9, #2
        bl      is_rec
        cmp     r0, #0
        bne     flushbyp
#endif
        mov     r9, #3
        cmp     r4, #0
        beq     bypass
        mov     r9, #4
        ldr     r0, [r4, #0xC]                  @ tree
        cmp     r0, #0
        beq     bypass
#ifndef MUT_NOREF
        mov     r9, #5
        ldr     r1, [r0, #0xC]                  @ tree refcount
        cmp     r1, #1
        bne     bypass
#endif
#ifndef MUT_NOQS
        mov     r9, #6
        ldr     r0, [r4, #8]                    @ name
        cmp     r0, #0
        beq     bypass
        ldrb    r1, [r0]
        cmp     r1, #'Q'
        ldrbeq  r1, [r0, #1]
        cmpeq   r1, #'S'
        ldrbeq  r1, [r0, #2]
        cmpeq   r1, #'_'
        beq     bypass
#endif
        mov     r9, #7
        mov     r0, r4
        bl      find
        cmp     r0, #0
        bge     bypass
        mov     r9, #8
        ldr     r6, [r10, #P_CAP]
        cmp     r6, #MAXN
        movhi   r6, #MAXN
#ifndef MUT_CAPOFF
        cmp     r6, #0
        beq     bypass
#endif
        @ make room: evict the oldest until count < capacity
#ifndef MUT_NOEVICT
3:      ldr     r1, [r10, #P_CNT]
        cmp     r1, r6
        blo     4f
        sub     r1, r1, #1
        str     r1, [r10, #P_CNT]
        add     r2, r10, #P_SLOT
        ldr     r0, [r2, r1, lsl #2]
        mov     ip, #0
        str     ip, [r2, r1, lsl #2]
        ldr     ip, [r10, #P_EVICT]
        add     ip, ip, #1
        str     ip, [r10, #P_EVICT]
        ldr     ip, =FW_UNLOAD | 1
        blx     ip
        b       3b
4:
#else
        ldr     r1, [r10, #P_CNT]
        cmp     r1, #MAXN
        bhs     bypass
#endif
        @ insert at the front (count < capacity <= MAXN here)
        ldr     r1, [r10, #P_CNT]
        add     r2, r10, #P_SLOT
1:      cmp     r1, #0
        beq     2f
        sub     r3, r1, #1
        ldr     ip, [r2, r3, lsl #2]
        str     ip, [r2, r1, lsl #2]
        mov     r1, r3
        b       1b
2:      str     r4, [r2]
        ldr     r1, [r10, #P_CNT]
        add     r1, r1, #1
        str     r1, [r10, #P_CNT]
        ldr     r1, [r10, #P_KEPT]
        add     r1, r1, #1
        str     r1, [r10, #P_KEPT]
8:      mov     r0, #0
        mov     sp, r11
        pop     {r4-r11, pc}

flushbyp:
        bl      flush_all
bypass:
        str     r9, [r10, #P_WHY]
        ldr     r0, [r10, #P_BYP]
        add     r0, r0, #1
        str     r0, [r10, #P_BYP]
        mov     r0, r4
        ldr     ip, =FW_UNLOAD | 1
        blx     ip
        mov     sp, r11
        pop     {r4-r11, pc}

        .ltorg
