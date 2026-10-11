.syntax unified
.arm
.text
/* proflog — 記下 FUN_c043a158(obj, profile_id, x) 的 profile_id。
 *
 * 源碼(反編譯)顯示這個函式用 mapping[profile_id](mapping_base = 0xC0BD05D4)
 * 取得 PARAM 的列索引,再把那 65 字載進 obj+0x5C —— 也就是我們的 canvas。
 * 所以「回放用 FHD 幾何」等於「這裡被帶著 profile_id = 175 呼叫」。
 *
 * 同時記下當下引擎的畫格率浮點,-1.0 表示回放。
 *   0xC0733400  筆數,之後每筆 8 bytes {profile_id, fps}
 */
.equ CFG,  0xC31DF564
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
    mov     r2, #0
scan:
    cmp     r2, r3
    beq     addent
    add     r0, ip, r2, lsl #3
    ldr     r0, [r0, #8]
    cmp     r0, r1
    beq     out
    add     r2, r2, #1
    b       scan
addent:
    cmp     r3, #10
    bhs     out
    add     r0, ip, r3, lsl #3
    str     r1, [r0, #8]
    LDA     r2, CFG
    ldr     r2, [r2, #0x10]
    str     r2, [r0, #12]
    add     r3, r3, #1
    str     r3, [ip]
out:
    pop     {r0, r2, r3, ip, lr}
    push    {r4, r5, r6, lr}        @ displaced
    LDA     ip, BACK
    bx      ip
