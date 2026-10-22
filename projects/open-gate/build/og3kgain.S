.syntax unified
.arm
.text
/* ============================================================================
 * og3kgain — 讓 OG3K 的擷取拿到 movie_raw_12bit 的增益分配。
 * ============================================================================
 * 2026-09-14 實測鏈條:
 *
 *   雙原生 ISO 的切換由 v30 @ 0xC03239C8 決定,參數 mode = gain_state:
 *       mode 1,2,3,5,6 → HCG 門檻 ISO 640
 *       mode 7 (movie_raw_12bit) → 門檻 ISO 3200
 *   mode 取自 G+0x0C(G = 0xC343A6A0),由 ContSet_Adr1 從擷取設定
 *   param_2+0x20 填進送給 imager 的命令:
 *       C031C110  ldr r1, [r6, #0x20]
 *       C031C114  ldr r0, [sp, #0x44]
 *       C031C118  str r1, [r0, #0xc]
 *
 *   用 gsobs.S 統計 v30 的 mode(只錄 OG3K 一段):
 *       gain_state 3 (movie, 門檻 640)      41 次
 *       gain_state 7 (movie_raw_12bit)       3 次
 *   原廠 FHD 幾乎全是 7。**所以 OG3K 拿到 3,在 ISO 640 以上就切了 HCG。**
 *
 *   後果不只是機內回放過亮:實測 OG3K 的 raw 比原廠 FHD 亮 2.675 EV、
 *   BaselineExposure 只有 +0.322 而非 +3.000 ——**少掉約 2.7 檔高光餘裕**。
 *   用 `imager fixed_gain_state 6`(內部 7)強制之後,兩者完全一致
 *   (+3.000 / 中位−黑階 79 vs 81),證明 gain_state 就是那個開關。
 *
 * 守衛很窄:必須「拿到的值正好是 3」且「OG3K 被選中」。
 *   - 原廠 FHD 本來就拿 7,不會被碰到
 *   - 拍照不走 ContSet(連續擷取)這條路
 *   - 其他影片格式拿 3 但 FLAG 為 0,也不會被碰到
 *
 * Hook:0xC031C110,B,位移指令 ldr r1,[r6,#0x20] 由我們自己做。
 * LOG(0xC07328C0):+0x00 介入次數  +0x04 最後看到的原值
 * ========================================================================== */

.equ FLAG, 0xC0731C08
.equ LOG,  0xC07328C0
.equ BACK, 0xC031C114
.equ FROM, 3                    /* movie,HCG 門檻 640 */
.equ TO,   7                    /* movie_raw_12bit,門檻 3200 */

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global entry
entry:
    ldr     r1, [r6, #0x20]             @ 位移指令
    push    {r0, r2, ip, lr}

    LDA     ip, LOG
    str     r1, [ip, #4]                @ 記下原值

    cmp     r1, #FROM
    bne     done
    LDA     r0, FLAG
    ldr     r0, [r0]
    cmp     r0, #1
    bne     done

    mov     r1, #TO
    ldr     r0, [ip]
    add     r0, r0, #1
    str     r0, [ip]

done:
    pop     {r0, r2, ip, lr}
    LDA     ip, BACK
    bx      ip
