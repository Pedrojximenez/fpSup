.syntax unified
.arm
.text
/* ============================================================================
 * fmthook — 機制驗證:讓 picker 回傳「我們自己的 entry」。
 * ============================================================================
 * 掛在 FUN_c043ccf8 進入點 0xC043CCF8,原指令 push {r4,r5,r6,r7,r10,r11,lr}。
 *   r0 = obj   r1 = table   r2 = key
 *
 * 條件:table == 0xC0BE5B50(CinemaDNG 那張) 且 key == "HD30"
 * 動作:直接回傳 0xC0730600 的自製 entry,不進原廠迴圈。
 *
 * 自製 entry 除了感光元件模式改成 117,其餘照抄原廠 FHD30:
 *     { 5, 175, 117, ptr("FHD30") }
 * 所以錄完讀 0xC343B590 應該是 117 而不是 106 —— 一個暫存器就能判定,
 * 不需要量素材。
 *
 * 命中次數記在 0xC0730700。
 * ========================================================================== */

.equ ENTRY, 0xC0730600
.equ HITS,  0xC0730700
.equ TAB3,  0xC0BE5B50
.equ BACK,  0xC043CCFC
.equ K0,    0x30334448          /* "HD30" 小端 */

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global entry
entry:
    push    {r3, r4, ip, lr}

    LDA     ip, TAB3
    cmp     r1, ip
    bne     pass

    ldr     r3, [r2]                    @ key 前四個 byte
    LDA     ip, K0
    cmp     r3, ip
    bne     pass
    ldrb    r3, [r2, #4]                @ NUL
    cmp     r3, #0
    bne     pass

    LDA     ip, HITS                    @ 命中計數
    ldr     r3, [ip]
    add     r3, r3, #1
    str     r3, [ip]

    LDA     r0, ENTRY                   @ 回傳自製 entry
    pop     {r3, r4, ip, lr}
    bx      lr

pass:
    pop     {r3, r4, ip, lr}
    push    {r4, r5, r6, r7, r10, r11, lr}   @ 位移的原指令
    LDA     ip, BACK
    bx      ip
