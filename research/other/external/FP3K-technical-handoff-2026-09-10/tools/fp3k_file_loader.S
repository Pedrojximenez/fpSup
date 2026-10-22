/* Bounded SD loader for the existing, checksummed F1 payload.
 * No sleep, task, allocation or UI drawing. NOT yet camera validated.
 * File object is 12 bytes (stock destructor supplies size 0xC).
 */
.syntax unified
.arm
.text
.global loader_entry
.equ LOADER_BASE, 0xC072E264
.equ PAYLOAD, 0xC072DE64
.equ LENGTH, 636
.equ STATUS, 0xC072E800
.macro addr reg,value
 movw \reg, #:lower16:\value
 movt \reg, #:upper16:\value
.endm
.macro call target
9: .word 0xEB000000 | (((\target - (LOADER_BASE + (9b-loader_entry)) - 8) >> 2) & 0xFFFFFF)
.endm
loader_entry:
 push {r4-r8,lr}
 sub sp,sp,#16
 addr r0,0xC0BAC2F8
 addr r1,0xC03D99A0
 str r1,[r0]                 /* Release echo before any filesystem call. */
 addr r8,STATUS
 addr r0,0x324C334B           /* K3L2 */
 str r0,[r8]
 mov r0,#0
 str r0,[r8,#8]
 str r0,[r8,#12]
 mov r0,#1
 str r0,[r8,#4]
 /* Match upstream media-manager initialization, but pin the file to SD. */
 call 0xC0444658
 mov r1,#0
 call 0xC0444698
 mov r0,sp
 mov r1,#1
 call 0xC0365E90
 mov r0,sp
 adr r1,path
 mov r2,#1
 call 0xC0365FB0
 mov r4,#0x21
 cmp r0,#0
 beq cleanup
 mov r0,#0
 str r0,[sp,#12]
 mov r0,sp
 addr r1,PAYLOAD
 movw r2,#LENGTH
 add r3,sp,#12
 call 0xC0366060
 ldr r5,[sp,#12]
 str r5,[r8,#8]
 mov r4,#0x22
 cmp r5,#LENGTH
 bne cleanup
 addr r0,PAYLOAD
 mov r1,#0
 mov r2,#(LENGTH/4)
1: ldr r3,[r0],#4
 add r1,r1,r3
 subs r2,r2,#1
 bne 1b
 mov r4,#0x23
 cmp r1,#0
 moveq r4,#0
cleanup:
 mov r0,sp
 mov r1,#2
 call 0xC0365ED0          /* Native destructor also closes the handle. */
 cmp r4,#0
 bne failed
 call 0xC000E91C
 addr r0,PAYLOAD
 blx r0                  /* Existing payload performs idle/table guards. */
 b done
failed:
 str r4,[r8,#4]
done:
 add sp,sp,#16
 pop {r4-r8,pc}
path:
 .byte 0x5c
 .asciz "FP3K.BIN"
 .align 2
loader_end:
