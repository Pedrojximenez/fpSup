.syntax unified
.arm
.text
#include "og_pic.inc"
/* ============================================================================
 * imx410_canvas — 畫布 hook 的動態版。掛在 0xC043A19C(BL,位移 mov r0,r4)。
 * ============================================================================
 *   r4 + 0x5C = 畫布   r5 = profile id   返回前要補做 mov r0, r4
 *
 * 與 og3kcanvas.S 的差別:**不把任何常數編進指令**。og3kcanvas 用 32 個 PUT
 * (x3 字)+ 2 個 PUTW(x4 字)= 104 個字把幾何寫死;那是它只能服務一組固定
 * 幾何的原因。這裡走 og3krecipe 產生的 (位移, 值) 陣列,所以幾何是資料。
 *
 * og3kcanvas.S 原封不動留著 —— 四個出貨目標在用。
 *
 * ★ 「畫布」就是一整列 PARAM profile(65 個字,位移 0x00..0x100 連續無缺口,
 *   由 FUN_c0439d18 從 65 張欄表組出來)。所以寫這裡 = 就地宣告一個 profile,
 *   借來的那一列只提供預設值。見 IMX410_FULL_DESIGN §13。
 *
 * 守衛只看 profile id:p13 在 306 個 profile 裡是真正沒人引用的兩個之一,
 * 所以不需要 FLAG —— 沒有別人會用這個 id 載入。
 *
 * 回放路徑(og3kcanvas 的 case B)這一版**不處理**,只做錄影。回放要另外
 * 一組幾何(柵格 = 片子的記錄尺寸),等錄影這條驗過再接。
 * ========================================================================== */

#ifndef CANVAS
.equ CANVAS,   OGA(0xC0733300)        /* +0x00 對數,之後 (位移, 值) 陣列 */
#endif
#ifndef PROFILE_ID
#error "PROFILE_ID comes from imx410_plan"   /* 我們宣告的 profile id 所在的 RAM 字 */
#endif
.equ FPSLATCH, OGA(0xC0731C40)        /* imx410_fmt 命中時寫的引擎格率 float bits */
.equ ROW,      0x5C
.equ LOG,      OGA(0xC0732A00)        /* +0 錄影命中次數  +8 最後看到的 profile id */
.equ MAX_PAIRS, 32               /* 對數超過這個就當資料壞了,不動畫布 */

.macro LDA reg, value
#ifdef OG_V3
    OGLDA   \reg, \value
#else
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
#endif
.endm

.global entry
entry:
    push    {r0, r1, r2, r3, ip, lr}
    LDA     ip, LOG
    str     r5, [ip, #8]

    LDA     ip, PROFILE_ID              @ 我們宣告的 profile id。還沒公布時是 0,
    ldr     ip, [ip]                    @ 而 mapping[0] 是空槽、韌體不會以 0 載入
    cmp     r5, ip                      @ -> 一樣走 out(槽只有 144 B,省掉明寫的檢查)
    bne     out

    LDA     r0, CANVAS
    ldr     r2, [r0]                    @ 對數
    cmp     r2, #0
    beq     out                         @ 沒有配方 -> 一個字都不碰
    cmp     r2, #MAX_PAIRS
    bhi     out                         @ 資料不合理 -> 同上,故障安全

    add     r1, r4, #ROW                @ 畫布
    add     r0, r0, #4                  @ 陣列起點
1:  ldr     r3, [r0], #4                @ 位移
    ldr     ip, [r0], #4                @ 值
    str     ip, [r1, r3]
    subs    r2, r2, #1
    bne     1b

    /* 引擎格率 +0x030。donor 原廠帶的值與我們在錄的格率無關(p13 是 60.0),
     * 而訊號處理引擎的組態 +0x10 就是它 —— FUN_c01caba0 的 `fps < 30` 分支、
     * FUN_c01cec08 的 >99 閘門、FUN_c01d11e8 的 timeout 全看這一個字。
     * 放在陣列外面是因為它的來源是 imx410_fmt 的鎖存,不是幾何。 */
    LDA     r0, FPSLATCH
    ldr     ip, [r0]
    cmp     ip, #0
    strne   ip, [r1, #0x30]

    LDA     r0, LOG
    ldr     r3, [r0]
    add     r3, r3, #1
    str     r3, [r0]

out:
    pop     {r0, r1, r2, r3, ip, lr}
    mov     r0, r4                      @ 位移指令
    bx      lr
