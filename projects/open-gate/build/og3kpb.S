.syntax unified
.arm
.text
/* ============================================================================
 * og3kpb — 回放:把 canvas 的 profile 換成 p43,原廠表一個字都不動
 * ============================================================================
 *
 * 源碼(反編譯)顯示 FUN_c0437af8 只讀表項的一個欄位:
 *
 *     undefined4 FUN_c0437af8(int entry, undefined4 x) {
 *         FUN_c0439668(&local, *(undefined4 *)(entry + 4), x, 3);   // profile id
 *         ...
 *     }
 *
 * 而回放傳進來的是**名稱表**的表項(實測:0xC0BE4508 第 0 筆
 * {6, p51, 222, "UHD"}),於是 canvas 用 p51 的 UHD 3856x2170 幾何去顯示一個
 * 3032 寬的檔案 —— 行距差 824 像素,就是水平條紋。
 *
 * 名稱表三組是連續的:0xC0BE4508 .. 0xC0BE45C8。
 *
 * 做法:表項指標落在那個範圍、而且 og3kname 剛判定內容是 3008x2000 時,
 * 把指標換成我們自己在 RAM 裡的一筆 {6, 43, 222, "OG3K"}。
 * FUN_c0437af8 只讀 +4,所以換指標是安全的,而且**原廠的名稱表完全沒被修改**
 * —— 2026-09-12 我改 FHDCROP 那一筆的 profile id,破壞了 373 的反向查詢,
 * 畫面直接黑掉。這一版沒有那個問題。
 * ========================================================================== */
.equ PBFLAG, 0xC0731C0C
.equ PBENT,  0xC0731C10          /* 我們的表項:{6, 43, 222, "OG3K" 指標} */
.equ NTLO,   0xC0BE4508
.equ NTHI,   0xC0BE45C8
.equ BACK,   0xC0437AFC
.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm
.global entry
entry:
    push    {r3, ip}
    LDA     ip, PBFLAG
    ldr     ip, [ip]
    cmp     ip, #0
    beq     out
    LDA     ip, NTLO
    cmp     r0, ip
    blo     out
    LDA     ip, NTHI
    cmp     r0, ip
    bhs     out
    LDA     r0, PBENT               @ 換成我們的表項
out:
    pop     {r3, ip}
    push    {r4, r5, r6, lr}        @ displaced
    LDA     ip, BACK
    bx      ip
