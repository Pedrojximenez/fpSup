/* boot_marker.S -- --boot-markers: one timestamp per call, for boot timing.
 *
 * Called through the echo handler slot (`mem set 0xC0BAC2F8 MARK_AT` + `echo`),
 * so it runs as a shell command handler and returns 0.  Reads the camera's own
 * microsecond clock (F_TICK_US, the same clock as LOAD_START_US / LOAD_DONE_US
 * and the firmware log) and appends it to the array at MARK_DATA:
 *
 *     MARK_DATA + 0   magic   'MRK1' written by the AutoRun this boot;
 *                             the v4 core turns it into 'MRKD' (seen) or, if it
 *                             was not 'MRK1' (warm boot, no AutoRun), 'NONE'
 *     MARK_DATA + 4   count   stamps written so far (capped at MARK_SLOTS)
 *     MARK_DATA + 8   stamp[MARK_SLOTS]
 *
 * lr is saved before the call (loader.S's two frozen-boot lessons: push first,
 * carry sp across the call in a callee-saved register, align sp to 8).
 *
 * Defines: MARK_DATA, MARK_SLOTS, F_TICK_US.
 */
    .syntax unified
    .arm
    .text
    .global mark
mark:
    push    {r4, r5, r6, lr}
    mov     r5, sp
    bic     sp, sp, #7
    movw    r4, #:lower16:F_TICK_US
    movt    r4, #:upper16:F_TICK_US
    blx     r4
    mov     sp, r5
    movw    r1, #:lower16:MARK_DATA
    movt    r1, #:upper16:MARK_DATA
    ldr     r2, [r1, #4]
    cmp     r2, #MARK_SLOTS
    addlo   r3, r1, #8
    strlo   r0, [r3, r2, lsl #2]
    addlo   r2, r2, #1
    strlo   r2, [r1, #4]
    mov     r0, #0
    pop     {r4, r5, r6, pc}
