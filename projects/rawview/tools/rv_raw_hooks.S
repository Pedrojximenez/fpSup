.syntax unified
.arm
.text
/* ============================================================================
 * rv_raw_hooks — rawview RAW 模式:增益 hook + 依 ISO 自動換 tone 表
 * ============================================================================
 *
 * 參數區(host 填):
 *   P+0x00 flag       0 = 原廠;非 0 = RAW
 *   P+0x04 last_rel   上次套表時的相對增益(host 開啟時清 0)
 *   P+0x08 tab_base   31 張 tone 表的起點,每張 0x1000,依 ISO 由低到高
 *   P+0x0C slots      11 格插槽陣列(每格 8 bytes,+4 是表位址)
 *   P+0x10 thr[30]    相對增益門檻:rel < thr[k] → 表 k;都不小於 → 表 30
 *
 * stub_gs 取代 0xC0313244 `ldr r2,[r5,#0xc]`(FUN_c03131e0:r5 = helper,r6 = 這次的相對增益,r4 使用中)
 *   待機(gain_state 0)且旗標開:r2 = 7;相對增益和上次不同時,把 11 格插槽指到對應的表並清 ctx0 快取鍵,
 *   原廠換表流程下一輪就會載入。只寫資料、不呼叫函式;sp 8-byte 對齊,r4/r5 自行保存。
 * stub_dg 取代 0xC032F728 `ldr r6,[ip]`:旗標開且 bank 0 → RAW_CORR 數位增益 1×(0x400)。
 *   sp 未對齊 → leaf,不呼叫任何函式。
 * ========================================================================== */

#ifndef P
.equ P,        0xC072E800      /* standalone default; the caller passes the real one */
#endif
.equ KEY_CTX0, 0xC2F19D44
.equ NTHR,     30

params:
flag:       .word 0
last_rel:   .word 0
tab_base:   .word 0
slots:      .word 0
thr:        .space NTHR * 4

stub_gs:
    ldr     r2, [r5, #0xc]          /* 原指令 */
    cmp     r2, #0
    bxne    lr                      /* 不是待機:不動 */
    ldr     r3, =P
    ldr     r0, [r3]                /* flag */
    cmp     r0, #0
    bxeq    lr
    ldr     r0, [r3, #4]            /* last_rel */
    cmp     r0, r6
    beq     1f
    ldr     r0, [r3, #8]            /* tab_base; 0 = 未載入表,只做增益 */
    cmp     r0, #0
    beq     1f
    str     r6, [r3, #4]
    push    {r4, r5}
    add     r4, r3, #0x10           /* thr[] */
    mov     r1, #0
2:  ldr     ip, [r4, r1, lsl #2]
    cmp     r6, ip
    blo     3f
    add     r1, r1, #1
    cmp     r1, #NTHR
    blo     2b
3:  add     r0, r0, r1, lsl #12     /* 表 k 的位址 */
    ldr     r4, [r3, #0xC]          /* slots */
    mov     r1, #11
4:  str     r0, [r4, #4]
    add     r4, r4, #8
    subs    r1, r1, #1
    bne     4b
    ldr     r4, =KEY_CTX0
    mvn     r0, #0
    str     r0, [r4]                /* 清 ctx0 快取鍵 → 原廠流程重新載入 */
    pop     {r4, r5}
1:  mov     r2, #7                  /* movie_raw_12bit */
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
