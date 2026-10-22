.syntax unified
.arm
.text
/* vtlog — 在 FUN_c043ccf8 進入點記下物件與它的函式指標表。
 * r0 = obj。表在 *(obj+8),解析度名發射器是該表 +0x0C,幀率是 +0x10。
 *   0xC0730900  flag
 *   +0x04 obj   +0x08 表位址   +0x0C slot[0x0C]   +0x10 slot[0x10]
 *   +0x14 slot[0x00] +0x18 slot[0x04] +0x1C slot[0x08] +0x20 slot[0x14]  */
.equ LOG,  0xC0730900
.equ BACK, 0xC043CCFC
.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm
.global entry
entry:
    push    {r3, r4, ip, lr}
    LDA     ip, LOG
    ldr     r3, [ip]
    cmp     r3, #0
    bne     out
    str     r0, [ip, #4]
    ldr     r4, [r0, #8]
    str     r4, [ip, #8]
    ldr     r3, [r4, #0x0C]
    str     r3, [ip, #0x0C]
    ldr     r3, [r4, #0x10]
    str     r3, [ip, #0x10]
    ldr     r3, [r4, #0x00]
    str     r3, [ip, #0x14]
    ldr     r3, [r4, #0x04]
    str     r3, [ip, #0x18]
    ldr     r3, [r4, #0x08]
    str     r3, [ip, #0x1C]
    ldr     r3, [r4, #0x14]
    str     r3, [ip, #0x20]
    mov     r3, #1
    str     r3, [ip]
out:
    pop     {r3, r4, ip, lr}
    push    {r4, r5, r6, r7, r10, r11, lr}
    LDA     ip, BACK
    bx      ip
