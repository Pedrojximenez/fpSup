.syntax unified
.arm
.text
/* Task-creation probe, USB shell edition.
 *
 * Same recipe as camera/heartbeat_probe_A5.S, which is the one that actually ran
 * live (id 119, heartbeat, no freeze) -- minus the gyro-thread hook and the
 * self-unhook, because over the shell we just call this directly.
 *
 * The point of running it here first: the WRONG pair (Cyc 0xC01F885C/0xC01F8D90)
 * freezes the camera outright with no readback, and that is what stage6 has been
 * carrying since 2026-08-18. On the card a freeze costs a battery pull and tells
 * you nothing; here the create's return value comes straight back.
 *
 * STATE readback:
 *   [0]  = 0x42   routine ran
 *   [4]  = create id (>0 good, <0 is an error code: E_PAR -17, E_RSATR -11)
 *   [8]  = start return (0 = OK)
 *   [12] = 'WORK' worker entry was reached
 *   [16] = heartbeat, increments every 10 ms while the task is scheduled
 */

.equ STATE,      0xC072EC00
.equ FN_CRETSK,  0xC0016A58
.equ FN_STATSK,  0xC0016BC0
.equ FN_SLEEP,   0xC01F89C4
.equ WORKER_PRI, 0x1C

.global cave_entry
cave_entry:
    push    {r4, r5, lr}
    movw    r5, #:lower16:STATE
    movt    r5, #:upper16:STATE
    ldr     r0, [r5, #4]
    cmp     r0, #0
    bne     done                      @ already created; never create twice
    mov     r0, #0x42
    str     r0, [r5]

    sub     sp, sp, #32
    mov     r0, #0
    str     r0, [sp, #0]              @ exinf
    mov     r0, #0x41
    str     r0, [sp, #4]              @ tskatr = TA_HLNG | TA_DSNAME
    adr     r0, worker_entry
    str     r0, [sp, #8]              @ entry, direct
    mov     r0, #WORKER_PRI
    str     r0, [sp, #12]             @ itskpri = 28
    movw    r0, #0x2000
    str     r0, [sp, #16]             @ stksz -- the field stage6 filled with ASCII
    movw    r0, #0x5354               @ "TS"
    movt    r0, #0x4b53               @ "SK"  -> "TSSK"
    str     r0, [sp, #20]
    movw    r0, #0x0031               @ "1\0"
    str     r0, [sp, #24]
    mov     r0, #0
    str     r0, [sp, #28]
    mov     r0, sp
    movw    r12, #:lower16:FN_CRETSK
    movt    r12, #:upper16:FN_CRETSK
    blx     r12
    add     sp, sp, #32
    str     r0, [r5, #4]
    cmp     r0, #0
    ble     done
    mov     r1, #0
    movw    r12, #:lower16:FN_STATSK
    movt    r12, #:upper16:FN_STATSK
    blx     r12
    str     r0, [r5, #8]
done:
    mov     r0, #0
    pop     {r4, r5, pc}

worker_entry:
    movw    r1, #:lower16:STATE
    movt    r1, #:upper16:STATE
    movw    r0, #0x524b
    movt    r0, #0x574f              @ 'WORK'
    str     r0, [r1, #12]
    push    {r4, lr}
    mov     r4, r1
worker_loop:
    ldr     r0, [r4, #16]
    add     r0, r0, #1
    str     r0, [r4, #16]
    mov     r0, #10
    movw    r12, #:lower16:FN_SLEEP
    movt    r12, #:upper16:FN_SLEEP
    blx     r12
    b       worker_loop
