.syntax unified
.arm
.text
/* Integration worker v2 — BOUNDED 16-ROUND autonomous USB echo worker.
 *
 * Extends the PROVEN one-round worker (integration_worker.S, INTEG1 run#2 success) into a
 * bounded loop per Codex's spec:
 *   - loop OUT arm/wait -> IN arm/wait; increment the round counter ONLY after a successful IN.
 *   - stop after 16 rounds and park (do NOT arm another OUT).
 *   - every wait keeps its finite timeout; ANY nonzero arm/wait return -> fail-fast to a parked
 *     FAULT state (record the code + the round it happened on).
 *   - a small inter-round yield gives a scheduling window to re-arm OUT before the host's next OUT
 *     (host runs --limit 16 with its 2500 ms inter-request guard).
 *
 * Same create/start recipe + gyro-hook starter + GO-block as INTEG1. State block 0xC072EC00:
 *   [0]=0x42 cave  [4]=id  [8]=start  [12]='WORK'  [16]=GO
 *   [20]=last OUT arm  [24]=last OUT wait  [28]=last IN arm  [32]=last IN wait
 *   [36]=result marker: 'DONE'(all 16) / 'FALT'(fail-fast)
 *   [40]=pre-GO heartbeat  [44]=stage(1..6 within a round)  [48]=completed rounds
 *   [52]=fault code  [56]=fault round
 */

.equ STATE,     0xC072EC00
.equ GO_OFF,    16
.equ HOOK,      0xC00D0794
.equ HOOK_ORIG, 0xFA046FD7
.equ ACCESSOR,  0xC01EC6F9
.equ FN_CRETSK, 0xC0016A58
.equ FN_STATSK, 0xC0016BC0
.equ FN_DLY,    0xC01F89C4
.equ FN_ENDX,   0xC01E6D49     /* EndTransfer (THUMB) */
.equ FN_STARTX, 0xC01E6B81     /* StartTransfer (THUMB) */
.equ FN_WAIT,   0xC01E4E81     /* FUN_c01e4e80 wait (THUMB) : r0=ctx,r1=ms */
.equ BUF_PTR,   0xC3757A7C
.equ CTX5_TBL,  0xC31E3278
.equ CTX4_TBL,  0xC31E3274
.equ TRB_ARMED, 0x813
.equ WORKER_PRI, 0x1C
.equ TMO,       50000
.equ NROUNDS,   16

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
    str     r0, [sp, #20]
    movw    r0, #0x0045
    str     r0, [sp, #24]
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

/* ================= 16-round worker ================= */
worker_entry:
    push    {r4, r5, r6, r7, r8, lr}   @ 6 regs -> 8-byte aligned; r4-r8 survive firmware calls
    movw    r4, #:lower16:STATE
    movt    r4, #:upper16:STATE
    movw    r0, #0x524b
    movt    r0, #0x574f              @ 'WORK'
    str     r0, [r4, #12]
    mov     r8, #0                    @ completed-round counter
wait_go:
    ldr     r0, [r4, #GO_OFF]
    cmp     r0, #0
    bne     round_loop
    ldr     r0, [r4, #40]
    add     r0, r0, #1
    str     r0, [r4, #40]            @ pre-GO heartbeat
    mov     r0, #20
    movw    r12, #:lower16:FN_DLY
    movt    r12, #:upper16:FN_DLY
    blx     r12
    b       wait_go

round_loop:
    /* ---- arm EP05 OUT ---- */
    movw    r0, #:lower16:BUF_PTR
    movt    r0, #:upper16:BUF_PTR
    ldr     r6, [r0]
    mov     r0, #0xc0000000
    add     r5, r6, r0                @ alias
    mov     r0, #1
    str     r0, [r4, #44]            @ stage 1
    mov     r0, #5
    movw    r12, #:lower16:FN_ENDX
    movt    r12, #:upper16:FN_ENDX
    blx     r12                       @ EndTransfer(5)
    movw    r0, #:lower16:CTX5_TBL
    movt    r0, #:upper16:CTX5_TBL
    ldr     r7, [r0]
    str     r5, [r7]
    mov     r0, #0
    str     r0, [r7, #4]
    mov     r0, #1024
    str     r0, [r7, #8]
    movw    r0, #TRB_ARMED
    str     r0, [r7, #12]
    mov     r0, #2
    str     r0, [r4, #44]            @ stage 2
    mov     r0, #10
    movw    r12, #:lower16:FN_STARTX
    movt    r12, #:upper16:FN_STARTX
    blx     r12                       @ StartTransfer(10)
    str     r0, [r4, #20]            @ OUT arm ret
    cmp     r0, #0
    bne     fault
    /* ---- wait EP05 OUT ---- */
    mov     r0, #3
    str     r0, [r4, #44]            @ stage 3
    mov     r0, #5
    movw    r1, #TMO
    movw    r12, #:lower16:FN_WAIT
    movt    r12, #:upper16:FN_WAIT
    blx     r12                       @ FUN_c01e4e80(5,TMO)
    str     r0, [r4, #24]            @ OUT wait ret
    cmp     r0, #0
    bne     fault
    /* ---- arm EP84 IN ---- */
    movw    r0, #:lower16:BUF_PTR
    movt    r0, #:upper16:BUF_PTR
    ldr     r6, [r0]
    mov     r0, #0xc0000000
    add     r5, r6, r0
    movw    r0, #:lower16:CTX4_TBL
    movt    r0, #:upper16:CTX4_TBL
    ldr     r7, [r0]
    str     r5, [r7]
    mov     r0, #0
    str     r0, [r7, #4]
    mov     r0, #64
    str     r0, [r7, #8]
    movw    r0, #TRB_ARMED
    str     r0, [r7, #12]
    mov     r0, #4
    str     r0, [r4, #44]            @ stage 4
    mov     r0, #9
    movw    r12, #:lower16:FN_STARTX
    movt    r12, #:upper16:FN_STARTX
    blx     r12                       @ StartTransfer(9)
    str     r0, [r4, #28]            @ IN arm ret
    cmp     r0, #0
    bne     fault
    /* ---- wait EP84 IN ---- */
    mov     r0, #5
    str     r0, [r4, #44]            @ stage 5
    mov     r0, #4
    movw    r1, #TMO
    movw    r12, #:lower16:FN_WAIT
    movt    r12, #:upper16:FN_WAIT
    blx     r12                       @ FUN_c01e4e80(4,TMO)
    str     r0, [r4, #32]            @ IN wait ret
    cmp     r0, #0
    bne     fault
    /* ---- round complete: count only after successful IN ---- */
    add     r8, r8, #1
    str     r8, [r4, #48]            @ completed rounds
    cmp     r8, #NROUNDS
    bge     done16
    /* inter-round scheduling window before re-arming OUT */
    mov     r0, #100
    movw    r12, #:lower16:FN_DLY
    movt    r12, #:upper16:FN_DLY
    blx     r12                       @ tk_dly_tsk(100)
    b       round_loop

done16:
    mov     r0, #6
    str     r0, [r4, #44]            @ stage 6
    movw    r0, #0x4f44
    movt    r0, #0x454e              @ 'DONE'
    str     r0, [r4, #36]
    b       park

fault:
    str     r0, [r4, #52]            @ fault code (the nonzero return)
    str     r8, [r4, #56]            @ fault round (0-based completed count)
    movw    r0, #0x4146
    movt    r0, #0x544c              @ 'FALT'
    str     r0, [r4, #36]
park:
    mov     r0, #1000
    movw    r12, #:lower16:FN_DLY
    movt    r12, #:upper16:FN_DLY
    blx     r12
    b       park
