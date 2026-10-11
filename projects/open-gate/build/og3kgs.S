.syntax unified
.arm
.text
#include "og_pic.inc"
/* ============================================================================
 * og3kgs — 只讓「增益分派」認為我們是 raw movie,不碰感測器模式重設。
 * ============================================================================
 * 2026-09-14:先前的做法是在 FUN_c043a1c8 算出的旗標補上 bit 3。
 * gain_state 確實變成 7(高光餘裕拿回來了),但**錄影預覽變綠且閃爍**。
 *
 * 原因:bit 3 有**兩個**消費者,我們只要其中一個。
 *     FUN_c03a6dd8() → 讀 bit3 → FUN_c039dde8 的增益分派 → gain_state 7   ← 要
 *     FUN_c03a66b0() → 讀 bit3 → FUN_c030ce00(mgr, fmtidx)               ← 不要
 *                                 = 錄影中用 fmtidx 重新程式化感測器模式
 *
 * 原廠本來就在 fmtidx 指定的那個模式,所以重設等於沒事;我們的時序是從別的
 * 模式抄來的(donor 只提供格式編號與 TT 指標),被重設就會不一致 → 綠色閃爍。
 * donor 換成 11 或 98 都一樣綠,因為問題是「重設」本身,不是重設成哪一個。
 *
 * 所以改成只 hook 增益分派那一路:FUN_c03a6dd8 在 OG3K 被選中時直接回 1,
 * FUN_c03a66b0 讀到的仍然是原廠的 0 → 維持提前返回 → 不重設感測器。
 *
 * 之後 FUN_c039dde8 會依位元深度分派:12-bit → gain_state 7(HCG 門檻 3200)。
 *
 * Hook:0xC03A6DD8,B,位移指令 push {r4, lr}。
 * LOG(0xC07328C0):+0x00 介入次數
 * ========================================================================== */

.equ FLAG, OGA(0xC0731C08)
.equ LOG,  OGA(0xC07328C0)
.equ BACK, 0xC03A6DDC

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
    push    {r1, ip}

    LDA     ip, FLAG
    ldr     ip, [ip]
    cmp     ip, #1
    bne     pass

    LDA     ip, LOG
    ldr     r1, [ip]
    add     r1, r1, #1
    str     r1, [ip]
    pop     {r1, ip}
    mov     r0, #1                      @ 「是 raw movie」→ 走位元深度分派
    bx      lr

pass:
    pop     {r1, ip}
#ifdef OG_CHAIN
    OG_PASS                     @ Loader v3: the layer below, or og_replay
.global og_replay
og_replay:
#endif
    push    {r4, lr}                    @ 位移指令
    LDA     ip, BACK
    bx      ip
