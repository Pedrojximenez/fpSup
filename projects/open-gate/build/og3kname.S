.syntax unified
.arm
.text
#include "og_pic.inc"
/* ============================================================================
 * og3kname — 解析度名:**新增一個 case**,不改原廠任何一格
 * ============================================================================
 *
 * 掛在 XC_LiveViewConfigurator::v1 @ C0437B48(解析度名發射器)的進入點。
 * 原函式的形狀(反編譯確認):
 *
 *     r0 = obj   r1 = 輸出緩衝   r2 = 結構,[r2+8] = 寬,[r2+0xC] = 高
 *     依序比對 0xC0BCFE70 (4096x2160) → "DCI4K"
 *              0xC0BCFE78 (3840x2160) → "UHD"
 *              0xC0BCFE80 (1280x720)  → "HD"
 *              都不中               → "FHD"
 *     最後 FUN_c01f578c(輸出緩衝, 選中的字串, 0xF) 寫出去
 *
 * v1(2026-09-12)的做法是髒的:它把 0xC0BCFE80/84 這一對(真實的 720p 格式)
 * 改成我們的尺寸,又把 0xC0437C34/38 的 "HD" 字串指標改指向我們的 "OG3K"。
 * 等於挪用一個仍在服役的格式槽,而且動了四個原廠位置。
 *
 * v2:自己呼叫同一個輸出函式,然後直接返回;不符合就原封不動跳回原函式。
 * 原廠的四個比對與四個字串一個字都沒動,而且因為不再需要換字串指標,
 * 連函式指標表 0xC0BE44DC 也不用動 —— 直接 hook 函式進入點就好。
 *
 * 淨效果:原本動四個原廠位置 + 一個 vtable 槽,現在是一個 hook。
 *
 * 命中條件(兩者皆可,互不干擾):
 *   旗標立起            —— 選單路徑。選單傳進來的尺寸是上一個模式的殘值,
 *                          因為 MenuItemMovieRecSize 沒有 OG3K 那一列。
 *   尺寸 == 3008x2000   —— 回放路徑。那是 DNG 的裁切尺寸。
 * ========================================================================== */
.equ FLAG,   OGA(0xC0731C08)
/* 2026-09-13:FUN_c043bc68 用**同一個發射器**組影片回放的查表鍵:
 *     C043BCA4  ldr r2,[r5,#8]        ; param_1 的 vtable
 *     C043BCA8  add r1,sp,#0x10       ; 鍵緩衝(堆疊上,16 bytes)
 *     C043BCAC  ldr r3,[r2,#0xc]      ; vtable+0xC = 這個發射器
 *     C043BCB8  blx r3                ; → 回來時 lr = 0xC043BCBC
 * 鍵基底是空字串,發射器接上 "UHD"/"FHD"/"DCI4"/"HD"(0xC0BCFE88 起的內嵌
 * 字串,退回值是 "FHD"),之後依旗標再接 "CROP" —— 所以影片表的鍵字面上
 * 就是 "UHD"/"FHD"/"UHDCROP"/"FHDCROP"。
 *
 * 我們原本只要看到 3008x2000 就無條件發射 "OG3K",**連鍵一起改掉了**:
 * 查表必然失敗 → FUN_c043bc68 退回表的第 0 筆 = p51。
 * 實測回放載入 p51 而不是 "FHD" 會選到的 p53,那就是我們自己的指紋。
 *
 * 這個發射器的輸出有兩種用途,只有「給人看的名字」該被我們改,
 * 「查表鍵」必須原封不動。用 lr 分辨,精確而且不動任何原廠碼。 */
.equ KEYBLD, 0xC043BCBC

/* 回放內容的尺寸判定。2026-09-15:原本寫死 3008x2000,那是 OG3K 的 DNG
 * 裁切尺寸;OG2K 是 2000x1334,永遠不相符 → PBFLAG 從來不會被設 →
 * 回放的畫布 case B 不觸發 → 回放 profile 保持原廠柵格(3856 / 1936)
 * 而片子只有 2016 寬 → 黑屏凍結。改吃目標參數。 */
#ifndef TARGET_AW
#define TARGET_AW 3008
#define TARGET_AH 2000
#endif

.equ PBFLAG, OGA(0xC0731C0C)          /* 1 = 正在顯示本目標裁切尺寸的內容(回放) */
.equ NAME,  OGA(0xC0730C00)          /* 我們自己的 "OG3K" 字串 */
.equ EMIT,  0xC01F578C          /* 原函式用來寫出字串的那個 */
.equ ORIG,  0xC0437B48
.equ BACK,  0xC0437B4C

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
    /* 先判尺寸並維護 PBFLAG,再決定輸出 —— 順序不能反。
     * v2 把旗標檢查放在最前面,OG3K 選中時就直接跳到 ours,
     * 尺寸那一段變成死碼,PBFLAG 永遠不會被設。
     *
     * PBFLAG 的規則:寬為 0(無意義的呼叫)就不動它;否則
     * PBFLAG = (寬 == TARGET_AW 且 高 == TARGET_AH)。這樣不相關的呼叫不會清掉它。 */
    ldr     r3, [r2, #0x08]
    cmp     r3, #0
    beq     decide                      @ 寬 0:不動 PBFLAG
    movw    ip, #TARGET_AW
    cmp     r3, ip
    bne     notours
    ldr     r3, [r2, #0x0C]
    movw    ip, #TARGET_AH
    cmp     r3, ip
    bne     notours
    LDA     ip, PBFLAG                  @ 是本目標裁切尺寸的內容
    mov     r3, #1
    str     r3, [ip]
    b       ours
notours:
    LDA     ip, PBFLAG
    mov     r3, #0
    str     r3, [ip]

decide:
    LDA     ip, FLAG                    @ 選單路徑:旗標立起就用 OG3K
    ldr     ip, [ip]
    cmp     ip, #0
    beq     pass

ours:
    /* 鍵組建者的呼叫一律放行 —— 它要的是原廠 token,不是我們的名字。
     * PBFLAG 上面已經維護過了,所以這裡放行不影響旗標。 */
    LDA     ip, KEYBLD
    cmp     lr, ip
    beq     pass

    push    {r4, lr}
    mov     r0, r1                      @ 輸出緩衝
    LDA     r1, NAME
    mov     r2, #0x0F
    LDA     ip, EMIT
    blx     ip
    pop     {r4, lr}
    bx      lr

pass:
#ifdef OG_CHAIN
    OG_PASS                     @ Loader v3: the layer below, or og_replay
.global og_replay
og_replay:
#endif
    push    {r4, r5, r6, r7, r8, sb, fp, lr}   @ 位移的原指令
    LDA     ip, BACK
    bx      ip
