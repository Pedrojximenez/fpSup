.syntax unified
.arm
.text
#include "og_pic.inc"
/* og3kaspect2 — C0306EEC 是全韌體第二個(也是最後一個)寫死 enum 3 的長寬比點。
 *
 * 它在 XC_DisplayZoomParameterW71C1 裡、我們 hook 的 C0306EA0 那條路徑 fit 完
 * 之後執行(條件是 C0307520(r4) 非零),把 r4+4 起的 6 字矩形連同 C0B54F60 的
 * (1,1) 像素比餵給 C02DAD20,用的長寬比是 16:9 —— 於是 3:2 的畫面又被按 16:9
 * 修正一次,變成等比例縮小、填不滿,邊緣露出前一幀。
 *
 * 長寬比表 C0B4CAB8 的項目就是字面比例對:enum 2 = (3,2)、enum 3 = (16,9)。
 *
 * 不需要 push:只動 r0(本來就要被設)與 ip(scratch,前一條 C0306EE8 是 ldrd,
 * 下一條是 bl,ip 在此無活值)。 */
.equ FLAG, OGA(0xC0731C08)
#ifdef TARGET_MATCH
.equ PICKOK, TARGET_MATCH   @ fmttable 寫:1 = picker 同意走 3:2
#endif
.equ BACK, 0xC0306EF0
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
    mov     r0, #3                   @ 16:9,原廠
    LDA     ip, BACK
    bx      ip
1:  mov     r0, #2                   @ 3:2
    LDA     ip, BACK
    bx      ip
#else
    movne   r0, #2                   @ 3:2
    moveq   r0, #3                   @ 16:9,原廠
    LDA     ip, BACK
    bx      ip
#endif
