.syntax unified
.arm
.text
/* Bounded camera-side UI pointer walk. Leaf echo handler; no firmware calls.
 * P is the maintained putfile.parm claim; result occupies +0x40..+0x70.
 * A valid flag is published only after rechecking the app's screen pointer.
 * This observes the active screen name, not completed LCD scanout. */
#ifndef P
#error P must name the owned parameter claim
#endif
.macro LDA reg, value
    movw \reg, #:lower16:\value
    movt \reg, #:upper16:\value
.endm
.macro READABLE reg
    lsr ip, \reg, #24
    cmp ip, #0xc0
    blo 1f
    cmp ip, #0xc8
    blo 2f
1:  lsr ip, \reg, #28
    cmp ip, #4
    beq 2f
    cmp ip, #5
    bne invalid
2:
.endm
.global entry
entry:
    LDA r0, P + 0x40
    mov r3, #0
    str r3, [r0, #12]
    LDA r1, 0xC37B7048
    ldr r1, [r1]
    READABLE r1
    tst r1, #3
    bne invalid
    str r1, [r0]
    ldr r1, [r1, #0x84c]
    READABLE r1
    tst r1, #3
    bne invalid
    str r1, [r0, #4]
    ldr r2, [r1, #8]
    READABLE r2
    str r2, [r0, #8]
    add r1, r0, #16
    mov r3, #32
copy_name:
    ldrb ip, [r2], #1
    strb ip, [r1], #1
    subs r3, r3, #1
    bne copy_name
    ldr r1, [r0]
    ldr r2, [r1, #0x84c]
    ldr r3, [r0, #4]
    cmp r2, r3
    bne invalid
    LDA r1, 0xC37B7048
    ldr r1, [r1]
    ldr r2, [r0]
    cmp r1, r2
    bne invalid
    mov r3, #1
    str r3, [r0, #12]
invalid:
    mov r0, #0
    bx lr
