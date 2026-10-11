.syntax unified
.arm
.text

/* fp 5.02 fixed H/L snapshot, shell TASK context only.
 * Load at C072F740; complete image including literals must end <= C072F800.
 * The existing approved lease owns C072F700..C072F9FF.  This helper does not
 * install itself, borrow echo, move a lens, or modify capture/settings.
 *
 * P+00 magic 31424641; +04 nonce; +08 operation, must equal 9.
 * Outputs: +18 echoed nonce, +1C state (1 running, 2 copy returned),
 * +20 return=0, +24 phase before, +28 mode before, +2C H, +30 L,
 * +34 phase after, +38 mode after.  All stores stay within P+00..3B.
 * Invalid magic/op performs no stores.  Consume magic before every copy so
 * repeating echo without a fresh request cannot repeat the observation.
 *
 * Caller-saved r0-r3/r12 only: SP, LR and r4-r11 are unchanged.  No stack
 * writes, firmware calls, USB, MMIO, waits, loops or arbitrary input pointers.
 * State 2 is published last after DMB; native mem get reads results via CPU,
 * not code-cave USB DMA.  DMB does not substitute for cache publication when
 * the host installs this code.
 *
 * This short same-handler copy is NOT atomic against interrupts, a seqlock,
 * a sensor-frame counter, optical settling proof, or exposure alignment.
 * Host must retain nonce/state, phase/mode, gain/context and settling guards.
 */
.equ P, 0xC072F700
.global entry
entry:
    ldr ip, =P
    ldr r0, [ip]
    ldr r1, =0x31424641
    cmp r0, r1
    bne exit
    ldr r0, [ip, #8]
    cmp r0, #9
    bne exit
    mov r0, #0
    str r0, [ip]                /* consume request before touching outputs */
    ldr r1, [ip, #4]
    str r1, [ip, #0x18]
    mov r1, #1
    str r1, [ip, #0x1c]
    str r0, [ip, #0x20]
    ldr r2, =0xC31F8CB4
    ldmia r2, {r0, r1}
    str r0, [ip, #0x24]
    str r1, [ip, #0x28]
    ldr r3, =0xC32985E8
    ldr r0, [r3]
    str r0, [ip, #0x2c]
    ldr r3, =0xC32986B4
    ldr r0, [r3]
    str r0, [ip, #0x30]
    ldmia r2, {r0, r1}
    str r0, [ip, #0x34]
    str r1, [ip, #0x38]
    dmb sy
    mov r0, #2
    str r0, [ip, #0x1c]         /* complete only after all six outputs */
    mov r0, #0
exit:
    bx lr
code_end:
.ltorg
