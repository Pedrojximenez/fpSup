.syntax unified
.arm
.text
.global fc_pool_entry

/* ============================================================================
 * fc_pool_entry — put a third-party payload in memory the allocator chose,
 * and leave only anchors in the cave.
 * ============================================================================
 *
 * The cave is not a heap.  Three products already treat it as one -- the gyro
 * logger's payload, OG3K's and OG2K's -- and after the loader, the park stub,
 * the shell's state, the boot descriptor and the host's one-shot block there is
 * no three-kilobyte hole left in the stock image's zero region.  So a fourth
 * payload that wants a fixed 3 KB cannot be added; it can only take somebody
 * else's bytes.  That is what made a gyro + FC card refuse to compose.
 *
 * The way out is the one worker.S and the gyro profile generator already use:
 * ask the allocator.  This runs as the card's entry, from the staging buffer,
 * with the payload travelling in the same section:
 *
 *      1. H_GET / H_ADDR for as much as the payload needs, class 0 (USER) --
 *         the same class the worker's pool comes from.
 *      2. copy the payload there.  It is position independent: every branch
 *         inside it is relative, every literal it loads is pc-relative, and
 *         the only absolute addresses it names are firmware entry points and
 *         its own state block, which stays in the cave.
 *      3. fill in the trampolines' target words -- pool + the offset of each
 *         hook routine.
 *      4. publish, because what was just written is instructions.
 *      5. arm the firmware sites, each with a branch to its trampoline, and
 *         publish again.
 *
 * A firmware site cannot branch to the pool directly: the allocator's blocks
 * are 48 MB away and an ARM `b` reaches 32.  Hence a trampoline per hook, eight
 * bytes in the cave, `ldr pc, [pc, #-4]` followed by the word this fills in.
 * One extra indirect load per call, and the display-submit hook is the only one
 * that runs often.
 *
 * Arming LAST is the whole point of the ordering.  The display submit fires
 * every frame, so a site armed before its target is copied and published is a
 * branch into whatever the pool held before.
 *
 * Everything specific to a payload -- where the state block is, how much to
 * ask for, which sites to arm and with what -- is a table appended after this
 * code by the builder.  `adr` finds it wherever the section lands, and the
 * payload is at a known offset from it, so a merge re-laying the file out
 * cannot break the reference.
 *
 *      tbl +0x00  the allocator descriptor, 16 bytes of cave
 *          +0x04  bytes to ask for
 *          +0x08  where to publish the pool address, or 0
 *          +0x0C  offset from tbl to the payload
 *          +0x10  the payload's length, a multiple of four
 *          +0x14  (address, pool offset) pairs, a zero word ends them
 *                 (address, word) pairs, a zero word ends them
 *
 * Called with r0 = the file's base, returns 0; stage2 requires the entry to
 * return.  Eight registers pushed, so the stack stays 8-byte aligned.
 *
 * If the allocator refuses, this arms nothing and returns.  The camera is then
 * exactly as it was, minus the payload -- which is the only safe failure: a
 * site armed with no code behind it is a freeze on the next frame.
 * ========================================================================== */

.equ H_GET,     0xC001D740      /* (desc, class, size, 0)                    */
.equ H_ADDR,    0xC001D7F0      /* (desc) -> address                         */
.equ POOL_CLASS, 0              /* USER -- NOT 10 (RAW), see loader.S        */
.equ F_DCACHE,  0xC000E91C      /* D-cache clean/invalidate + barriers       */
.equ F_ICACHE,  0xC000EABC      /* whole I-cache invalidate + barriers       */

/* Absolute, not `bl`: this runs from the staging buffer, at an address the
 * allocator chose this boot, so nothing pc-relative reaches the firmware. */
.macro FCALL target
    movw    ip, #:lower16:\target
    movt    ip, #:upper16:\target
    blx     ip
.endm

fc_pool_entry:
    push    {r4, r5, r6, r7, r8, r9, r10, lr}
    adr     r4, tbl

    ldr     r5, [r4]                    @ the descriptor, in the cave: it has
    ldr     r6, [r4, #4]                @ to outlive the call
    mov     r0, r5
    mov     r1, #POOL_CLASS
    mov     r2, r6
    mov     r3, #0
    FCALL   H_GET
    mov     r0, r5
    FCALL   H_ADDR
    cmp     r0, #0
    beq     done                        @ refused: arm nothing
    mov     r7, r0                      @ the pool

    ldr     r1, [r4, #8]                @ publish it, for a host tool or a
    cmp     r1, #0                      @ later payload to find
    strne   r7, [r1]

    ldr     r2, [r4, #0xC]              @ the payload travels with this code
    add     r2, r4, r2
    ldr     r3, [r4, #0x10]
1:  subs    r3, r3, #4
    ldrge   r1, [r2, r3]
    strge   r1, [r7, r3]
    bgt     1b

    add     r6, r4, #0x14               @ the trampolines' targets
2:  ldr     r0, [r6], #4
    cmp     r0, #0
    beq     3f
    ldr     r1, [r6], #4
    add     r1, r1, r7
    str     r1, [r0]
    b       2b

3:  bl      publish                     @ the pool holds instructions now, and
                                        @ the trampolines point at them
4:  ldr     r0, [r6], #4                @ the firmware sites, last
    cmp     r0, #0
    beq     5f
    ldr     r1, [r6], #4
    str     r1, [r0]
    b       4b
5:  bl      publish

done:
    mov     r0, #0
    pop     {r4, r5, r6, r7, r8, r9, r10, pc}

/* r4 is pushed for the same reason stage2's s2_publish pushes it: these two
 * routines are known to leave r5-r8 alone and r4 is the one that was worth
 * protecting when that was found out. */
publish:
    push    {r4, lr}
    FCALL   F_DCACHE
    FCALL   F_ICACHE
    pop     {r4, pc}

.balign 4
tbl:
    /* Appended by the builder: the header, the two patch lists, the payload. */
