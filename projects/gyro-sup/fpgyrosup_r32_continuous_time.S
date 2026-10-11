/* r32 r29-only cross-block timestamp continuity helpers.
 *
 * r29 formats every row inside a raw block at exactly +400 us, but starts the
 * next block from its callback-time anchor.  Normal slot hand-off overhead is
 * therefore exposed as a 400..935 us seam and accumulates to about 0.02% even
 * when no producer batch was dropped.
 *
 * Keep both the corrected next timestamp and the uncorrected raw-anchor next
 * timestamp across blocks.  Comparing against the latter prevents suppressed
 * seams from accumulating into a false large jump.  A local anchor discrepancy
 * no more than 1,000 us is treated as hand-off jitter; a larger forward jump
 * remains visible, so the known 40-ms writer loss cannot be hidden.
 */
    .syntax unified
    .arm

    .section .text

    /* Exact end of the r29 PGEN body. */
    .org 0x1D4C

    /* Replaces `mov r0,#1` during stream open and returns the same r0. */
    .global timestamp_continuity_init
timestamp_continuity_init:
    add     r1, sl, #0x1A0
    mov     r0, #0
    str     r0, [r1, #0x38]          /* corrected next */
    str     r0, [r1, #0x3C]          /* raw-anchor next */
    str     r0, [r1, #0x40]          /* raw minus corrected bias */
    mov     r0, #1
    bx      lr

    /* Replaces the three-instruction raw-anchor setup at stream body+0x18D0.
     * Output: sb = chosen relative timestamp; fp = recording start anchor. */
    .global timestamp_choose_block_start
timestamp_choose_block_start:
    add     r0, sl, #0x1A0
    ldr     r1, [r0, #0x38]          /* corrected next, zero on first */
    ldr     sb, [r4, #8]             /* this raw block's absolute anchor */
    ldr     fp, [sl, #0x88]          /* recording start anchor */
    sub     sb, sb, fp               /* this block's relative anchor */
    cmp     r1, #0
    beq     2f
    ldr     r2, [r0, #0x3C]          /* expected raw anchor */
    cmp     sb, r2
    bls     1f                       /* never turn a backward anchor into a gap */
    sub     r3, sb, r2               /* local seam only, not cumulative bias */
    cmp     r3, #1000
    addhi   r1, r1, r3               /* preserve a real producer gap */
1:  sub     r2, sb, r1
    str     r2, [r0, #0x40]
    mov     sb, r1
    bx      lr
2:  mov     r1, #0
    str     r1, [r0, #0x40]
    bx      lr

    /* Replaces the original text-length subtraction at stream body+0x1B70,
     * preserving its r1 result while publishing the next +400-us timestamp. */
    .global timestamp_store_next
timestamp_store_next:
    add     r0, sl, #0x1A0
    str     sb, [r0, #0x38]
    ldr     r2, [r0, #0x40]
    add     r2, sb, r2
    str     r2, [r0, #0x3C]
    sub     r1, r5, r6
    bx      lr
