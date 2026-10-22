/* r34 post-recording JSON-path diagnostics, based on exact r33.
 *
 * No recording/GCSV hot path is changed.  The existing JSON builder still
 * runs normally.  This tail records its last failure phase in spare state
 * words and, only when the queue is about to consume an event without a JSON,
 * writes a small Axxx_xxx.jdg sidecar.  It distinguishes the two fast-unlock
 * paths that the SD card alone could not separate:
 *
 *   reason=1  kind 2 auto-completed JSON without calling the builder
 *   reason=2  kind 1 exhausted the existing twelve immediate retries
 */
    .syntax unified
    .arm

    .equ J_PHASE,   0x1EC
    .equ J_ATTEMPT, 0x1F0

    .section .text
    .org 0x1E58                 /* exact end of r33 PGEN body */

/* Replaces the old BL json_builder at body+0x458. */
    .global json_attempt_probe
json_attempt_probe:
    push    {r4, lr}
    mov     r0, #1              /* entered JSON builder */
    str     r0, [sl, #J_PHASE]
    ldr     r0, [r5, #4]
    add     r0, r0, #1
    str     r0, [sl, #J_ATTEMPT]
    .global json_attempt_call_builder
json_attempt_call_builder:
    bl      .                   /* builder patches to old body+0xD88 */
    pop     {r4, pc}

/* Conditional branches in the old builder are redirected to one of these
 * stubs.  Each records a precise failure phase, then returns through the old
 * common failure epilogue at body+0x1264. */
    .global phase_enabled_before
phase_enabled_before:
    mov     r0, #2
    b       phase_store_failure
    .global phase_rate_zero
phase_rate_zero:
    mov     r0, #3
    b       phase_store_failure
    .global phase_width_zero
phase_width_zero:
    mov     r0, #4
    b       phase_store_failure
    .global phase_height_zero
phase_height_zero:
    mov     r0, #5
    b       phase_store_failure
    .global phase_lens_query_0d
phase_lens_query_0d:
    mov     r0, #6
    b       phase_store_failure
    .global phase_enabled_after_0d
phase_enabled_after_0d:
    mov     r0, #7
    b       phase_store_failure
    .global phase_lens_0d_short
phase_lens_0d_short:
    mov     r0, #8
    b       phase_store_failure
    .global phase_lens_query_2d
phase_lens_query_2d:
    mov     r0, #9
    b       phase_store_failure
    .global phase_enabled_after_2d
phase_enabled_after_2d:
    mov     r0, #10
    b       phase_store_failure
    .global phase_enabled_before_file
phase_enabled_before_file:
    mov     r0, #11
    b       phase_store_failure

phase_store_failure:
    str     r0, [sl, #J_PHASE]
    .global phase_store_failure_exit
phase_store_failure_exit:
    b       .                   /* builder patches to old body+0x1264 */

/* Replace the two `mov r0,#0` exits in the old JSON file writer. */
    .global phase_file_gate_return_zero
phase_file_gate_return_zero:
    mov     r1, #12
    str     r1, [sl, #J_PHASE]
    mov     r0, #0
    bx      lr

    .global phase_file_open_return_zero
phase_file_open_return_zero:
    mov     r1, #13
    str     r1, [sl, #J_PHASE]
    mov     r0, #0
    bx      lr

/* Replaces `mov r6,r0` after F_WRITE. */
    .global phase_file_write_result
phase_file_write_result:
    mov     r6, r0
    cmp     r0, #0
    moveq   r1, #14
    movne   r1, #99             /* JSON bytes reached F_WRITE successfully */
    str     r1, [sl, #J_PHASE]
    bx      lr

/* Replaces `add r4,sl,#0x2A0` at the shared event-consume point. */
    .global diagnostic_before_consume
diagnostic_before_consume:
    push    {r0-r9, ip, lr}      /* 48 bytes; preserve the displaced ABI */
    ldr     r0, [r5]             /* queue-entry flags */
    ubfx    r8, r0, #16, #8      /* kind */
    ubfx    r9, r0, #8, #8       /* volume */
    ldr     r6, [r5, #4]         /* current retry counter */

    cmp     r8, #2
    bne     diagnostic_check_retry
    mov     r7, #1              /* kind-2 auto-completion */
    mov     r1, #0
    str     r1, [sl, #J_PHASE]
    bl      diagnostic_write_sidecar
    b       diagnostic_consume_done

diagnostic_check_retry:
    tst     r0, #2              /* JSON-complete bit really set? */
    bne     diagnostic_consume_done
    cmp     r6, #12
    blo     diagnostic_consume_done
    mov     r7, #2              /* twelve immediate JSON failures */
    bl      diagnostic_write_sidecar

diagnostic_consume_done:
    pop     {r0-r9, ip, lr}
    add     r4, sl, #0x2A0      /* replay displaced instruction */
    bx      lr

diagnostic_prefix:
    .asciz  "FPJ1;reason="
diagnostic_kind:
    .asciz  ";kind="
diagnostic_volume:
    .asciz  ";volume="
diagnostic_attempts:
    .asciz  ";attempts="
diagnostic_phase:
    .asciz  ";phase="
    .balign 4

/* Inputs: r6 attempts, r7 reason, r8 kind, r9 volume.
 * Uses the now-idle GCSV text region as a tiny formatting buffer and the
 * already-idle JSON file object at state+0x800. */
diagnostic_write_sidecar:
    push    {r3-r9, r11, ip, lr} /* 40 bytes; keep call alignment */
    adr     r11, diagnostic_prefix

    movw    r4, #0xA000
    movt    r4, #1
    add     r4, sl, r4           /* state+0x1A000 */
    mov     r5, r4

    mov     r0, r11
    mov     r1, r5
    bl      diagnostic_copy
    mov     r5, r0
    mov     r0, r7
    mov     r1, r5
    bl      diagnostic_uint
    mov     r5, r0

    add     r0, r11, #(diagnostic_kind - diagnostic_prefix)
    mov     r1, r5
    bl      diagnostic_copy
    mov     r5, r0
    mov     r0, r8
    mov     r1, r5
    bl      diagnostic_uint
    mov     r5, r0

    add     r0, r11, #(diagnostic_volume - diagnostic_prefix)
    mov     r1, r5
    bl      diagnostic_copy
    mov     r5, r0
    mov     r0, r9
    mov     r1, r5
    bl      diagnostic_uint
    mov     r5, r0

    add     r0, r11, #(diagnostic_attempts - diagnostic_prefix)
    mov     r1, r5
    bl      diagnostic_copy
    mov     r5, r0
    mov     r0, r6
    mov     r1, r5
    bl      diagnostic_uint
    mov     r5, r0

    add     r0, r11, #(diagnostic_phase - diagnostic_prefix)
    mov     r1, r5
    bl      diagnostic_copy
    mov     r5, r0
    ldr     r0, [sl, #J_PHASE]
    mov     r1, r5
    bl      diagnostic_uint
    mov     r5, r0
    mov     r0, #10
    strb    r0, [r5], #1

    /* c48 already built the current event's .json path at state+0x180.
     * Change only the extension to .jdg. */
    add     r3, sl, #0x180
    movw    r0, #0x646A         /* "jd" */
    movt    r0, #0x0067         /* "g\0" */
    str     r0, [r3, #0x1A]

    cmp     r9, #1
    beq     diagnostic_open
    cmp     r9, #5
    bne     diagnostic_write_done

diagnostic_open:
    add     r0, sl, #0x800
    movw    ip, #0x5E90
    movt    ip, #0xC036
    blx     ip                  /* F_CTOR */

    add     r0, sl, #0x800
    add     r1, sl, #0x180
    mov     r2, #7
    movw    ip, #0x5FB0
    movt    ip, #0xC036
    blx     ip                  /* F_OPEN overwrite */
    cmp     r0, #0
    bne     diagnostic_write

    add     r0, sl, #0x800
    mov     r1, #2
    movw    ip, #0x5ED0
    movt    ip, #0xC036
    blx     ip                  /* F_DTOR after failed open */
    b       diagnostic_write_done

diagnostic_write:
    add     r0, sl, #0x800
    mov     r1, r4
    sub     r2, r5, r4
    movw    ip, #0x60E8
    movt    ip, #0xC036
    blx     ip                  /* F_WRITE */

    add     r0, sl, #0x800
    movw    ip, #0x6020
    movt    ip, #0xC036
    blx     ip                  /* F_CLOSE */

    add     r0, sl, #0x800
    mov     r1, #2
    movw    ip, #0x5ED0
    movt    ip, #0xC036
    blx     ip                  /* F_DTOR */

diagnostic_write_done:
    pop     {r3-r9, r11, ip, pc}

/* Tail shims preserve the caller's LR while reusing the exact old formatters. */
diagnostic_copy:
    .global diagnostic_copy_tail
diagnostic_copy_tail:
    b       .                   /* builder patches to old body+0x173C */

diagnostic_uint:
    .global diagnostic_uint_tail
diagnostic_uint_tail:
    b       .                   /* builder patches to old body+0x14C8 */
