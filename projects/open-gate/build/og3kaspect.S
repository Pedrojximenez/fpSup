.syntax unified
.arm
.text
#include "og_pic.inc"
/* ============================================================================
 * og3kaspect — live view 的決定性修正。
 * ============================================================================
 * XC_DisplayZoomParameterW71C1 (C0306DF8) 在 C0306EA0 把長寬比 enum 寫死成 3:
 *
 *     C0306EA0   mov r0, #3          <- 16:9
 *     C0306EA4   bl  0xC02DAFA0
 *
 * 長寬比表 C0B4CAB8,8 bytes 一筆: 1=4:3  2=3:2  3=16:9  4=1:1
 * OG3K 生效時改成 2,其餘維持 3。之後原生的矩形適配自己會做對。
 *
 * 位移的是 mov r0,#3 本身,所以只動 r0(本來就要被設)與 ip
 * (前一條 C0306E94 剛做完 bl,ip 已是 scratch),不需要 push。
 * ========================================================================== */

.equ FLAG, OGA(0xC0731C08)
#ifdef TARGET_MATCH
.equ PICKOK, TARGET_MATCH   @ fmttable 寫:1 = picker 同意走 3:2
#endif
.equ BACK, 0xC0306EA4

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
#ifdef TARGET_MATCH
    /* 2026-09-27:條件從「FLAG」收緊成「FLAG && PICKOK」。
     * FLAG==0 就跳過第二次載入,旗標仍是第一次 cmp 的結果(EQ);
     * FLAG!=0 才看 PICKOK,旗標換成它的結果。所以下面原本那幾條
     * 一個字都不用改。 */
    beq     pickdone
    LDA     ip, PICKOK
    ldr     ip, [ip]
    cmp     ip, #0
pickdone:
#endif
#ifdef OG_CHAIN
    /* Loader v3 layer: not ours -> whoever is below decides (og_replay is the
     * stock `mov r0, #3` when nobody is). */
    bne     1f
    OG_PASS
.global og_replay
og_replay:
    mov     r0, #3                      @ 16:9,原廠
    LDA     ip, BACK
    bx      ip
1:  mov     r0, #2                      @ 3:2
    LDA     ip, BACK
    bx      ip
#else
    movne   r0, #2                      @ 3:2
    moveq   r0, #3                      @ 16:9,原廠
    LDA     ip, BACK
    bx      ip
#endif
