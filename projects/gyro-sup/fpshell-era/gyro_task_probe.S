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
.global cave_entry
/* Task-ABI probe invoked from the gyro-thread hook site 0xC00D0794 (a proven,
   always-running boot-time call site). This is a trampoline: it calls the
   original gyro accessor first (to preserve gyro behaviour), then ONCE creates
   a background task via the firmware task ABI and records markers, then returns.
   The created task self-loops (heartbeat), proving the ABI + self-sustaining
   worker. STATE @0xC072E900. */
.equ STATE, 0xC072E900

cave_entry:
    push    {r4, r5, r6, lr}         @ preserve callee-saved (r6 unused, keeps 8-byte align)
    /* r0 = gyro output buffer (sp) on entry; call the original accessor first */
    movw    r12, #0xC6F9
    movt    r12, #0xC01E             @ 0xC01EC6F9 (Thumb gyro accessor)
    blx     r12
    mov     r4, r0                   @ save accessor return (restored at exit)
    /* guard: if STATE[0] == 'STRT', the task is already created -> skip */
    movw    r0, #:lower16:STATE
    movt    r0, #:upper16:STATE
    ldr     r1, [r0]
    movw    r2, #0x5254
    movt    r2, #0x5354              @ 'STRT' = 0x53545254
    cmp     r1, r2
    beq     cave_done
    /* ---- run the starter exactly once ---- */
    str     r2, [r0]                 @ STATE[0] = STRT (marker + re-entry guard)
    sub     sp, sp, #32              @ 32-byte task descriptor on stack
    mov     r1, #0
    str     r1, [sp, #0]
    mov     r1, #1
    str     r1, [sp, #4]
    adr     r1, cave_worker
    str     r1, [sp, #8]             @ entry = worker (PC-relative, position independent)
    mov     r1, #0x3c
    str     r1, [sp, #12]            @ priority 0x3C
    movw    r1, #0x5046
    movt    r1, #0x4853
    str     r1, [sp, #16]           @ name "FPSH"
    movw    r1, #0x5250
    movt    r1, #0x424f
    str     r1, [sp, #20]           @ "PROB"
    mov     r1, #0
    str     r1, [sp, #24]
    mov     r0, sp
    movw    r12, #0x885C
    movt    r12, #0xC01F             @ 0xC01F885C task-create
    blx     r12                      @ -> r0 = handle
    add     sp, sp, #32
    mov     r5, r0                   @ save handle
    movw    r0, #:lower16:STATE
    movt    r0, #:upper16:STATE
    str     r5, [r0, #4]            @ STATE[4] = handle
    cmp     r5, #1
    blt     cave_failed
    mov     r0, r5                  @ r0 = handle
    movw    r12, #0x8D90
    movt    r12, #0xC01F            @ 0xC01F8D90 task-start
    blx     r12                     @ -> r0 = start return
    movw    r1, #:lower16:STATE
    movt    r1, #:upper16:STATE
    str     r0, [r1, #8]           @ STATE[8] = start return
    movw    r0, #0x4152
    movt    r0, #0x5354            @ 'STAR' = 0x53544152
    str     r0, [r1, #12]
    b       cave_done
cave_failed:
    movw    r0, #0x494c
    movt    r0, #0x4641            @ 'FAIL' = 0x4641494c
    movw    r1, #:lower16:STATE
    movt    r1, #:upper16:STATE
    str     r0, [r1, #12]
cave_done:
    mov     r0, r4                 @ restore original accessor return
    pop     {r4, r5, r6, pc}

cave_worker:
    push    {r4, r5, lr}
    movw    r4, #:lower16:STATE
    movt    r4, #:upper16:STATE
    movw    r0, #0x524b
    movt    r0, #0x574f            @ 'WORK' = 0x574f524b
    str     r0, [r4, #16]
cave_worker_loop:
    ldr     r0, [r4, #20]
    add     r0, r0, #1
    str     r0, [r4, #20]          @ STATE[20] heartbeat++
    mov     r0, #10
    movw    r12, #0x05D8
    movt    r12, #0xC037           @ 0xC03705D8 cooperative sleep(10)
    blx     r12
    b       cave_worker_loop
