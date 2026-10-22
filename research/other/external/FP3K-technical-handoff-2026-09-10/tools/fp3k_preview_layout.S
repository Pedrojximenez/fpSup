/* This instruction is inside the native movie display-fit branch, not a
 * sensor or allocation routine. Change its aspect argument only for the
 * private mode on device kind 1 (native C02E9F78). Preserve live registers
 * and flags because this is a mid-function trampoline.
 * Diagnostic +56: bit0 = reached, bit1 = applied; +60: last output descriptor.
 */
.align 2
preview_layout:
 push {r1-r3,ip}
 mrs r2,cpsr
 addr r1,STATE
 mov r0,#3
 mov r3,#1
 ldr ip,[r1,#16]
 cmp ip,#1
 bne preview_layout_done
 ldr ip,[r4]
 ldr ip,[ip,#8]
 cmp ip,#1
 bne preview_layout_done
 mov r0,#2
 mov r3,#3
preview_layout_done:
 ldr ip,[r1,#56]
 orr r3,r3,ip
 str r3,[r1,#56]
 str r5,[r1,#60]
 msr cpsr_f,r2
 pop {r1-r3,ip}
 ldr pc,preview_layout_resume
preview_layout_resume:
 .word 0xC0306EA4
