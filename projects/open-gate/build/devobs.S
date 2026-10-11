.syntax unified
.arm
.text
/* ============================================================================
 * devobs — 記下回放交給 RAW 顯像引擎的影格描述子。純觀測。
 * ============================================================================
 * FUN_c05bb4a0(engine, prev_frame, cur_frame) 是回放把一格 raw 送去顯像的地方:
 *
 *   piVar3 = FUN_c0055ab8();                        ; RAW 顯像引擎
 *   (**(*piVar3 + 0x1c))(local_24, piVar3);         ; 取得參數區塊
 *   FUN_c0014dac(param_3 + 0x24, uStack_20, 0x264); ; 612 bytes 複製進描述子
 *   FUN_c02b8e38(0xc, 6, piVar3, uVar1);            ; 送出顯像工作
 *
 * 也就是說**幾何來自顯像引擎當下的參數區塊,不是 DNG**,而每個影格描述子
 * 的 +0x24 都留著一份。抓到描述子指標就能把那 612 bytes 讀出來看幾何。
 *
 * 描述子的已知佈局(來自 FUN_c05c2d10 / CinemaDngRawMemInterface__v1):
 *   +0x10 StripOffsets   +0x14 緩衝指標   +0x18 緩衝大小
 *   +0x24..+0x288 顯像參數(612 bytes)   +0x288/+0x28C 兩個字
 *
 * 後寫為準。Hook:0xC05BB4A0,B,位移指令 push {r4,r5,r6,r7,r8,fp,lr}。
 *
 * LOG(0xC0732300):+0x00 次數  +0x04 cur 描述子  +0x08 prev 描述子
 *                 +0x0C 引擎(r0)
 *                 +0x10 起:提交**當下**從 cur 描述子抄下來的欄位
 *                   +0x10 desc+0x10 StripOffsets   +0x14 desc+0x14 緩衝
 *                   +0x18 desc+0x18 大小           +0x1C desc+0x20 解析器
 *                   +0x20 desc+0x260 寬            +0x24 desc+0x264 高
 *                   +0x28 desc+0x268 位元深度      +0x2C desc+0x26C
 *
 * 2026-09-13:v1 只記指標,回放結束後再讀 —— 讀到的是拆除後的殘留
 * (解析器已釋放、strip 已清),看不到提交當下的狀態。必須在 hook 當下抄。
 * ========================================================================== */

.equ LOG,  0xC0732600
.equ BACK, 0xC05BB4A4

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global entry
entry:
    push    {r3, ip}
    LDA     ip, LOG
    ldr     r3, [ip]
    add     r3, r3, #1
    str     r3, [ip]
    str     r2, [ip, #4]                @ cur frame
    str     r1, [ip, #8]                @ prev frame
    str     r0, [ip, #12]               @ engine

    push    {r0, r1}                    @ 從 cur 描述子(r2)抄關鍵欄位
    ldr     r0, [r2, #0x10]
    str     r0, [ip, #0x10]
    ldr     r0, [r2, #0x14]
    str     r0, [ip, #0x14]
    ldr     r0, [r2, #0x18]
    str     r0, [ip, #0x18]
    ldr     r0, [r2, #0x20]
    str     r0, [ip, #0x1C]
    movw    r1, #0x260
    ldr     r0, [r2, r1]
    str     r0, [ip, #0x20]
    movw    r1, #0x264
    ldr     r0, [r2, r1]
    str     r0, [ip, #0x24]
    movw    r1, #0x268
    ldr     r0, [r2, r1]
    str     r0, [ip, #0x28]
    movw    r1, #0x26C
    ldr     r0, [r2, r1]
    str     r0, [ip, #0x2C]
    pop     {r0, r1}

    pop     {r3, ip}
    push    {r4, r5, r6, r7, r8, fp, lr}   @ 位移指令
    LDA     ip, BACK
    bx      ip
