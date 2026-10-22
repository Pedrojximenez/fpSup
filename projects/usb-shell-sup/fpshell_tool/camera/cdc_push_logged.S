.syntax unified
.arm
.text
/* CDC 推送探針 —— 這版把結果寫進卡片。
 *
 * 前一版在 CDC 模式下推了 90 秒、零回應,但**完全沒有診斷資訊**:探針有沒有跑?
 * StartTransfer 回什麼?端點 enable 了嗎?全都不知道。切到 CDC 之後沒有回饋管道,
 * 所以必須自己把結果寫到卡上,重開機後再讀。
 *
 * 流程:掛 hook + ACTIVE=1 → 靜默 30 秒(給我時間切 CDC)→ 快照 USB 狀態
 *       → 輪流試候選並記錄 → 全部試完寫檔一次 → 停止。
 *
 * 日誌 \CDCLOG.BIN:
 *   +0x00  'CDLG' / tick / DALEPENA / DALEPENA_SH
 *   +0x10  端點指標表 0xC31E3264 的 16 項
 *   +0x50  TRB 結構 0xC31E32C0 的 7 項(每項 0x10)
 *   +0xC0  10 筆記錄 x 24 bytes:{cand, idx, phys, start_ret, wait_ret, ctrl_after}
 */

.equ CHAIN,      0xC01EC6F9
.equ ACTIVE,     0xC072F480
.equ ST,         0x44F6BE00
.equ PAYLOAD,    0x44F6BF00
.equ PAYLOAD_DMA,0x04F6BF00
.equ LOG,        0x44F6C000
.equ PATHBUF,    0x44F6BE80
.equ FILEOBJ,    0x44F6BEC0
.equ EPTAB,      0xC31E3264
.equ TRBARR,     0xC31E32C0
.equ DALEPENA,   0x2100C720
.equ DALEPENA_SH,0xC31E398C
.equ FN_EPENABLE,0xC01E62A9      /* FUN_c01e62a9(logical_ep):端點 bring-up */
.equ FN_START,   0xC01E6B81
.equ FN_WAIT,    0xC01E4E81
.equ ARM_DELAY,  2700            /* 30 秒:給我時間切到 CDC */
.equ TICKS_PER,  180
.equ NCAND,      3
.equ NREC,       10

