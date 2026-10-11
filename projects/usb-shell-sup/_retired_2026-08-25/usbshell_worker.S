/* ============================================================================
 * usbshell_worker — USB shell over the camera's own PTP bulk pipes
 * ============================================================================
 *
 * The gadget is the firmware's stock PTP gadget, untouched: the firmware builds
 * its descriptors, creates and enables its endpoints, and rebuilds them after a
 * record-mode reconfig.  AutoRun changes exactly two words:
 *
 *   0xC0031ADC  mode 5's class handler -> NULL   (FUN_c04dbc10 only answers the
 *               PTP class control requests 0x64/0x66/0x67 and never touches the
 *               bulk endpoints, so nothing is left to compete for them)
 *   0xC0CF3740  interface class 06/01/01 -> ff/ff/ff  (so the host's PTP stack
 *               does not bind the interface out from under us)
 *
 * Everything the old worker did to fake firmware ownership is therefore gone:
 * no descriptor hook, no CTX4_MODE write, no FUN_c01e62a9, no DALEPENA poke, no
 * recording gate, no GO handshake.
 *
 * ENDPOINTS — the PTP gadget's own, verified against the firmware's transfer
 * helper at 0xC01E5BC0 which arms them exactly this way:
 *     EP 0x01 OUT bulk   logical 1   physical 2   TRB ptr @ 0xC31E3268
 *     EP 0x82 IN  bulk   logical 2   physical 5   TRB ptr @ 0xC31E326C
 *     (EP 0x83 IN interrupt exists and is left alone)
 *   physical = (logical << 1) | (dir == IN); StartTransfer takes physical,
 *   EndTransfer/Wait take logical; TRB buffer address is CPU - 0x40000000 and
 *   the control word is 0x813 — all four confirmed against firmware code.
 *
 * COMMAND SET: `shl <line>` only.  The firmware shell's own commands (including
 * `mem set` and `mem save`) are reachable through it, so nothing else is needed.
 *
 * WIRE FORMAT: FPSH v1, 64-byte frame.  Replies may be CHUNKED: flags bit0 means
 * another frame follows, so shell output is no longer truncated at 44 bytes.
 * A long command may spill past byte 64 of the same OUT transfer, because the
 * worker reads the payload as a NUL-terminated string.
 *
 * STATE @0xC072F000 (read with: shl mem save \VSHL.BIN 0xC072F000,,0x40)
 *   +00 'VSHL'  +04 task id     +08 start ret   +0C rounds
 *   +10 OUT arm +14 OUT wait    +18 IN arm      +1C IN wait
 *   +20 served  +24 faults      +28 gate holds  +2C last USB_STATE
 * ========================================================================== */

/* ---- firmware entry points ---- */
.equ FN_CRETSK,   0xC0016A58      /* tk_cre_tsk(desc) -> id                    */
.equ FN_STATSK,   0xC0016BC0      /* tk_sta_tsk(id, code)                      */
.equ FN_DLY,      0xC01F89C4      /* delay(ms), yields                         */
.equ FN_ENDX,     0xC01E6D49      /* EndTransfer(logical_ep)          [thumb]  */
.equ FN_STARTX,   0xC01E6B81      /* StartTransfer(physical_ep)       [thumb]  */
.equ FN_WAIT,     0xC01E4E81      /* WaitTransfer(logical_ep, tmo)    [thumb]  */
.equ FN_SHINIT,   0xC03D9A10      /* shell ctx one-time init                   */
.equ FN_SHPUSH,   0xC03D9AC0      /* push output sink                          */
.equ FN_SHPOP,    0xC03D9B20      /* pop output sink                           */
.equ FN_SHEXEC,   0xC03D9C20      /* tokenize + dispatch + run one line        */
.equ FN_VSNPRINT, 0xC0013F48      /* vsnprintf(buf,size,fmt,va)                */

