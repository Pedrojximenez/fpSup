.syntax unified
.arm
.text
/* Shell-over-USB worker v1 — SAFE bounded "mem set ADDR VAL" over USB.
 *
 * Per Codex's safety boundary: keep the wire text in shell syntax, but the worker itself parses and
 * executes ONLY `mem set <hexaddr> <hexval>`, and ONLY when <addr> is in the scratch allowlist
 * [0xC072EC60, 0xC072EC7C]. It does NOT call the firmware shell dispatcher FUN_c03d9c20 (shared
 * console/context concurrency with the prio-25 shell task is unproven). Reject everything else.
 *
 * Coherent read (Codex): the received command bytes are read via the UNCACHED CPU view
 * raw_buf(+0x40000000); the TRB still uses raw_buf(+0xC0000000). Never call FUN_c000ea54.
 *
 * One command / one round + SD readback for the minimal proof. Ack = echo the UNCHANGED request frame
 * back (valid daemon CRC) only after a successful bounded write; on parse/range failure, still echo
 * (host sees OK) but the on-camera parse-result marker records the rejection.
 *
 * State 0xC072EC00 (readback 0x80):
 *   [0]=0x42 [4]=id [8]=start [12]='WORK' [16]=GO
 *   [20]=OUT arm [24]=OUT wait [28]=IN arm [32]=IN wait  [36]='DONE'
 *   [40]=pre-GO hb  [44]=stage
 *   [48]=parse result (1=prefix-mismatch 2=addr-out-of-range 3=OK-written)
 *   [52]=parsed addr  [56]=parsed val
 *   [0x60..0x7C]=scratch allowlist (mem set target); zeroed, then written by the command
 */

.equ STATE,     0xC072EC00
.equ GO_OFF,    16
.equ HOOK,      0xC00D0794
.equ HOOK_ORIG, 0xFA046FD7
.equ ACCESSOR,  0xC01EC6F9
.equ FN_CRETSK, 0xC0016A58
.equ FN_STATSK, 0xC0016BC0
.equ FN_DLY,    0xC01F89C4
.equ FN_ENDX,   0xC01E6D49
.equ FN_STARTX, 0xC01E6B81
.equ FN_WAIT,   0xC01E4E81
.equ BUF_PTR,   0xC3757A7C
.equ CTX5_TBL,  0xC31E3278
.equ CTX4_TBL,  0xC31E3274
.equ TRB_ARMED, 0x813
.equ WORKER_PRI, 0x1C
.equ TMO,       50000
.equ UNCACHED,  0x40000000     /* raw_buf + this = 0x44.. CPU read view (Codex) */
.equ CACHED,    0xC0000000     /* raw_buf + this = 0xC4.. TRB view (unchanged) */
.equ ALLOW_LO,  0xC072EC60
.equ ALLOW_HI,  0xC072EC7C

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

