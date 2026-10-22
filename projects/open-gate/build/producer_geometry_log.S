.syntax unified
.thumb
.text

/*
 * Read-only producer geometry logger.
 *
 * Hook site: 0xC01BE5E4, immediately after FUN_c01becd8 returns.
 * The preceding stock instruction (0xC01BE5E2) has already loaded the channel
 * into r0.  r4 points at C302444C and sl points at the large stage config.
 *
 * The hook site contains one complete 32-bit Thumb instruction:
 *     movw r1, #0xd844
 * It is replayed before returning to 0xC01BE5E8.
 *
 * This records up to five distinct geometry tuples instead of only the first
 * invocation.  The function also runs for live view, so a first-hit logger is
 * guaranteed to hide the later CinemaDNG configuration.
 *
 * State at 0xC072FA10:
 *   +0x00 magic ('PGL2')
 *   +0x04 total calls
 *   +0x08 unique records
 *   +0x0c distinct tuples dropped after the five slots filled
 *   +0x10 five records, 0x28 bytes each:
 *          signature, channel,
 *          producer W/H  [r4+0x08/+0x0c],
 *          source W/H    [sl+0x58/+0x60],
 *          target W/H    [sl+0x74/+0x78],
 *          crop X/Y      [sl+0x7c/+0x80]
 *
 * Only the state block is written.  All caller-visible registers are restored;
 * the stack remains eight-byte aligned while the logger runs.
 */

.equ LOG,         0xC072FA10
.equ RECORDS,     5
.equ RECORD_SIZE, 0x28
.equ MAGIC,       0x324C4750          /* little-endian ASCII "PGL2" */

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

/* Mix one word into r6.  The signature is only a de-duplication aid; the full
 * tuple is retained in the record and inspected by the host. */
.macro MIX base, off, rot
    ldr     r1, [\base, #\off]
    eor.w   r6, r6, r1, ror #\rot
.endm

.global entry
.thumb_func
entry:
    push    {r0, r1, r2, r3, r5, r6, r7, ip, lr}
    sub     sp, sp, #4                  /* 9 saved regs + pad = 40 bytes */

    LDA     r5, LOG

    ldr     r1, [r5, #4]               /* total calls */
    adds    r1, r1, #1
    str     r1, [r5, #4]

    /* Hash every recorded dimension plus channel. */
    mov     r6, r0
    MIX     r4, 0x08, 3
    MIX     r4, 0x0c, 7
    MIX     sl, 0x58, 11
    MIX     sl, 0x60, 13
    MIX     sl, 0x74, 17
    MIX     sl, 0x78, 19
    MIX     sl, 0x7c, 23
    MIX     sl, 0x80, 29
    cmp     r6, #0                     /* zero marks an unused slot */
    bne     0f
    movs    r6, #1
0:

    add.w   r7, r5, #0x10
    movs    r2, #0

1:  ldr     r1, [r7]                   /* signature */
    cmp     r1, r6
    beq     4f                          /* tuple already represented */
    cmp     r1, #0
    beq     3f                          /* first free slot */
    adds    r2, r2, #1
    cmp     r2, #RECORDS
    beq     2f
    add.w   r7, r7, #RECORD_SIZE
    b       1b

2:  ldr     r1, [r5, #0x0c]            /* table full */
    adds    r1, r1, #1
    str     r1, [r5, #0x0c]
    b       4f

3:  /* Publish the signature last, after the complete tuple is visible. */
    str     r0, [r7, #0x04]            /* channel */

    ldr     r1, [r4, #0x08]
    str     r1, [r7, #0x08]
    ldr     r1, [r4, #0x0c]
    str     r1, [r7, #0x0c]

    ldr     r1, [sl, #0x58]
    str     r1, [r7, #0x10]
    ldr     r1, [sl, #0x60]
    str     r1, [r7, #0x14]
    ldr     r1, [sl, #0x74]
    str     r1, [r7, #0x18]
    ldr     r1, [sl, #0x78]
    str     r1, [r7, #0x1c]
    ldr     r1, [sl, #0x7c]
    str     r1, [r7, #0x20]
    ldr     r1, [sl, #0x80]
    str     r1, [r7, #0x24]

    dmb     ish
    str     r6, [r7]
    ldr     r1, [r5, #8]
    adds    r1, r1, #1
    str     r1, [r5, #8]

4:  add     sp, sp, #4
    pop     {r0, r1, r2, r3, r5, r6, r7, ip, lr}
    movw    r1, #0xd844                /* displaced instruction */
    bx      lr
