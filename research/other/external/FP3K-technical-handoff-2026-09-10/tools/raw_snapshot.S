.syntax unified
.arm
.text
.global raw_snapshot

/* Offline development component, NOT an AutoRun or deployable firmware.
 * r0: caller-owned 0x340-byte output, word aligned.
 * No allocation, filesystem, sleep, MMIO or firmware calls.
 * flags: 1=profile copied, 2=source/parameter pointer changed, 4=mode changed.
 * Caller must ensure destination allocation and scheduling.
 */
.macro address reg, value
    movw \reg, #:lower16:\value
    movt \reg, #:upper16:\value
.endm

raw_snapshot:
    push {r4-r10, lr}
    mov r4, r0
    mov r1, #0
    mov r2, #0
1:  str r2, [r4, r1]
    add r1, r1, #4
    cmp r1, #0x340
    blo 1b
    address r5, 0xC343B588
    ldr r6, [r5, #4]
    str r6, [r4, #4]
    address r7, 0xC375D840
    ldr r8, [r7, #8]
    str r8, [r4, #12]
    mov r10, #0

    /* Fixed RAM regions. */
    mov r0, r5
    add r1, r4, #0x20
    mov r2, #0x100
    bl copy_words
    address r0, 0xC31F869C
    add r1, r4, #0x120
    mov r2, #0x80
    bl copy_words
    address r0, 0xC343A950
    add r1, r4, #0x310
    mov r2, #0x30
    bl copy_words

    /* Only dereference a complete, aligned object in these RAM windows.
     * Unsupported pointers yield an incomplete record instead of a read.
     */
    tst r8, #3
    bne finish
    address r0, 0x40000000
    cmp r8, r0
    blo finish
    address r0, 0x4FFFFE94
    cmp r8, r0
    bls pointer_ok
    address r0, 0xC0000000
    cmp r8, r0
    blo finish
    address r0, 0xC3FFFE94
    cmp r8, r0
    bhi finish
pointer_ok:
    ldr r9, [r8, #4]
    str r9, [r4, #0x14]
    add r0, r8, #0x5c
    cmp r9, r0
    bne finish
    mov r0, r8
    add r1, r4, #0x1a0
    mov r2, #0x60
    bl copy_words
    mov r0, r9
    add r1, r4, #0x200
    movw r2, #0x10c
    bl copy_words
    orr r10, r10, #1
    ldr r0, [r8, #4]
    cmp r0, r9
    orrne r10, r10, #2
finish:
    ldr r0, [r7, #8]
    str r0, [r4, #0x10]
    cmp r0, r8
    orrne r10, r10, #2
    ldr r0, [r5, #4]
    str r0, [r4, #8]
    cmp r0, r6
    orrne r10, r10, #4
    str r10, [r4, #0x18]
    /* Store both published movie flags plus selector, without interpreting
     * either as proof that native file finalization is complete. */
    address r0, 0xC347D1D4
    ldr r1, [r0]
    str r1, [r4, #0x1c]
    address r0, 0xC347E08F
    ldrb r1, [r0]
    strb r1, [r4, #0x30c]
    address r0, 0xC3476609
    ldrb r1, [r0]
    strb r1, [r4, #0x30d]
    mov r0, r10
    pop {r4-r10, pc}

copy_words:
    ldr r3, [r0], #4
    str r3, [r1], #4
    subs r2, r2, #4
    bne copy_words
    bx lr