/* ================= worker ================= */
worker_entry:
    push    {r4, r5, r6, r7, r8, r9, r10, lr}   @ 8 regs -> 8-byte aligned
    movw    r4, #:lower16:STATE
    movt    r4, #:upper16:STATE
    movw    r0, #0x524b
    movt    r0, #0x574f              @ 'WORK'
    str     r0, [r4, #12]
wait_go:
    ldr     r0, [r4, #GO_OFF]
    cmp     r0, #0
    bne     go
    ldr     r0, [r4, #40]
    add     r0, r0, #1
    str     r0, [r4, #40]
    mov     r0, #20
    movw    r12, #:lower16:FN_DLY
    movt    r12, #:upper16:FN_DLY
    blx     r12
    b       wait_go

go:
    /* ---- arm EP05 OUT ---- */
    movw    r0, #:lower16:BUF_PTR
    movt    r0, #:upper16:BUF_PTR
    ldr     r6, [r0]                  @ r6 = raw buf
    mov     r0, #CACHED
    add     r5, r6, r0                @ r5 = TRB alias (0xC4..)
    mov     r0, #1
    str     r0, [r4, #44]
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
    str     r0, [r4, #44]
    mov     r0, #10
    movw    r12, #:lower16:FN_STARTX
    movt    r12, #:upper16:FN_STARTX
    blx     r12                       @ StartTransfer(10)
    str     r0, [r4, #20]
    /* ---- wait EP05 OUT (receive the command frame) ---- */
    mov     r0, #3
    str     r0, [r4, #44]
    mov     r0, #5
    movw    r1, #TMO
    movw    r12, #:lower16:FN_WAIT
    movt    r12, #:upper16:FN_WAIT
    blx     r12
    str     r0, [r4, #24]

    /* ================= parse + execute "mem set ADDR VAL" ================= */
    /* r6 = raw buf; command frame payload = uncached (raw+0x40000000)+20 */
    movw    r0, #:lower16:BUF_PTR
    movt    r0, #:upper16:BUF_PTR
    ldr     r6, [r0]
    mov     r0, #UNCACHED
    add     r6, r6, r0                @ r6 = uncached buf base (0x44..)
    add     r10, r6, #20              @ r10 = command string ptr (payload, null-terminated by padding)
    /* check prefix "mem set " (8 bytes): "mem "=0x206D656D, "set "=0x20746573 */
    ldr     r0, [r10]
    movw    r1, #0x656d
    movt    r1, #0x206d              @ 0x206D656D
    cmp     r0, r1
    bne     rej_prefix
    ldr     r0, [r10, #4]
    movw    r1, #0x6573
    movt    r1, #0x2074              @ 0x20746573
    cmp     r0, r1
    bne     rej_prefix
    add     r10, r10, #8             @ past "mem set "
    /* parse hex addr -> r8 */
    mov     r0, r10
    bl      parse_hex                @ r2=value, r0=ptr after
    mov     r8, r2
    mov     r10, r0
    /* skip one space */
    ldrb    r0, [r10]
    cmp     r0, #0x20
    addeq   r10, r10, #1
    /* parse hex val -> r9 */
    mov     r0, r10
    bl      parse_hex
    mov     r9, r2
    str     r8, [r4, #52]           @ parsed addr
    str     r9, [r4, #56]           @ parsed val
    /* allowlist check: ALLOW_LO <= addr <= ALLOW_HI (unsigned) */
    movw    r0, #:lower16:ALLOW_LO
    movt    r0, #:upper16:ALLOW_LO
    cmp     r8, r0
    blo     rej_range
    movw    r0, #:lower16:ALLOW_HI
    movt    r0, #:upper16:ALLOW_HI
    cmp     r8, r0
    bhi     rej_range
    /* execute the bounded write */
    str     r9, [r8]
    mov     r0, #3
    str     r0, [r4, #48]           @ parse result = 3 (OK written)
    b       arm_in
rej_prefix:
    mov     r0, #1
    str     r0, [r4, #48]           @ 1 = prefix mismatch
    b       arm_in
rej_range:
    mov     r0, #2
    str     r0, [r4, #48]           @ 2 = addr out of allowlist
    /* (do NOT write) */

arm_in:
    /* ---- arm EP84 IN (echo the unchanged request frame back as ack) ---- */
    movw    r0, #:lower16:BUF_PTR
    movt    r0, #:upper16:BUF_PTR
    ldr     r6, [r0]
    mov     r0, #CACHED
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
    str     r0, [r4, #44]
    mov     r0, #9
    movw    r12, #:lower16:FN_STARTX
    movt    r12, #:upper16:FN_STARTX
    blx     r12                       @ StartTransfer(9)
    str     r0, [r4, #28]
    mov     r0, #5
    str     r0, [r4, #44]
    mov     r0, #4
    movw    r1, #TMO
    movw    r12, #:lower16:FN_WAIT
    movt    r12, #:upper16:FN_WAIT
    blx     r12
    str     r0, [r4, #32]
    mov     r0, #6
    str     r0, [r4, #44]
    movw    r0, #0x4f44
    movt    r0, #0x454e              @ 'DONE'
    str     r0, [r4, #36]
park:
    mov     r0, #1000
    movw    r12, #:lower16:FN_DLY
    movt    r12, #:upper16:FN_DLY
    blx     r12
    b       park

/* parse_hex: r0=ptr -> r2=value, r0=ptr after last hex digit. skips optional "0x". uses r1,r3. */
parse_hex:
    mov     r2, #0
    /* skip "0x"/"0X" */
    ldrb    r1, [r0]
    cmp     r1, #0x30               @ '0'
    bne     ph_loop
    ldrb    r1, [r0, #1]
    cmp     r1, #0x78               @ 'x'
    cmpne   r1, #0x58               @ 'X'
    addeq   r0, r0, #2
ph_loop:
    ldrb    r1, [r0]
    /* digit? '0'..'9' */
    sub     r3, r1, #0x30
    cmp     r3, #9
    bls     ph_acc
    /* 'a'..'f' */
    sub     r3, r1, #0x61
    cmp     r3, #5
    bhi     ph_upper
    add     r3, r3, #10
    b       ph_acc
ph_upper:
    /* 'A'..'F' */
    sub     r3, r1, #0x41
    cmp     r3, #5
    bhi     ph_done
    add     r3, r3, #10
ph_acc:
    lsl     r2, r2, #4
    orr     r2, r2, r3
    add     r0, r0, #1
    b       ph_loop
ph_done:
    bx      lr
