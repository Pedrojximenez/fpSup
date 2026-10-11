.syntax unified
.arm
.text
/* cfglog v2 — 只要引擎組態的「可見高」或「基礎柵格高」變了就記一筆。
 * 欄位依交接包:+28/+2C 覆寫, +30/+34 可見裁切, +38/+3C 基礎柵格, +68 kind。
 *   0xC0732600  +00 筆數  +04 上次可見高  +08 上次柵格高
 *               每筆 48 bytes,第 i 筆的 11 個欄位在 +16 + 48*i 起
 *               後四個是主管理器 C375D840 的 +1C/+20/+2C/+30 */
.equ CFG,  0xC31DF564
.equ MGR,  0xC375D840
.equ LOG,  0xC0732600
.equ BACK, 0xC02F43AC
.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm
.global entry
entry:
    push    {r0, r1, r2, r3, ip, lr}
    LDA     ip, LOG
    LDA     r0, CFG
    ldr     r2, [r0, #0x34]
    ldr     r3, [ip, #4]
    cmp     r2, r3
    bne     rec
    ldr     r2, [r0, #0x3C]
    ldr     r3, [ip, #8]
    cmp     r2, r3
    beq     done
rec:
    ldr     r2, [r0, #0x34]
    str     r2, [ip, #4]
    ldr     r2, [r0, #0x3C]
    str     r2, [ip, #8]
    ldr     r3, [ip]
    cmp     r3, #8
    bhs     done
    add     lr, ip, r3, lsl #5
    add     lr, lr, r3, lsl #4       @ ip + r3*48
    ldr     r2, [r0, #0x28]
    str     r2, [lr, #16]
    ldr     r2, [r0, #0x2C]
    str     r2, [lr, #20]
    ldr     r2, [r0, #0x30]
    str     r2, [lr, #24]
    ldr     r2, [r0, #0x34]
    str     r2, [lr, #28]
    ldr     r2, [r0, #0x38]
    str     r2, [lr, #32]
    ldr     r2, [r0, #0x3C]
    str     r2, [lr, #36]
    ldr     r2, [r0, #0x68]
    str     r2, [lr, #40]
    LDA     r0, MGR
    ldr     r2, [r0, #0x1C]
    str     r2, [lr, #44]
    ldr     r2, [r0, #0x20]
    str     r2, [lr, #48]
    ldr     r2, [r0, #0x2C]
    str     r2, [lr, #52]
    ldr     r2, [r0, #0x30]
    str     r2, [lr, #56]
    add     r3, r3, #1
    str     r3, [ip]
done:
    pop     {r0, r1, r2, r3, ip, lr}
    push    {r4, r5, r6, r7, lr}     @ displaced
    LDA     ip, BACK
    bx      ip
