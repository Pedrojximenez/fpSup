.syntax unified
.arm
.text
/* ============================================================================
 * pairlog — 唯讀。記錄 FUN_c06ccd10(key, table, count, default) 每次被呼叫時
 * 拿到的 (table, count)。這是筆記 §24 那條「enum -> 顯示狀態」的通用查表:
 *
 *     FUN_c06bd988(obj, enum) -> 虛擬呼叫 vtable+0x5C 取得 (table, count)
 *                             -> FUN_c06ccd10(enum, table, count, 0)
 *
 * 掛在 0xC06CCD10,原指令 push {r4,r5,r6,r7,r10} 位移後補回,回 0xC06CCD14。
 * 進入點的暫存器(由 0xC06CCD14 起的 mov 鏈確認):
 *     r0 = key(enum)   r1 = table   r2 = count   r3 = default
 *
 * 0xC0730000  count
 * +0x04       12 筆 x 12 bytes: { table, count, key }
 * 依 (table, count) 去重 —— 這個函式是全機共用的,不去重會瞬間塞滿。
 * ========================================================================== */

.equ LOG,   0xC0730000
.equ SLOTS, 12
.equ BACK,  0xC06CCD14

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global entry
entry:
    push    {r0, r1, r2, r3, ip, lr}

    LDA     ip, LOG
    ldr     r0, [ip]                    @ 已記幾筆
    cmp     r0, #SLOTS
    bhs     out
    add     r3, ip, #4                  @ 第一筆
    mov     lr, r0                      @ 還要掃幾筆

scan:
    cmp     lr, #0
    beq     append
    ldr     r0, [r3]
    cmp     r0, r1                      @ 同一張表?
    bne     nextent
    ldr     r0, [r3, #4]
    cmp     r0, r2                      @ 同一個 count?
    beq     out                         @ 記過了
nextent:
    add     r3, r3, #12
    sub     lr, lr, #1
    b       scan

append:
    str     r1, [r3]                    @ table
    str     r2, [r3, #4]                @ count
    ldr     r0, [sp]                    @ 進來時的 r0 = key
    str     r0, [r3, #8]
    ldr     r0, [ip]
    add     r0, r0, #1
    str     r0, [ip]

out:
    pop     {r0, r1, r2, r3, ip, lr}
    push    {r4, r5, r6, r7, r10}       @ 位移的原指令
    LDA     ip, BACK
    bx      ip
