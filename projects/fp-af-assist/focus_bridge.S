.syntax unified
.arm
.text

/* fp 5.02, shell TASK context only. No arbitrary function/address input.
 * P: request magic, nonce, operation, target, expected position;
 * +0x18 completed nonce; +0x1c execution state; +0x20 return register;
 * +0x24 initialized event-reference output (three words).
 * Clearing request magic BEFORE calling makes an accidental second echo inert.
 * State 2 means wrapper returned, NOT that a physical movement completed.
 */
.equ P, 0xC072F700
.global entry
entry:
    push {r4, r5, r6, r7, r8, lr}
    ldr r4, =P
    ldr r0, [r4]
    ldr r1, =0x31424641
    cmp r0, r1
    bne exit
    mov r0, #0
    str r0, [r4]             /* consume single-use request */
    ldr r5, [r4, #4]
    str r5, [r4, #0x18]
    mov r0, #1
    str r0, [r4, #0x1c]
    ldr r6, [r4, #8]
    cmp r6, #8
    bhi reject
    cmp r6, #7
    bhs motion
    cmp r6, #5
    blo getter
    ldr r0, =0xC3476458  /* native-L focus object's event wrapper */
    cmp r6, #6
    ldreq r0, =0xC347E02C /* lens synchronization ready event wrapper */
    bl flags
    b returned
getter:
    adr r7, getters
    ldr ip, [r7, r6, lsl #2]
    blx ip
    b returned
motion:
    /* Both directions repeat the capture and driver gates in camera context.
     * Host independently verifies native-L identity, settings, radius, bounds.
     * These checks are NOT an atomic exclusion against physical user input.
     */
    ldr r0, =0xC303384C
    ldr r1, [r0, #0x7c] /* exposing/saving/processing bytes, all four */
    cmp r1, #0
    ldrbeq r1, [r0, #0x84] /* actual MovieRecording */
    cmpeq r1, #0
    ldreq r1, [r0, #0x220] /* shutter sequence, not camera mode */
    cmpeq r1, #0
    bne reject
    ldr ip, =0xC035F560
    blx ip
    cmp r0, #1
    bne reject
    ldr ip, =0xC0362558
    blx ip
    cmp r0, #0
    bne reject
    ldr r0, =0xC3476458
    bl flags
    cmp r0, #1
    bne reject
    ldr r0, [r4, #0x2c]
    cmp r6, #8
    beq abort_check
    cmp r0, #3
    bne reject
    ldr r7, [r4, #0xc]
    ldr r0, =0xC3476418
    ldr r0, [r0]
    ldr r1, [r4, #0x10]
    cmp r0, r1
    bne reject
    subs r0, r7, r0
    bvs reject             /* signed subtraction overflow is not a small step */
    beq reject
    rsbmi r0, r0, #0
    cmp r0, #100
    bhi reject
    ldr ip, =0xC02DFFB0
    blx ip
    cmp r7, r0
    blt reject
    ldr ip, =0xC02DFFD0
    blx ip
    cmp r7, r0
    bgt reject
    b sync_check
abort_check:
    cmp r0, #3
    moveq r0, #0       /* already complete; no abort request */
    beq returned
sync_check:
    ldr r0, =0xC347E02C
    bl flags
    cmp r0, #1
    bne reject
    ldr r0, [r4, #0x2c]
    tst r0, #1
    beq reject
    cmp r6, #8
    ldreq ip, =0xC035FEE8
    ldrne ip, =0xC035FFC0
    movne r0, r7
    moveq r0, #0
    mov r1, #0
    mov r2, #0
    blx ip
returned:
    str r0, [r4, #0x20]
    mov r0, #2
    str r0, [r4, #0x1c]
    b exit
reject:
    mov r0, #3
    str r0, [r4, #0x1c]
exit:
    pop {r4, r5, r6, r7, r8, pc}
flags:
    push {r8, lr}
    mov r2, #0
    str r2, [r4, #0x24]
    str r2, [r4, #0x28]
    str r2, [r4, #0x2c]
    add r1, r4, #0x24
    ldr ip, =0xC036D888
    blx ip
    pop {r8, pc}
.balign 4
getters:
    .word 0xC035FD48 /* cached position */
    .word 0xC02DFFB0 /* minimum including native allowance */
    .word 0xC02DFFD0 /* maximum including native allowance */
    .word 0xC035F560 /* initialized lens-controller state == 2 */
    .word 0xC0362558 /* property predicate, NOT an AF-busy test */
.ltorg
