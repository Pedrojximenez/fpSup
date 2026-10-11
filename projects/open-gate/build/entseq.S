.syntax unified
.arm
.text
/* entseq — FUN_c0437af8(entry_ptr, x) 的 entry_ptr,環形最近 8 筆。
 *
 * 源碼:FUN_c0437af8 讀 *(entry_ptr + 4) 當 profile id,再一路建出 canvas。
 * 所以「回放用哪個 profile」等於「回放傳哪個表項指標進來」。
 * 環形、無判別條件 —— 讀取前最後的操作就是閘。
 *   0xC0733400  總數   0xC0733410 起每筆 4 bytes */
.equ LOG,  0xC0733400
.equ BACK, 0xC0437AFC
.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm
.global entry
entry:
    push    {r1, r2, r3, ip, lr}
    LDA     ip, LOG
    ldr     r3, [ip]
    and     r2, r3, #7
    add     r1, ip, r2, lsl #2
    str     r0, [r1, #16]
    add     r3, r3, #1
    str     r3, [ip]
    pop     {r1, r2, r3, ip, lr}
    push    {r4, r5, r6, lr}        @ displaced
    LDA     ip, BACK
    bx      ip
