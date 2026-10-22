.syntax unified
.arm
.text
#include "og_pic.inc"
/* ============================================================================
 * imx410_aspect — 長寬比,從配方讀,不寫死。
 * ============================================================================
 * 全韌體只有兩個點把長寬比 enum 寫死成 3(16:9),兩個都在
 * XC_DisplayZoomParameterW71C1 裡:
 *     0xC0306EA0   mov r0, #3     矩形適配
 *     0xC0306EEC   mov r0, #3     適配之後的第二次修正(條件是 C0307520(r4) 非零)
 * 兩處位移的都是那條 `mov r0,#3`,而且都用 `bx ip` 回去(hook 是 B 不是 BL,
 * 所以 lr 不可靠)。**同一份原始碼組兩次**,只有 BACK 不同。
 *
 * og3kaspect.S / og3kaspect2.S 原封不動 —— 那兩顆寫死 3:2,是 OG3K/OG2K/
 * OG6K/HSW 在用的。全功能版的長寬比是算出來的(3:2、16:9、21:9 都可能),
 * 所以讀 RECIPE 的 R_ASPECT。
 *
 * 那個 enum 由 og3krecipe 算好,而且**吃 donor 的 geometry scale** ——
 * mode 12 是 3x6 非對稱縮減,光柵 2000x662 的實際顯示比例是 1.51 = 3:2。
 * 出貨的 HSW 把它寫死成 2 正是這個原因;現在那個值是推導出來的。
 *
 * 條件是 FLAG && PICKOK,與 og3kaspect 相同:
 *   FLAG   選了本目標
 *   PICKOK picker 同意(查得到鍵)。不看它的話,「選了本目標但沒有 mode」
 *          會讓顯示鏈走我們的比例而錄影走 FHD -> 畫面拉長。
 *          見 notes/FLAG_AND_PICKER_DISAGREE.md。
 * 任何一個不成立就交回原廠的 3。
 * ========================================================================== */

#ifndef RECIPE
.equ RECIPE,  OGA(0xC0733040)
#endif
#ifndef BACK
.equ BACK,    0xC0306EA4        /* 第一個點;第二個點是 0xC0306EF0 */
#endif
.equ FLAG,    OGA(0xC0731C08)
.equ PICKOK,  OGA(0xC0731C44)
.equ R_VALID,  9*4
.equ R_ASPECT, 20*4
.equ STOCK,   3                 /* 16:9,原廠 */

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
    LDA     ip, FLAG
    ldr     ip, [ip]
    cmp     ip, #0
    beq     stock
    LDA     ip, PICKOK
    ldr     ip, [ip]
    cmp     ip, #0
    beq     stock
    LDA     ip, RECIPE
    ldr     r0, [ip, #R_VALID]
    cmp     r0, #0
    beq     stock                   @ 還沒算出配方 -> 原廠
    ldr     r0, [ip, #R_ASPECT]
    /* 值域 1..5。**只能動 r0 與 ip** —— 位移的是 mov r0,#3,其餘暫存器在
     * 這個點都還活著(og3kaspect.S 的檔頭記著這件事)。 */
    sub     ip, r0, #1
    cmp     ip, #5
    movhs   r0, #STOCK              @ 值域外 -> 原廠,故障安全
    b       out
stock:
    mov     r0, #STOCK
out:
    LDA     ip, BACK
    bx      ip
