.syntax unified
.arm
.text
/* profseq — FUN_c043a158(obj, profile_id, x) 的 profile_id,環形最近 8 筆。
 *
 * 不用判別條件。先前 proflog 用「引擎畫格率 == -1」標記回放,
 * 但引擎組態是在配置器跑完之後才寫的,所以那個標記不可信 ——
 * keyseq 已證明同一個閘讓 keyring 漏掉了回放的全部呼叫。
 *   0xC0733400  總呼叫數   0xC0733410 起每筆 4 bytes */
.equ LOG,  0xC0733400
.equ BACK, 0xC043A15C
.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm
.global entry
entry:
    push    {r0, r2, r3, ip, lr}
    LDA     ip, LOG
    ldr     r3, [ip]
    and     r2, r3, #7
    add     r0, ip, r2, lsl #2
    str     r1, [r0, #16]
    add     r3, r3, #1
    str     r3, [ip]
    pop     {r0, r2, r3, ip, lr}
    push    {r4, r5, r6, lr}        @ displaced
    LDA     ip, BACK
    bx      ip
