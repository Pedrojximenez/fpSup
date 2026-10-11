.syntax unified
.arm
.text
/* ============================================================================
 * rowprobe — 唯讀。記錄 FUN_c043a158 每次拿到的 (寬,高) 與 selector。
 * ============================================================================
 * 掛點與 rowpatch_v4 相同:0xC043A19C,位移指令 `mov r0,r4`。
 * 差別是這支「不改任何東西」,只把看到的幾何去重後記下來。
 *
 * 用途:選單第三列選下去之後,錄一小段,回讀 log 就知道那一列送進來的
 * 幾何長什麼樣 —— 也就是 rowpatch 的守衛該改成比對什麼。
 *
 *   0xC072FA60  count
 *   +0x04       8 筆 × 8 bytes:  key = (w<<16 | h),  selector
 * ========================================================================== */

.equ LOG,  0xC072FA60
.equ ROW,  0x5C
.equ SLOTS, 8

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global entry
entry:
    push    {r0, r1, r2, r3, r6, r7, ip, lr}   @ 八個:堆疊維持八位元組對齊

    add     r1, r4, #ROW
    ldr     r0, [r1]                    @ 寬
    ldr     r6, [r1, #4]                @ 高
    orr     r0, r6, r0, lsl #16         @ key

    LDA     ip, LOG
    ldr     r3, [ip]                    @ 已記錄筆數
    cmp     r3, #SLOTS
    bhs     out                         @ 滿了就不再記

    add     r1, ip, #4
    mov     r2, r3
scan:
    cmp     r2, #0
    beq     append
    ldr     r7, [r1]
    cmp     r7, r0
    beq     out                         @ 這組幾何記過了
    add     r1, r1, #8
    sub     r2, r2, #1
    b       scan

append:
    str     r0, [r1]
    str     r5, [r1, #4]
    add     r3, r3, #1
    str     r3, [ip]

out:
    pop     {r0, r1, r2, r3, r6, r7, ip, lr}
    mov     r0, r4                      @ 位移指令
    bx      lr
