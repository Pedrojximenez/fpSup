.syntax unified
.arm
.text
/* ============================================================================
 * ratesel —— 純記錄探針,掛 MenuItemSelector<eXC_MenuFrameRate>::v1 0xC00B20E8
 * ============================================================================
 * 目的:讀出格率選單的**值陣列**與**游標界線**,確認最後一項是不是 119.88。
 *
 *   r0 = 選擇器物件   r1 = 步進量
 *
 * 物件版面(由 ::v2 的位移導出,大小 0x1C):
 *     +0x04 設定物件   +0x08 值陣列   +0x0C 游標
 *     +0x10 ?          +0x14 最大索引  +0x18 環繞旗標
 *
 * 只 dump 一次(LOG 的 count 非 0 就跳過),因為物件是堆積配置的、選單關掉就
 * 消失 —— 事後拿指標回讀會拿到別的東西(og3kcanvas 檔頭記過同一個坑)。
 * 所以**當場**把物件七個字與陣列前十二個字抄進 cave。
 *
 * 版面:  P+0x00  payload
 *        P+0xC0  count(非 0 = 已抄過)
 *        P+0xC4  物件七個字
 *        P+0xE0  值陣列前十二個字
 * ========================================================================== */
#ifndef P
.equ P,     0xC072F700      /* standalone 預設;呼叫端會傳真正的位址 */
#endif
.equ LOG,   P + 0xC0
.equ BACK,  0xC00B20EC

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global entry
entry:
    push    {r0, r1, r2, r3, ip, lr}
    LDA     ip, LOG
    ldr     r3, [ip]
    cmp     r3, #0
    bne     out                         @ 只抄第一次
    mov     r2, #0
obj:                                    @ 物件七個字 -> LOG+0x04
    ldr     r3, [r0, r2]
    str     r3, [ip, #4]
    add     ip, ip, #4
    add     r2, r2, #4
    cmp     r2, #28
    bne     obj
    sub     ip, ip, #28
    ldr     r3, [r0, #8]                @ 值陣列指標
    cmp     r3, #0
    beq     done
    mov     r2, #0
arr:                                    @ 陣列前十二個字 -> LOG+0x20
    ldr     r1, [r3, r2]
    movw    r0, #0x20
    add     r0, r0, r2
    str     r1, [ip, r0]
    add     r2, r2, #4
    cmp     r2, #48
    bne     arr
done:
    mov     r3, #1
    str     r3, [ip]                    @ count = 1,之後不再抄
out:
    pop     {r0, r1, r2, r3, ip, lr}
    push    {r4, r5, r6, lr}            @ 位移的原指令
    LDA     ip, BACK
    bx      ip
