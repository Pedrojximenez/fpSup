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
.global task_probe_start

.equ STATE, 0xC072E900

task_probe_start:
    push    {r4, lr}
    /* We are invoked AS the hijacked `mem` command handler (slot 0xC0BAC478).
       Restore the real mem handler first so the following `mem save` works. */
    ldr     r0, =0xC0BAC478
    ldr     r1, =0xC03F9C38
    str     r1, [r0]
    ldr     r4, =STATE
    ldr     r0, =0x53545254          /* STRT */
    str     r0, [r4, #0]
    sub     sp, sp, #32
    mov     r0, #0
    str     r0, [sp, #0]
    mov     r0, #1
    str     r0, [sp, #4]
    adr     r0, task_probe_worker
    str     r0, [sp, #8]
    mov     r0, #0x3c
    str     r0, [sp, #12]
    ldr     r0, =0x48535046          /* FPSH */
    str     r0, [sp, #16]
    ldr     r0, =0x424f5250          /* PROB */
    str     r0, [sp, #20]
    mov     r0, #0
    str     r0, [sp, #24]
    mov     r0, sp
    ldr     ip, =0xC01F885C
    blx     ip
    str     r0, [r4, #4]
    cmp     r0, #1
    blt     task_probe_failed
    ldr     ip, =0xC01F8D90
    blx     ip
    str     r0, [r4, #8]
    ldr     r0, =0x53544152          /* STAR */
    str     r0, [r4, #12]
    b       task_probe_done
task_probe_failed:
    ldr     r1, =0x4641494c          /* FAIL */
    str     r1, [r4, #12]
task_probe_done:
    add     sp, sp, #32
    mov     r0, #1
    pop     {r4, pc}

task_probe_worker:
    push    {r4-r5, lr}
    ldr     r4, =STATE
    ldr     r0, =0x574f524b          /* WORK */
    str     r0, [r4, #16]
task_probe_loop:
    ldr     r0, [r4, #20]
    add     r0, r0, #1
    str     r0, [r4, #20]
    mov     r0, #10
    ldr     r5, =0xC03705D8
    blx     r5
    b       task_probe_loop

