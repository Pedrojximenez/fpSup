.syntax unified
.arm
.text
/* ============================================================================
 * ratelog —— 純記錄探針,掛在**格率 setter** 0xC005C0B8 的進入點。
 * ============================================================================
 * 目的:量出「119.88 / 100 fps 的選單 enum 是多少」。
 *
 * 為什麼需要探針而不是直接讀設定:那兩個格率只有接了 SSD 才可寫,而 SSD 佔住
 * USB 口 -> 沒有 shell;拔掉 SSD 設定又會被打回合法值。**但 RAM 不受換媒體
 * 影響**,所以在 setter 上記下請求的 enum,之後換回 USB 再讀那個字。
 *
 *   r0 = obj   r1 = 請求的 enum   r2 = flag
 *
 * 與 setlog.S 逐條相同(去重、滿 SLOTS 就停),只有兩處不同:
 *   1. BACK = 0xC005C0BC(格率 setter),不是 0xC005C024(解析度 setter)
 *   2. 區塊位址由呼叫端給(#ifndef P),**不寫死** —— setlog.S 寫死的
 *      0xC0731400 在現行 OG3K 建置裡是 og3kfmt 的 payload,照用會蓋掉它。
 *
 * 進入指令與兩個已 hook 的兄弟 setter 完全相同(0xE92D4070 =
 * push {r4,r5,r6,lr}),所以位移補回的方式也一樣。
 *
 * 版面:  P+0x00  payload(約 0x60 bytes)
 *        P+0xA0  count,之後 SLOTS 筆 x 16 bytes { r0, r1, r2, - }
 *        總共需要 0xA0 + 4 + 6*16 = 0x104 -> claim 0x120
 * ========================================================================== */

#ifndef P
.equ P,     0xC072F700      /* standalone 預設;呼叫端會傳真正的位址 */
#endif
.equ LOG,   P + 0xA0
.equ SLOTS, 6
.equ BACK,  0xC005C0BC

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
