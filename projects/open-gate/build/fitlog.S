.syntax unified
.arm
.text
/* fitlog — 掛在原生矩形適配 C02F43A8 進入點。
 *   r0 = obj   r1 = 長寬比 enum   r2 = 參數塊
 *   +0x60 來源寬|高   +0x78 實體目的寬|高   +0x7C 可見寬|高   +0x80 可見 X|Y
 * 依 (來源, 可見) 去重。
 *   0xC0731400  count
 *   +0x04       6 筆 × 20 bytes { src, phys, vis, xy, aspect }         */
.equ LOG,   0xC0731400
.equ SLOTS, 6
.equ BACK,  0xC02F43AC
.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm
.global entry
entry:
    push    {r3, r4, r5, r6, ip, lr}
    LDA     ip, LOG
    ldr     r3, [ip]
    cmp     r3, #SLOTS
    bhs     out
    ldr     r4, [r2, #0x60]             @ 來源 寬|高
    ldr     r5, [r2, #0x7C]             @ 可見 寬|高
    add     r6, ip, #4
    mov     lr, r3
scan:
    cmp     lr, #0
    beq     append
    ldr     r3, [r6]
    cmp     r3, r4
    bne     nextent
    ldr     r3, [r6, #8]
    cmp     r3, r5
    beq     out
nextent:
    add     r6, r6, #20
    sub     lr, lr, #1
    b       scan
append:
    str     r4, [r6]
    ldr     r3, [r2, #0x78]
    str     r3, [r6, #4]
    str     r5, [r6, #8]
    ldr     r3, [r2, #0x80]
    str     r3, [r6, #12]
    str     r1, [r6, #16]               @ 長寬比 enum
    ldr     r3, [ip]
    add     r3, r3, #1
    str     r3, [ip]
out:
    pop     {r3, r4, r5, r6, ip, lr}
    push    {r4, r5, r6, r7, lr}        @ 位移的原指令
    LDA     ip, BACK
    bx      ip
