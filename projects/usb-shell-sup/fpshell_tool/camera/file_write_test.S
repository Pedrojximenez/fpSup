.syntax unified
.arm
.text
/* Parametrised file write, so the open mode can be settled by experiment.
 * ARG: [0]=path [4]=data [8]=len [12]=mode      OUT: [0]=open ret [4]=write ret
 */
.equ ARG,     0xC072F400
.equ OUT,     0xC072F440
.equ FILEOBJ, 0xC072F480

.macro la reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global cave_entry
cave_entry:
    push    {r4-r8, lr}
    la      r4, ARG
    ldr     r5, [r4]
    ldr     r6, [r4, #4]
    ldr     r7, [r4, #8]
    ldr     r8, [r4, #12]
    la      r4, OUT
    mov     r0, #0
    str     r0, [r4]
    str     r0, [r4, #4]

    la      ip, 0xC0444658
    blx     ip
    mov     r1, #0
    la      ip, 0xC0444698
    blx     ip
    mov     r1, r0
    la      r0, FILEOBJ
    la      ip, 0xC0365E90
    blx     ip

    la      r0, FILEOBJ
    mov     r1, r5
    mov     r2, r8
    la      ip, 0xC0365FB0
    blx     ip
    la      r4, OUT
    str     r0, [r4]

    la      r0, FILEOBJ
    mov     r1, r6
    mov     r2, r7
    la      ip, 0xC03660E8
    blx     ip
    la      r4, OUT
    str     r0, [r4, #4]

    la      r0, FILEOBJ
    la      ip, 0xC0366020
    blx     ip
    la      r0, FILEOBJ
    mov     r1, #2
    la      ip, 0xC0365ED0
    blx     ip
    mov     r0, #0
    pop     {r4-r8, pc}
