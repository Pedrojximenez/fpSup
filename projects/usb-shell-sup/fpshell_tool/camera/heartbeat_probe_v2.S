.syntax unified
.arm
.text
/* CORRECTED minimal TK-OS task heartbeat probe (probe A).
 *
 * Purpose: VALIDATE the task-creation ABI in isolation (no USB), using the
 * descriptor layout verified in notes/TASK_ABI_VERIFIED.md:
 *     +0  exinf   = 0
 *     +4  tskatr  = 1        (TA_HLNG; NOT 0x40, so no dsname)
 *     +8  entry
 *     +12 itskpri = 0x3C
 *     +16 stksz   = 0x2000   <-- STACK SIZE (the field the old probes wrongly
 *                                filled with the ASCII name -> ~1.2 GiB stack)
 *     +20 dsname  = (unused, tskatr has no 0x40)
 *
 * Injection: the proven gyro-thread hook site 0xC00D0794 (boot-time, no USB).
 * This trampoline calls the original gyro accessor, then ONCE creates + starts
 * a tiny heartbeat task and SELF-UNHOOKS (restores the original instruction so
 * the gyro thread returns to normal after one frame).
 *
 * Readback (SD mem save 0xC072EC00,,0x40):
 *   STATE[0]  guard/marker  'B'(0x42) once the trampoline ran
 *   STATE[4]  cre_tsk return (task id >=1, else negative)
 *   STATE[8]  sta_tsk return (0 = OK)
 *   STATE[12] worker 'WORK' marker (proves the task actually started)
 *   STATE[16] heartbeat counter (>0 after the sleep = task is scheduling)
 */

.equ STATE,     0xC072EC00
.equ HOOK,      0xC00D0794     /* gyro-thread call site */
.equ HOOK_ORIG, 0xFA046FD7     /* original: blx 0xC01EC6F8 */
.equ ACCESSOR,  0xC01EC6F9     /* original gyro accessor (Thumb) */
.equ FN_CRETSK, 0xC01F885C     /* cre_tsk (id 0x80470100) : r0=&desc -> id */
.equ FN_STATSK, 0xC01F8D90     /* sta_tsk (id 0x80490100) : r0=id -> 0/neg  */
.equ FN_SLEEP,  0xC03705D8     /* dly_tsk wrapper : r0 = ms */

.global cave_entry
cave_entry:
    push    {r4, r5, r6, lr}          @ preserve callee-saved (r6 pad, keeps 8B align)
    /* call original gyro accessor (r0 already = sp output buffer) */
    movw    r12, #:lower16:ACCESSOR
    movt    r12, #:upper16:ACCESSOR
    blx     r12
    mov     r4, r0                    @ save accessor return (restored at exit)
    /* guard: run once */
    movw    r0, #:lower16:STATE
    movt    r0, #:upper16:STATE
    ldr     r1, [r0]
    cmp     r1, #0x42
    beq     cave_done
    mov     r1, #0x42
    str     r1, [r0]                  @ STATE[0] = 'B'
    /* self-unhook: restore original instruction at the hook site */
    movw    r0, #:lower16:HOOK
    movt    r0, #:upper16:HOOK
    movw    r1, #:lower16:HOOK_ORIG
    movt    r1, #:upper16:HOOK_ORIG
    str     r1, [r0]
    /* build CORRECT 32-byte descriptor on stack */
    sub     sp, sp, #32
    mov     r0, #0
    str     r0, [sp, #0]              @ exinf = 0
    mov     r0, #1
    str     r0, [sp, #4]              @ tskatr = 1 (TA_HLNG)
    adr     r0, worker_entry
    str     r0, [sp, #8]              @ entry
    mov     r0, #0x3c
    str     r0, [sp, #12]            @ itskpri = 0x3C
    movw    r0, #0x2000
    str     r0, [sp, #16]            @ stksz = 0x2000  (CORRECT field)
    mov     r0, #0
    str     r0, [sp, #20]            @ dsname (unused)
    mov     r0, #0
    str     r0, [sp, #24]
    mov     r0, #0
    str     r0, [sp, #28]
    mov     r0, sp
    movw    r12, #:lower16:FN_CRETSK
    movt    r12, #:upper16:FN_CRETSK
    blx     r12                       @ r0 = task id (>=1) or negative
    add     sp, sp, #32
    movw    r5, #:lower16:STATE
    movt    r5, #:upper16:STATE
    str     r0, [r5, #4]             @ STATE[4] = cre_tsk return
    cmp     r0, #1
    blt     cave_done                @ create failed -> stop (task id in STATE[4])
    movw    r12, #:lower16:FN_STATSK
    movt    r12, #:upper16:FN_STATSK
    blx     r12                       @ r0 (=id) -> sta_tsk -> return
    str     r0, [r5, #8]             @ STATE[8] = sta_tsk return
cave_done:
    mov     r0, r4                    @ restore accessor return
    pop     {r4, r5, r6, pc}

/* ---- the heartbeat task ---- */
worker_entry:
    push    {r4, lr}
    movw    r4, #:lower16:STATE
    movt    r4, #:upper16:STATE
    movw    r0, #0x524b
    movt    r0, #0x574f              @ 'WORK'
    str     r0, [r4, #12]
worker_loop:
    ldr     r0, [r4, #16]
    add     r0, r0, #1
    str     r0, [r4, #16]            @ heartbeat++
    mov     r0, #10
    movw    r12, #:lower16:FN_SLEEP
    movt    r12, #:upper16:FN_SLEEP
    blx     r12                       @ dly_tsk(10 ms) — real sleep, yields
    b       worker_loop
