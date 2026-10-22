.syntax unified
.arm
.text
#include "og_pic.inc"
/* ============================================================================
 * hswrate — 給格率列舉 11 一個有理數:240000/1001 = 239.760240 fps。
 *
 * 原廠 FUN_c00c9bd0 是「格率 enum -> (分子, 分母)」的表,被
 *     cmp r2, #10 ; bhi default
 * 夾住,跳表只有 0..10。enum 11 原廠會落到 default(29.97),
 * 而 picker 鍵發射器 FUN_c043caf0 **原廠就已經**把 enum 11 印成 "240"
 * (字串在 0xC0BE4804),12 印成 "400" —— 也就是說列舉空間本來就留了
 * 240/400 兩格,只是沒有有理數、也沒有選單列。
 *
 * 掛在 0xC00C9BF8(那顆 cmp)。到這裡為止函式已經 push 過
 * {r4,r5,r6,r7,r8,lr},而且
 *     r4 = 輸出結構    [r4] = 分子   [r4+4] = 分母
 *     r2 = 格率 enum
 * 所以命中時直接寫兩個字,再跳原廠收尾 0xC00C9CEC(pop {..,pc})。
 *
 * 不命中就原地重做位移掉的 cmp 再跳回 0xC00C9BFC —— movw/movt 不動旗標,
 * 所以後面那顆 bhi 讀到的條件碼與原廠完全相同。
 *
 * **不用 FLAG 守衛**:enum 11 只有在選單第十列存在時才可能出現,而那一列
 * 是我們自己加的,本來就是 opt-in。有理數是 enum 的屬性,不是 HSW 的屬性。
 * ========================================================================== */

.equ BACK, 0xC00C9BFC           @ 原廠 bhi,位移指令的下一條
.equ EXIT, 0xC00C9CEC           @ 原廠收尾 pop {r4,r5,r6,r7,r8,pc}
.equ NUM,  240000               @ 0x0003A980
.equ DEN,  1001

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
    cmp     r2, #11
    bne     pass
    movw    r3, #:lower16:NUM
    movt    r3, #:upper16:NUM
    str     r3, [r4]
    movw    r3, #DEN
    str     r3, [r4, #4]
    LDA     ip, EXIT
    bx      ip
pass:
    cmp     r2, #10                     @ 位移的原指令
    LDA     ip, BACK                    @ movw/movt 不動旗標
    bx      ip
