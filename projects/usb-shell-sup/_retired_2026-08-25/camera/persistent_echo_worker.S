/* ============================================================================
 * OBSOLETE — DO NOT DEPLOY. WRONG TK-OS TASK DESCRIPTOR.
 * Verified (notes/TASK_ABI_VERIFIED.md): descriptor +16 = STACK SIZE (stksz),
 * name is at +20 and only used if tskatr&0x40. These files write the task NAME
 * ("FPSH"/"S6GFWR") at +16 -> firmware reads it as a ~1.2 GiB stack size ->
 * cre_tsk returns a valid id but sta_tsk corrupts memory / crashes.
 * persistent_echo_worker.S additionally polls the TRB HWO bit instead of the
 * native event-flag wait (FUN_c01e4e80). Superseded by the corrected probe.
 * ============================================================================ */
.syntax unified
.arm
.text
/* Persistent USB echo worker for SIGMA fp (v1).
 *
 * Built entirely from v29's PROVEN primitives (ep05_ep84_echo.S):
 *   arm EP05 OUT  : TRB{buf,0,1024,0x813} in [0xC31E3278], StartTransfer(10)
 *   completion    : poll TRB.control[+12] HWO bit0 until clear
 *   arm EP84 IN   : TRB{buf,0,64,0x813}   in [0xC31E3274], StartTransfer(9)
 *
 * Unlike v29 (a manually single-stepped 0..9 state machine driven by 29 `log`s),
 * this is a SELF-RUNNING task: create it once, it loops forever with no external
 * stepping, no EndTransfer/teardown, no SD shuffle.
 *
 * Layout:  bootstrap @ cave+0x00, worker @ its own label, state @ 0xC072E900.
 *   STATE[0] = bootstrap guard / marker  ('B' once run)
 *   STATE[4] = cre_tsk handle
 *   STATE[8] = sta_tsk return
 *   STATE[12]= loop counter (heartbeat: bumps every completed round)
 */

.equ STATE,       0xC072EC00
.equ BUF_PTR,     0xC3757A7C   /* [.] = DMA buffer base (AutoRun: memmgr bufmem get) */
.equ CTX5_TBL,    0xC31E3278   /* [.] = EP05 (OUT) TRB table */
.equ CTX4_TBL,    0xC31E3274   /* [.] = EP84 (IN)  TRB table */
.equ CTX4_MODE,   0xC31E38C8
.equ TRB_CTRL,    0x813        /* HWO|active, armed */

.equ FN_START,    0xC01E6B81   /* StartTransfer (Thumb) : r0 = (ep<<1)|dir */
.equ FN_END,      0xC01E6D49   /* EndTransfer   (Thumb) : r0 = context */
.equ FN_SLEEP,    0xC03705D8   /* cooperative sleep (ARM): r0 = interval */
.equ FN_CRETSK,   0xC01F885C   /* create task (ARM) : r0 = descriptor -> handle */
.equ FN_STATSK,   0xC01F8D90   /* start task (ARM)  : r0 = handle */
.equ FN_OP5,      0xC04E9148   /* original op-5 action we displaced (chain it) */

/* ============================ bootstrap ============================ */
/* Installed via branch-patch at 0xC04DC618 (replaces `bl 0xC04E9148`).
 * Fires when the USB state dispatcher reaches state 5 (on USB connect).
 * Chains the original op-5 action, then creates the worker task ONCE. */
