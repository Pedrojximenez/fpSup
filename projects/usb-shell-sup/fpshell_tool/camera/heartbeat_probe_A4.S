.syntax unified
.arm
.text
/* A4 probe — use the PROVEN main-path task recipe (the one the SHELL task uses).
 *
 * ROOT CAUSE of the A/A2 freeze (notes/TASK_PRIORITY_MAP.md): we used the WRONG
 * create/start syscalls. There are two task subsystems:
 *   service 0x8047  stub 0xC01F885C -> FUN_c000c6b8  : ONLY the Cyc-thread wrapper
 *                     (passes stksz=0 + entry=fixed trampoline 0xC0370BF0)
 *   service 0x8001  stub 0xC0016A58 -> FUN_c000a9c0  : the MAIN path — real tasks
 *                     with DIRECT entries + real stksz (shell, CamMain, LcdTh, ...)
 * A/A2 used the Cyc create (0xC01F885C) + Cyc start (0xC01F8D90) with a DIRECT entry
 * -> mismatch -> sta corrupts/crashes.
 *
 * A4 copies the shell task's exact recipe (FUN_c03da178 @0xC03DA258):
 *   id  = 0xC0016A58(&desc)   ; MAIN create  (desc: tskatr=0x41, direct entry, real stksz, dsname)
 *   if id>0: 0xC0016BC0(id,0) ; MAIN start   (returns 0 = OK)
 * Descriptor layout is identical (+0 exinf,+4 tskatr,+8 entry,+12 itskpri,+16 stksz,+20 dsname[8]).
 *
 * Injection: gyro-thread hook 0xC00D0794 (boot, no USB), self-unhooks after one frame.
 * Readback (mem save 0xC072EC00,,0x40):
 *   [0]=0x42 trampoline ran   [4]=create id (>0)   [8]=start return (0=OK)
 *   [12]='WORK' worker entry reached   [16]=heartbeat (>0 = scheduling)
 */

.equ STATE,     0xC072EC00
.equ HOOK,      0xC00D0794
.equ HOOK_ORIG, 0xFA046FD7
.equ ACCESSOR,  0xC01EC6F9
.equ FN_CRETSK, 0xC0016A58     /* MAIN create (service 0x8001) : r0=&desc -> id */
.equ FN_STATSK, 0xC0016BC0     /* MAIN start  : r0=id, r1=0 -> 0/err (shell uses this) */
.equ FN_SLEEP,  0xC01F89C4     /* direct dly_tsk : r0 = ms */
.equ WORKER_PRI, 0x64          /* 100 — strictly below shell(25)+gyro(20); priority is NOT the freeze cause */

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
    /* build 32-byte descriptor matching shell's (tskatr=0x41 + dsname) */
    sub     sp, sp, #32
    mov     r0, #0
    str     r0, [sp, #0]              @ exinf = 0
    mov     r0, #0x41
    str     r0, [sp, #4]              @ tskatr = 0x41 (TA_HLNG|TA_DSNAME) — same as shell
    adr     r0, worker_entry
    str     r0, [sp, #8]              @ entry (direct)
    mov     r0, #WORKER_PRI
    str     r0, [sp, #12]             @ itskpri
    movw    r0, #0x2000
    str     r0, [sp, #16]             @ stksz = 0x2000
    movw    r0, #0x5250              @ 'PR'
    movt    r0, #0x424f              @ 'OB'  -> "PROB"
    str     r0, [sp, #20]             @ dsname[0..3]
    movw    r0, #0x0045              @ 'E\0'
    str     r0, [sp, #24]            @ dsname[4..7] = "E\0\0\0"
    mov     r0, #0
    str     r0, [sp, #28]
    mov     r0, sp
    movw    r12, #:lower16:FN_CRETSK
    movt    r12, #:upper16:FN_CRETSK
    blx     r12                       @ r0 = task id
    add     sp, sp, #32
    movw    r5, #:lower16:STATE
    movt    r5, #:upper16:STATE
    str     r0, [r5, #4]              @ STATE[4] = create id
    cmp     r0, #0
    ble     cave_done                @ id<=0 -> create failed (shell uses bgt)
    mov     r1, #0                    @ start arg2 = 0
    movw    r12, #:lower16:FN_STATSK
    movt    r12, #:upper16:FN_STATSK
    blx     r12                       @ 0xC0016BC0(id, 0) -> 0=OK
    str     r0, [r5, #8]              @ STATE[8] = start return
cave_done:
    mov     r0, r4
    pop     {r4, r5, r6, pc}

/* ---- heartbeat worker (direct entry, priority 0x64) ---- */
worker_entry:
    movw    r1, #:lower16:STATE
    movt    r1, #:upper16:STATE
    movw    r0, #0x524b
    movt    r0, #0x574f              @ 'WORK'
    str     r0, [r1, #12]            @ STATE[12]='WORK' (entry reached) — first thing
    push    {r4, lr}
    mov     r4, r1
worker_loop:
    ldr     r0, [r4, #16]
    add     r0, r0, #1
    str     r0, [r4, #16]            @ heartbeat++
    mov     r0, #10
    movw    r12, #:lower16:FN_SLEEP
    movt    r12, #:upper16:FN_SLEEP
    blx     r12                       @ dly_tsk(10ms)
    b       worker_loop
