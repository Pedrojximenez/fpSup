.syntax unified
.arm
.text
/* Copy a window of memory into a host-readable scratch buffer.
 *
 * The host's own mem read only answers for a limited address range -- outside it the
 * worker echoes the command string back instead of the memory, which reads as
 * plausible-looking data and is how a couple of earlier "dumps" came out as ASCII.
 * Camera-side code has no such restriction, so anything we want to look at has to be
 * copied into the readable window first.
 *
 * ARG: [0]=src [4]=length (clamped to 0x400)
 * OUT: the bytes, at SCRATCH
 */
.equ ARG,     0xC072F400
.equ SCRATCH, 0xC072FC00

.macro la reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global cave_entry
cave_entry:
    push    {r4, lr}
    la      r4, ARG
    ldr     r0, [r4]
    ldr     r1, [r4, #4]
    movw    r2, #0x400
    cmp     r1, r2
    movhi   r1, r2
    la      r2, SCRATCH
1:  cmp     r1, #0
    beq     2f
    ldrb    r3, [r0], #1
    strb    r3, [r2], #1
    sub     r1, r1, #1
    b       1b
2:  mov     r0, #0
    pop     {r4, pc}
