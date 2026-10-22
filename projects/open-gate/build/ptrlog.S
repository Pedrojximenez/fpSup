.syntax unified
.arm
.text
/* ptrlog — 記下 C02F43A8 的 r0/r1/r2,只記第一次,之後從主機端直接讀記憶體。
 *   0xC0731400  flag   +0x04 r0   +0x08 r1   +0x0C r2                  */
.equ LOG,  0xC0731400
.equ BACK, 0xC02F43AC
.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm
.global entry
entry:
    push    {r3, ip, lr, r4}
    LDA     ip, LOG
    ldr     r3, [ip]
    cmp     r3, #0
    bne     out
    str     r0, [ip, #4]
    str     r1, [ip, #8]
    str     r2, [ip, #12]
    mov     r3, #1
    str     r3, [ip]
out:
    pop     {r3, ip, lr, r4}
    push    {r4, r5, r6, r7, lr}
    LDA     ip, BACK
    bx      ip
