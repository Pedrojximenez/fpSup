.syntax unified
.arm
.text
/* Scan a memory range for a 32-bit value, report the hits.
 * ARG: [0]=needle [4]=lo [8]=hi [12]=stride(1 or 4)
 * OUT: [0]=count, then up to 24 hit addresses.
 */
.equ ARG, 0xC072F400
.equ OUT, 0xC072F440

.macro la reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global cave_entry
cave_entry:
    push    {r4-r8, lr}
    la      r8, ARG
    ldr     r4, [r8]                 @ needle
    ldr     r5, [r8, #4]             @ lo
    ldr     r6, [r8, #8]             @ hi
    ldr     r7, [r8, #12]            @ stride
    la      r8, OUT
    mov     r0, #0
    str     r0, [r8]
    mov     r3, #0                   @ count
1:  cmp     r5, r6
    bhs     9f
    cmp     r3, #24
    bhs     9f
    ldr     r0, [r5]
    cmp     r0, r4
    bne     2f
    add     r1, r8, #4
    str     r5, [r1, r3, lsl #2]
    add     r3, r3, #1
2:  add     r5, r5, r7
    b       1b
9:  str     r3, [r8]
    mov     r0, r3
    pop     {r4-r8, pc}