/* ---- firmware data ---- */
.equ BUF_PTR,     0xC3757A7C      /* memmgr bufmem result: [0] = CPU address   */
.equ EP_OUT_TRB,  0xC31E3268      /* PTP EP 0x01 OUT: table[1]                 */
.equ EP_IN_TRB,   0xC31E326C      /* PTP EP 0x82 IN : table[2]                 */
.equ USB_STATE,   0xC31E3748      /* <2 not configured, ==4 suspended          */
.equ SHELL_CTX,   0xC3756904      /* firmware shell context singleton          */

.equ PHYS_OUT,    2
.equ PHYS_IN,     5
.equ LOG_OUT,     1
.equ LOG_IN,      2

/* ---- our RAM (see SHELL_MEMORY_MAP.md; 0xC072F050..7F left for hook-push) ---- */
.equ STATE,       0xC072F000      /* 16 words                                  */
.equ CAP_OFF,     0xC072F040      /* capture write offset                      */
.equ CAP_BUF,     0xC072F080      /* capture buffer                            */
.equ CAP_SZ,      0x0400          /* 1 KiB, ends 0xC072F480                    */

/* ---- bootstrap: one-shot gyro-callback hook that creates the task ---- */
.equ HOOK,        0xC00D0794
.equ HOOK_ORIG,   0xFA046FD7      /* BLX 0xC01EC6F8                            */
.equ ACCESSOR,    0xC01EC6F9      /* the thumb function the hook displaced     */

.equ TRB_ARMED,   0x813
.equ TMO,         50000
.equ WORKER_PRI,  0x1C            /* 28; verified safe (TASK_ABI_VERIFIED.md)  */
.equ STKSZ,       0x2000          /* 8 KiB; NEVER raise, shared stack pool     */
.equ UNCACHED,    0x40000000
.equ DMA_BIAS,    0xC0000000      /* +0xC0000000 mod 2^32 == -0x40000000       */
.equ CHUNK,       44              /* payload bytes per FPSH frame              */

.macro LDW reg, val
    movw    \reg, #:lower16:\val
    movt    \reg, #:upper16:\val
.endm

/* ==========================================================================
 * cave_entry — runs once from the gyro callback site, creates the worker task
 * and puts the original instruction back.  Must call the displaced accessor
 * first and return its value.
 * ========================================================================== */
