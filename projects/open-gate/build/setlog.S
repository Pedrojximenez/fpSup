.syntax unified
.arm
.text
/* setlog — 掛在設定 setter 進入點,記下 (r0, r1, r2),依三者去重。
 *   0xC0731400  count
 *   +0x04       6 筆 × 16 bytes { r0, r1, r2, - }
 * 原指令 push {r4,r5,r6,lr} 位移後補回。 */
.equ LOG,   0xC0731400
.equ SLOTS, 6
.equ BACK,  0xC005C024
.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm
.global entry
entry:
    push    {r3, r4, ip, lr}
    LDA     ip, LOG
    ldr     r3, [ip]
    cmp     r3, #SLOTS
    bhs     out
    add     r4, ip, #4
    mov     lr, r3
scan:
    cmp     lr, #0
    beq     append
    ldr     r3, [r4]
    cmp     r3, r0
    bne     nextent
    ldr     r3, [r4, #4]
    cmp     r3, r1
    bne     nextent
    ldr     r3, [r4, #8]
    cmp     r3, r2
    beq     out
nextent:
    add     r4, r4, #16
    sub     lr, lr, #1
    b       scan
append:
    str     r0, [r4]
    str     r1, [r4, #4]
    str     r2, [r4, #8]
    ldr     r3, [ip]
    add     r3, r3, #1
    str     r3, [ip]
out:
    pop     {r3, r4, ip, lr}
    push    {r4, r5, r6, lr}                 @ 位移的原指令
    LDA     ip, BACK
    bx      ip
