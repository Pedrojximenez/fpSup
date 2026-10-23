.syntax unified
.arm
.text
/* spi_read2 -- one READ transaction on serial ch1 (the IMX410), completed the way driver A completes a read
 * (FUN_c012a690): pop RX (+0x1C) and read status (+0x20) every iteration until (status & 0x11) == 0x11,
 * keeping the LAST popped word. spi_read.S stopped at status bit0 and popped once -- that is the difference.
 * See notes/SENSOR_BUS_READ.md "Driver A read recipe". NOT RUN YET.
 *
 *   r0 = header word, LSByte goes out first: chip_id | reg_hi << 8 | reg_lo << 16   (0x82 = guessed read ID)
 *   r1 = TX data byte for the data phase (0 for a read)
 *   r2 = result block, 29 words (116 bytes):
 *          +0x00 last RX popped         +0x04 last status        +0x08 polls left (0 = timed out)
 *          +0x0C status before start    +0x10 n pairs recorded   +0x14.. up to 12 (RX, status) pairs, in order
 *   r3 = mode (pass it explicitly):
 *          bit0 = 0: stock framing, +0x0C = 0x818 (24 header bits in +0x14, then 8 data bits in +0x18)
 *          bit0 = 1: driver-A framing, +0x0C = 0x2000 (0 bits in +0x14, one 32-bit phase in +0x18 =
 *                    header | data << 24; the data byte should come back in RX[31:24] [I])
 *          bits 15:8 = clock divider for +0x04[15:8] (0 -> 1 = the stock value); +0x08 = 0x30 when the
 *                    divider is <= 1, else 0x00 (driver B's rule, c012b748)
 * Returns the last RX word. IRQs are masked for the whole transaction (the stock writer takes no lock).
 * +0x10 is cleared at the end, as driver A does; the stock writer re-initialises the channel on every call.
 */
    .global spi_read2
spi_read2:
    push    {r4-r10, lr}
    mrs     r7, cpsr
    cpsid   i
    ldr     r4, =0x21C00100
    mov     r10, r2
    mov     r8, r3
    ubfx    r5, r8, #8, #8          @ divider
    cmp     r5, #0
    moveq   r5, #1

    mov     r6, #0x11               @ +0x00: 0x11 -> 0x13, as the stock writer
    str     r6, [r4, #0x00]
    mov     r6, #0x13
    str     r6, [r4, #0x00]
    mov     r6, #0
    str     r6, [r4, #0x10]
    str     r6, [r4, #0x2C]
    lsl     r6, r5, #8              @ +0x04 = div << 8, bit0 = 0 (driver A read: RX kept)
    str     r6, [r4, #0x04]
    cmp     r5, #1
    movls   r6, #0x30
    movhi   r6, #0
    str     r6, [r4, #0x08]
    tst     r8, #1
    ldreq   r6, =0x818
    movne   r6, #0x2000
    str     r6, [r4, #0x0C]
    mov     r6, #0
    str     r6, [r4, #0x20]
    ldr     r6, [r4, #0x20]
    str     r6, [r10, #0x0C]        @ status before start
    mov     r6, #1
    str     r6, [r4, #0x10]

    tst     r8, #1
    bne     1f
    str     r0, [r4, #0x14]         @ stock framing: header, then data (the +0x18 write starts it)
    str     r1, [r4, #0x18]
    b       2f
1:  mov     r6, #0
    str     r6, [r4, #0x14]         @ driver-A framing: +0x14 carries 0 bits
    orr     r6, r0, r1, lsl #24
    str     r6, [r4, #0x18]

2:  ldr     r5, =10000
    mov     r9, #0
3:  ldr     r3, [r4, #0x1C]         @ pop RX every iteration (FUN_c012a690)
    ldr     r6, [r4, #0x20]
    cmp     r9, #12
    bhs     4f
    add     r12, r10, #0x14
    add     r12, r12, r9, lsl #3
    str     r3, [r12, #0]
    str     r6, [r12, #4]
    add     r9, r9, #1
4:  and     r12, r6, #0x11
    cmp     r12, #0x11
    beq     5f
    subs    r5, r5, #1
    bne     3b

5:  str     r3, [r10, #0x00]
    str     r6, [r10, #0x04]
    str     r5, [r10, #0x08]
    str     r9, [r10, #0x10]
    mov     r12, #0
    str     r12, [r4, #0x10]        @ stop, as driver A
    msr     cpsr_c, r7
    mov     r0, r3
    pop     {r4-r10, pc}
    .ltorg