.global cave_entry
cave_entry:
    push    {r4, r5, lr}
    LDW     r12, ACCESSOR
    blx     r12
    mov     r4, r0                  @ preserve the accessor's return value

    LDW     r5, STATE
    ldr     r0, [r5]
    LDW     r1, 0x4C485356          @ 'VSHL'
    cmp     r0, r1
    beq     cave_done               @ already bootstrapped

    str     r1, [r5]                @ claim, before anything can re-enter
    LDW     r0, HOOK
    LDW     r1, HOOK_ORIG
    str     r1, [r0]                @ restore the displaced instruction

    sub     sp, sp, #32
    mov     r0, #0
    str     r0, [sp, #0]            @ exinf
    mov     r0, #0x41
    str     r0, [sp, #4]            @ tskatr
    adr     r0, worker_entry
    str     r0, [sp, #8]            @ task entry
    mov     r0, #WORKER_PRI
    str     r0, [sp, #12]           @ itskpri
    movw    r0, #STKSZ
    str     r0, [sp, #16]           @ stksz
    LDW     r0, 0x4853565F          @ dsname "_VSH"
    str     r0, [sp, #20]
    movw    r0, #0x004C             @ "L"
    str     r0, [sp, #24]
    mov     r0, #0
    str     r0, [sp, #28]
    mov     r0, sp
    LDW     r12, FN_CRETSK
    blx     r12
    add     sp, sp, #32
    str     r0, [r5, #4]            @ task id
    cmp     r0, #0
    ble     cave_done
    mov     r1, #0
    LDW     r12, FN_STATSK
    blx     r12
    str     r0, [r5, #8]            @ start result
cave_done:
    mov     r0, r4
    pop     {r4, r5, pc}

/* ==========================================================================
 * worker_entry — the standing service
 * ========================================================================== */
worker_entry:
    push    {r4, r5, r6, r7, r8, r9, r10, lr}   @ 8 regs: keeps sp 8-byte aligned
    LDW     r4, STATE

round_loop:
    ldr     r0, [r4, #0x0C]
    add     r0, r0, #1
    str     r0, [r4, #0x0C]         @ round counter (liveness)

    /* Only arm while the gadget is configured and the link is awake.  This is
     * NOT the old record gate: it is a cheap guard against arming into a
     * suspended link, which busy-spins DEPCMD regardless of who owns the EP. */
    LDW     r0, USB_STATE
    ldr     r1, [r0]
    str     r1, [r4, #0x2C]
    cmp     r1, #2
    blt     gate_hold
    cmp     r1, #4
    beq     gate_hold

    bl      arm_out
    str     r0, [r4, #0x10]
    cmp     r0, #0
    bne     fault

    mov     r0, #LOG_OUT
    movw    r1, #TMO
    LDW     r12, FN_WAIT
    blx     r12
    str     r0, [r4, #0x14]
    cmp     r0, #0
    bne     fault                   @ timeout is normal when idle: just re-arm

    /* r6 = uncached view of the shared frame buffer */
    LDW     r0, BUF_PTR
    ldr     r6, [r0]
    mov     r0, #UNCACHED
    add     r6, r6, r0
    add     r10, r6, #20            @ payload

    /* the only command: "shl <line>" */
    ldr     r0, [r10]
    LDW     r1, 0x206C6873          @ "shl "
    cmp     r0, r1
    bne     reply_empty

/* ---- run one firmware shell line, capturing console output ---- */
    add     r7, r10, #4             @ the line (writable+uncached, strtok-safe)
    LDW     r0, SHELL_CTX
    ldr     r1, [r0]
    cmp     r1, #0
    bne     ctx_ready
    LDW     r0, SHELL_CTX
    LDW     r12, FN_SHINIT
    blx     r12
ctx_ready:
    LDW     r0, CAP_OFF
    mov     r1, #0
    str     r1, [r0]
    LDW     r0, SHELL_CTX
    adr     r1, capture_sink
    LDW     r12, FN_SHPUSH
    blx     r12
    LDW     r0, SHELL_CTX
    mov     r1, r7
    LDW     r12, FN_SHEXEC
    blx     r12
    LDW     r0, SHELL_CTX
    LDW     r12, FN_SHPOP
    blx     r12                     @ restore the UART sink

    LDW     r0, CAP_OFF
    ldr     r9, [r0]                @ captured byte count
    LDW     r8, CAP_BUF
    b       send_reply

reply_empty:
    mov     r9, #0
    LDW     r8, CAP_BUF

/* ==========================================================================
 * send_reply — r8 = source, r9 = length.  Emits ceil(len/44) frames (>=1);
 * every frame but the last sets flags bit0.  Reuses the received header so the
 * host's magic/version/sequence check still passes.
 * ========================================================================== */
send_reply:
    mov     r5, r9
    cmp     r5, #CHUNK
    movhi   r5, #CHUNK              @ r5 = bytes in this frame
    sub     r9, r9, r5              @ r9 = bytes still to send

    add     r7, r6, #20
    mov     r0, #0
sr_copy:
    cmp     r0, r5
    bhs     sr_pad
    ldrb    r1, [r8, r0]
    strb    r1, [r7, r0]
    add     r0, r0, #1
    b       sr_copy
sr_pad:
    cmp     r0, #CHUNK
    bhs     sr_hdr
    mov     r1, #0
    strb    r1, [r7, r0]
    add     r0, r0, #1
    b       sr_pad
sr_hdr:
    add     r8, r8, r5              @ advance source for the next frame
    cmp     r9, #0
    movne   r0, #1
    moveq   r0, #0
    strh    r0, [r6, #6]            @ flags bit0 = more frames follow
    strh    r5, [r6, #12]           @ payload_length
    mov     r0, #0
    strh    r0, [r6, #14]           @ status
    str     r0, [r6, #16]           @ checksum field zeroed for the CRC

    mvn     r3, #0
    mov     r0, #0
crc_byte:
    ldrb    r1, [r6, r0]
    eor     r3, r3, r1
    mov     r2, #8
crc_bit:
    tst     r3, #1
    lsr     r3, r3, #1
    beq     crc_next
    LDW     r1, 0xEDB88320
    eor     r3, r3, r1
crc_next:
    subs    r2, r2, #1
    bne     crc_bit
    add     r0, r0, #1
    cmp     r0, #64
    blo     crc_byte
    mvn     r3, r3
    str     r3, [r6, #16]

    bl      arm_in
    str     r0, [r4, #0x18]
    cmp     r0, #0
    bne     fault
    mov     r0, #LOG_IN
    movw    r1, #TMO
    LDW     r12, FN_WAIT
    blx     r12
    str     r0, [r4, #0x1C]
    cmp     r0, #0
    bne     fault

    cmp     r9, #0
    bgt     send_reply              @ more chunks

    ldr     r0, [r4, #0x20]
    add     r0, r0, #1
    str     r0, [r4, #0x20]         @ commands served
    b       round_loop

fault:
    ldr     r0, [r4, #0x24]
    add     r0, r0, #1
    str     r0, [r4, #0x24]
    mov     r0, #20
    LDW     r12, FN_DLY
    blx     r12
    b       round_loop

gate_hold:
    ldr     r0, [r4, #0x28]
    add     r0, r0, #1
    str     r0, [r4, #0x28]
    mov     r0, #50
    LDW     r12, FN_DLY
    blx     r12
    b       round_loop

/* ---- arm EP 0x01 OUT for one command frame; returns StartTransfer status ---- */
arm_out:
    push    {r4, r5, r6, r7, lr}
    mov     r0, #LOG_OUT
    LDW     r12, FN_ENDX
    blx     r12                     @ drop any stale TRB from a timed-out round
    LDW     r0, BUF_PTR
    ldr     r6, [r0]
    mov     r0, #DMA_BIAS
    add     r5, r6, r0              @ bus address for the controller
    LDW     r0, EP_OUT_TRB
    ldr     r7, [r0]
    str     r5, [r7]
    mov     r0, #0
    str     r0, [r7, #4]
    mov     r0, #1024
    str     r0, [r7, #8]
    movw    r0, #TRB_ARMED
    str     r0, [r7, #12]
    dsb
    mov     r0, #PHYS_OUT
    LDW     r12, FN_STARTX
    blx     r12
    pop     {r4, r5, r6, r7, pc}

/* ---- arm EP 0x82 IN with the 64-byte reply frame ---- */
arm_in:
    push    {r4, r5, r6, r7, lr}
    LDW     r0, BUF_PTR
    ldr     r6, [r0]
    mov     r0, #DMA_BIAS
    add     r5, r6, r0
    LDW     r0, EP_IN_TRB
    ldr     r7, [r0]
    str     r5, [r7]
    mov     r0, #0
    str     r0, [r7, #4]
    mov     r0, #64
    str     r0, [r7, #8]
    movw    r0, #TRB_ARMED
    str     r0, [r7, #12]
    dsb                             @ frame + TRB visible before the DMA starts
    mov     r0, #PHYS_IN
    LDW     r12, FN_STARTX
    blx     r12
    pop     {r4, r5, r6, r7, pc}

/* ==========================================================================
 * capture_sink — the firmware calls the output sink as printf(fmt, a1, a2, a3)
 * with further arguments on the stack, so &a1 must be contiguous with them.
 * ========================================================================== */
capture_sink:
    push    {r1, r2, r3}            @ va_list head, contiguous with stack varargs
    push    {r4, r5, lr}
    mov     r2, r0                  @ fmt
    add     r3, sp, #12             @ &a1
    LDW     r4, CAP_OFF
    ldr     r5, [r4]
    LDW     r0, CAP_BUF
    add     r0, r0, r5
    movw    r1, #CAP_SZ
    subs    r1, r1, r5
    ble     cs_done
    sub     r1, r1, #1              @ room for the NUL
    LDW     r12, FN_VSNPRINT
    blx     r12
    cmp     r0, #0
    ble     cs_done
    ldr     r5, [r4]
    add     r5, r5, r0
    str     r5, [r4]
cs_done:
    pop     {r4, r5, lr}
    add     sp, sp, #12
    bx      lr
