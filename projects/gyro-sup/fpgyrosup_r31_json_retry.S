/* r31 paced, non-dropping JSON retry tail.
 *
 * The existing PGEN queue retries a failed lens-profile JSON build twelve
 * times back-to-back.  It then consumes the event as though it had completed,
 * which releases the recording/power transaction lock without a JSON file.
 *
 * r31 redirects that failure edge here.  Tear down the temporary lens-query
 * session exactly as the normal PGEN return path does, yield for 50 ms, and
 * return with the event still pending.  The writer's next cooperative pass
 * retries it.  Success continues through the original path unchanged.
 */
    .syntax unified
    .arm

    .section .text

    /* Exact end of the r29/r30 PGEN body. */
    .org 0x1D4C
    .global json_retry_wait
json_retry_wait:
    cmp     r7, #0
    beq     1f
    mov     r0, #0

    /* Patched by the builder to BL the existing lens-session helper at 0x284. */
    .global json_retry_cleanup_call
json_retry_cleanup_call:
    bl      .
    mov     r7, #0

1:  mov     r0, #50
    movw    ip, #0x05D8
    movt    ip, #0xC037
    blx     ip

    /* Patched by the builder to B the existing common pop at 0x558. */
    .global json_retry_return
json_retry_return:
    b       .
