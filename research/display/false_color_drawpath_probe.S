.syntax unified
.arm
.text
.equ STATE, 0xC072E500

.global setter_probe
setter_probe:
    push {r4-r6, lr}
    movw r12, #:lower16:STATE
    movt r12, #:upper16:STATE
    ldr r3, [r12, #4]
    add r3, r3, #1
    str r3, [r12, #4]
    str r0, [r12, #8]
    str r1, [r12, #12]
    str r2, [r12, #16]
    movw r12, #0xDBA4
    movt r12, #0xC005
    bx r12

.balign 128
.global dispatch_probe
dispatch_probe:
    push {r4-r9, r11, lr}
    movw r12, #:lower16:STATE
    movt r12, #:upper16:STATE
    str r3, [r12, #40]
    ldr r3, [r12, #20]
    add r3, r3, #1
    str r3, [r12, #20]
    str r0, [r12, #24]
    str r1, [r12, #28]
    str r2, [r12, #32]
    ldr r3, [r12, #40]
    movw r12, #0x8704
    movt r12, #0xC052
    bx r12

.balign 128
.global cyclic_probe
cyclic_probe:
    push {r4-r7, lr}
    movw r12, #:lower16:STATE
    movt r12, #:upper16:STATE
    ldr r3, [r12, #36]
    add r3, r3, #1
    str r3, [r12, #36]
    movw r12, #0x76F4
    movt r12, #0xC052
    bx r12

