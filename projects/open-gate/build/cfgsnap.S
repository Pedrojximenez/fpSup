.syntax unified
.arm
.text
/* cfgsnap v2 — 抓引擎組態的「兩個通道」各 0x360 位元組。
 * 觸發改用 +0x10 的畫格率浮點:待機 60.0f (0x42700000),錄影是別的值。
 *   0xC0732800  待機:+00 旗標, +04.. 0x360 資料
 *   0xC0733000  錄影:同上 */
.equ CFG,  0xC31DF564
.equ SLA,  0xC0732800
.equ SLB,  0xC0733000
.equ STBY, 0x42700000
.equ BACK, 0xC02F43AC
.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm
.global entry
entry:
    push    {r0, r1, r2, r3, ip, lr}
    LDA     r0, CFG
    ldr     r2, [r0, #0x10]
    LDA     r3, STBY
    cmp     r2, r3
    beq     slota
    LDA     ip, SLB
    b       cap
slota:
    LDA     ip, SLA
cap:
    ldr     r3, [ip]
    cmp     r3, #0
    bne     out
    mov     r3, #1
    str     r3, [ip]
    mov     r2, #0
copy:
    ldr     r3, [r0, r2]
    add     lr, ip, r2
    str     r3, [lr, #4]
    add     r2, r2, #4
    LDA     r1, 0x360
    cmp     r2, r1
    blo     copy
out:
    pop     {r0, r1, r2, r3, ip, lr}
    push    {r4, r5, r6, r7, lr}     @ displaced
    LDA     ip, BACK
    bx      ip
