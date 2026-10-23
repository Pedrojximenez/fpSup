@ inputredraw: redraw as soon as a key reaches the GUI, instead of waiting for
@ the next 48 ms CYC_DRAW boundary.  CHANGES STOCK BEHAVIOUR (user agreed).
@
@ Site: C06D1418 `bl C055E1E8` inside UicContentsIfBase::v1 (C06D13A0) -- the
@ one call that puts a key message (down and up) on the GUI queue.  The queue is
@ consumed by the UIC drawer C0561198, which only runs inside DrawThread's
@ redraw round, so stock latency = wait for the next 48 ms round.
@
@ ir_enq_hook(r0 = queue, r1 = msg):
@   C055E1E8(r0, r1)                       stock enqueue first, unchanged
@   if !enable                -> done
@   if recording && !rec_ok   -> done      (C00178D8()->+0x9C, as `status get`)
@   mgr = C05278F8()
@   if C0527F30(mgr) != 0     -> done      (a ReqForceDraw is already pending)
@   if now - last < min_ms    -> preload the CYC_DRAW counters so the next
@                                16 ms tick runs a full round; done
@   last = now; C0527E68(mgr, req)         the stock ReqForceDraw request
@                                          ({1,1,0,0, -1, 0} = C2E45DB0):
@                                          all 4 slots dirty + wake flag 4
@ Nothing in the redraw round itself is touched.
@
@ Position independent.  Writable words: the header only.

        .syntax unified
        .arm

        .equ    FW_ENQ,         0xC055E1E8
        .equ    FW_MGR,         0xC05278F8
        .equ    FW_PENDING,     0xC0527F30
        .equ    FW_REQ,         0xC0527E68
        .equ    FW_SYSSTAT,     0xC00178D8
        .equ    CUR_MS,         0xC301EAE4      @ TK-OS current_time (ms)
        .equ    CYC,            0xC3782F98      @ +0 dirty cnt, +4 req cnt, +8 dirty div, +C req div

@ ---------------------------------------------------------------- header
ir_base:
        .word   0x44524E49                      @ +00 'INRD'
        .word   1                               @ +04 version
ir_enable:
        .word   1                               @ +08 0 = stock
ir_rec_ok:
        .word   0                               @ +0C 1 = also while recording
ir_min_ms:
        .word   16                              @ +10 minimum gap between forced rounds
ir_calls:
        .word   0                               @ +14 key messages seen
ir_kicks:
        .word   0                               @ +18 forced rounds requested
ir_preloads:
        .word   0                               @ +1C too soon -> counters preloaded
ir_skip_rec:
        .word   0                               @ +20 skipped: recording
ir_skip_pend:
        .word   0                               @ +24 skipped: request already pending
ir_last_ms:
        .word   0                               @ +28 time of the last forced round
ir_req:                                         @ +2C copy of C2E45DB0
        .byte   1, 1, 0, 0
        .word   0xFFFFFFFF
        .word   0

@ ---------------------------------------------------------------- hook
        .global ir_enq_hook
ir_enq_hook:
        push    {r4-r7, lr}
        mov     r7, sp
        bic     sp, sp, #7                      @ firmware may arrive with sp = 4 mod 8
        ldr     ip, =FW_ENQ
        blx     ip                              @ r0, r1 as the caller gave them

        adr     r4, ir_base
        ldr     r0, [r4, #0x14]
        add     r0, r0, #1
        str     r0, [r4, #0x14]

        ldr     r0, [r4, #0x08]
        cmp     r0, #0
        beq     9f

        ldr     ip, =FW_SYSSTAT
        blx     ip
        ldrb    r0, [r0, #0x18 + 0x84]          @ is_recording
        cmp     r0, #0
        beq     1f
        ldr     r0, [r4, #0x0C]
        cmp     r0, #0
        bne     1f
        ldr     r0, [r4, #0x20]
        add     r0, r0, #1
        str     r0, [r4, #0x20]
        b       9f
1:
        ldr     ip, =FW_MGR
        blx     ip
        mov     r5, r0
        ldr     ip, =FW_PENDING
        blx     ip
        cmp     r0, #0
        beq     2f
        ldr     r0, [r4, #0x24]
        add     r0, r0, #1
        str     r0, [r4, #0x24]
        b       9f
2:
        ldr     r0, =CUR_MS
        ldr     r6, [r0]
        ldr     r1, [r4, #0x28]
        sub     r2, r6, r1
        ldr     r3, [r4, #0x10]
        cmp     r2, r3
        blo     3f

        str     r6, [r4, #0x28]
        ldr     r0, [r4, #0x18]
        add     r0, r0, #1
        str     r0, [r4, #0x18]
        mov     r0, r5
        add     r1, r4, #0x2C
        ldr     ip, =FW_REQ
        blx     ip
        b       9f
3:                                              @ too soon: next 16 ms tick fires
        ldr     r0, [r4, #0x1C]
        add     r0, r0, #1
        str     r0, [r4, #0x1C]
        mrs     r3, cpsr
        orr     r2, r3, #0xC0                   @ the cyclic handler runs in the timer IRQ
        msr     cpsr_c, r2
        ldr     r0, =CYC
        ldr     r1, [r0, #0x08]
        sub     r1, r1, #1
        ldr     r2, [r0, #0x00]
        cmp     r2, r1
        strlo   r1, [r0, #0x00]
        ldr     r1, [r0, #0x0C]
        sub     r1, r1, #1
        ldr     r2, [r0, #0x04]
        cmp     r2, r1
        strlo   r1, [r0, #0x04]
        msr     cpsr_c, r3
9:
        mov     sp, r7
        pop     {r4-r7, pc}

        .ltorg
ir_end:
