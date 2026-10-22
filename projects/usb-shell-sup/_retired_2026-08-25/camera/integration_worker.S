.syntax unified
.arm
.text
/* Integration worker v1 — the autonomous USB echo worker as a real main-path task.
 *
 * Built on the CONFIRMED A5 task recipe + Codex's v29 constraints:
 *   - created/started at boot via the gyro one-shot hook 0xC00D0794 (A5, self-restoring)
 *   - BLOCKS behind the GO flag STATE[16]=0xC072EC10 (set by AutoRun *after* `echo`, i.e.
 *     after v27 registration + ctx4-mode2 restore + ctx4/ctx5 init are complete)
 *   - worker ONLY does EndTransfer / prepare TRB / StartTransfer / wait. It does NOT touch
 *     registration, ctx4-mode restore, ctx4 init, or ctx5 config (owned by the v27 path).
 *   - ONE round only, no teardown; records every return code.
 *
 * Arm sequences copied verbatim from v29 ep05_ep84_echo.S stage0 (EP05 OUT) and stage6 (EP84 IN).
 * Wait indices from Codex: EP05 OUT = FUN_c01e4e80(5,tmo), EP84 IN = FUN_c01e4e80(4,tmo).
 *
 * State block 0xC072EC00:
 *   [0]=0x42 cave marker   [4]=create id   [8]=start ret   [12]='WORK'
 *   [16]=GO flag (AutoRun sets 1)          [20]=OUT arm ret (StartTransfer 10)
 *   [24]=OUT wait ret FUN_c01e4e80(5)      [28]=IN arm ret (StartTransfer 9)
 *   [32]=IN wait ret FUN_c01e4e80(4)       [36]='DONE'   [40]=pre-GO wait heartbeat
 */

.equ STATE,     0xC072EC00
.equ GO_OFF,    16
.equ HOOK,      0xC00D0794
.equ HOOK_ORIG, 0xFA046FD7
.equ ACCESSOR,  0xC01EC6F9
.equ FN_CRETSK, 0xC0016A58     /* tk_cre_tsk */
.equ FN_STATSK, 0xC0016BC0     /* tk_sta_tsk (id,0) */
.equ FN_DLY,    0xC01F89C4     /* tk_dly_tsk (ms) */
.equ FN_ENDX,   0xC01E6D49     /* EndTransfer (THUMB) : r0=ctx */
.equ FN_STARTX, 0xC01E6B81     /* StartTransfer (THUMB) : r0=(ep<<1)|dir param */
.equ FN_WAIT,   0xC01E4E81     /* FUN_c01e4e80 completion wait (THUMB) : r0=ctx_index, r1=ms */
.equ BUF_PTR,   0xC3757A7C     /* [.] = DMA buffer base (memmgr bufmem get) */
.equ CTX5_TBL,  0xC31E3278     /* [.] = EP05 OUT TRB table */
.equ CTX4_TBL,  0xC31E3274     /* [.] = EP84 IN  TRB table */
.equ TRB_ARMED, 0x813
.equ WORKER_PRI, 0x1C          /* 28 */
.equ TMO,       50000          /* wait timeout ms (generous; host pings after GO) */
/* STAGE marker at STATE[44]: 1=before EndTransfer(5) 2=before StartTransfer(10)
   3=before OUT wait 4=before StartTransfer(9) 5=before IN wait 6=reached DONE. */

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
    str     r1, [r0]                  @ self-unhook gyro
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

/* ================= worker ================= */
worker_entry:
    movw    r4, #:lower16:STATE
    movt    r4, #:upper16:STATE
    movw    r0, #0x524b
    movt    r0, #0x574f              @ 'WORK'
    str     r0, [r4, #12]
    push    {r5, r6, r7, lr}
    /* --- block until GO --- */
wait_go:
    ldr     r0, [r4, #GO_OFF]
    cmp     r0, #0
    bne     go
    ldr     r0, [r4, #40]
    add     r0, r0, #1
    str     r0, [r4, #40]            @ pre-GO heartbeat
    mov     r0, #20
    movw    r12, #:lower16:FN_DLY
    movt    r12, #:upper16:FN_DLY
    blx     r12                       @ tk_dly_tsk(20)
    b       wait_go

go:
    /* ---- arm EP05 OUT (v29 stage0) ---- */
    movw    r0, #:lower16:BUF_PTR
    movt    r0, #:upper16:BUF_PTR
    ldr     r6, [r0]                  @ r6 = buf base
    mov     r0, #0xc0000000
    add     r5, r6, r0                @ r5 = alias = buf + 0xC0000000
    mov     r0, #1
    str     r0, [r4, #44]            @ STAGE 1
    mov     r0, #5
    movw    r12, #:lower16:FN_ENDX
    movt    r12, #:upper16:FN_ENDX
    blx     r12                       @ EndTransfer(5)
    movw    r0, #:lower16:CTX5_TBL
    movt    r0, #:upper16:CTX5_TBL
    ldr     r7, [r0]                  @ r7 = EP05 TRB
    str     r5, [r7]
    mov     r0, #0
    str     r0, [r7, #4]
    mov     r0, #1024
    str     r0, [r7, #8]
    movw    r0, #TRB_ARMED
    str     r0, [r7, #12]
    mov     r0, #2
    str     r0, [r4, #44]            @ STAGE 2
    mov     r0, #10
    movw    r12, #:lower16:FN_STARTX
    movt    r12, #:upper16:FN_STARTX
    blx     r12                       @ StartTransfer(10)
    str     r0, [r4, #20]            @ [20] OUT arm ret
    /* ---- wait EP05 OUT complete ---- */
    mov     r0, #3
    str     r0, [r4, #44]            @ STAGE 3
    mov     r0, #5
    movw    r1, #TMO
    movw    r12, #:lower16:FN_WAIT
    movt    r12, #:upper16:FN_WAIT
    blx     r12                       @ FUN_c01e4e80(5, TMO)
    str     r0, [r4, #24]            @ [24] OUT wait ret
    /* ---- arm EP84 IN (v29 stage6) ---- */
    movw    r0, #:lower16:BUF_PTR
    movt    r0, #:upper16:BUF_PTR
    ldr     r6, [r0]
    mov     r0, #0xc0000000
    add     r5, r6, r0
    movw    r0, #:lower16:CTX4_TBL
    movt    r0, #:upper16:CTX4_TBL
    ldr     r7, [r0]                  @ r7 = EP84 TRB
    str     r5, [r7]
    mov     r0, #0
    str     r0, [r7, #4]
    mov     r0, #64
    str     r0, [r7, #8]
    movw    r0, #TRB_ARMED
    str     r0, [r7, #12]
    mov     r0, #4
    str     r0, [r4, #44]            @ STAGE 4
    mov     r0, #9
    movw    r12, #:lower16:FN_STARTX
    movt    r12, #:upper16:FN_STARTX
    blx     r12                       @ StartTransfer(9)
    str     r0, [r4, #28]            @ [28] IN arm ret
    /* ---- wait EP84 IN complete ---- */
    mov     r0, #5
    str     r0, [r4, #44]            @ STAGE 5
    mov     r0, #4
    movw    r1, #TMO
    movw    r12, #:lower16:FN_WAIT
    movt    r12, #:upper16:FN_WAIT
    blx     r12                       @ FUN_c01e4e80(4, TMO)
    str     r0, [r4, #32]            @ [32] IN wait ret
    /* ---- done: one round, no teardown ---- */
    mov     r0, #6
    str     r0, [r4, #44]            @ STAGE 6 (reached DONE)
    movw    r0, #0x4f44
    movt    r0, #0x454e              @ 'DONE'
    str     r0, [r4, #36]
done_park:
    mov     r0, #1000
    movw    r12, #:lower16:FN_DLY
    movt    r12, #:upper16:FN_DLY
    blx     r12
    b       done_park
