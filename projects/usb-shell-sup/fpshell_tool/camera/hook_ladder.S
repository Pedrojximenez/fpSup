.syntax unified
.arm
.text
/* 二分階梯:從「什麼都不做」開始,一次加一項,找出讓錄影凍結的那一項。
 *
 * 背景:自己寫的區塊 hook 在錄影一開始就凍結,而且 ACTIVE=0(完全不碰檔案)也一樣。
 * 但 stage5 掛在同一個位置、在錄影中跑了好幾週都沒事。所以差別不在「有沒有 hook」,
 * 是我的程式碼裡某一項。與其猜,不如從零開始一項項加。
 *
 * LEVEL(0xC072F480)決定做到哪一層,主機可改:
 *   0  只串接原指令,其餘什麼都不做   ← 真正的對照組
 *   1  + 寫計數器到 cave(不在 bufmem 池裡)
 *   2  + 寫計數器到 bufmem 池尾(0x44F6BE00,我們偷佔的那塊)
 *   3  + 讀陀螺 ring 的 head
 *   4  + 從 ring 複製資料到 cave 緩衝
 *
 * 每一層都只多做一件事。錄影凍結在哪一層,兇手就是那一層加的東西。
 */

.equ CHAIN,     0xC01EC6F9      /* 被取代的原指令:BLX 0xC01EC6F9 */
.equ LEVEL,     0xC072F480
.equ CAVE_CNT,  0xC072F4A0      /* cave 區計數器,不在 bufmem 池裡 */
.equ POOL_CNT,  0x44F6BE34      /* 池尾計數器 */
.equ CAVE_BUF,  0xC072F4C0      /* 64 bytes,cave 區 */
.equ RING_PTR,  0xC31E3FCC

.macro la reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global hook_entry
hook_entry:
    push    {r3-r11, lr}
    la      ip, CHAIN
    blx     ip
    mov     r11, r0

    la      r10, LEVEL
    ldr     r10, [r10]
    cmp     r10, #0
    beq     done                     @ level 0:什麼都不做

    la      r0, CAVE_CNT             @ level 1:寫 cave 計數器
    ldr     r1, [r0]
    add     r1, r1, #1
    str     r1, [r0]
    cmp     r10, #1
    beq     done

    la      r0, POOL_CNT             @ level 2:寫池尾計數器
    ldr     r1, [r0]
    add     r1, r1, #1
    str     r1, [r0]
    cmp     r10, #2
    beq     done

    la      r0, RING_PTR             @ level 3:讀 ring head
    ldr     r0, [r0]
    ldr     r9, [r0, #0x60]
    ldr     r8, [r9]
    la      r0, CAVE_CNT
    str     r8, [r0, #4]
    cmp     r10, #3
    beq     done

    la      r0, CAVE_CNT             @ level 4:從 ring 複製 32 bytes
    ldr     r7, [r0, #8]             @ 上次 head
    cmp     r7, #0
    moveq   r7, r8
    str     r8, [r0, #8]
    cmp     r8, r7
    bls     done
    sub     r1, r8, r7
    cmp     r1, #32
    movhi   r1, #32
    mov     r0, r7
    la      r2, CAVE_BUF
1:  ldrb    r3, [r0], #1
    strb    r3, [r2], #1
    subs    r1, r1, #1
    bne     1b
done:
    mov     r0, r11
    pop     {r3-r11, pc}
