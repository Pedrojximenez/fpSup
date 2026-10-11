.syntax unified
.arm
.text
/* reqlog — 掛在解析度名發射器 FUN_c0437b48 進入點 0xC0437B48。
 *   r0 = obj   r1 = key buffer   r2 = request
 * 把 request 的前 0x30 bytes 整筆記下來,依內容去重(比對前 0x30 bytes)。
 *   0xC0730000  count
 *   +0x04       4 筆 × 0x30 bytes
 * 原指令 push {r4,r5,r6,r7,r8,r9,r11,lr} 位移後補回。 */
.equ LOG,   0xC0730000
.equ SLOTS, 4
.equ SPAN,  0x30
.equ BACK,  0xC0437B4C
.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm
.global entry
entry:
    push    {r0, r1, r3, r4, ip, lr}
    LDA     ip, LOG
    ldr     r0, [ip]
    cmp     r0, #SLOTS
    bhs     out
    add     r1, ip, #4
    mov     r3, r0
scan:
    cmp     r3, #0
    beq     append
    mov     r0, #0
cmp1:
    ldr     r4, [r1, r0]
    ldr     lr, [r2, r0]
    cmp     r4, lr
    bne     nextent
    add     r0, r0, #4
    cmp     r0, #SPAN
    blt     cmp1
    b       out                         @ 完全相同,記過了
nextent:
    add     r1, r1, #SPAN
    sub     r3, r3, #1
    b       scan
append:
    mov     r0, #0
copy:
    ldr     r4, [r2, r0]
    str     r4, [r1, r0]
    add     r0, r0, #4
    cmp     r0, #SPAN
    blt     copy
    ldr     r0, [ip]
    add     r0, r0, #1
    str     r0, [ip]
out:
    pop     {r0, r1, r3, r4, ip, lr}
    push    {r4, r5, r6, r7, r8, r9, r11, lr}   @ 位移的原指令
    LDA     ip, BACK
    bx      ip
