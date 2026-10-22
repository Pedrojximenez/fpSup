/* endx_inline.S — EndTransfer(9) then jump to worker loop_yield (0xC072E860).
 * Patched into do_rawpush: replace `b loop_yield` @0xC072E60C with `b endx_inline`. */
.syntax unified
.arm
.text
.global _start
_start:
    push  {r0-r3, lr}
    mov   r0, #9
    movw  r1, #0x6D49
    movt  r1, #0xC01E          @ FN_ENDX 0xC01E6D49
    blx   r1
    pop   {r0-r3, lr}
    ldr   pc, .Lyield
.align 2
.Lyield: .word 0xC072E860
