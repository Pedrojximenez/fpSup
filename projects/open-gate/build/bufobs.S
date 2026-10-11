.syntax unified
.arm
.text
/* ============================================================================
 * bufobs — 量回放影格緩衝的位元組數。純觀測,不改任何東西。
 * ============================================================================
 * FUN_c05c2d10(obj, nbytes)(src/library/CinemaDngPlay/src/DngBufferInfo.cpp):
 *   uVar1 = (nbytes + 0x1fff) & 0xfffff000       ; 向上對齊 4K 再多一頁
 *   配置 0x6f090 的描述子陣列(每筆 0x5ec = 1516 bytes,最多 300 筆)
 *   然後**不斷配置 uVar1 大小的緩衝直到失敗**,每個都成為一格的影格緩衝
 *
 * nbytes 來自 XC_CinemaDngPlay+0xA0,而整個 library 裡只有建構子 CPlayM
 * 把它歸零,沒有任何地方寫入非零值 —— 反編譯可能漏了,所以直接量。
 *
 * 如果 OG3K 的 nbytes 明顯小於影格實際大小(3032x2012 未壓縮 12-bit =
 * 9,150,576 bytes),那就是花屏的根因:緩衝只有需要的一小部分。
 * 對照值:FHD 1936x1090 = 3,165,360。
 *
 * Hook:0xC05C2D10,B,位移指令是 push {r4, r5, r6, r7, sl, lr}。
 *
 * LOG(0xC0732300):+0x00 呼叫次數,+0x04 起最多 6 筆 nbytes(去重)
 * ========================================================================== */

.equ LOG,   0xC0732300
.equ BACK,  0xC05C2D14
.equ SLOTS, 6

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global entry
entry:
    push    {r2, r3, ip, lr}
    LDA     ip, LOG

    ldr     r2, [ip]                    @ 呼叫次數
    add     r2, r2, #1
    str     r2, [ip]

    ldr     r3, [ip]                    @ 去重掃描
    mov     r2, #0
scan:
    cmp     r2, #SLOTS
    bhs     done
    add     r3, ip, r2, lsl #2
    ldr     r3, [r3, #4]
    cmp     r3, #0
    beq     add_it
    cmp     r3, r1
    beq     done                        @ 記過了
    add     r2, r2, #1
    b       scan
add_it:
    add     r3, ip, r2, lsl #2
    str     r1, [r3, #4]
done:
    pop     {r2, r3, ip, lr}
    push    {r4, r5, r6, r7, sl, lr}    @ 位移指令
    LDA     ip, BACK
    bx      ip
