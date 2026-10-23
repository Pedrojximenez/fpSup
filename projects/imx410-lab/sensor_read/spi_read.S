.syntax unified
.arm
.text
/* spi_read -- one transaction on serial ch1 (the IMX410) with a caller-chosen chip-ID, then read RX.
 * Mirrors the stock writer FUN_c0128898 (notes/SENSOR_BUS_READ.md), except the header's low byte.
 *   r0 = header word: chip_id | reg_hi << 8 | reg_lo << 16      r1 = TX data byte (0 for a read)
 *   r2 = result block (3 words): RX (+0x1C), status (+0x20), poll count left
 * IRQs are masked for the whole transaction so the AE writer cannot interleave on the channel.
 */
    .global spi_read
spi_read:
    push    {r4-r7, lr}
    mrs     r7, cpsr
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
    str     r0, [r4, #0x14]
    str     r1, [r4, #0x18]
    ldr     r5, =10000
1:  ldr     r6, [r4, #0x20]
    tst     r6, #1
    bne     2f
    subs    r5, r5, #1
    bne     1b
2:  ldr     r3, [r4, #0x1C]
    str     r3, [r2, #0]
    str     r6, [r2, #4]
    str     r5, [r2, #8]
    msr     cpsr_c, r7
    mov     r0, r3
    pop     {r4-r7, pc}
    .ltorg
