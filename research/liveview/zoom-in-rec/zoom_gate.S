.syntax unified
.arm
.text
/* ============================================================================
 * zoom_gate — 把 canZoom 路徑上的兩道守門改寫成常數,再讓 I-cache 看見。
 * ============================================================================
 *
 * 只動兩個字,都在 `FUN_c04a5650`(canZoom)這條路徑的呼叫點上,不動被共用的
 * 被呼叫函式本體 —— 所以錄影中其他也在問 `FUN_c04a4eb8` / `FUN_c04a7618`
 * 的程式碼(例如 `FUN_c04843b0`、QS 選單)行為完全不變。
 *
 *   0xC04A569C  BL FUN_c04a4eb8  → MOV r0,#0   「正在錄影」那道門
 *   0xC04A579C  BL FUN_c04a7618  → MOV r0,#0   會跳 3 秒提示的那道門
 *
 * 兩處後面都緊接 `cmp r0,#0`,所以把回傳值直接做成 0 是安全的替換。
 *
 * 位址與值由主機在組譯時用 -D 帶進來(apply 與 revert 各組一次),函式裡沒有
 * 參數塊 —— 少一個要放在可寫區、還要回讀重試的東西。
 *
 * 寫完一定要做快取維護:改的是 ROM 位址上的指令,D-cache 裡是新的、I-cache
 * 裡還是舊的,少了這一步就是「寫進去了但沒生效」,而且回讀還會給你新值。
 * ========================================================================== */

#ifndef A1
.equ A1, 0xC04A569C
.equ V1, 0xE3A00000
.equ A2, 0xC04A579C
.equ V2, 0xE3A00000
#endif

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global entry
entry:
    /* 偶數個暫存器:AAPCS 要求呼叫時堆疊 8 位元組對齊,推奇數個會留在 4,
     * 直到被中斷的那一刻才以 LDRD 的 data abort 收費。 */
    push    {r4, lr}

    LDA     r0, A1
    LDA     r1, V1
    str     r1, [r0]
    dsb
    mcr     p15, 0, r0, c7, c14, 1      @ DCCIMVAC: 這一行清到 PoC

    LDA     r0, A2
    LDA     r1, V2
    str     r1, [r0]
    dsb
    mcr     p15, 0, r0, c7, c14, 1

    dsb
    mov     r0, #0
    mcr     p15, 0, r0, c7, c5, 0       @ ICIALLU: 整個 I-cache 失效
    mcr     p15, 0, r0, c7, c5, 6       @ BPIALL:  分支預測器也一起
    dsb
    isb

    mov     r0, #0
    pop     {r4, pc}
