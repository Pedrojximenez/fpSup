.syntax unified
.arm
.text
/* ============================================================================
 * gsobs — 統計 HCG 決策函式 v30 被用到的 gain_state。純觀測。
 * ============================================================================
 * v30 @ 0xC03239C8 是雙原生 ISO 的切換決策(notes/ISO_FIRMWARE_COMPLETE.md §3b):
 *     r0 = G,r1 = rel%(數值上等於 ISO),r2 = mode(= gain_state 0..8)
 *     mode 1,2,3,5,6 → HCG 門檻 640;mode 7 → 3200;mode 4,8 → 永不切
 *
 * 2026-09-14 實測:強制 gain_state 7 之後,OG3K 的 raw 與 BaselineExposure
 * 和原廠 FHD 完全一致(+3.000 / 中位−黑階 79 vs 81)。所以 gain_state 就是
 * 那 2.7 檔高光餘裕的開關。但正常路徑是誰把它設成 7 還沒找到 ——
 * FUN_c0313188(唯一的 setter)只被 FrameExpos_s 用 0/1 呼叫過。
 *
 * 這個觀測器直接記錄錄影當下實際用到的 mode,不需要推論。
 * 錄影期間 USB 必須拔掉(卡片 I/O 與 USB IRQ 互鎖),但 hook 在相機端照跑。
 *
 * LOG(0xC0732880):+0x00 總次數  +0x04 最後 mode  +0x08 最後 rel%
 *                  +0x10 起 9 個計數,索引 = gain_state 0..8
 * ========================================================================== */

.equ LOG,  0xC0732880
.equ BACK, 0xC03239CC

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global entry
entry:
    push    {r0, r1, r2, r3, ip, lr}

    LDA     ip, LOG
    ldr     r3, [ip]
    add     r3, r3, #1
    str     r3, [ip]
    str     r2, [ip, #4]                @ 最後的 mode
    str     r1, [ip, #8]                @ 最後的 rel%

    cmp     r2, #8                      @ 只統計 0..8
    bhi     out
    add     r0, ip, #0x10
    ldr     r3, [r0, r2, lsl #2]
    add     r3, r3, #1
    str     r3, [r0, r2, lsl #2]

out:
    pop     {r0, r1, r2, r3, ip, lr}
    .word   0xE92D40F0                  @ 位移指令 push {r4,r5,r6,r7,lr}
    LDA     ip, BACK
    bx      ip
