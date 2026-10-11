/* r35 immediate JSON-return diagnostics, appended to exact r34.
 *
 * r34 wrote its JDG only when the queue was finally consumed.  A JSON failure
 * followed by a lifecycle/stream early return never reached that point.  This
 * replacement wrapper first leaves one pre-builder breadcrumb, then records
 * timing and gate state and overwrites FPJ2 on the first failed return, before
 * the old main loop can take an early exit.  The recording/GCSV hot path
 * remains byte-identical to r34/r33.
 */
    .syntax unified
    .arm

    .equ J_PHASE,       0x1EC
    .equ J_ATTEMPT,     0x1F0
    .equ J_ELAPSED,     0x1F4
    .equ J_LIFECYCLE,   0x1F8
    .equ J_STREAM,      0x1FC

    .section .text
    .org 0x20FC                 /* exact end of r34 PGEN body */

/* Replaces r34's BL at body+0x458.  r5 is the current queue entry and the
 * caller needs its old r4 flags preserved exactly. */
    .global json_attempt_probe_v2
json_attempt_probe_v2:
    push    {r4, r6-r9, lr}      /* 24 bytes; preserve ABI and alignment */

    mov     r0, #1
    str     r0, [sl, #J_PHASE]
    ldr     r0, [r5, #4]
    add     r0, r0, #1
    str     r0, [sl, #J_ATTEMPT]

    /* Leave one pre-builder breadcrumb.  If the builder itself never returns,
     * reason 0 remains on card.  The old JSON writer always replaces the
     * extension with .json before its own F_OPEN. */
    mov     r6, r0
    cmp     r6, #1
    bne     json_attempt_v2_start_timer
    mov     r0, #0
    str     r0, [sl, #J_ELAPSED]
    ldr     r0, [sl, #0xA0]
    str     r0, [sl, #J_LIFECYCLE]
    ldr     r0, [sl, #8]
    str     r0, [sl, #J_STREAM]
    mov     r7, #0              /* immediately before first builder entry */
    ldr     r0, [r5]
    ubfx    r8, r0, #16, #8
    ubfx    r9, r0, #8, #8
    bl      diagnostic_write_sidecar_v2

json_attempt_v2_start_timer:
    movw    ip, #0xB6E0
    movt    ip, #0xC002
    blx     ip                  /* TickTimer before builder */
    mov     r6, r0

    .global json_attempt_call_builder_v2
json_attempt_call_builder_v2:
    bl      .                   /* builder patches to old body+0xD88 */
    mov     r4, r0              /* preserve exact builder return */

    movw    ip, #0xB6E0
    movt    ip, #0xC002
    blx     ip                  /* TickTimer immediately after return */
    sub     r0, r0, r6
    str     r0, [sl, #J_ELAPSED]
    ldr     r0, [sl, #0xA0]
    str     r0, [sl, #J_LIFECYCLE]
    ldr     r0, [sl, #8]
    str     r0, [sl, #J_STREAM]

    ldr     r6, [sl, #J_ATTEMPT]
    cmp     r4, #0
    beq     json_attempt_v2_failed

    /* Always replace reason 0 after a successful return.  This distinguishes
     * a builder that never returned from one that reported success even if the
     * JSON directory entry is later absent. */
    ldr     r0, [sl, #J_ELAPSED]
    movw    r1, #0x4240
    movt    r1, #0x000F         /* 1,000,000 us */
    cmp     r0, r1
    movlo   r7, #8              /* builder reported success under one second */
    movhs   r7, #7              /* slow builder success */
    b       json_attempt_v2_emit

json_attempt_v2_failed:
    ldr     r0, [sl, #J_LIFECYCLE]
    cmp     r0, #1
    movne   r7, #5              /* failure returned after lifecycle changed */
    bne     json_attempt_v2_emit
    ldr     r0, [sl, #J_STREAM]
    cmp     r0, #0
    movne   r7, #6              /* failure returned while stream non-idle */
    bne     json_attempt_v2_emit
    cmp     r6, #1
    moveq   r7, #3              /* ordinary first builder failure */
    beq     json_attempt_v2_emit
    ldr     r0, [sl, #J_ELAPSED]
    movw    r1, #0x4240
    movt    r1, #0x000F
    cmp     r0, r1
    blo     json_attempt_v2_return
    mov     r7, #4              /* later failure took >=1 second */

json_attempt_v2_emit:
    ldr     r0, [r5]
    ubfx    r8, r0, #16, #8
    ubfx    r9, r0, #8, #8
    bl      diagnostic_write_sidecar_v2

json_attempt_v2_return:
    mov     r0, r4
    pop     {r4, r6-r9, pc}

/* Replaces r34's BL at the shared body+0x518 consume point.  A kind-2
 * auto-completion or the twelfth failed retry overwrites the first-failure
 * FPJ2 with its final outcome.  A recovered JSON leaves the first marker next
 * to the successful JSON, which proves a transient first-attempt failure. */
    .global diagnostic_before_consume_v2
diagnostic_before_consume_v2:
    push    {r0-r9, ip, lr}
    ldr     r0, [r5]
    ubfx    r8, r0, #16, #8
    ubfx    r9, r0, #8, #8
    ldr     r6, [r5, #4]

    cmp     r8, #2
    bne     diagnostic_v2_check_retry
    mov     r7, #1              /* kind-2 auto-completion */
    mov     r1, #0
    str     r1, [sl, #J_PHASE]
    str     r1, [sl, #J_ATTEMPT]
    str     r1, [sl, #J_ELAPSED]
    ldr     r1, [sl, #0xA0]
    str     r1, [sl, #J_LIFECYCLE]
    ldr     r1, [sl, #8]
    str     r1, [sl, #J_STREAM]
    mov     r6, #0
    bl      diagnostic_write_sidecar_v2
    b       diagnostic_v2_consume_done

diagnostic_v2_check_retry:
    tst     r0, #2
    bne     diagnostic_v2_consume_done
    cmp     r6, #12
    blo     diagnostic_v2_consume_done
    mov     r7, #2              /* twelve JSON failures exhausted */
    bl      diagnostic_write_sidecar_v2

diagnostic_v2_consume_done:
    pop     {r0-r9, ip, lr}
    add     r4, sl, #0x2A0      /* replay displaced instruction */
    bx      lr

diagnostic_v2_prefix:
    .asciz  "FPJ2;reason="
diagnostic_v2_kind:
    .asciz  ";kind="
diagnostic_v2_volume:
    .asciz  ";volume="
diagnostic_v2_attempts:
    .asciz  ";attempts="
diagnostic_v2_phase:
    .asciz  ";phase="
diagnostic_v2_elapsed:
    .asciz  ";elapsed_us="
diagnostic_v2_lifecycle:
    .asciz  ";lifecycle="
diagnostic_v2_stream:
    .asciz  ";stream="
    .balign 4

/* Inputs: r6 attempts, r7 reason, r8 kind, r9 volume. */
diagnostic_write_sidecar_v2:
    push    {r3-r9, r11, ip, lr}
    adr     r11, diagnostic_v2_prefix

    movw    r4, #0xA000
    movt    r4, #1
    add     r4, sl, r4           /* idle state+0x1A000 text buffer */
    mov     r5, r4

    mov     r0, r11
    mov     r1, r5
    bl      diagnostic_copy_v2
    mov     r5, r0
    mov     r0, r7
    mov     r1, r5
    bl      diagnostic_uint_v2
    mov     r5, r0

    add     r0, r11, #(diagnostic_v2_kind - diagnostic_v2_prefix)
    mov     r1, r5
    bl      diagnostic_copy_v2
    mov     r5, r0
    mov     r0, r8
    mov     r1, r5
    bl      diagnostic_uint_v2
    mov     r5, r0

    add     r0, r11, #(diagnostic_v2_volume - diagnostic_v2_prefix)
    mov     r1, r5
    bl      diagnostic_copy_v2
    mov     r5, r0
    mov     r0, r9
    mov     r1, r5
    bl      diagnostic_uint_v2
    mov     r5, r0

    add     r0, r11, #(diagnostic_v2_attempts - diagnostic_v2_prefix)
    mov     r1, r5
    bl      diagnostic_copy_v2
    mov     r5, r0
    mov     r0, r6
    mov     r1, r5
    bl      diagnostic_uint_v2
    mov     r5, r0

    add     r0, r11, #(diagnostic_v2_phase - diagnostic_v2_prefix)
    mov     r1, r5
    bl      diagnostic_copy_v2
    mov     r5, r0
    ldr     r0, [sl, #J_PHASE]
    mov     r1, r5
    bl      diagnostic_uint_v2
    mov     r5, r0

    add     r0, r11, #(diagnostic_v2_elapsed - diagnostic_v2_prefix)
    mov     r1, r5
    bl      diagnostic_copy_v2
    mov     r5, r0
    ldr     r0, [sl, #J_ELAPSED]
    mov     r1, r5
    bl      diagnostic_uint_v2
    mov     r5, r0

    add     r0, r11, #(diagnostic_v2_lifecycle - diagnostic_v2_prefix)
    mov     r1, r5
    bl      diagnostic_copy_v2
    mov     r5, r0
    ldr     r0, [sl, #J_LIFECYCLE]
    mov     r1, r5
    bl      diagnostic_uint_v2
    mov     r5, r0

    add     r0, r11, #(diagnostic_v2_stream - diagnostic_v2_prefix)
    mov     r1, r5
    bl      diagnostic_copy_v2
    mov     r5, r0
    ldr     r0, [sl, #J_STREAM]
    mov     r1, r5
    bl      diagnostic_uint_v2
    mov     r5, r0
    mov     r0, #10
    strb    r0, [r5], #1

    /* c48 built the current basename at state+0x180. */
    add     r3, sl, #0x180
    movw    r0, #0x646A         /* "jd" */
    movt    r0, #0x0067         /* "g\0" */
    str     r0, [r3, #0x1A]

    cmp     r9, #1
    beq     diagnostic_v2_open
    cmp     r9, #5
    bne     diagnostic_v2_write_done

diagnostic_v2_open:
    add     r0, sl, #0x800
    mov     r1, r9              /* required media volume (1 or 5) */
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
    bne     diagnostic_v2_write

    add     r0, sl, #0x800
    mov     r1, #2
    movw    ip, #0x5ED0
    movt    ip, #0xC036
    blx     ip
    b       diagnostic_v2_write_done

diagnostic_v2_write:
    add     r0, sl, #0x800
    mov     r1, r4
    sub     r2, r5, r4
    movw    ip, #0x60E8
    movt    ip, #0xC036
    blx     ip

    add     r0, sl, #0x800
    movw    ip, #0x6020
    movt    ip, #0xC036
    blx     ip

    add     r0, sl, #0x800
    mov     r1, #2
    movw    ip, #0x5ED0
    movt    ip, #0xC036
    blx     ip

diagnostic_v2_write_done:
    /* Restore the path invariant before returning to the old retry/early-exit
     * logic.  The production writer uses the same little-endian "json\0". */
    add     r3, sl, #0x180
    movw    r0, #0x736A         /* "js" */
    strh    r0, [r3, #0x1A]
    movw    r0, #0x6E6F         /* "on" */
    strh    r0, [r3, #0x1C]
    mov     r0, #0
    strb    r0, [r3, #0x1E]
    pop     {r3-r9, r11, ip, pc}

diagnostic_copy_v2:
    .global diagnostic_copy_tail_v2
diagnostic_copy_tail_v2:
    b       .                   /* builder patches to old body+0x173C */

diagnostic_uint_v2:
    .global diagnostic_uint_tail_v2
diagnostic_uint_tail_v2:
    b       .                   /* builder patches to old body+0x14C8 */
