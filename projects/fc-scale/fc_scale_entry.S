.syntax unified
.arm
.text
.global fc_entry

/* ============================================================================
 * fc_entry — the entry an fpSup payload needs, for a card that was written as
 * an AutoRun.
 * ============================================================================
 *
 * sigma-fp-lab's False Color / EL Zone card carries its code as 728 `mem set`
 * lines and arms three firmware sites at the end of the file.  The order there
 * is deliberate: the two button sites go in, then `echo` is borrowed to call
 * 0xC000E91C so the caches publish what was just written, and only then does
 * the display-submit site go in -- that one fires every frame, so arming it
 * over code the I-cache has not seen yet is a branch into whatever was there.
 *
 * A VBIN card cannot express that order.  stage2 places every section in table
 * order and publishes once, at the end of the pass, so a hook word sitting in
 * the table can be armed before the code it points at is visible.  So the hook
 * words do not travel as sections: they travel as a table here, and this runs
 * from the entry -- which stage2 calls AFTER its own publish, meaning the
 * payload is already visible before the first site is touched.  Then this
 * publishes again for the sites themselves.
 *
 * Nothing about it is specific to that card.  The table is (site, word) pairs
 * terminated by a zero word, appended by fc_scale_to_vbin.py after this code,
 * and `adr` finds it wherever the section lands.
 *
 * Called with (r0 = the file's base), returns 0; stage2 requires the entry to
 * come back.  Four registers pushed, so the stack stays 8-byte aligned -- the
 * firmware's interrupt path STRDs into it.
 * ========================================================================== */

.equ F_DCACHE, 0xC000E91C       /* D-cache clean/invalidate + barriers */
.equ F_ICACHE, 0xC000EABC       /* whole I-cache invalidate + barriers */

fc_entry:
    push    {r4, r5, r6, lr}
    adr     r4, table
1:  ldr     r5, [r4], #4            @ the site, or zero at the end
    cmp     r5, #0
    beq     2f
    ldr     r6, [r4], #4            @ the word to put there
    str     r6, [r5]
    b       1b

2:  movw    ip, #:lower16:F_DCACHE
    movt    ip, #:upper16:F_DCACHE
    blx     ip
    movw    ip, #:lower16:F_ICACHE
    movt    ip, #:upper16:F_ICACHE
    blx     ip
    mov     r0, #0
    pop     {r4, r5, r6, pc}

table:
    /* (site, word) pairs and a zero terminator, appended by the builder. */
