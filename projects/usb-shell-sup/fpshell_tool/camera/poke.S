.syntax unified
.arm
.text
/* 相機端寫入原語,補 pushread 的另一半。
 *
 * 主機的 mem set 有位址閘門:0xC072Fxxx 可寫,韌體程式碼區(例 0xC00D0794 陀螺
 * hook 點)被忽略 —— 而且是**靜默**忽略,回讀還是舊值。相機端執行的程式碼沒有
 * 這個限制。
 *
 * 改到指令記憶體時要做 cache 維護,否則寫進去的是 D-cache,CPU 取指仍可能拿到
 * 舊指令。ARMv7 的標準序列:清 D-cache line → 廢除 I-cache line → DSB → ISB。
 *
 * ARG: [0]=位址 [4]=新值 [8]=1 表示要做 cache 維護
 * OUT: [0]=寫入前的舊值
 */
.equ ARG, 0xC072F484
.equ OUT, 0xC072F494

.macro la reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global cave_entry
cave_entry:
    push    {r4-r6, lr}
    la      r4, ARG
    ldr     r5, [r4]                 @ 位址
    ldr     r6, [r4, #4]             @ 新值
    ldr     r3, [r4, #8]             @ 是否做 cache 維護
    ldr     r0, [r5]
    la      r1, OUT
    str     r0, [r1]                 @ 回報舊值
    str     r6, [r5]
    cmp     r3, #0
    beq     1f
    mcr     p15, 0, r5, c7, c10, 1   @ DCCMVAC  清 D-cache 到記憶體
    dsb
    mcr     p15, 0, r5, c7, c5, 1    @ ICIMVAU  廢除該行 I-cache
    dsb
    isb
1:  mov     r0, #0
    pop     {r4-r6, pc}
