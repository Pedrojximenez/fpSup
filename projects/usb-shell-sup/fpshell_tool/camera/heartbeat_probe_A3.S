.syntax unified
.arm
.text
/* A3 probe — isolate the sta_tsk FREEZE via a LOW-priority worker.
 *
 * Rationale (see notes/TASK_ABI_VERIFIED.md live-probe section):
 *   A1 (create-only)      -> id 14, mem-save survives         => create OK
 *   A / A2 (create+start) -> FREEZE, no readback              => start is the boundary
 * The freeze blocks the shell's mem-save, so we cannot read whether the worker
 * even reached its entry. Three candidate causes:
 *   (a) itskpri 0x3C higher-priority than the shell -> worker starves shell.
 *   (b) worker enters but first dly_tsk does not block -> busy-loop starvation.
 *   (c) sta_tsk startup frame / OS stack un-modeled  -> fault on entry.
 *
 * A3 sets the worker to a LOW priority (below the shell + gyro thread, from the
 * recovered priority map). Then:
 *   - if (b): worker busy-loops but the higher-priority shell PREEMPTS it and runs
 *     the mem-save -> we read WORK + a LARGE heartbeat  => worker DID run (rules out c).
 *   - if (a) was the sole cause: no more starvation -> shell survives, WORK readable.
 *   - if (c): still freezes / no WORK marker -> fault on entry, independent of priority.
 * So A3 distinguishes (c) from (a)/(b).
 *
 * WORKER_PRI is a PLACEHOLDER: fill from notes/TASK_PRIORITY_MAP.md (recommended
 * value strictly below shell AND gyro-thread priority, within the valid range).
 * Worker writes WORK as its very FIRST instruction (before any stack use), so a
 * later stack fault still leaves the entry-reached evidence in RAM.
 */

.equ STATE,     0xC072EC00
.equ HOOK,      0xC00D0794
.equ HOOK_ORIG, 0xFA046FD7
.equ ACCESSOR,  0xC01EC6F9
.equ FN_CRETSK, 0xC01F885C
.equ FN_STATSK, 0xC01F8D90
.equ FN_SLEEP,  0xC01F89C4     /* DIRECT dly_tsk stub (r0 = ms) */

.equ WORKER_PRI, 0x00000000    /* <<< FILL FROM PRIORITY MAP (must be nonzero, below shell) */

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
    str     r1, [r0]                  @ STATE[0]='B'
    movw    r0, #:lower16:HOOK
    movt    r0, #:upper16:HOOK
    movw    r1, #:lower16:HOOK_ORIG
    movt    r1, #:upper16:HOOK_ORIG
    str     r1, [r0]                  @ self-unhook
    sub     sp, sp, #32
    mov     r0, #0
    str     r0, [sp, #0]              @ exinf
    mov     r0, #1
    str     r0, [sp, #4]              @ tskatr=1
    adr     r0, worker_entry
    str     r0, [sp, #8]              @ entry
    movw    r0, #:lower16:WORKER_PRI
    movt    r0, #:upper16:WORKER_PRI
    str     r0, [sp, #12]             @ itskpri = LOW (from map)
    movw    r0, #0x2000
    str     r0, [sp, #16]             @ stksz
    mov     r0, #0
    str     r0, [sp, #20]
    str     r0, [sp, #24]
    str     r0, [sp, #28]
    mov     r0, sp
    movw    r12, #:lower16:FN_CRETSK
    movt    r12, #:upper16:FN_CRETSK
    blx     r12
    add     sp, sp, #32
    movw    r5, #:lower16:STATE
    movt    r5, #:upper16:STATE
    str     r0, [r5, #4]              @ STATE[4]=cre id
    cmp     r0, #1
    blt     cave_done
    movw    r12, #:lower16:FN_STATSK
    movt    r12, #:upper16:FN_STATSK
    blx     r12
    str     r0, [r5, #8]              @ STATE[8]=sta ret
cave_done:
    mov     r0, r4
    pop     {r4, r5, r6, pc}

/* ---- low-priority heartbeat worker ---- */
worker_entry:
    /* WORK marker FIRST — no stack needed (scratch regs only) */
    movw    r1, #:lower16:STATE
    movt    r1, #:upper16:STATE
    movw    r0, #0x524b
    movt    r0, #0x574f              @ 'WORK'
    str     r0, [r1, #12]            @ STATE[12]='WORK' (entry reached)
    push    {r4, lr}
    mov     r4, r1
worker_loop:
    ldr     r0, [r4, #16]
    add     r0, r0, #1
    str     r0, [r4, #16]            @ heartbeat++
    mov     r0, #10
    movw    r12, #:lower16:FN_SLEEP
    movt    r12, #:upper16:FN_SLEEP
    blx     r12                       @ direct dly_tsk(10ms)
    b       worker_loop
