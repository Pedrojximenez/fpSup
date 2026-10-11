.syntax unified
.arm
.text
/* Probe B1 — does the USB completion-wait FUN_c01e4e80 BLOCK from our task?
 *
 * Builds on the CONFIRMED main-path task recipe (A5). The worker task calls the
 * completion-wait wrapper FUN_c01e4e80(r0=ctx_index, r1=timeout_ms) — THUMB, entry
 * 0xC01E4E81 — with ctx index 0 and a 500 ms timeout, in a loop, with NO transfer
 * armed. The wait's real body FUN_c01e4b30 uses r0 as a bounded array index and has
 * a USB-ready guard (ldrb [0xC31E396C]; returns -1 if USB not up), so this is safe.
 *
 * Readback (mem save 0xC072EC00,,0x40):
 *   [0]=0x42  [4]=create id  [8]=start ret  [12]='WORK'
 *   [16] = loop/wait count over the 1500 ms window:
 *          ~3   => the wait BLOCKED ~500 ms each  => completion-wait works from our task
 *          huge => returned immediately (USB not ready / ctx0 special) — see [20]
 *   [20] = last FUN_c01e4e80 return code (0=event? negative=timeout/err; -1=USB-not-ready path)
 */

.equ STATE,     0xC072EC00
.equ HOOK,      0xC00D0794
.equ HOOK_ORIG, 0xFA046FD7
.equ ACCESSOR,  0xC01EC6F9
.equ FN_CRETSK, 0xC0016A58     /* tk_cre_tsk */
.equ FN_STATSK, 0xC0016BC0     /* tk_sta_tsk (id,0) */
.equ FN_WAIT,   0xC01E4E81     /* FUN_c01e4e80 completion wait — THUMB (odd for blx) : r0=ctx,r1=ms */
.equ WORKER_PRI, 0x1C          /* 28 */

.global cave_entry
cave_entry:
    push    {r4, r5, r6, lr}
    movw    r12, #:lower16:ACCESSOR
    movt    r12, #:upper16:ACCESSOR
    blx     r12
    mov     r4, r0
    movw    r0, #:lower16:STATE
    movt    r0, #:upper16:STATE
    ldr     r1, [r0]
    cmp     r1, #0x42
    beq     cave_done
    mov     r1, #0x42
    str     r1, [r0]
    movw    r0, #:lower16:HOOK
    movt    r0, #:upper16:HOOK
    movw    r1, #:lower16:HOOK_ORIG
    movt    r1, #:upper16:HOOK_ORIG
    str     r1, [r0]
    sub     sp, sp, #32
    mov     r0, #0
    str     r0, [sp, #0]
    mov     r0, #0x41
    str     r0, [sp, #4]
    adr     r0, worker_entry
    str     r0, [sp, #8]
    mov     r0, #WORKER_PRI
    str     r0, [sp, #12]
    movw    r0, #0x2000
    str     r0, [sp, #16]
    movw    r0, #0x5250
    movt    r0, #0x424f
    str     r0, [sp, #20]             @ dsname "PROB"
    movw    r0, #0x0045
    str     r0, [sp, #24]             @ "E"
    mov     r0, #0
    str     r0, [sp, #28]
    mov     r0, sp
    movw    r12, #:lower16:FN_CRETSK
    movt    r12, #:upper16:FN_CRETSK
    blx     r12
    add     sp, sp, #32
    movw    r5, #:lower16:STATE
    movt    r5, #:upper16:STATE
    str     r0, [r5, #4]
    cmp     r0, #0
    ble     cave_done
    mov     r1, #0
    movw    r12, #:lower16:FN_STATSK
    movt    r12, #:upper16:FN_STATSK
    blx     r12
    str     r0, [r5, #8]
cave_done:
    mov     r0, r4
    pop     {r4, r5, r6, pc}

/* ---- worker: loop calling the completion wait ---- */
worker_entry:
    movw    r1, #:lower16:STATE
    movt    r1, #:upper16:STATE
    movw    r0, #0x524b
    movt    r0, #0x574f              @ 'WORK'
    str     r0, [r1, #12]
    push    {r4, lr}
    mov     r4, r1
b_loop:
    ldr     r0, [r4, #16]
    add     r0, r0, #1
    str     r0, [r4, #16]            @ [16] = wait/loop count
    mov     r0, #0                   @ ctx index 0
    movw    r1, #500                 @ timeout 500 ms
    movw    r12, #:lower16:FN_WAIT
    movt    r12, #:upper16:FN_WAIT
    blx     r12                       @ FUN_c01e4e80(0, 500) — switches to Thumb
    str     r0, [r4, #20]            @ [20] = last wait return code
    b       b_loop
