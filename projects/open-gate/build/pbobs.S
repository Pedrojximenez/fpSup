.syntax unified
.arm
.text
/* ============================================================================
 * pbobs — 純觀測。回放時到底有沒有「影片回放類」的畫布經過 0xC043A19C?
 * ============================================================================
 * og3kpbrow 的守衛擋掉全部 4906 次,而 reject 只有一個計數器,分不出是
 * 類別守衛還是尺寸守衛擋的(最後退回寬度 1620 = 顯示畫布寬,不是片源寬)。
 *
 * 這一版什麼都不改,只記錄。過濾條件是畫布 +0x80 的 bit16 ——
 * 那個位元就是「壓縮位元流」,12 個影片回放 profile 全有,其餘 494 個全沒有。
 * 依 profile id 去重,最多 12 格。
 *
 * LOG 佈局(0xC0732600):
 *   +0x00 總呼叫次數
 *   +0x04 影片回放類的次數
 *   +0x08 已用格數
 *   +0x10 起,每格 32 bytes:
 *         pid, +0x44, +0x80, +0x0C, +0x10, +0x1C, obj+8, obj+0xC
 * ========================================================================== */

.equ ROW, 0x5C
.equ LOG, 0xC0732600
.equ SLOTS, 12

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global entry
entry:
    push    {r0, r1, r2, r3, r6, r7, ip, lr}

    add     r1, r4, #ROW                @ 畫布
    LDA     ip, LOG

    ldr     r0, [ip]                    @ 總呼叫次數
    add     r0, r0, #1
    str     r0, [ip]

    movw    r0, #0x80
    ldr     r2, [r1, r0]                @ 畫布 +0x80
    tst     r2, #0x10000                @ 壓縮位元流?
    beq     out

    ldr     r0, [ip, #4]
    add     r0, r0, #1
    str     r0, [ip, #4]

    ldr     r7, [ip, #8]                @ 已用格數
    add     r2, ip, #0x10               @ 第一格
    mov     r0, #0
dloop:
    cmp     r0, r7
    bge     newslot
    ldr     r3, [r2]
    cmp     r3, r5                      @ 這個 profile 記過了?
    beq     out
    add     r2, r2, #32
    add     r0, r0, #1
    b       dloop

newslot:
    cmp     r7, #SLOTS
    bge     out
    add     r7, r7, #1
    str     r7, [ip, #8]

    str     r5, [r2]                    @ profile id
    movw    r0, #0x44
    ldr     r3, [r1, r0]
    str     r3, [r2, #4]
    movw    r0, #0x80
    ldr     r3, [r1, r0]
    str     r3, [r2, #8]
    ldr     r3, [r1, #0x0C]
    str     r3, [r2, #12]
    ldr     r3, [r1, #0x10]
    str     r3, [r2, #16]
    ldr     r3, [r1, #0x1C]
    str     r3, [r2, #20]
    ldr     r3, [r4, #0x08]
    str     r3, [r2, #24]
    ldr     r3, [r4, #0x0C]
    str     r3, [r2, #28]

out:
    pop     {r0, r1, r2, r3, r6, r7, ip, lr}
    mov     r0, r4                      @ 位移指令
    bx      lr
