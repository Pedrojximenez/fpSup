.syntax unified
.arm
.text
/* keyseq — picker C043CCF8 的鍵,環形記錄最近 8 筆(一律覆寫)。
 *
 * 不用判別條件:讀取前最後發生的操作就是回放,所以「最近幾筆」本身就是閘。
 * 先前用 fps == -1 當閘是錯的 —— 引擎組態在配置器跑完之後才寫,
 * picker 被呼叫的當下那個欄位還是舊值。
 *   0xC0733400  總呼叫數(不含 wrap)
 *   0xC0733410 起,每筆 16 bytes,索引 = (總數-1) mod 8 為最新 */
.equ LOG,  0xC0733400
.equ BACK, 0xC043CCFC
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
    ldr     r3, [ip]                @ 總數
    and     r1, r3, #7              @ 環形索引
    add     r0, ip, r1, lsl #4
    ldr     r1, [r2]
    str     r1, [r0, #16]
    ldr     r1, [r2, #4]
    str     r1, [r0, #20]
    ldr     r1, [r2, #8]
    str     r1, [r0, #24]
    ldr     r1, [r2, #12]
    str     r1, [r0, #28]
    add     r3, r3, #1
    str     r3, [ip]
out:
    pop     {r0, r1, r3, ip, lr}
    push    {r4, r5, r6, r7, r10, r11, lr}   @ displaced
    LDA     ip, BACK
    bx      ip
