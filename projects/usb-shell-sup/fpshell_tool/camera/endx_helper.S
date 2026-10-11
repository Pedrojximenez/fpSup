/* endx_helper.S — EndTransfer(9) cleanup for EP84 after a raw push (fixes the stall).
 * Injected into the cave, called via `call`. r0=STATE (unused). AAPCS-preserves r4-r11. */
.syntax unified
.arm
.text
.global _start
_start:
    push  {r4-r11, lr}
    mov   r0, #9              @ EP84 IN (ctx4<<1|IN), same as StartTransfer(9)
    movw  r1, #0x6D49         @ FN_ENDX = 0xC01E6D49 (thumb)
    movt  r1, #0xC01E
    blx   r1                  @ FUN_c01e6d48(9) — clean EndTransfer
    pop   {r4-r11, lr}
    bx    lr
