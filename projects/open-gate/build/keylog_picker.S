.syntax unified
.arm
.text
/* ============================================================================
 * keylog — 唯讀。記錄 FUN_c043ccf8(obj, table, key) picker 每次被呼叫時的 table 與 key。
 * ============================================================================
 * 掛在函式進入點 0xC043CCF8,原指令 push {r4,r5,r6,r7,r10,r11,lr} 位移後補回。
 * r0=obj  r1=table  r2=key(15 bytes 字串)
 *
 * 0xC0730000  count
 * +0x04       12 筆 × 24 bytes: { table, key[0..15] }
 * 依 key 的前 8 bytes 去重。
 * ========================================================================== */

.equ LOG,   0xC0730000
.equ SLOTS, 12
.equ BACK,  0xC043CCFC

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global entry
entry:
    push    {r0, r1, r2, r3, ip, lr}

    LDA     ip, LOG
    ldr     r0, [ip]                    @ count
    cmp     r0, #SLOTS
    bhs     out
    add     r1, ip, #4                  @ entry ptr
    mov     r3, r0                      @ remaining

scan:
    cmp     r3, #0
    beq     append
    ldr     lr, [r1, #4]
    ldr     r0, [r2]
    cmp     lr, r0
    bne     nextent
    ldr     lr, [r1, #8]
    ldr     r0, [r2, #4]
    cmp     lr, r0
    beq     out                         @ 這個鍵記過了
nextent:
    add     r1, r1, #24
    sub     r3, r3, #1
    b       scan

append:
    ldr     lr, [sp, #4]                @ 原本的 r1 = table base
    str     lr, [r1]
    ldr     lr, [r2]
    str     lr, [r1, #4]
    ldr     lr, [r2, #4]
    str     lr, [r1, #8]
    ldr     lr, [r2, #8]
    str     lr, [r1, #12]
    ldr     lr, [r2, #12]
    str     lr, [r1, #16]
    ldr     r0, [ip]
    add     r0, r0, #1
    str     r0, [ip]

out:
    pop     {r0, r1, r2, r3, ip, lr}
    push    {r4, r5, r6, r7, r10, r11, lr}   @ 位移的原指令
    LDA     ip, BACK
    bx      ip
