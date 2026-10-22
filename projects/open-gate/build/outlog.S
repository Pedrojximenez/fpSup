.syntax unified
.arm
.text
/* outlog — C0437E98 是 `return *(obj + idx*8)`。記下 idx==0 的每個不同 obj
 * 以及它當下回傳的描述子指標,最多 8 筆,之後從主機端讀描述子內容。
 *   0xC0731E00  筆數    +0x04+i*8  obj    +0x08+i*8  ptr    0xC0731E48 總呼叫數 */
.equ LOG,  0xC0731E00
.equ BACK, 0xC0437E9C
.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm
.global entry
entry:
    cmp     r1, #0
    bne     out
    push    {r0, r1, r2, r3, ip, lr}
    LDA     ip, LOG
    ldr     r2, [ip, #0x48]          @ 總呼叫數
    add     r2, r2, #1
    str     r2, [ip, #0x48]
    LDA     r2, 0xC0000000           @ obj 必須像指標
    cmp     r0, r2
    blo     done
    LDA     r2, 0xC4000000
    cmp     r0, r2
    bhs     done
    ldr     r3, [r0]                 @ idx 0 的描述子
    ldr     r2, [ip]                 @ 現有筆數
    mov     r1, #0
scan:
    cmp     r1, r2
    beq     addent
    add     lr, ip, r1, lsl #3
    ldr     lr, [lr, #4]
    cmp     lr, r0
    beq     done
    add     r1, r1, #1
    b       scan
addent:
    cmp     r2, #8
    bhs     done
    add     lr, ip, r2, lsl #3
    str     r0, [lr, #4]
    str     r3, [lr, #8]
    add     r2, r2, #1
    str     r2, [ip]
done:
    pop     {r0, r1, r2, r3, ip, lr}
out:
    push    {r4, r5, lr}             @ displaced
    LDA     ip, BACK
    bx      ip
