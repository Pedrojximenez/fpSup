.syntax unified
.arm
.text
/* ============================================================================
 * og3ksize — 讓 UI 知道 OG3K 的解析度尺寸。
 * ============================================================================
 * MenuItemMovieRecSize::v3(0xC00A81E8)是「目前解析度 → 寬高」的查表:
 *
 *   for (p = &DAT_c0742228; p != s_Invalid_MovSize_c0742240; p += 3)
 *       if (*p == 目前的 enum) { param_2[0] = p[1]; param_2[1] = p[2]; return; }
 *   → 都不中就記 "Invalid MovSize" 錯誤
 *
 * 那張表**只有兩筆**,而且緊接著就是終止用的字串,無法就地擴充:
 *
 *   [0] 值 2 → 0x780 x 0x438 = 1920 x 1080   (FHD)
 *   [1] 值 3 → 0xF00 x 0x870 = 3840 x 2160   (UHD)
 *
 * OG3K 用的是 enum **4**(og3ksel 比的就是 #4),查不到 → 走錯誤路徑。
 * 三個 UI 症狀都是這一個原因:
 *   - 記錄設定的「解析度」顯示 `3` 而不是名稱
 *   - QS 的 RES. 格子畫出疊在一起的亂圖
 *   - QS 底部只有 UHD / FHD 兩個選項
 *
 * 這裡不去搬那張表(那要改原廠函式裡的兩個立即值),而是加一個 case:
 * OG3K 被選中時直接回傳 3008x2000。原廠表一個位元都不動,
 * 其他解析度完全走原廠路徑。
 *
 * 3008x2000 是 DNG 的裁切尺寸,也就是使用者實際得到的畫面尺寸
 * (記錄尺寸 3024x2010 含 +16/+10 的邊界,不該顯示給使用者 ——
 *  原廠也是顯示 1920x1080 而不是 1936x1090)。
 *
 * Hook:0xC00A81E8,B,位移指令 push {r4,r5,r6,r7,r8,sb,fp,lr}。
 * r0 = param_1,r1 = param_2(輸出:[0] 寬 [4] 高)
 * ========================================================================== */

.equ FLAG, 0xC0731C08
.equ LOG,  0xC0732780           /* +0 呼叫次數  +4 命中次數 */
.equ BACK, 0xC00A81EC
.equ W,    3008
.equ H,    2000

.macro LDA reg, value
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
.endm

.global entry
entry:
    push    {r2, r3, ip, lr}

    LDA     ip, LOG
    ldr     r3, [ip]
    add     r3, r3, #1
    str     r3, [ip]

    LDA     r3, FLAG
    ldr     r3, [r3]
    cmp     r3, #0
    beq     pass                        @ 不是 OG3K:完全原廠

    ldr     r3, [ip, #4]
    add     r3, r3, #1
    str     r3, [ip, #4]

    movw    r2, #W
    str     r2, [r1]
    movw    r2, #H
    str     r2, [r1, #4]
    pop     {r2, r3, ip, lr}
    bx      lr

pass:
    pop     {r2, r3, ip, lr}
    .word   0xE92D4BF0                  @ 位移指令(原始編碼,助記符組出來不一致)
    LDA     ip, BACK
    bx      ip
