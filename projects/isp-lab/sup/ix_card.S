/* ISPL fork of projects/imx410-lab/sup/ix_card.S (IMXL, sha256 46c55698...):
 * a second task shim (ix_ctl_task), passed to wr_card_init in r3.
 *
 * IMXL: rec-core/writer/wr_card.S (ULWR, sha256 640dafbb...) unchanged but for
 * this line; C entries come from ix_wr.c / ix_card.c.
 *
 * ULWR (Unlocked Writer) -- the writer's inner entry, hooks and veneers (fp 5.02).
 *
 * build.py wraps this in fp_usb_shell/v3 patch_sup: the outer entry claims
 * C063F140, C063F220 and C03A549C (8 bytes each, SL_EXCL, claim only) and then calls
 * `inner` with r0 = its own address, r1 = the service table.  We:
 *   1. continue at the CACHED alias of the block (the loader's block is
 *      non-cacheable; LOSS card.S measured the cost), cleaning first;
 *   2. check both sites still hold the stock bytes;
 *   3. fill the words the shims read (state, C entries);
 *   4. wr_card_init: firmware table, event flag, writer task;
 *   5. only then write the two hooks and publish.
 * Any failure before 5 leaves the firmware untouched.
 *
 * Hook form at C063F140/C063F220 (Thumb functions, 8 bytes, no pc-relative
 * code in them): `ldr.w pc, [pc, #0]` + the address of our ARM shim.  At
 * C03A549C (ARM, C03A5348's `ldrb r3,[fp,#0xd]; cmp r3,#0`, nothing branches
 * into it): `ldr pc, [pc, #-4]` + the address.  ldr pc interworks, so the
 * shims run in ARM state.
 *
 * Defines from build.py: STATE_REL (the state, from `inner`), OFF_* (C entry
 * offsets from c_base, Thumb bit set). */
.syntax unified
.arm
.text

