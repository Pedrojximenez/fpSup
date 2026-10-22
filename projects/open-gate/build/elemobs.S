.syntax unified
.thumb
.text
/* ============================================================================
 * elemobs — 觀察用:記錄誰在建 0x34-byte 的元素物件。
 * ============================================================================
 * 目標 FUN_c05edc40 @0xC05EDC40(Thumb-2):
 *
 *     C05EDC40  B530   push {r4, r5, lr}
 *     C05EDC42  6B41   ldr  r1, [r0, #0x34]
 *     C05EDC44  6802   ldr  r2, [r0, #0]        ← 跳回這裡,r2 立刻被覆寫
 *     C05EDC46  4605   mov  r5, r0
 *     C05EDC48  2034   movs r0, #0x34
 *     C05EDC4A  4790   blx  r2
 *
 * 掛法:把前 4 bytes 換成 Thumb-2 的 B.W(不是 BL,所以 lr 不會被動到),
 * payload 記錄 (r0, lr) 之後原樣執行那兩道位移指令再跳回 0xC05EDC45。
 *
 * lr 會指出是直譯器 FUN_c05e6400 裡的哪一條分支在建元素 —— 那就是之後
 * 要加第三個槽位的地方。
 *
 * 這一版只記錄,不改任何行為。
 *
 * 紀錄:每筆 8 bytes,+0x00 = r0(建構器的參數物件),+0x04 = lr(呼叫點)
 * ========================================================================== */

.equ SLOTP,  0xC07330F0         @ 下一筆的寫入位址(套用前由主機初始化)
.equ LOGEND, 0xC0734000
.equ BACK,   0xC05EDC45         @ 位移指令之後,Thumb

.global entry
.thumb_func
entry:
    push    {r0, r1, r2, r3}

    ldr     r2, =SLOTP
    ldr     r3, [r2]
    ldr     r1, =LOGEND
    cmp     r3, r1
    bhs     done

    str     r0, [r3, #0]
    mov     r1, lr
    str     r1, [r3, #4]
    @ 再抄 14 個字的呼叫端堆疊 —— 我們是被 BL 呼叫的,所以 sp 指著直譯器的框架。
    @ push {r0-r3} 用掉 16 bytes,所以呼叫時的 sp = sp + 16。
    add     r1, sp, #16
    movs    r0, #0
copy:
    ldr     r2, [r1, r0]
    str     r2, [r3, r0]
    adds    r0, #4
    cmp     r0, #56
    blo     copy
    ldr     r2, =SLOTP
    adds    r3, #64
    str     r3, [r2]

done:
    pop     {r0, r1, r2, r3}

    push    {r4, r5, lr}                @ 位移指令 1
    ldr     r1, [r0, #0x34]             @ 位移指令 2
    ldr     r2, =BACK                   @ r2 在 0xC05EDC44 會立刻被覆寫,可以借用
    bx      r2
