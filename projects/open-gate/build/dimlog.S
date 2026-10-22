.syntax unified
.arm
.text
/* dimlog — 記下解析度名發射器 C0437B48 收到的每一組不同的 (寬,高)。
 * r5 = 結構,[r5+8] = 寬,[r5+0xC] = 高。最多 10 組。
 *   0xC0733400  筆數,之後每筆 8 bytes */
.equ LOG,  0xC0733400
.equ BACK, 0xC0437B4C
.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm
.global entry
entry:
    push    {r0, r1, r3, ip, lr}
    LDA     ip, LOG
    LDA     r0, 0xC0000000
    cmp     r2, r0
    blo     out
    ldr     r0, [r2, #8]
    ldr     r1, [r2, #0x0C]
    cmp     r0, #0
    beq     out
    ldr     r3, [ip]
    mov     lr, #0
scan:
    cmp     lr, r3
    beq     addent
    add     ip, ip, #8
    ldr     ip, [ip]
    cmp     ip, r0
    LDA     ip, LOG
    beq     out
    add     lr, lr, #1
    b       scan
addent:
    cmp     r3, #10
    bhs     out
    add     ip, ip, r3, lsl #3
    str     r0, [ip, #8]
    str     r1, [ip, #12]
    LDA     ip, LOG
    add     r3, r3, #1
    str     r3, [ip]
out:
    pop     {r0, r1, r3, ip, lr}
    push    {r4, r5, r6, r7, r8, sb, fp, lr}   @ displaced
    LDA     ip, BACK
    bx      ip
