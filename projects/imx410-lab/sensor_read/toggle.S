.syntax unified
.arm
.text
/* toggle -- alternate one IMX410 register between two values for a while, to see whether a register takes effect
 * row by row during readout (bands in the frame) or once per frame. Each write is the stock writer's transaction
 * (spi_read.S, chip 0x81), IRQs masked only during the write.
 *   r0 = header (0x81 | reg_hi << 8 | reg_lo << 16)    r1 = value A | value B << 8
 *   r2 = number of A/B pairs                            r3 = busy-wait loop count after each write
 * Returns r0 = pairs done.
 */
    .global toggle
toggle:
    push    {r4-r11, lr}
    sub     sp, sp, #4
    mov     r8, r0
    mov     r9, r1
    mov     r10, r2
    mov     r11, r3
    mov     r7, #0
1:  cmp     r7, r10
    bhs     9f
    and     r1, r9, #0xFF
    bl      write1
    mov     r0, r11
2:  subs    r0, r0, #1
    bne     2b
    lsr     r1, r9, #8
    and     r1, r1, #0xFF
    bl      write1
    mov     r0, r11
3:  subs    r0, r0, #1
    bne     3b
    add     r7, r7, #1
    b       1b
9:  mov     r0, r7
    add     sp, sp, #4
    pop     {r4-r11, pc}

/* write1: header in r8, value in r1 */
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