.global boot_entry
boot_entry:
    push    {r4, lr}
    /* chain original displaced call so USB state handling is unchanged */
    movw    r12, #:lower16:FN_OP5
    movt    r12, #:upper16:FN_OP5
    blx     r12
    /* guard: run once */
    movw    r4, #:lower16:STATE
    movt    r4, #:upper16:STATE
    ldr     r0, [r4]
    cmp     r0, #0x42                 /* 'B' */
    beq     boot_ret
    mov     r0, #0x42
    str     r0, [r4]
    /* build 32-byte task descriptor on stack */
    sub     sp, sp, #32
    mov     r0, #0
    str     r0, [sp, #0]
    mov     r0, #1
    str     r0, [sp, #4]
    adr     r0, worker_entry
    str     r0, [sp, #8]              /* entry */
    mov     r0, #0x3c
    str     r0, [sp, #12]             /* priority */
    movw    r0, #0x5046
    movt    r0, #0x4853
    str     r0, [sp, #16]             /* name "FPSH" */
    movw    r0, #0x4c45
    movt    r0, #0x4c48
    str     r0, [sp, #20]             /* "HLEL" */
    mov     r0, #0
    str     r0, [sp, #24]
    mov     r0, sp
    movw    r12, #:lower16:FN_CRETSK
    movt    r12, #:upper16:FN_CRETSK
    blx     r12                       /* r0 = handle */
    add     sp, sp, #32
    str     r0, [r4, #4]
    cmp     r0, #1
    blt     boot_ret
    movw    r12, #:lower16:FN_STATSK
    movt    r12, #:upper16:FN_STATSK
    blx     r12
    movw    r4, #:lower16:STATE
    movt    r4, #:upper16:STATE
    str     r0, [r4, #8]
boot_ret:
    pop     {r4, pc}

/* ============================ worker task ============================ */
/* Self-running loop: arm OUT, wait, arm IN (echo), wait, repeat. Forever.
 * r4 = current TRB ptr, r5 = buffer base, r6 = &STATE (all callee-saved,
 * preserved across the firmware calls). */
worker_entry:
    push    {r4, r5, r6, lr}
    movw    r6, #:lower16:STATE
    movt    r6, #:upper16:STATE
    /* one-time: force ctx4 IN mode = 2 */
    movw    r0, #:lower16:CTX4_MODE
    movt    r0, #:upper16:CTX4_MODE
    mov     r1, #2
    str     r1, [r0]

worker_loop:
    /* ---- arm EP05 OUT receive ---- */
    mov     r0, #5
    bl      call_end                  /* EndTransfer(5) */
    movw    r0, #:lower16:BUF_PTR
    movt    r0, #:upper16:BUF_PTR
    ldr     r5, [r0]                  /* r5 = buffer base */
    add     r5, r5, #0xc0000000       /* v29: TRB ptr = buf + 0xC0000000 alias */
    movw    r0, #:lower16:CTX5_TBL
    movt    r0, #:upper16:CTX5_TBL
    ldr     r4, [r0]                  /* r4 = EP05 TRB */
    str     r5, [r4]                  /* TRB.bufptr */
    mov     r0, #0
    str     r0, [r4, #4]              /* TRB.hi = 0 */
    mov     r0, #1024
    str     r0, [r4, #8]              /* TRB.size = 1024 */
    movw    r0, #TRB_CTRL
    str     r0, [r4, #12]             /* TRB.control = 0x813 (armed) */
    mov     r0, #10
    bl      call_start                /* StartTransfer(10) EP05 OUT */
    /* ---- wait OUT complete: poll HWO bit0 ---- */
1:
    ldr     r0, [r4, #12]
    tst     r0, #1                    /* HWO still set? */
    beq     2f
    mov     r0, #2
    bl      call_sleep                /* yield, don't busy-spin */
    b       1b
2:
    /* ---- arm EP84 IN send (echo first 64 bytes back) ---- */
    movw    r0, #:lower16:BUF_PTR
    movt    r0, #:upper16:BUF_PTR
    ldr     r5, [r0]
    add     r5, r5, #0xc0000000       /* v29: TRB ptr = buf + 0xC0000000 alias */
    movw    r0, #:lower16:CTX4_TBL
    movt    r0, #:upper16:CTX4_TBL
    ldr     r4, [r0]                  /* r4 = EP84 TRB */
    str     r5, [r4]
    mov     r0, #0
    str     r0, [r4, #4]
    mov     r0, #64
    str     r0, [r4, #8]
    movw    r0, #TRB_CTRL
    str     r0, [r4, #12]
    mov     r0, #9
    bl      call_start                /* StartTransfer(9) EP84 IN */
3:
    ldr     r0, [r4, #12]
    tst     r0, #1
    beq     4f
    mov     r0, #2
    bl      call_sleep
    b       3b
4:
    /* heartbeat: bump completed-round counter */
    ldr     r0, [r6, #12]
    add     r0, r0, #1
    str     r0, [r6, #12]
    b       worker_loop

/* ---- thin trampolines for the firmware entrypoints ---- */
call_start:
    movw    r12, #:lower16:FN_START
    movt    r12, #:upper16:FN_START
    bx      r12
call_end:
    movw    r12, #:lower16:FN_END
    movt    r12, #:upper16:FN_END
    bx      r12
call_sleep:
    movw    r12, #:lower16:FN_SLEEP
    movt    r12, #:upper16:FN_SLEEP
    bx      r12
