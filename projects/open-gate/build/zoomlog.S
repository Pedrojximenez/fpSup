.syntax unified
.arm
.text
/* zoomlog — XC_DisplayZoomParameterW71C1 (C0306DF8) 在 C0306F34 收尾,
 * sp+0x54 是累積的結果矩形。把整個 0x5C 位元組的區域變數區抓下來,
 * 待機與錄影各一份(以引擎組態的畫格率浮點區分),直接 diff。
 *   0xC0733800  待機:+00 旗標  +04..+5F 堆疊框  +60..+15F 目的物件(r5)
 *               +160..+19F 引擎輸出維度區塊 C31E0DD4+0x300
 *   0xC0733A00  錄影:同上
 * 目的物件必須在當下抓 —— 事後再讀會是已經回到待機的狀態。
 * 位移的原指令是 add r1, sp, #0x54,pop 之後 sp 已還原才執行。 */
.equ CFG,  0xC31DF564
.equ SLA,  0xC0733800
.equ SLB,  0xC0733A00
.equ STBY, 0x42700000
.equ EOUT, 0xC31E10D4          /* C31E0DD4 + 0x300 */
.equ BACK, 0xC0306F38
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
    LDA     ip, SLA
    beq     have
    LDA     ip, SLB
have:
    ldr     r3, [ip]                 @ 改成「最後一次覆寫」而不是「只抓第一次」——
    add     r3, r3, #1               @ 錄影一開始那次是短暫的正確狀態,
    str     r3, [ip]                 @ 之後被 latch 的版面覆蓋,要抓的是最後那次。
    add     r0, sp, #24              @ 原始 sp(剛推了 6 個暫存器)
    mov     r2, #0
copy:
    ldr     r3, [r0, r2]
    add     lr, ip, r2
    str     r3, [lr, #4]
    add     r2, r2, #4
    cmp     r2, #0x5C
    blo     copy
    mov     r2, #0                   @ 再抓目的物件 r5 的 0x100 位元組
copy2:
    ldr     r3, [r5, r2]
    add     lr, ip, r2
    str     r3, [lr, #0x60]
    add     r2, r2, #4
    LDA     r1, 0x100
    cmp     r2, r1
    blo     copy2
    LDA     r0, EOUT                 @ 再抓引擎輸出維度區塊 0x40 位元組
    mov     r2, #0
copy3:
    ldr     r3, [r0, r2]
    add     lr, ip, r2
    LDA     r1, 0x160
    add     lr, lr, r1
    str     r3, [lr]
    add     r2, r2, #4
    cmp     r2, #0x40
    blo     copy3
out:
    pop     {r0, r1, r2, r3, ip, lr}
    add     r1, sp, #0x54            @ displaced
    LDA     ip, BACK
    bx      ip
