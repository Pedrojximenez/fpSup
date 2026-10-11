.syntax unified
.arm
.text
/* cfgring — 引擎組態每出現一組「沒見過的」幾何就記一筆,最多 8 筆。
 * 掛在原生 fit C02F43A8(顯示更新時會跑),所以待機、錄影、回放都會經過。
 * 去重的鍵是 可見W|可見H|柵格W|柵格H 四個字。
 *   0xC0733000  筆數
 *   0xC0733010 起,每筆 32 bytes:
 *     +00 可見W +04 可見H +08 柵格W +0C 柵格H +10 視窗W +14 視窗H +18 kind +1C 畫格率 */
.equ CFG,  0xC31DF564
.equ LOG,  0xC0733000
.equ BACK, 0xC02F43AC
.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm
.global entry
entry:
    push    {r0, r1, r2, r3, r4, ip, lr}
    LDA     ip, LOG
    LDA     r0, CFG
    ldr     r2, [r0, #0x30]              @ 可見W
    cmp     r2, #0
    beq     out
    ldr     r3, [ip]                     @ 現有筆數
    mov     r4, #0
scan:
    cmp     r4, r3
    beq     addent
    add     lr, ip, r4, lsl #5
    ldr     r1, [lr, #0x10]
    cmp     r1, r2
    bne     snext
    ldr     r1, [r0, #0x34]
    ldr     lr, [lr, #0x14]
    cmp     r1, lr
    beq     out                          @ 這組看過了
snext:
    add     r4, r4, #1
    b       scan
addent:
    cmp     r3, #8
    bhs     out
    add     lr, ip, r3, lsl #5
    ldr     r1, [r0, #0x30]
    str     r1, [lr, #0x10]
    ldr     r1, [r0, #0x34]
    str     r1, [lr, #0x14]
    ldr     r1, [r0, #0x38]
    str     r1, [lr, #0x18]
    ldr     r1, [r0, #0x3C]
    str     r1, [lr, #0x1C]
    ldr     r1, [r0, #0x44]
    str     r1, [lr, #0x20]
    ldr     r1, [r0, #0x48]
    str     r1, [lr, #0x24]
    ldr     r1, [r0, #0x68]
    str     r1, [lr, #0x28]
    ldr     r1, [r0, #0x10]
    str     r1, [lr, #0x2C]
    add     r3, r3, #1
    str     r3, [ip]
out:
    pop     {r0, r1, r2, r3, r4, ip, lr}
    push    {r4, r5, r6, r7, lr}         @ displaced
    LDA     ip, BACK
    bx      ip
