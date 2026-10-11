.syntax unified
.arm
.text
#include "og_pic.inc"
/* og3krange — 讓分派器把我們的格式表認成 picker 表 3(CinemaDNG)。
 *
 * C043D258(r0, r1, r2) 是範圍檢查:r2 <= r1 < r2 + 0x1A0 回 1。
 * 0xC043C5F0 起的分派器用它判斷 r5(一個表項指標)屬於哪張表,
 * 再選對應的目的偏移。我們的 fmttable hook 回傳的是指向自己的表
 * 0xC0731000 的指標,不在任何已知範圍內,分派器就認不出來 ——
 * 回放因此走到錯的分支,用 FHD 的幾何去解一個 3032 寬的檔案。
 *
 * 只在「查的是表 3」且「指標落在我們的表內」時才回 1,
 * 其他情況原封不動走原路。 */
.equ T3,    0xC0BE5B50          /* picker 表 3 = CinemaDNG */
/* 2026-09-28:加 #ifndef,讓全功能版能帶單一 ENTRY 的範圍進來。
 * 預設值一個位元都沒動 —— 四個出貨目標組出來的位元組逐字相同。 */
#ifndef OURLO
.equ OURLO, OGA(0xC0731000)
#endif
#ifndef OURHI
.equ OURHI, OGA(0xC07311E0)          /* 9 筆 x 48 bytes */
#endif
.equ BACK,  0xC043D25C
.macro LDA reg, value
#ifdef OG_V3
    OGLDA   \reg, \value
#else
    movw    \reg, #:lower16:\value
    movt    \reg, #:upper16:\value
#endif
.endm
.global entry
entry:
    LDA     ip, T3
    cmp     r2, ip
    bne     pass
    LDA     ip, OURLO
    cmp     r1, ip
    blo     pass
    LDA     ip, OURHI
    cmp     r1, ip
    bhs     pass
    mov     r0, #1
    bx      lr
pass:
    push    {r4, r5}            @ displaced
    LDA     ip, BACK
    bx      ip
