/* r33 diagnostic trailer for the existing r32 GCSV final flush.
 *
 * The trailer deliberately contains no comma, so it is one flexible-CSV
 * field.  Gyroflow telemetry-parser's GCSV reader skips every one-field row
 * before header or numeric parsing.  No file is opened and no extra media call
 * is made: the trailer rides in the already pending command-3 final flush.
 */
    .syntax unified
    .arm

    .section .text

    /* Exact end of the r32 PGEN body. */
    .org 0x1DD4

    .global diagnostic_append_and_flush
diagnostic_append_and_flush:
    push    {r4, lr}

    adr     r0, diagnostic_prefix
    mov     r1, r5
    .global diagnostic_copy_prefix
diagnostic_copy_prefix:
    bl      .                       /* builder -> existing strcpy at 0x173C */
    mov     r5, r0

    ldr     r0, [sl, #0x14]         /* original cumulative dropped samples */
    mov     r1, r5
    .global diagnostic_format_drop
diagnostic_format_drop:
    bl      .                       /* builder -> existing put_uint at 0x14C8 */
    mov     r5, r0

    adr     r0, diagnostic_middle
    mov     r1, r5
    .global diagnostic_copy_middle
diagnostic_copy_middle:
    bl      .                       /* builder -> existing strcpy at 0x173C */
    mov     r5, r0

    ldr     r0, [sl, #0x1E8]        /* max relevant block-anchor clock delta */
    mov     r1, r5
    .global diagnostic_format_delay
diagnostic_format_delay:
    bl      .                       /* builder -> existing put_uint at 0x14C8 */
    mov     r5, r0

    mov     r0, #10
    strb    r0, [r5], #1

    /* Return the exact success/failure value of r32's existing final flush. */
    .global diagnostic_final_flush
diagnostic_final_flush:
    bl      .                       /* builder -> existing flush at 0x1C04 */
    pop     {r4, pc}

diagnostic_prefix:
    .asciz  "#FPD1;drop_samples="
diagnostic_middle:
    .asciz  ";max_block_head_tick_us="
    .balign 4
