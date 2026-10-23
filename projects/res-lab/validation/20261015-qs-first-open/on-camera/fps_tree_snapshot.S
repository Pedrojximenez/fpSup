.syntax unified
.arm
.text
/* Read-only snapshot of the active cached root and target object's component
 * descriptors. DFS depth <=16, <=2048 nodes, <=64 children, <=12 components.
 * No native calls. P is a 256-byte owned claim; only P[0..224) is written. */
.macro LDA reg, value
 movw \reg, #:lower16:\value
 movt \reg, #:upper16:\value
.endm
.macro PTR reg
 tst \reg, #3
 bne done
 lsr ip, \reg, #24
 cmp ip, #0xc0
 blo 1f
 cmp ip, #0xc8
 blo 2f
1: lsr ip, \reg, #28
 cmp ip, #4
 beq 2f
 cmp ip, #5
 bne done
2:
.endm
.global entry
entry:
 push {r4-r11, lr}
 sub sp, sp, #132
 LDA r4, P
 mov r0, #0
 str r0, [r4]
 LDA r5, 0xC37B7048
 ldr r5, [r5]
 PTR r5
 str r5, [r4, #4]
 ldr r6, [r5, #0x84c]
 PTR r6
 str r6, [r4, #8]
 ldr r10, [r6, #12]
 PTR r10
 str r10, [r4, #12]
 mov r7, r10
 mov r8, #0
 mov r9, #0
 LDA r11, TARGET
walk:
 add r9, r9, #1
 cmp r9, #2048
 bhi done
 PTR r7
 ldr r0, [r7, #0x18]
 cmp r0, r11
 beq found
 ldr r0, [r7, #0x54]
 cmp r0, #64
 bhi done
 cmp r0, #0
 beq ascend
 cmp r8, #16
 bhs done
 ldr r1, [r7, #0x60]
 PTR r1
 ldr r7, [r1], #4
 sub r0, r0, #1
 add r2, sp, r8, lsl #3
 stmia r2, {r0,r1}
 add r8, r8, #1
 b walk
ascend:
 cmp r8, #0
 beq done
 sub r8, r8, #1
 add r2, sp, r8, lsl #3
 ldmia r2, {r0,r1}
 cmp r0, #0
 beq ascend
 ldr r7, [r1], #4
 sub r0, r0, #1
 stmia r2, {r0,r1}
 add r8, r8, #1
 b walk
found:
 str r7, [r4, #16]
 str r0, [r4, #20]
 str r9, [r4, #28]
 ldr r8, [r7, #0x40]
 cmp r8, #0
 beq done
 cmp r8, #12
 bhi done
 str r8, [r4, #24]
 ldr r9, [r7, #0x4c]
 PTR r9
 mov r11, #0
copy:
 ldr r0, [r9, r11, lsl #2]
 PTR r0
 ldr r1, [r0, #8]
 ldr r2, [r0, #0x10]
 PTR r2
 ldr r3, [r2, #12]
 add ip, r4, #32
 add ip, ip, r11, lsl #4
 stmia ip, {r0-r3}
 add r11, r11, #1
 cmp r11, r8
 blo copy
 ldr r0, [r5, #0x84c]
 cmp r0, r6
 bne done
 ldr r0, [r6, #12]
 cmp r0, r10
 bne done
 LDA r0, 0xC37B7048
 ldr r0, [r0]
 cmp r0, r5
 bne done
 mov r0, #1
 str r0, [r4]
done:
 mov r0, #0
 add sp, sp, #132
 pop {r4-r11, pc}
