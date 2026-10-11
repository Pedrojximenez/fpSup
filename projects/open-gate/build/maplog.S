.syntax unified
.arm
.text
/* maplog — 掛在 FUN_c06ccd10 進入點,記下 (key, table, count),依三者去重。
 *   r0 = key   r1 = table   r2 = count   r3 = default
 *   0xC0731C20  count
 *   +0x04       8 筆 × 16 bytes { key, table, count, - }               */
.equ LOG,   0xC0731C20
.equ SLOTS, 8
.equ BACK,  0xC06CCD14
.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm
.global entry
entry:
    push    {r4, r5, ip, lr}
    LDA     ip, LOG
    ldr     r4, [ip]
    cmp     r4, #SLOTS
    bhs     out
    add     r5, ip, #4
    mov     lr, r4
scan:
    cmp     lr, #0
    beq     append
    ldr     r4, [r5]
    cmp     r4, r0
    bne     nextent
    ldr     r4, [r5, #4]
    cmp     r4, r1
    bne     nextent
    ldr     r4, [r5, #8]
    cmp     r4, r2
    beq     out
nextent:
    add     r5, r5, #16
    sub     lr, lr, #1
    b       scan
append:
    str     r0, [r5]
    str     r1, [r5, #4]
    str     r2, [r5, #8]
    ldr     r4, [ip]
    add     r4, r4, #1
    str     r4, [ip]
out:
    pop     {r4, r5, ip, lr}
    push    {r4, r5, r6, r7, r10}       @ 位移的原指令(葉函式,沒有 lr)
    LDA     ip, BACK
    bx      ip
