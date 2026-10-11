.syntax unified
.arm
.text
/* asplog v2 — 記下 (r1, lr) 配對。r1 是原生 fit 收到的參數指標,
 * lr 是呼叫端的返回位址 —— 直接指出是誰用 enum 3 呼叫的。
 *   0xC0732500  筆數,之後每筆 8 bytes {r1, lr},最多 8 筆 */
.equ LOG,  0xC0732500
.equ BACK, 0xC02F43AC
.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm
.global entry
entry:
    push    {r0, r2, r3, ip, lr}
    LDA     ip, LOG
    ldr     r2, [ip]
    mov     r3, #0
scan:
    cmp     r3, r2
    beq     addent
    add     r0, ip, r3, lsl #3
    ldr     r0, [r0, #4]
    cmp     r0, r1
    beq     done
    add     r3, r3, #1
    b       scan
addent:
    cmp     r2, #8
    bhs     done
    add     r0, ip, r2, lsl #3
    str     r1, [r0, #4]
    ldr     r3, [sp, #16]            @ 進入時的 lr(push 的最後一個)
    str     r3, [r0, #8]
    add     r2, r2, #1
    str     r2, [ip]
done:
    pop     {r0, r2, r3, ip, lr}
    push    {r4, r5, r6, r7, lr}     @ displaced
    LDA     ip, BACK
    bx      ip
