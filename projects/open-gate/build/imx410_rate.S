.syntax unified
.arm
.text
#include "og_pic.inc"
/* ============================================================================
 * imx410_rate — CinemaDNG 的**容器格率**,從配方讀。
 * ============================================================================
 *   掛在 FUN_c00c9bd0 的進入點(B,不是 BL)。r0 = 兩個字的輸出緩衝
 *   {分子, 分母},寫完直接返回。
 *
 * 為什麼需要:`FUN_c00c9bd0` 是一個 switch,查 movie framerate enum 吐
 * 有理數,然後 `FUN_c00ba378(..., 0xC764, 10, 1, buf)` 把它寫成 DNG 的
 * FrameRate 標籤。那張表最高只到 **120000/1001**,沒有 240。
 *
 * 2026-09-29 上機(A001_170):感測器跑 239.760 而標籤寫 30000/1001 ——
 * 因為我們的 fps 軸只驅動感測器時序,app 層的 movie framerate 沒被碰。
 * §5.3 說的「容器格率 ≠ 感測器格率,原廠 enum 仍要設成最接近的合法值」
 * 在 240 上做不到:選單最高 120。所以改成**直接供應有理數**。
 *
 * 這比 HSW 當年那四件事(有理數表、CSV 第十列、控制器上限、新 enum)省 ——
 * 標籤的唯一來源就是這個函式,換掉它就換掉了標籤。
 *
 * ⚠ 這顆只管**標籤**。時間碼與音訊同步仍走原廠 enum(§5.3 的未列舉消費端),
 *   那些還沒查。
 *
 * fail-open,一項不符就把被覆寫的 push 補回去、跳回原函式第二條指令:
 *   FLAG == 1              選了本目標
 *   RECIPE.valid == 1      配方算得出來
 *   rate 索引 < RATE_COUNT  表內
 * ========================================================================== */

#ifndef RECIPE
.equ RECIPE,   OGA(0xC0733040)
#endif
#ifndef AXIS
.equ AXIS,     OGA(0xC0733020)
#endif
#ifndef RATNUM
.equ RATNUM,   OGA(0xC0730AA0)       /* 11 筆 x {分子, 分母} */
#endif
#ifndef BACK
.equ BACK,     0xC00C9BD4       /* 原函式第二條指令 */
#endif
.equ FLAG,       OGA(0xC0731C08)
.equ R_VALID,    9*4
.equ A_RATE,     1*4
.equ RATE_COUNT, 11

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
    /* 六個 register 維持 8-byte stack alignment。r0 不能動 —— 它是輸出緩衝。 */
    push    {r1, r2, r3, r4, ip, lr}

    LDA     r4, FLAG
    ldr     r4, [r4]
    cmp     r4, #1
    bne     pass

    LDA     r4, RECIPE
    ldr     r1, [r4, #R_VALID]
    cmp     r1, #1
    bne     pass

    LDA     r4, AXIS
    ldr     r4, [r4, #A_RATE]
    cmp     r4, #RATE_COUNT
    bhs     pass                    @ 索引超界 -> 交回原廠,不要讀出表外

    LDA     r1, RATNUM
    add     r1, r1, r4, lsl #3
    ldr     r2, [r1]                @ 分子
    ldr     r3, [r1, #4]            @ 分母
    cmp     r3, #0
    beq     pass                    @ 分母 0 -> 表壞了,交回原廠
    str     r2, [r0]
    str     r3, [r0, #4]
    pop     {r1, r2, r3, r4, ip, lr}
    bx      lr

pass:
    pop     {r1, r2, r3, r4, ip, lr}
    push    {r4, r5, r6, r7, r8, lr}    @ 補被覆寫的那條 stolen instruction
    LDA     ip, BACK
    bx      ip
