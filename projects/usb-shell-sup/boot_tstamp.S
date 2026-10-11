.syntax unified
.arm
.text
.global tstamp

/* ============================================================================
 * tstamp — read the camera's clock into a slot, called from the AutoRun.
 * ============================================================================
 *
 * Boot time has been argued about with a stopwatch, and the two numbers the
 * bar-vs-no-bar experiment produced could not be compared because nobody wrote
 * down where the measurement started (AUTORUN_STORE_BOOT.md §9.2).  A clock
 * read from inside the script fixes both halves of that: the start is a sample
 * rather than a memory, and the difference between two samples is the script's
 * own duration, whatever the camera did before it.
 *
 * Called the way --boot-call calls things: the `echo` handler's slot is pointed
 * here, `echo` is issued, and the slot is put back.  So this is a command
 * handler -- (ctx, argc, argv) in r0-r2 -- and a handler returns int.
 *
 *     SLOTS  +0x00  the index, and the next sample goes to +4 + 4*index
 *     TAIL   0, or a routine to fall through to once the sample is taken
 *
 * TAIL exists for one case: on a card with fast start the interpreter is
 * stopped by the abort routine, armed into this same slot by stage2, and the
 * `echo` that triggers it is the last command that runs.  Overwriting the slot
 * to take a sample there would throw the abort away and let the script run on
 * into the slow path it exists to skip -- so the sample is taken here and the
 * abort is called afterwards, with the arguments it was going to get.
 *
 * Guarded, because on the FIRST boot of a fast card the store is not seeded:
 * store_boot returns without running the loader, stage2 never runs, and nothing
 * is ever written at the abort's address.  A word of zero there means "not
 * armed", and then this returns like an ordinary handler and the script carries
 * on -- which is exactly what an unseeded boot is supposed to do.
 *
 * Read the samples back over USB once the shell is up:
 *
 *     ./fpsh mem get 0xC072F280,,0x40
 * ========================================================================== */

.equ CLOCK, 0xC002B920          /* the firmware's own clock; r0 = a tick count.
                                 * sigma-fp-lab measures a half-second button
                                 * hold with it, so it counts milliseconds --
                                 * but only monotonicity and a fixed rate are
                                 * needed here, because every number reported is
                                 * a difference between two samples. */

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

tstamp:
    /* Six registers: the stack stays 8-byte aligned, and r0-r2 are the
     * handler's own arguments, which TAIL is entitled to. */
    push    {r0, r1, r2, r4, r5, lr}
    LDA     r4, SLOTS
    LDA     ip, CLOCK
    blx     ip
    ldr     r5, [r4]
    cmp     r5, #14                     @ leave the last slot alone rather than
    bhs     1f                          @ run off the end of the block
    add     r1, r4, r5, lsl #2
    str     r0, [r1, #4]
    add     r5, r5, #1
    str     r5, [r4]
1:
.if TAIL != 0
    LDA     ip, TAIL
    ldr     r3, [ip]                    @ r3 is scratch: the handler's arguments
    cmp     r3, #0                      @ are r0-r2
    pop     {r0, r1, r2, r4, r5, lr}    @ LDM leaves the flags alone
    moveq   r0, #0
    bxeq    lr                          @ not armed: this is the first boot
    bx      ip
.else
    pop     {r0, r1, r2, r4, r5, lr}
    mov     r0, #0
    bx      lr
.endif
