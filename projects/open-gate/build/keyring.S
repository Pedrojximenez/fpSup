.syntax unified
.arm
.text
/* keyring v3 — 只在「回放中」記錄 picker 看到的鍵。
 *
 * 判別條件:引擎組態的畫格率浮點 C31DF564+0x10 == -1.0f(0xBF800000)。
 * 實測回放時那個欄位是 -1(待機 60.0、錄影是實際格率),UHD 與 OG3K 回放都是。
 *
 * v2 的問題不是程式碼而是**歸因**:它記到 OG3K30,但那可能來自「回到拍攝
 * 模式」時的查詢,不是回放。鍵必須綁定到回放那一刻才有意義。
 * r2 指向鍵字串。去重比前 8 bytes。
 * v1 的去重寫錯了:ip 在迴圈裡被重設,每次都只跟第 0 筆比,所以記錄全是重複值。
 *   0xC0733400  筆數,之後每筆 16 bytes */
.equ LOG,  0xC0733400
.equ BACK, 0xC043CCFC
.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm
.global entry
entry:
    push    {r0, r1, r3, r4, r5, ip, lr}
    LDA     r0, 0xC31DF564              @ 只在回放中記錄
    ldr     r0, [r0, #0x10]
    LDA     ip, 0xBF800000
    cmp     r0, ip
    bne     out
    LDA     ip, LOG
    LDA     r0, 0xC0000000
    cmp     r2, r0
    blo     out
    ldr     r3, [r2]                    @ 鍵前 8 bytes
    ldr     r4, [r2, #4]
    ldr     r5, [ip]                    @ 現有筆數
    mov     r1, #0
scan:
    cmp     r1, r5
    beq     addent
    add     r0, ip, r1, lsl #4
    ldr     lr, [r0, #16]
    cmp     lr, r3
    bne     snext
    ldr     lr, [r0, #20]
    cmp     lr, r4
    beq     out                         @ 記過了
snext:
    add     r1, r1, #1
    b       scan
addent:
    cmp     r5, #10
    bhs     out
    add     r0, ip, r5, lsl #4
    str     r3, [r0, #16]
    str     r4, [r0, #20]
    ldr     r3, [r2, #8]
    str     r3, [r0, #24]
    ldr     r3, [r2, #12]
    str     r3, [r0, #28]
    add     r5, r5, #1
    str     r5, [ip]
out:
    pop     {r0, r1, r3, r4, r5, ip, lr}
    push    {r4, r5, r6, r7, r10, r11, lr}   @ displaced
    LDA     ip, BACK
    bx      ip
