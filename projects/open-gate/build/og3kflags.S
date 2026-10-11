.syntax unified
.arm
.text
/* ============================================================================
 * og3kflags — 讓 OG3K 的擷取被當成「影片 raw」,拿回 2.7 檔高光餘裕。
 * ============================================================================
 * 2026-09-14 追出來的完整鏈條:
 *
 *   錄影的 gain_state 由 FUN_c039dde8 分派:
 *       FUN_c03a6df8() → bit 8 → gain_state 7
 *       FUN_c03a6db8() → bit 2 → gain_state 3
 *       FUN_c03a6dd8() → bit 3 → 依位元深度 5 / 6 / 7(12-bit → 7)
 *       全假                    → gain_state 3
 *
 *   三者讀的是同一個值的不同位元,而那個值就是
 *   **FUN_c043a1c8(pid) 依 profile id 的數值範圍算出來的旗標**
 *   (存在 obj+0x168):
 *       bit 3 的條件是 131 <= pid <= 190
 *
 *   p83 = 83 → 旗標 0x00 → 三個判斷全假 → **gain_state 3**(HCG 門檻 640)
 *   p175 = 175 → bit 3 → 位元深度分派 → 12-bit → **gain_state 7**(門檻 3200)
 *
 *   實測完全吻合(gsobs.S 統計 v30 的 mode,只錄 OG3K 一段):
 *       gain_state 3 = 41 次,gain_state 7 = 3 次;原廠 FHD 幾乎全是 7。
 *
 *   後果:ISO 640 以上 OG3K 就切了 HCG,**少掉約 2.7 檔高光餘裕**。
 *   實測 raw 比原廠 FHD 亮 2.675 EV、BaselineExposure +0.322 而非 +3.000。
 *   用 `imager fixed_gain_state`(內部 7)強制之後兩者完全一致
 *   (+3.000 / 中位−黑階 79 vs 81),證明 gain_state 就是那個開關。
 *
 * 131..190 裡**沒有任何空的 pid**,所以「換一個落在正確範圍的 pid」行不通。
 * 改成在旗標算完之後補上 bit 3:
 *
 *       C043A1A0  bl  c043a1c8      ; 算旗標
 *       C043A1A4  mov r3, r0        ; <= hook 這一格,r5 還是 pid
 *       C043A1A8  str r3, [r4, #0x168]
 *
 * 守衛:pid 必須是 83,且 OG3K 被選中。原廠格式與其他 profile 都不會被碰到。
 * 拍照雖然也載入 p83,但它的 gain_state 由 FrameExpos_s 直接設 1,不走這條分派。
 * ========================================================================== */

.equ FLAG, 0xC0731C08
.equ LOG,  0xC07328C0           /* +0x00 介入次數 */
.equ BACK, 0xC043A1A8
.equ PROF, 83
.equ BIT,  8                    /* bit 3 = 走位元深度分派 */

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global entry
entry:
    mov     r3, r0                      @ 位移指令
    push    {r0, r1, ip, lr}

    cmp     r5, #PROF
    bne     done
    LDA     ip, FLAG
    ldr     ip, [ip]
    cmp     ip, #1
    bne     done

    orr     r3, r3, #BIT
    LDA     ip, LOG
    ldr     r0, [ip]
    add     r0, r0, #1
    str     r0, [ip]

done:
    pop     {r0, r1, ip, lr}
    LDA     ip, BACK
    bx      ip
