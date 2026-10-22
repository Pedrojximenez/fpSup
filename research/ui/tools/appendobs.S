.syntax unified
.thumb
.text
/* ============================================================================
 * appendobs — 觀察:哪個容器接了哪個元素、元素的名字是什麼。
 * ============================================================================
 * FUN_c05e2ca8(容器, 元素) @0xC05E2CA8(Thumb-2):
 *
 *     C05E2CA8  B530   push {r4, r5, lr}
 *     C05E2CAA  4605   mov  r5, r0
 *     C05E2CAC  4608   mov  r0, r1       ← 跳回這裡
 *
 * 這是直譯器 case 10 的元素迴圈裡「把填好的元素接進容器」那一步,
 * 此時元素的 +0x18 已經是圖示名字的位址,所以可以直接分辨是哪個 widget。
 *
 * 紀錄:每筆 12 bytes —— 容器 / 元素 / 名字
 * ========================================================================== */

.equ SLOTP,  0xC07330F0
.equ LOGEND, 0xC0734000
.equ NAME1,  0xC18E92DC         @ qs_resolution_1_S
.equ NAME2,  0xC18E92F0         @ qs_resolution_2_S
.equ BACK,   0xC05E2CAD

.global entry
.thumb_func
entry:
    push    {r0, r1, r2, r3}

    ldr     r2, =SLOTP
    ldr     r3, [r2]
    ldr     r0, =LOGEND
    cmp     r3, r0
    bhs     done

    ldr     r0, [sp, #4]                @ 原本的 r1 = 元素
    ldr     r1, [r0, #0x18]             @ 元素的名字指標
    @ 一次繪製有三百多次 append,緩衝會先滿。只留解析度那兩個名字。
    ldr     r2, =NAME1
    cmp     r1, r2
    beq     keep
    ldr     r2, =NAME2
    cmp     r1, r2
    bne     done
keep:
    ldr     r2, =SLOTP
    ldr     r3, [r2]
    str     r0, [r3, #4]
    str     r1, [r3, #8]
    ldr     r0, [sp, #0]
    str     r0, [r3, #0]
    adds    r3, #12
    str     r3, [r2]

done:
    pop     {r0, r1, r2, r3}

    push    {r4, r5, lr}                @ 位移指令 1
    mov     r5, r0                      @ 位移指令 2
    ldr     ip, =BACK
    bx      ip
