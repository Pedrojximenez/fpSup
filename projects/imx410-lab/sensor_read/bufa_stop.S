.syntax unified
.arm
.text
/* bufa_stop -- stop BUFA0 between frames, the way the firmware does (FUN_c031d3e8 at C031D434..C031D488):
 * tk_clr_flg(flag, ~1), tk_wai_flg(flag, 1, TWF_ORW, &out, tmo) for the next BUFA0 completion, then at once
 * c06316b8(100) (clears 0x30002060 bit 0, 0x30182000 = 0).  Stopping at a random moment cut a frame's DMA in
 * half about once per 100 stops and froze the whole camera (freeze_iso group B, 2026-10-23).  The wait and the
 * stop must be one call: a USB round trip (~30 ms) is longer than the blanking gap.
 *   r0 = flag id ([0xC2F14C98], set by the BUFA0 ISR)      r1 = timeout ms
 * Returns the tk_wai_flg result: 0 = stopped right after a completion; nonzero = no frame within the timeout
 * (no DMA in flight), stopped anyway.
 */
    .global bufa_stop
bufa_stop:
    push    {r4, r5, r6, lr}
    mov     r6, sp
    bic     sp, sp, #7
    sub     sp, sp, #8
    mov     r4, r0
    mov     r5, r1
    mvn     r1, #1
    ldr     ip, =0xC00169C8             @ tk_clr_flg(id, ~1)
    blx     ip
    str     r5, [sp]                    @ 5th argument: timeout
    add     r3, sp, #4                  @ &out
    mov     r2, #1                      @ TWF_ORW, as the firmware
    mov     r1, #1
    mov     r0, r4
    ldr     ip, =0xC0016C08             @ tk_wai_flg
    blx     ip
    mov     r4, r0
    mov     r0, #100
    ldr     ip, =0xC06316B9             @ c06316b8(100), Thumb
    blx     ip
    mov     r0, r4
    mov     sp, r6
    pop     {r4, r5, r6, pc}
    .ltorg
