.syntax unified
.arm
.text
.equ STATE, 0xC072E500
.equ OBJECT, (STATE+0x80)
.equ CYC_DRAW_FN, 0xC05278F8
.equ REGISTER_FN, 0xC0527D88
.equ UNREGISTER_FN, 0xC0527DB0

/* Installed over the first instruction of FUN_c05276f0. */
.global cyclic_hook
cyclic_hook:
    push {r4-r7, lr}
    movw r4, #:lower16:STATE
    movt r4, #:upper16:STATE
    ldr r0, [r4, #4]
    cmp r0, #0
    bne 1f
    mov r0, #1
    str r0, [r4, #4]
    movw r12, #:lower16:CYC_DRAW_FN
    movt r12, #:upper16:CYC_DRAW_FN
    blx r12
    mov r1, #1
    movw r2, #:lower16:OBJECT
    movt r2, #:upper16:OBJECT
    movw r12, #:lower16:REGISTER_FN
    movt r12, #:upper16:REGISTER_FN
    blx r12
1:
    ldr r0, [r4, #8]
    cmp r0, #0
    beq 3f
    ldr r0, [r4, #12]
    cmp r0, #0
    bne 3f
    mov r0, #1
    str r0, [r4, #12]
    movw r12, #:lower16:CYC_DRAW_FN
    movt r12, #:upper16:CYC_DRAW_FN
    blx r12
    mov r1, #1
    movw r2, #:lower16:OBJECT
    movt r2, #:upper16:OBJECT
    movw r12, #:lower16:UNREGISTER_FN
    movt r12, #:upper16:UNREGISTER_FN
    blx r12
3:
    movw r12, #0x76F4
    movt r12, #0xC052
    bx r12

.balign 256
/* Installed over the first instruction of FUN_c005dba0. */
.global setter_hook
setter_hook:
    push {r4-r6, lr}
    movw r12, #:lower16:STATE
    movt r12, #:upper16:STATE
    and r3, r1, #1
    str r3, [r12, #16]
    ldr r3, [r12, #20]
    add r3, r3, #1
    str r3, [r12, #20]
    movw r12, #0xDBA4
    movt r12, #0xC005
    bx r12

.balign 128
/* XC_DrawInterface::v1(object, surface, context). */
.global drawer_draw
drawer_draw:
    push {r4-r8, lr}
    sub sp, sp, #32
    movw r4, #:lower16:STATE
    movt r4, #:upper16:STATE
    ldr r0, [r4, #16]
    cmp r0, #0
    beq 5f
    ldr r0, [r4, #24]
    add r0, r0, #1
    str r0, [r4, #24]
    str r1, [r4, #28]
    mov r5, r1
    add r0, sp, #8
    mov r1, r5
    movw r12, #0x9BD8
    movt r12, #0xC052
    blx r12
    mov r6, #20
4:
    mov r0, #20
    str r0, [sp]
    str r6, [sp, #4]
    add r0, sp, #8
    mov r1, sp
    movw r12, #0x9C80
    movt r12, #0xC052
    blx r12
    mov r1, #1
    mov r2, #80
    movw r12, #0x5058
    movt r12, #0xC001
    blx r12
    add r6, r6, #1
    cmp r6, #60
    blo 4b
    mov r0, #1
    b 6f
5:
    mov r0, #0
6:
    add sp, sp, #32
    pop {r4-r8, pc}

.balign 128
.global method_destruct
method_destruct: bx lr
.balign 16
.global method_setup
method_setup: bx lr
.balign 16
.global method_teardown
method_teardown: bx lr
.balign 16
.global method_noop
method_noop: bx lr
.balign 16
.global method_true
method_true: mov r0, #1
             bx lr

