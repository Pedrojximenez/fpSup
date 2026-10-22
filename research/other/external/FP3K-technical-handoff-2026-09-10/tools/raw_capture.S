.syntax unified
.arm
.text
.global capture_entry
.equ LOAD_BASE, 0xC072DE64
.equ NRECORDS, 120
.equ RECORD_SIZE, 0x340
.equ TOTAL_SIZE, 64 + NRECORDS * RECORD_SIZE
.macro addr reg, value
    movw \reg, #:lower16:\value
    movt \reg, #:upper16:\value
.endm
.macro self reg, label
    ldr \reg, 90f
    b 91f
90: .word LOAD_BASE + (\label - _capture_start)
91:
.endm
.macro call target
    addr ip, \target
    blx ip
.endm

capture_entry:
_capture_start:
    push {r4-r11, lr}
    sub sp, sp, #68
    mov r4, r0
    /* Restore the borrowed shell handler before any wait or file operation. */
    addr r0, 0xC0BAC2F8
    addr r1, 0xC03D99A0
    str r1, [r0]
    /* Additive integrity check of this entire assembled blob. This catches
     * body-loading errors; it cannot prove a corrupted bootstrap ran safely. */
    addr r0, LOAD_BASE
    movw r2, #:lower16:((payload_end-_capture_start)/4)
    mov r1, #0
1:  ldr r3, [r0], #4
    add r1, r1, r3
    subs r2, r2, #1
    bne 1b
    cmp r1, #0
    bne failure

    addr r0, 0xC3757A7C
    ldr r5, [r0]
    ldr r6, [r0, #4]
    tst r5, #3
    bne failure
    addr r1, 0x40000000
    cmp r5, r1
    blo failure
    addr r1, 0x4FFE0000
    cmp r5, r1
    bhi failure
    cmp r6, #0x20000
    blo failure
    mov r0, #0
    mov r1, #0
2:  str r0, [r5, r1]
    add r1, r1, #4
    cmp r1, #64
    blo 2b
    addr r0, 0x33525046       /* FPR3 */
    str r0, [r5]
    mov r0, #3
    str r0, [r5, #4]
    mov r0, #RECORD_SIZE
    str r0, [r5, #8]
    str r5, [r5, #0x10]
    str r6, [r5, #0x14]
    mov r0, #250
    str r0, [r5, #0x18]
    addr r0, TOTAL_SIZE
    str r0, [r5, #0x20]
    add r6, r5, #64
    mov r7, #0
sample_loop:
    mov r0, r6
    bl raw_snapshot
    str r7, [r6]
    add r7, r7, #1
    str r7, [r5, #12]
    add r6, r6, #RECORD_SIZE
    mov r0, #250
    call 0xC0421770
    cmp r7, #NRECORDS
    blo sample_loop

    /* Stop sampling after ~30s. Save only after 3s continuously idle, with
     * both movie flags and both native file-lifecycle signals clear.
     * Give up after ~60s additional wait rather than saving during a take.
     * User must not start a second take while waiting for completion.
     */
    mov r7, #0
    mov r8, #240
idle_loop:
    bl native_busy
    cmp r0, #0
    moveq r0, #1
    addeq r7, r7, r0
    movne r7, #0
    cmp r7, #13
    bhs save_result
    mov r0, #250
    call 0xC0421770
    subs r8, r8, #1
    bne idle_loop
    mov r0, #2
    str r0, [r5, #0x1c]
    b failure
save_result:
    mov r0, #1
    str r0, [r5, #0x1c]
    /* argv = {"save", "\\FPD003\\STATE.BIN", "0xBASE,,99904"}. */
    self r0, save_word
    str r0, [sp]
    self r0, save_path
    str r0, [sp, #4]
    add r0, sp, #16
    str r0, [sp, #8]
    mov r1, #48
    strb r1, [r0], #1
    mov r1, #120
    strb r1, [r0], #1
    mov r1, r5
    bl hex_word
    self r1, range_suffix
3:  ldrb r2, [r1], #1
    strb r2, [r0], #1
    cmp r2, #0
    bne 3b
    mov r0, r4
    mov r1, #3
    mov r2, sp
    call 0xC03FA0E0
    b done
failure:
    mov r0, #0
done:
    add sp, sp, #68
    pop {r4-r11, pc}

native_busy:
    addr r1, 0xC347E08F
    ldrb r0, [r1]
    addr r1, 0xC3476609
    ldrb r2, [r1]
    orr r0, r0, r2
    addr r1, 0xC358E140
    ldr r2, [r1]
    orr r0, r0, r2
    addr r1, 0xC35A952C
    ldrb r2, [r1]
    orr r0, r0, r2
    addr r1, 0xC343B58C
    ldr r2, [r1]
    cmp r2, #8
    orrne r0, r0, #1
    bx lr

hex_word:
    mov r2, #8
4:  mov r3, r1, lsr #28
    cmp r3, #10
    addlo r3, r3, #48
    addhs r3, r3, #55
    strb r3, [r0], #1
    lsl r1, r1, #4
    subs r2, r2, #1
    bne 4b
    bx lr

save_word: .asciz "save"
save_path: .asciz "\\FPD003\\STATE.BIN"
range_suffix: .asciz ",,99904"
.balign 4
.include "tools/raw_snapshot.S"
.balign 4
.global checksum_word
checksum_word: .word 0
payload_end:
