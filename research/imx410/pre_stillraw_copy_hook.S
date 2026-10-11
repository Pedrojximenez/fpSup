    .syntax unified
    .arm
    .global pre_stillraw_copy_hook
pre_stillraw_copy_hook:
    push    {r4-r7, lr}
    mov     r4, r1

    movw    r12, #0x8a38
    movt    r12, #0xc031
    blx     r12

    ldr     r5, [r4, #0x30]
    movw    r6, #0x7a7c
    movt    r6, #0xc375
    ldr     r7, [r6]
    ldr     r3, [r6, #4]
    movw    r2, #0
    movt    r2, #0x0300
    cmp     r7, #0
    beq     1f
    cmp     r3, r2
    blo     1f
    mov     r0, r7
    mov     r1, r5
    movw    r12, #0x510c
    movt    r12, #0xc001
    blx     r12
    ldr     r3, [r6, #4]
    b       2f
1:
    mov     r3, #0
2:
    movw    r1, #0xe500
    movt    r1, #0xc072
    str     r5, [r1, #0x00]
    str     r7, [r1, #0x04]
    str     r3, [r1, #0x08]
    ldr     r0, [r4, #0x14]
    str     r0, [r1, #0x0c]
    ldr     r0, [r4, #0x18]
    str     r0, [r1, #0x10]
    ldr     r0, [r4, #0x24]
    str     r0, [r1, #0x14]
    pop     {r4-r7, pc}
