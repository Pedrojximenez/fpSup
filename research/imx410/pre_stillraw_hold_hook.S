    .syntax unified
    .arm
    .global pre_stillraw_hold_hook
pre_stillraw_hold_hook:
    push    {r4-r6, lr}
    mov     r4, r1
    movw    r12, #0x8a38
    movt    r12, #0xc031
    blx     r12

    ldr     r5, [r4, #0x30]
    movw    r6, #0xe500
    movt    r6, #0xc072
    str     r5, [r6, #0x00]
    mov     r0, #1
    str     r0, [r6, #0x04]
    ldr     r0, [r4, #0x14]
    str     r0, [r6, #0x0c]
    ldr     r0, [r4, #0x18]
    str     r0, [r6, #0x10]
    ldr     r0, [r4, #0x24]
    str     r0, [r6, #0x14]

1:
    ldr     r0, [r6, #0x08]
    cmp     r0, #0
    bne     2f
    mov     r0, #100
    movw    r12, #0x05d8
    movt    r12, #0xc037
    blx     r12
    b       1b
2:
    pop     {r4-r6, pc}