.equ F_DCACHE,     0xC000E91C
.equ SVC_PUBLISH,  24
.equ VOL_LOOKUP,   0xC0644B69    /* C0644B68(dev) -> vol, Thumb             */
.equ SITE140,      0xC063F140
.equ SITE220,      0xC063F220
.equ SITE549C,     0xC03A549C
.equ LDR_PC_M4,    0xE51FF004    /* ldr pc, [pc, #-4]                        */
.equ S549C_0,      0xE5DB300D    /* ldrb r3, [fp, #0xd]                      */
.equ S549C_1,      0xE3530000    /* cmp r3, #0                               */
.equ LDRW_PC0,     0xF000F8DF    /* DF F8 00 F0: ldr.w pc, [pc, #0]          */
.equ S140_0,       0x45F0E92D    /* push.w {r4-r8, sl, lr}                   */
.equ S140_1,       0x4604B084    /* sub sp, #0x10 ; mov r4, r0               */
.equ S220_0,       0x41F0E92D    /* push.w {r4-r8, lr}                       */
.equ S220_1,       0x460D4607    /* mov r7, r0 ; mov r5, r1                  */

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.macro SITE_IS addr, w0, w1
    LDA     r0, \addr
    ldr     r1, [r0]
    LDA     r2, \w0
    cmp     r1, r2
    bne     out
    ldr     r1, [r0, #4]
    LDA     r2, \w1
    cmp     r1, r2
    bne     out
.endm

.macro ENTRY_WORD label, off
    LDA     r0, \off
    add     r0, r8, r0
    str     r0, \label
.endm

inner:
    push    {r4, r5, r6, r7, r8, r9, r10, r11, ip, lr}
    mov     r4, r0
    mov     r5, r1                      @ svc
    LDA     ip, F_DCACHE                @ the cached alias must hold no stale line
    blx     ip
    mov     r6, #0
    cmp     r4, #0x40000000
    blo     1f
    cmp     r4, #0x80000000
    movlo   r6, #0x80000000             @ VA 0x4xxxxxxx -> cached at +0x80000000
1:  adr     r0, cached
    add     r0, r0, r6
    bx      r0
cached:                                 @ from here every adr is the cached one
    SITE_IS SITE140, S140_0, S140_1
    SITE_IS SITE220, S220_0, S220_1
    SITE_IS SITE549C, S549C_0, S549C_1
    adr     r7, inner
    LDA     r0, STATE_REL
    add     r7, r7, r0                  @ r7 = wr_t
    str     r7, g_state
    adr     r8, c_base
    ENTRY_WORD w_init,      OFF_INIT
    ENTRY_WORD w_send,      OFF_SEND
    ENTRY_WORD w_installed, OFF_INSTALLED
    ENTRY_WORD w_cookie,    OFF_COOKIE
    ENTRY_WORD w_acq,       OFF_ACQ
    ENTRY_WORD w_add,       OFF_ADD
    ENTRY_WORD w_ckpt,      OFF_CKPT
    ENTRY_WORD w_rb,        OFF_RB
    ENTRY_WORD w_rel,       OFF_REL
    ENTRY_WORD w_task,      OFF_TASK
    ENTRY_WORD w_start,     OFF_START
    ENTRY_WORD w_late,      OFF_LATE
    ENTRY_WORD w_ctl,       OFF_CTL
    mov     r0, r5                      @ the words above reach memory
    ldr     ip, [r5, #SVC_PUBLISH]
    blx     ip
    mov     r0, r7
    adr     r1, task_shim
    adr     r2, veneers
    adr     r3, ctl_shim
    ldr     ip, w_init
    blx     ip                          @ wr_card_init(w, task, veneers, ctl)
    cmp     r0, #0
    bne     out
#ifndef ISPL_CTL_ONLY                   /* the control-only build arms no writer hook */
    LDA     r0, SITE140                 @ armed last
    LDA     r1, LDRW_PC0
    adr     r2, hook140
    str     r1, [r0]
    str     r2, [r0, #4]
    LDA     r0, SITE220
    adr     r2, hook220
    str     r1, [r0]
    str     r2, [r0, #4]
    LDA     r0, SITE549C
    LDA     r1, LDR_PC_M4
    adr     r2, hook549c
    str     r2, [r0, #4]                @ the address before the instruction
    str     r1, [r0]
#endif
    mov     r0, r5
    ldr     ip, [r5, #SVC_PUBLISH]
    blx     ip
out:
    pop     {r4, r5, r6, r7, r8, r9, r10, r11, ip, pc}

/* C063F140(vol).  lr = the Thumb caller (0xC063F34D from C063F310).  The
 * firmware may arrive with sp = 4 mod 8: align around the C call. */
hook140:
    push    {r0, r4, r5, lr}
    mov     r4, sp
    bic     sp, sp, #7
    mov     r2, lr
    mov     r1, r0
    ldr     r0, g_state
    ldr     ip, w_send
    blx     ip                          @ wr_send(w, vol, lr): 0 = done
    mov     sp, r4
    cmp     r0, #0
    pop     {r0, r4, r5, lr}
    bxeq    lr
    push    {r4, r5, r6, r7, r8, sl, lr}    @ stock C063F140, replayed
    sub     sp, sp, #0x10
    mov     r4, r0
    ldr     pc, resume140

/* C063F220(dev, params) -> 1 = aggregation set up.  A take starts (ours or
 * not): forget the last stop.  Run stock, then take the vol's arena pointers. */
hook220:
    push    {r4, r5, r6, lr}
    mov     r5, r0                      @ dev (callee-saved through stock)
    mov     r6, r1
    mov     r4, sp
    bic     sp, sp, #7
    ldr     r0, g_state
    ldr     ip, w_start
    blx     ip                          @ wr_take_start(w)
    mov     sp, r4
    mov     r0, r5
    mov     r1, r6
    bl      stock220
    cmp     r0, #1
    bne     2f
    mov     r4, sp
    bic     sp, sp, #7
    mov     r0, r5
    ldr     ip, vol_lookup
    blx     ip
    mov     r1, r0
    ldr     r0, g_state
    ldr     ip, w_installed
    blx     ip                          @ wr_installed(w, vol)
    mov     sp, r4
    mov     r0, #1
2:  pop     {r4, r5, r6, pc}
stock220:
    push    {r4, r5, r6, r7, r8, lr}    @ stock C063F220, replayed
    mov     r7, r0
    mov     r5, r1
    ldr     pc, resume220

/* C03A5348 (SRecFile) after its write C069ADE0 returned (r6:r7 = bytes),
 * fp = mgr, r4 = the frame's node; r0-r3, ip, lr are dead here.  A frame
 * written after our stop restored the vol takes stock's own aggregation-off
 * branch (C03A54A8: C03A55D0(node, written ? 0 : -1)). */
hook549c:
    mov     r3, sp
    bic     sp, sp, #7
    push    {r3, lr}
    ldr     r0, g_state
    mov     r1, fp
    mov     r2, r4
    ldr     ip, w_late
    blx     ip                          @ wr_late_frame(w, mgr, node)
    pop     {r3, lr}
    mov     sp, r3
    ldrb    r3, [fp, #0xd]              @ stock C03A549C, replayed
    cmp     r0, #0
    movne   r3, #0
    cmp     r3, #0                      @ stock C03A54A0
    ldr     pc, resume549c

task_shim:                              @ tk_sta_tsk entry; wr_task never returns
    ldr     r0, g_state
    ldr     pc, w_task

ctl_shim:                               @ the control task; ix_ctl_task never returns
    ldr     r0, g_state
    ldr     pc, w_ctl

/* vol+0x4834..0x4848 while installed: wr.h slot order, 16 bytes apart.  Tail
 * calls: the C returns straight to the firmware (built -mstackrealign). */
    .align  4
veneers:
    mov     r2, r1                      @ +0x4834 cookie(frame, status)
    mov     r1, r0
    ldr     r0, g_state
    ldr     pc, w_cookie
    ldr     r0, g_state                 @ +0x4838 acquire()
    ldr     pc, w_acq
    nop
    nop
    mov     r2, r1                      @ +0x483C add(addr, len)
    mov     r1, r0
    ldr     r0, g_state
    ldr     pc, w_add
    ldr     r0, g_state                 @ +0x4840 checkpoint()
    ldr     pc, w_ckpt
    nop
    nop
    ldr     r0, g_state                 @ +0x4844 rollback()
    ldr     pc, w_rb
    nop
    nop
    ldr     r0, g_state                 @ +0x4848 release()
    ldr     pc, w_rel
    nop
    nop

    .align  2
g_state:     .word 0
w_init:      .word 0
w_send:      .word 0
w_installed: .word 0
w_cookie:    .word 0
w_acq:       .word 0
w_add:       .word 0
w_ckpt:      .word 0
w_rb:        .word 0
w_rel:       .word 0
w_task:      .word 0
w_start:     .word 0
w_late:      .word 0
w_ctl:       .word 0
resume140:   .word 0xC063F149
resume220:   .word 0xC063F229
resume549c:  .word 0xC03A54A4      /* ARM */
vol_lookup:  .word VOL_LOOKUP
    .align  3
c_base:
    /* the compiled C (bq.c, wr.c, wr_card.c as one unit) is appended here */
