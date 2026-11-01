// SPDX-License-Identifier: GPL-3.0-or-later
.syntax unified
.arm
.text
/* Entered from relocated stub_gs via params.P_BLOCK (the original module).
 * Original r4/r5 are already stacked. Preserve r3
 * (relocated params), and lr. Never write cm_buf/cm_tab/P_SAT.
 */
.global preview_color
preview_color:
    ldr     r4, [r3, #0x1b0]       /* existing saturation selection, untouched */
    cmp     r4, #1
    movhi   r4, #0
    add     r4, r4, r4, lsl #1
    ldr     r5, [r3, #0x1a4]       /* SA=0, GA=1 */
    tst     r5, #1
    addeq   r5, r3, #0x1d0         /* SA keeps original preview table */
    adrne   r5, preview_tables     /* GA uses preview-only boosted table */
    add     r4, r5, r4, lsl #3     /* index *24 */
    ldr     r1, [r3, #0x1a8]
    add     r5, r1, #0x330         /* only display matrix copy's OFF row */
    mov     r0, #6
copy:
    ldr     ip, [r4], #4
    str     ip, [r5], #4
    subs    r0, r0, #1
    bne     copy
done:
    pop     {r4, r5}              /* displaced original instruction */
    mov     r0, #1                /* displaced original instruction */
    movw    r2, #0x4b8            /* return165c - original params11a4 */
    add     r2, r3, r2            /* correct even when resident relocated */
    bx      r2                    /* r2 overwritten to7 before stub returns */
.align 2
preview_tables:
    /* Two 24-byte records supplied below by build.py. */
