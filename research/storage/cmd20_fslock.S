.syntax unified
.arm
.text
/* cmd20_fslock -- send one CMD20 (Speed Class Control) the way the firmware does.
 *
 * Called through callfn:  r0 = address of the 32-bit CMD20 argument,
 *                         r1 = 0 or an 11-word buffer: after the ioctl, still under
 *                              the lock, the driver's UHS-II command/response block
 *                              0xC381B480..+0x2C is copied there.
 * Returns what the SD ioctl returned (1 = success, as C0649DB8 tests).
 *
 * Mirrors stock C0649DB8: the ioctl runs with the FS global lock held, so no
 * other card I/O can be in flight on the controller.
 *   lock    C01F8E8C(lock=[0xC37D0644], 1, -1)   ARM
 *   ioctl   C01EB940(dev=0xE, 0x198, &arg)       THUMB -> call 0xC01EB941
 *   unlock  C01F8CDC(lock, 1)                    ARM
 * 2026-10-14: an even address for C01EB940 froze the shell (ARM-state jump
 * into Thumb code).  The +1 below is the fix; do not remove it.
 */
.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global entry
entry:
    push    {r4, r5, r6, r7, r8, lr}  /* six registers: sp stays 8-aligned */
    mov     r5, r0                    /* argument pointer */
    mov     r7, r1                    /* response copy, may be 0 */
    LDA     r4, 0xC37D0644            /* &fs_lock_id */

    ldr     r0, [r4]
    mov     r1, #1
    mvn     r2, #0
    LDA     r3, 0xC01F8E8C
    blx     r3

    mov     r0, #0xE
    movw    r1, #0x198
    mov     r2, r5
    LDA     r3, 0xC01EB941            /* Thumb */
    blx     r3
    mov     r6, r0

    cmp     r7, #0
    beq     1f
    LDA     r8, 0xC381B480
    mov     r2, #0
0:  ldr     r3, [r8, r2]
    str     r3, [r7, r2]
    add     r2, r2, #4
    cmp     r2, #0x2C
    blt     0b
1:
    ldr     r0, [r4]
    mov     r1, #1
    LDA     r3, 0xC01F8CDC
    blx     r3

    mov     r0, r6
    pop     {r4, r5, r6, r7, r8, pc}
