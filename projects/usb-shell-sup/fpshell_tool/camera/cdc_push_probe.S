.syntax unified
.arm
.text
/* 在 CDC 模式下,試著從韌體管理的端點推資料給主機。
 *
 * 背景:CDC 是原廠 gadget,端點由韌體註冊與管理,實測跟錄影完全共存。
 * 若能從它的 IN 端點推資料,Bayer 串流「邊錄邊串」就成立,而且不需要
 * worker 那三處覆寫(ctx 模式、DALEPENA、描述元 hook)。
 *
 * 難處:切到 CDC 後 vendor 通道消失,沒有任何回饋管道。所以這裡**輪流試多組
 * 候選參數**,每組約 2 秒,酬載開頭寫上組別編號 —— 主機收到什麼就知道哪組對。
 *
 * TRB 結構陣列 @0xC31E32C0,每項 0x10:{bufptr, hi, size, ctrl}
 * 指標表 @0xC31E3264,每項 4 bytes,索引 = 端點編號(實測索引 4 = EP 0x84 IN)
 * StartTransfer 的參數是 DWC3 實體端點編號 = 2×邏輯 + 方向
 *   EP 0x84 IN → 9(worker 用的值,已驗證)
 *   EP 0x82 IN → 5      EP 0x83 IN → 7      EP 0x01 OUT → 2
 */

.equ CHAIN,      0xC01EC6F9
.equ ACTIVE,     0xC072F480
.equ ST,         0x44F6BE00      /* 狀態 */
.equ PAYLOAD,    0x44F6BF00      /* 64 B 酬載 */
.equ EPTAB,      0xC31E3264
.equ FN_START,   0xC01E6B81      /* StartTransfer(phys_ep) */
.equ FN_WAIT,    0xC01E4E81      /* wait(idx, timeout) */
.equ TICKS_PER,  180             /* ~90 Hz x 2 秒 */
.equ ARM_DELAY,  2700            /* ~90 Hz x 30 秒:裝上後先靜默,給我時間切模式 */
.equ NCAND,      5

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
    la      r1, 0x43444331           /* 'CDC1' */
    cmp     r0, r1
    beq     1f
    str     r1, [r10]
    mov     r0, #0
    str     r0, [r10, #4]            /* tick */
    str     r0, [r10, #8]            /* cand */
    str     r0, [r10, #12]           /* pushes */
    str     r0, [r10, #16]           /* 起始延遲計數 */
1:
    la      r0, ACTIVE
    ldr     r0, [r0]
    cmp     r0, #0
    beq     out

    /* 起始延遲:在 vendor 模式下絕不動作 —— 候選裡有索引 1/2/3,那些在 vendor
     * 模式下也有 armed 的 TRB,提早推會干擾正在用的端點。等我切到 CDC 之後才開始。 */
    ldr     r0, [r10, #16]
    movw    r1, #ARM_DELAY
    cmp     r0, r1
    bhs     2f
    add     r0, r0, #1
    str     r0, [r10, #16]
    b       out
2:
    ldr     r0, [r10, #4]
    add     r0, r0, #1
    str     r0, [r10, #4]
    movw    r1, #TICKS_PER
    cmp     r0, r1
    blo     out
    mov     r0, #0
    str     r0, [r10, #4]

    /* 取當前候選,並前進 */
    ldr     r4, [r10, #8]
    add     r0, r4, #1
    cmp     r0, #NCAND
    movhs   r0, #0
    str     r0, [r10, #8]

    /* 候選表:每筆 {表索引, StartTransfer 實體端點} */
    adr     r5, cand_table
    add     r5, r5, r4, lsl #3
    ldr     r6, [r5]                 /* 表索引 */
    ldr     r7, [r5, #4]             /* 實體端點 */

    /* ---- 準備酬載:'CDCP' + 候選編號 + 計數 ---- */
    la      r0, PAYLOAD
    la      r1, 0x50434443           /* 'CDCP' */
    str     r1, [r0]
    str     r4, [r0, #4]
    str     r6, [r0, #8]
    str     r7, [r0, #12]
    ldr     r1, [r10, #12]
    add     r1, r1, #1
    str     r1, [r10, #12]
    str     r1, [r0, #16]
    la      r1, 0xAABBCCDD
    str     r1, [r0, #20]
    str     r1, [r0, #24]
    str     r1, [r0, #28]

    /* ---- 填 TRB ---- */
    la      r0, EPTAB
    ldr     r5, [r0, r6, lsl #2]     /* 該端點的 TRB 結構(uncached 別名) */
    cmp     r5, #0
    beq     out
    la      r1, 0x04F6BF00           /* PAYLOAD 的 DMA 視角 */
    str     r1, [r5]
    mov     r1, #0
    str     r1, [r5, #4]
    mov     r1, #32
    str     r1, [r5, #8]
    movw    r1, #0x0813
    str     r1, [r5, #0xC]
    dsb

    /* ---- StartTransfer(實體端點) ---- */
    mov     r0, r7
    la      ip, FN_START
    blx     ip
    /* ---- 短等待,不要卡住陀螺執行緒 ---- */
    mov     r0, r6
    movw    r1, #2000
    la      ip, FN_WAIT
    blx     ip
out:
    mov     r0, r11
    pop     {r3-r11, pc}

.align 2
cand_table:
    .word 2, 5          /* EP 0x82 IN,實體 5   ← 最可能 */
    .word 2, 2          /* 同索引,實體用邏輯編號 */
    .word 3, 7          /* EP 0x83 IN,實體 7 */
    .word 1, 5          /* 索引 1,實體 5 */
    .word 2, 9          /* 索引 2,實體用 worker 那個值 */
