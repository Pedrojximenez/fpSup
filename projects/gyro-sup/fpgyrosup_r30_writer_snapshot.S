/* r30 writer-private raw snapshot helper.
 *
 * This code is appended to the verified r17/r29 resident logger at offset
 * 0xE24.  writer_block has already built the complete GFB6 header at r4 and
 * r5 still addresses the source slot's metadata.  Copy the fixed 32 KiB slot
 * to the verified free state+0x38000 window, publish the producer slot EMPTY,
 * then invoke the unchanged PGEN formatter on the private copy.
 *
 * The high-rate callback is untouched.  The copy is RAM-only and bounded;
 * formatting, 64 KiB F_WRITE calls and their 5 ms yields remain exactly r29.
 */
    .syntax unified
    .arm

    .section .text

    /* Existing resident trampoline called by writer_block. */
    .org 0xE10
pgen_trampoline:

    .org 0xE24
    .global writer_snapshot
writer_snapshot:
    push    {r4-r9, r11, lr}

    /* r9 = writer-private 32 KiB snapshot; r7 = source end. */
    movw    r9, #0x8000
    movt    r9, #0x0003
    add     r9, r10, r9
    add     r7, r4, #0x8000

1:  ldmia   r4!, {r0-r3, r6, r8, r11, r12}
    stmia   r9!, {r0-r3, r6, r8, r11, r12}
    cmp     r4, r7
    blo     1b

    /* Recover the snapshot base after the post-increment copy. */
    sub     r4, r9, #0x8000

    /* The private copy is complete.  Clear publication metadata before EMPTY
     * so a newly claimed slot cannot be damaged after the formatter returns. */
    mov     r0, #0
    str     r0, [r5, #0x18]
    str     r0, [r5, #0x1C]
    str     r0, [r5, #0x14]
    dmb     ish
    str     r0, [r5]

    /* Unchanged streaming command 2; return its success/failure in r0. */
    mov     r0, #2
    mov     r1, r4
    bl      pgen_trampoline
    pop     {r4-r9, r11, pc}

