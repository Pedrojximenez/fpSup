.syntax unified
.arm
.text
/* entlog — 記下分派器 0xC043C600 看到的每一個不同的 r5(表項指標),最多 10 個。
 * r5 在這裡一定是活的:分派器接著會逐一用範圍檢查判斷它屬於哪張表。
 *   0xC0733400  筆數,之後每筆 4 bytes */
.equ LOG,  0xC0733400
.equ BACK, 0xC043C604
.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm
.global entry
entry:
    push    {r0, r1, r3, ip, lr}
    LDA     ip, LOG
    LDA     r0, 0xC0000000
    cmp     r5, r0
    blo     out
    ldr     r3, [ip]                @ 現有筆數
    mov     r1, #0
scan:
    cmp     r1, r3
    beq     addent
    add     r0, ip, r1, lsl #2
    ldr     r0, [r0, #4]
    cmp     r0, r5
    beq     out
    add     r1, r1, #1
    b       scan
addent:
    cmp     r3, #10
    bhs     out
    add     r0, ip, r3, lsl #2
    str     r5, [r0, #4]
    add     r3, r3, #1
    str     r3, [ip]
out:
    pop     {r0, r1, r3, ip, lr}
    movw    r2, #0x5b50             @ displaced
    LDA     ip, BACK
    bx      ip
