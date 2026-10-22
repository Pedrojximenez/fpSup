.syntax unified
.arm
.text
/* ============================================================================
 * xcitrace — 攔 gui image log 的回呼,順手抄一段呼叫端的堆疊。
 * ============================================================================
 * 目的:找出 .xci 的來源 blob 在記憶體哪裡。
 *
 * FUN_c0601f98(handle, path) 是 XCI 解碼器。它拿到的不是路徑而是已經定位好
 * 的資料控制代碼:
 *     FUN_c05d7118(handle, &data_ptr)   data_ptr = *(handle[0] + 0xC)
 *     FUN_c05d7100(handle, &size)       size     = *(handle[0] + 4)
 * 那兩個值解碼時都在 FUN_c0601f98 的區域變數裡(local_11c / local_118)。
 *
 * 解碼成功後它呼叫 _DAT_c37cecf8(basename, w, h) —— 就是 `gui image log 1`
 * 掛上去的那個回呼(原廠 FUN_c055fdc8)。那個呼叫發生在同一個堆疊框裡,
 * 所以在回呼裡把呼叫端的堆疊抄下來,就能撈到 data_ptr。
 *
 * 這裡不改任何指令 —— 只換 0xC37CECF8 那個函式指標,還原就是寫回 0xC055FDC8。
 * 而且目標是 ARM(bit0 = 0),不用處理 Thumb 交互。
 *
 * 記錄格式,每筆 128 bytes:
 *     +0x00 r0 = basename 指標
 *     +0x04 r1 = 寬
 *     +0x08 r2 = 高
 *     +0x0C lr = 呼叫點(應該在 FUN_c0601f98 內)
 *     +0x10 起 28 個字 = 呼叫端堆疊
 * ========================================================================== */

.equ SLOTP,  0xC07330F0         @ 下一筆的寫入位址(套用前由主機初始化成 LOGBEG)
.equ LOGEND, 0xC0734000
.equ STOCK,  0xC055FDC8         @ 原廠回呼,抄完轉交給它

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global entry
entry:
    push    {r0, r1, r2, r3, r4, r5, ip, lr}     @ 8 個字 = 32 bytes

    LDA     ip, SLOTP
    ldr     r4, [ip]
    LDA     r5, LOGEND
    cmp     r4, r5
    bhs     done                                 @ 滿了就只轉交,不再寫

    str     r0, [r4, #0]
    str     r1, [r4, #4]
    str     r2, [r4, #8]
    str     lr, [r4, #12]

    add     r4, r4, #16
    add     r5, sp, #32                          @ 呼叫時的 sp
    mov     r3, #0
copy:
    ldr     r0, [r5, r3]
    str     r0, [r4, r3]
    add     r3, r3, #4
    cmp     r3, #256                             @ 64 個字
    blo     copy

    add     r4, r4, #256                         @ 一筆共 272 bytes
    str     r4, [ip]

done:
    pop     {r0, r1, r2, r3, r4, r5, ip, lr}
    LDA     ip, STOCK
    bx      ip                                   @ 尾呼叫,lr 已還原
