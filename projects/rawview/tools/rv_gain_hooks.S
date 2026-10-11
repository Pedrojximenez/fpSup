.syntax unified
.arm
.text
/* ============================================================================
 * rv_gain_hooks — rawview RAW 模式的兩個增益 hook(README「增益 hook 設計」)
 * ============================================================================
 *
 * P+0x00  flag        0 = 原廠行為;非 0 = RAW 模式
 * P+0x04  stub_gs     取代 0xC0313244 `ldr r2,[r5,#0xc]`(E595200C)
 *                     待機(gain_state 0)且旗標開 → 改用 7(12-bit 錄影的增益規則)
 *                     可用 r0/r1/r3/ip,旗標無用,sp 8-byte 對齊,lr 已在 prologue 保存
 * P+0x24  stub_dg     取代 0xC032F728 `ldr r6,[ip]`(E59C6000),最終夾好的 RAW_CORR 數位增益(Q10)
 *                     旗標開且 bank 0(r5==0)→ 1×(0x400)
 *                     可用 r0–r3、ip;sp 未 8-byte 對齊 → 必須是 leaf,不能呼叫任何函式
 *
 * 兩個 stub 都以 `bl` 進入,原指令在 stub 裡重做一次。
 * ========================================================================== */

#ifndef P
.equ P,        0xC072E800      /* standalone default; the caller passes the real one */
#endif

flag:
    .word   0

stub_gs:
    ldr     r2, [r5, #0xc]          /* 原指令 */
    cmp     r2, #0
    bxne    lr                      /* 不是待機:不動 */
    ldr     r3, =P
    ldr     r3, [r3]
    cmp     r3, #0
    movne   r2, #7                  /* movie_raw_12bit */
    bx      lr

stub_dg:
    ldr     r6, [ip]                /* 原指令 */
    ldr     r0, =P
    ldr     r0, [r0]
    cmp     r0, #0
    bxeq    lr
    cmp     r5, #0
    bxne    lr                      /* bank 1(拍照)不動 */
    mov     r6, #0x400              /* 1.0× */
    bx      lr

.ltorg
