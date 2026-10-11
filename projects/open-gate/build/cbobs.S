.syntax unified
.arm
.text
/* ============================================================================
 * cbobs — 包住回放把影格交給顯示的那個 callback,記下它是誰、收到什麼。
 * ============================================================================
 *   C05C2730  str r5, [r4, #0x10]
 *   C05C2734  ldr r3, [r4, #0x180]     ; callback 函式指標
 *   C05C2738  ldr r2, [r4, #0x17c]     ; context
 *   C05C273C  sub r0, r5, #1           ; 影格索引 - 1
 *   C05C2740  mov r1, r6               ; 28-byte 結構
 *   C05C2744  blx r3                   ; <= hook 這一條
 *   C05C2748  ...
 *
 * 這個 callback 是執行期註冊的,靜態分析追不到 —— 它是整條回放鏈裡
 * 最後一個未知的環節(緩衝已證明大小正確、管線選擇已完全畫出來)。
 *
 * 做法:用 B 取代 blx,自己記錄後再 `bx` 到目標(lr 手動設成 0xC05C2748,
 * 等同原本的 blx),回來後再抄那個結構 —— 它是被呼叫者填的,所以**呼叫後**
 * 抄才有意義。
 *
 * 後寫為準(last-wins):在會反覆latch 的系統上,第一次呼叫往往是短暫的
 * 正確狀態,2026-09-12 已經被這件事誤導過一次。
 *
 * LOG(0xC0732300):
 *   +0x00 呼叫次數   +0x04 callback 位址   +0x08 影格索引   +0x0C context
 *   +0x10 結構指標   +0x14 回傳值          +0x18.. 結構的 28 bytes
 * ========================================================================== */

.equ LOG,  0xC0732300
.equ BACK, 0xC05C2748

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global entry
entry:
    push    {r4, r5, r6, lr}            @ 四個,堆疊維持八位元組對齊

    mov     r4, r1                      @ 結構指標(呼叫後要抄)
    mov     r5, r3                      @ 目標

    LDA     r6, LOG
    ldr     ip, [r6]
    add     ip, ip, #1
    str     ip, [r6]
    str     r3, [r6, #4]                @ callback 位址
    str     r0, [r6, #8]                @ 影格索引
    str     r2, [r6, #12]               @ context
    str     r1, [r6, #16]               @ 結構指標

    blx     r5                          @ r0/r1/r2 原封不動交給它

    LDA     r6, LOG
    str     r0, [r6, #20]               @ 回傳值
    mov     ip, #0
copy:
    ldr     r5, [r4, ip]
    add     r3, r6, ip
    str     r5, [r3, #24]
    add     ip, ip, #4
    cmp     ip, #28
    blo     copy

    pop     {r4, r5, r6, lr}
    LDA     ip, BACK
    bx      ip
