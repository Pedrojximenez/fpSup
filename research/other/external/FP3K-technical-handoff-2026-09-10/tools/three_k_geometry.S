.syntax unified
.arm
.text
.global patch_entry
.equ LOAD_BASE, 0xC072DE64
.equ STATUS, 0xC072E800
.macro addr reg, value
    movw \reg, #:lower16:\value
    movt \reg, #:upper16:\value
.endm
patch_entry:
    push {r4-r8, lr}
    addr r0, 0xC0BAC2F8
    addr r1, 0xC03D99A0
    str r1, [r0]                 /* Return borrowed echo command immediately. */
    addr r8, STATUS
    addr r0, 0x3147334B         /* K3G1 */
    str r0, [r8]
    mov r0, #1
    str r0, [r8, #4]
    mov r0, #0
    str r0, [r8, #8]
    str r0, [r8, #12]
    addr r0, LOAD_BASE
    mov r1, #0
    movw r2, #:lower16:((payload_end-patch_entry)/4)
1:  ldr r3, [r0], #4
    add r1, r1, r3
    subs r2, r2, #1
    bne 1b
    cmp r1, #0
    movne r0, #2
    bne done
    bl idle_check
    cmp r0, #0
    moveq r0, #3
    beq done
    adr r4, patch_table
    mov r5, #6
2:  ldm r4!, {r0-r2}
    ldr r3, [r0]
    cmp r3, r1
    strne r0, [r8, #8]
    strne r3, [r8, #12]
    movne r0, #4
    bne done
    subs r5, r5, #1
    bne 2b
    bl idle_check
    cmp r0, #0
    moveq r0, #3
    beq done
    adr r4, patch_table
    mov r5, #6
3:  ldm r4!, {r0-r2}
    str r2, [r0]
    subs r5, r5, #1
    bne 3b
    dsb sy
verify_readback:
    adr r4, patch_table
    mov r5, #6
4:  ldm r4!, {r0-r2}
    ldr r3, [r0]
    cmp r3, r2
    bne rollback
    subs r5, r5, #1
    bne 4b
    mov r0, #0x10
    b done
rollback:
    str r0, [r8, #8]
    str r3, [r8, #12]
    adr r4, patch_table
    mov r5, #6
5:  ldm r4!, {r0-r2}
    str r1, [r0]
    subs r5, r5, #1
    bne 5b
    dsb sy
    mov r0, #5
done:
    str r0, [r8, #4]
    pop {r4-r8, pc}
idle_check:
    addr r0, 0xC343B58C
    ldr r1, [r0]
    cmp r1, #8
    bne busy
    addr r0, 0xC3476609
    ldrb r1, [r0]
    cmp r1, #0
    bne busy
    addr r0, 0xC347E08F
    ldrb r1, [r0]
    cmp r1, #0
    bne busy
    addr r0, 0xC358E140
    ldr r1, [r0]
    cmp r1, #0
    bne busy
    addr r0, 0xC35A952C
    ldrb r1, [r0]
    cmp r1, #0
    bne busy
    mov r0, #1
    bx lr
busy:
    mov r0, #0
    bx lr
.balign 4
patch_table:
    .word 0xC0BE3F54, 3856, 3032
    .word 0xC0BE441C, 2170, 2020
    .word 0xC0BE2C34, 3840, 3000
    .word 0xC0BE30FC, 2160, 2000
    .word 0xC0BE35C4, 3856, 3032
    .word 0xC0BE3A8C, 2170, 2020
checksum_word: .word 0
payload_end:
