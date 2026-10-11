.syntax unified
.arm
.text
/* ============================================================================
 * fmtsub — 回放 OG3K 片子時,把顯像工作拿到的格式編號從 222 換成 98。
 * ============================================================================
 * 這一段的鏈條(2026-09-13 追出來):
 *
 *   XC_LiveViewConfiguratorW71c1::v3  選出一筆名稱表表項
 *     → 存進 **LiveViewState + 0x10**(實測 0xC375D850 指向 0xC0BE4990)
 *   FUN_c02ba640 組硬體顯像工作區塊時:
 *     param_2[0x45] = FUN_c0437060(FUN_c0436590())
 *   而 FUN_c0437060 就是
 *     return *(*(obj + 0x10) + 8);        ← 表項的**第三欄** = 格式編號
 *
 * 表項是 {型別, profile, 格式編號, 名稱}:
 *     回放表(0xC0BE4508/4548/4588)十二筆**全都是 222**
 *     S 尺寸 12-bit 照片 {1, 43, 98, "12BLOW"} 是 **98**
 *
 * 也就是說 222 不是「每個解析度一個」的幾何索引,而是「回放格式」的模式標籤;
 * 98 才是描述 3008x2000 12-bit 的那一個 —— 而那正好是我們錄影借的 donor。
 * (98 在 TT 感測器時序表裡是第 2 筆;222 根本不在 TT 裡。)
 *
 * 所以這裡只換一個字:回放我們的片子時回 98,其他一概不動。
 * 管線選擇(v5 用位址範圍認表)完全不受影響,原廠表項一個位元都沒改。
 *
 * 守衛:PBFLAG == 1(og3kname 從真實片源尺寸 3008x2000 設的,
 * 已由 og3kpbsel 的 40 命中 / 36 放行證明它確實跟著片子走)
 * 且原本要回傳的值是 222(確定是回放表項)。
 *
 * Hook:0xC0437060,B,位移指令是 mov ip, r0。
 * ========================================================================== */

.equ PBFLAG, 0xC0731C0C
.equ LOG,    0xC0732600         /* +0 呼叫次數  +4 換掉的次數  +8 最後原值 */
.equ BACK,   0xC0437064
.equ FROM,   222
.equ TO,     98

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global entry
entry:
    push    {r1, r2, r3, lr}

    LDA     r3, LOG
    ldr     r2, [r3]
    add     r2, r2, #1
    str     r2, [r3]

    ldr     r1, [r0, #0x10]             @ 目前的表項
    cmp     r1, #0
    beq     pass
    ldr     r1, [r1, #8]                @ 它的格式編號
    str     r1, [r3, #8]                @ 記下原值

    cmp     r1, #FROM                   @ 必須是回放表項
    bne     pass
    LDA     r2, PBFLAG
    ldr     r2, [r2]
    cmp     r2, #1                      @ 必須正在顯示 3008x2000
    bne     pass

    ldr     r2, [r3, #4]                @ 換掉計次
    add     r2, r2, #1
    str     r2, [r3, #4]
    mov     r0, #TO
    pop     {r1, r2, r3, lr}
    bx      lr

pass:
    pop     {r1, r2, r3, lr}
    mov     ip, r0                      @ 位移指令
    LDA     r1, BACK
    bx      r1
