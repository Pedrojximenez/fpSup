.syntax unified
.arm
.text
/* batch -- write a table of IMX410 registers in one call (each write = the stock writer's ch1 transaction,
 * chip 0x81, IRQs masked during the write only, as in toggle.S).
 *   r0 = table address: pairs of words {header = 0x81 | reg_hi << 8 | reg_lo << 16, value}
 *   r1 = number of pairs
 * Returns r0 = pairs written.
 */
    .global batch
batch:
    push    {r4-r10, lr}
    mov     r9, r0
    mov     r10, r1
    mov     r7, #0
1:  cmp     r7, r10
    bhs     9f
    ldr     r8, [r9], #4
    ldr     r1, [r9], #4
    bl      write1
    add     r7, r7, #1
    b       1b
9:  mov     r0, r7
    pop     {r4-r10, pc}

write1:
    push    {r4-r6, lr}
    mrs     r6, cpsr
    cpsid   i
    ldr     r4, =0x21C00100
    mov     r3, #0x11
    str     r3, [r4, #0x00]
    mov     r3, #0x13
    str     r3, [r4, #0x00]
    mov     r3, #0
    str     r3, [r4, #0x10]
    str     r3, [r4, #0x2C]
    mov     r3, #0x100
    str     r3, [r4, #0x04]
    mov     r3, #0x30
    str     r3, [r4, #0x08]
    ldr     r3, =0x818
    str     r3, [r4, #0x0C]
    mov     r3, #0
    str     r3, [r4, #0x20]
    mov     r3, #1
    str     r3, [r4, #0x10]
    str     r8, [r4, #0x14]
    str     r1, [r4, #0x18]
    ldr     r5, =10000
4:  ldr     r3, [r4, #0x20]
    tst     r3, #1
    bne     5f
    subs    r5, r5, #1
    bne     4b
5:  msr     cpsr_c, r6
    pop     {r4-r6, pc}
    .ltorg
