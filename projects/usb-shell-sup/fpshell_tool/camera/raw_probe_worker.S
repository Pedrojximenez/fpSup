.syntax unified
.arm
.text
/* Raw-push PROBE worker — prove the camera can DMA the sensor raw buffer (0x50000000) out EP84 IN at
 * SuperSpeed bulk rates, and let the host measure real MB/s.
 *
 * Per notes/RAW_PUSH.md: single-TRB max ~16MB (24-bit size); copy-free — the DWC3 can DMA straight from
 * 0x50000000. So the worker loops: write TRB{bufptr=0x50000000, size=0xFF0000, ctrl=0x813} into the
 * ctx4 (EP84 IN) TRB, StartTransfer(9), wait FUN_c01e4e80(4). The host does one big bulk-IN per chunk
 * (RAWREAD) and times it. Content need not be a valid frame for a throughput proof.
 *
 * Created/started + GO-blocked exactly like the proven shell worker (gyro hook 0xC00D0794).
 * State 0xC072F000: [0]=0x42 [4]=id [8]=start [12]='WORK' [16]=GO
 *   [20]=last StartTransfer(9) ret  [24]=last wait ret  [28]=chunks pushed  [2C]=pre-GO hb
 */

.equ STATE,     0xC072F000
.equ HOOK,      0xC00D0794
.equ HOOK_ORIG, 0xFA046FD7
.equ ACCESSOR,  0xC01EC6F9
.equ FN_CRETSK, 0xC0016A58
.equ FN_STATSK, 0xC0016BC0
.equ FN_DLY,    0xC01F89C4
.equ FN_STARTX, 0xC01E6B81     /* StartTransfer (THUMB) */
.equ FN_WAIT,   0xC01E4E81     /* FUN_c01e4e80 wait (THUMB) : r0=ctx,r1=ms */
.equ CTX4_TBL,  0xC31E3274     /* [.] = EP84 IN TRB table ptr */
.equ RAWBUF,    0x50000000     /* sensor raw / LV ring base */
.equ CHUNK,     0x00FF0000     /* ~16 MB (<= 24-bit TRB size max) */
.equ TRB_ARMED, 0x813
.equ WORKER_PRI, 0x1C
.equ TMO,       50000

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

/* ================= raw-push probe worker ================= */
worker_entry:
    push    {r4, r5, r6, r7, lr}
    movw    r4, #:lower16:STATE
    movt    r4, #:upper16:STATE
    movw    r0, #0x524b
    movt    r0, #0x574f
    str     r0, [r4, #12]            @ 'WORK'
wait_go:
    ldr     r0, [r4, #16]
    cmp     r0, #0
    bne     push_loop
    ldr     r0, [r4, #0x2c]
    add     r0, r0, #1
    str     r0, [r4, #0x2c]
    mov     r0, #20
    movw    r12, #:lower16:FN_DLY
    movt    r12, #:upper16:FN_DLY
    blx     r12
    b       wait_go

push_loop:
    /* write the big TRB into ctx4 (EP84 IN) */
    movw    r0, #:lower16:CTX4_TBL
    movt    r0, #:upper16:CTX4_TBL
    ldr     r7, [r0]                  @ r7 = EP84 TRB
    movw    r5, #:lower16:RAWBUF
    movt    r5, #:upper16:RAWBUF
    str     r5, [r7]                  @ bufptr = 0x50000000  (direct; try no alias first)
    mov     r0, #0
    str     r0, [r7, #4]
    movw    r0, #:lower16:CHUNK
    movt    r0, #:upper16:CHUNK
    str     r0, [r7, #8]              @ size = ~16MB
    movw    r0, #TRB_ARMED
    str     r0, [r7, #12]
    dsb
    mov     r0, #9
    movw    r12, #:lower16:FN_STARTX
    movt    r12, #:upper16:FN_STARTX
    blx     r12                       @ StartTransfer(9) EP84 IN
    str     r0, [r4, #20]            @ last StartTransfer ret
    mov     r0, #4
    movw    r1, #TMO
    movw    r12, #:lower16:FN_WAIT
    movt    r12, #:upper16:FN_WAIT
    blx     r12                       @ wait completion (host drained the chunk)
    str     r0, [r4, #24]            @ last wait ret
    ldr     r0, [r4, #28]
    add     r0, r0, #1
    str     r0, [r4, #28]            @ chunks pushed
    mov     r0, #1
    movw    r12, #:lower16:FN_DLY
    movt    r12, #:upper16:FN_DLY
    blx     r12                       @ tiny yield
    b       push_loop