.macro la reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global hook_entry
hook_entry:
    push    {r3-r11, lr}
    la      ip, CHAIN
    blx     ip
    mov     r11, r0

    la      r10, ST
    ldr     r0, [r10]
    la      r1, 0x43444C47           /* 'CDLG' */
    cmp     r0, r1
    beq     1f
    str     r1, [r10]
    mov     r0, #0
    str     r0, [r10, #4]            /* tick */
    str     r0, [r10, #8]            /* cand */
    str     r0, [r10, #12]           /* nrec */
    str     r0, [r10, #16]           /* arm delay */
    str     r0, [r10, #20]           /* snapshot done */
    str     r0, [r10, #24]           /* file written */
1:
    la      r0, ACTIVE
    ldr     r0, [r0]
    cmp     r0, #0
    beq     out
    ldr     r0, [r10, #24]
    cmp     r0, #0
    bne     out                      /* 已寫檔,收工 */

    ldr     r0, [r10, #16]
    movw    r1, #ARM_DELAY
    cmp     r0, r1
    bhs     2f
    add     r0, r0, #1
    str     r0, [r10, #16]
    b       out
2:
    /* ---- 一次性快照 ---- */
    ldr     r0, [r10, #20]
    cmp     r0, #0
    bne     3f
    mov     r0, #1
    str     r0, [r10, #20]
    la      r4, LOG
    la      r0, 0x43444C47
    str     r0, [r4]
    ldr     r0, [r10, #16]
    str     r0, [r4, #4]
    la      r0, DALEPENA
    ldr     r0, [r0]
    str     r0, [r4, #8]
    la      r0, DALEPENA_SH
    ldr     r0, [r0]
    str     r0, [r4, #12]
    la      r5, EPTAB
    add     r6, r4, #0x10
    mov     r7, #0
4:  ldr     r0, [r5, r7, lsl #2]
    str     r0, [r6, r7, lsl #2]
    add     r7, r7, #1
    cmp     r7, #16
    blo     4b
    la      r5, TRBARR
    add     r6, r4, #0x50
    mov     r7, #0
5:  ldr     r0, [r5, r7, lsl #2]
    str     r0, [r6, r7, lsl #2]
    add     r7, r7, #1
    cmp     r7, #28
    blo     5b

    /* ---- 對 CDC 的端點做 bring-up ----
     * 對照實驗證明:探針在 vendor 模式下完全正常(收到 7 次 CDCP),但在 CDC 模式下
     * 連 vendor 的 (4,9) 都送不出去。差別是 worker 開機時對 vendor 端點做過
     * FUN_c01e62a9 + DALEPENA。CDC 沒有消費者,韌體很可能只列舉、沒 bring-up ——
     * 這也解釋最早的觀察:第一次寫入成功、之後全部塞住。 */
    mov     r0, #1                   /* EP 0x01 OUT */
    la      ip, FN_EPENABLE
    blx     ip
    str     r0, [r4, #0xB0]          /* 記錄回傳 */
    mov     r0, #2                   /* EP 0x82 IN */
    la      ip, FN_EPENABLE
    blx     ip
    str     r0, [r4, #0xB4]
    mov     r0, #3                   /* EP 0x83 IN */
    la      ip, FN_EPENABLE
    blx     ip
    str     r0, [r4, #0xB8]
    la      r0, DALEPENA
    ldr     r1, [r0]
    str     r1, [r4, #0xBC]          /* bring-up 後的 DALEPENA */
3:
    /* ---- 每 2 秒一組候選 ---- */
    ldr     r0, [r10, #4]
    add     r0, r0, #1
    str     r0, [r10, #4]
    movw    r1, #TICKS_PER
    cmp     r0, r1
    blo     out
    mov     r0, #0
    str     r0, [r10, #4]

    ldr     r4, [r10, #8]
    add     r0, r4, #1
    cmp     r0, #NCAND
    movhs   r0, #0
    str     r0, [r10, #8]
    adr     r5, cand_table
    add     r5, r5, r4, lsl #3
    ldr     r6, [r5]                 /* 表索引 */
    ldr     r7, [r5, #4]             /* 實體端點 */

    /* 酬載 */
    la      r0, PAYLOAD
    la      r1, 0x50434443
    str     r1, [r0]
    str     r4, [r0, #4]
    str     r6, [r0, #8]
    str     r7, [r0, #12]
    la      r1, 0xAABBCCDD
    str     r1, [r0, #16]
    str     r1, [r0, #20]
    str     r1, [r0, #24]
    str     r1, [r0, #28]

    /* 填 TRB */
    la      r0, EPTAB
    ldr     r5, [r0, r6, lsl #2]
    cmp     r5, #0
    moveq   r8, #0xE0                /* 記錄:指標為零 */
    beq     6f
    la      r1, PAYLOAD_DMA
    str     r1, [r5]
    mov     r1, #0
    str     r1, [r5, #4]
    mov     r1, #32
    str     r1, [r5, #8]
    movw    r1, #0x0813
    str     r1, [r5, #0xC]
    dsb
    mov     r0, r7
    la      ip, FN_START
    blx     ip
    mov     r8, r0                   /* StartTransfer 回傳 */
    mov     r0, r6
    movw    r1, #2000
    la      ip, FN_WAIT
    blx     ip
    mov     r9, r0                   /* wait 回傳 */
6:
    /* 記錄 */
    la      r0, LOG
    add     r0, r0, #0xC0
    ldr     r1, [r10, #12]
    mov     r2, #24
    mla     r0, r1, r2, r0
    str     r4, [r0]
    str     r6, [r0, #4]
    str     r7, [r0, #8]
    str     r8, [r0, #12]
    str     r9, [r0, #16]
    cmp     r5, #0
    ldrne   r2, [r5, #0xC]
    moveq   r2, #0
    str     r2, [r0, #20]
    add     r1, r1, #1
    str     r1, [r10, #12]
    cmp     r1, #NREC
    blo     out

    /* ---- 全部試完,寫檔一次 ---- */
    mov     r0, #1
    str     r0, [r10, #24]
    adr     r0, s_path
    la      r1, PATHBUF
7:  ldrb    r2, [r0], #1
    strb    r2, [r1], #1
    cmp     r2, #0
    bne     7b
    la      ip, 0xC0444658
    blx     ip
    mov     r1, #0
    la      ip, 0xC0444698
    blx     ip
    mov     r1, r0
    la      r0, FILEOBJ
    la      ip, 0xC0365E90
    blx     ip
    la      r0, FILEOBJ
    la      r1, PATHBUF
    mov     r2, #7
    la      ip, 0xC0365FB0
    blx     ip
    cmp     r0, #0
    beq     out
    la      r0, FILEOBJ
    la      r1, LOG
    movw    r2, #0x1B0
    la      ip, 0xC03660E8
    blx     ip
    la      r0, FILEOBJ
    la      ip, 0xC0366020
    blx     ip
    la      r0, FILEOBJ
    mov     r1, #2
    la      ip, 0xC0365ED0
    blx     ip
out:
    mov     r0, r11
    pop     {r3-r11, pc}

.align 2
cand_table:
    .word 2, 5          /* EP 0x82 IN —— bring-up 之後再試 */
    .word 4, 9          /* 對照:vendor 組合 */
    .word 3, 7          /* EP 0x83 IN */
    .word 4, 9          /* ★ 對照組:worker 實際在用的組合(索引 4 / 實體 9)
                         * 沒有它就分不出「機制在 CDC 模式下失效」跟
                         * 「我推導的 CDC 索引錯了」—— 前一輪漏了這組。 */
    .word 2, 5          /* EP 0x82 IN,由描述元推導 */
    .word 3, 7          /* EP 0x83 IN */
    .word 1, 2          /* EP 0x01 OUT(方向不對,但看回傳值) */
    .word 2, 9
.align 2
s_path: .asciz "\\CDCLOG.BIN"
.align 2
