.syntax unified
.arm
.text
#include "og_pic.inc"
/* ============================================================================
 * imx410_fps — 快門角度的 nominal fps,從配方讀。
 * ============================================================================
 *   r0 進來是 sensor mode,回去必須是整數 nominal fps。
 *
 * 四條已確認的快門角度換算/同步路徑各有一條本地 `BL FUN_c032c750(mode)`。
 * 不動全域 getter —— donor 模式通常也被照片路徑共用。
 *
 * 為什麼需要:donor 的 metadata +0x40 是它**自己出廠**的格率,而我們借它
 * 承載別的格率。mode 98 的 +0x40 是 78,拿它算 29.97/180° 會得到 1/156
 * (約 -1.38 EV)。
 *
 * 與 og3kfps.S 的差別:那一顆把「哪些 timing tuple 對應哪個 nominal」做成
 * **編譯期白名單表**(TARGET_T0_W0/W1/FPS ... 七組)。全功能版的 donor 與
 * 時序都是算出來的,表不可能預先列完,所以改讀 RECIPE。
 *
 * og3kfps.S 原封不動 —— OG3K/OG2K/OG6K 在用。
 *
 * fail-open 的條件與 og3kfps 相同,一項不符就交回原 getter 的結果:
 *   FLAG == 1                     選了本目標
 *   RECIPE.valid == 1             配方算得出來
 *   r0 == RECIPE.mode             問的正是我們的 donor
 *   donor 的時序記錄兩個字**精確等於** RECIPE 算出來的那兩個字
 *                                 —— 原廠、混合、損壞或切換中的 tuple 全部
 *                                    保留原值,不要在半套狀態下說謊
 * ========================================================================== */

#ifndef RECIPE
.equ RECIPE,   OGA(0xC0733040)
#endif
.equ FLAG,     OGA(0xC0731C08)
.equ IMAGER,   0xC343B588
.equ ORIGINAL, 0xC032C750
.equ R_VALID,  9*4
.equ R_MODE,   10*4
.equ R_IDX,    11*4
.equ R_TW0,    12*4
.equ R_TW1,    13*4
.equ R_NOM,    18*4

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
    /* 四個 register 維持呼叫點的 8-byte stack alignment。 */
    push    {r4, r5, r6, lr}
    mov     r4, r0                      @ 問的 sensor mode
    LDA     ip, ORIGINAL
    blx     ip
    mov     r5, r0                      @ 原 getter 的結果 = fail-open 值

    LDA     ip, FLAG
    ldr     ip, [ip]
    cmp     ip, #0
    beq     out

    LDA     r6, RECIPE
    ldr     r0, [r6, #R_VALID]
    cmp     r0, #0
    beq     out
    ldr     r0, [r6, #R_MODE]
    cmp     r0, r4
    bne     out                         @ 問的不是我們的 donor
    ldr     r0, [r6, #R_IDX]
    cmp     r0, #70
    bhs     out

    /* donor 的時序記錄現在是不是我們寫的那一組 */
    LDA     ip, IMAGER
    ldr     ip, [ip]
    ldr     ip, [ip]                    @ 時序表基底
    add     ip, ip, r0, lsl #5
    ldr     r1, [ip, #4]
    ldr     r2, [r6, #R_TW0]
    cmp     r1, r2
    bne     out
    ldr     r1, [ip, #8]
    ldr     r2, [r6, #R_TW1]
    cmp     r1, r2
    bne     out

    ldr     r5, [r6, #R_NOM]
out:
    mov     r0, r5
    pop     {r4, r5, r6, pc}
