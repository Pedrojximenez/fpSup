.syntax unified
.arm
.text
#include "og_pic.inc"
/* ============================================================================
 * fmttable — 格式註冊表。掛在 FUN_c043ccf8 進入點 0xC043CCF8。
 * ============================================================================
 *   r0 = obj   r1 = table   r2 = key
 *
 * 2026-09-15:三張 picker table **都是 CinemaDNG**,差的只有位元深度。
 * 呼叫端 FUN_c043b828 依 *(param_2+0x20)(= eRawBitType)選表:
 *     4 → TAB1 8-bit     3 → TAB2 10-bit     其餘 → TAB3 12-bit
 * v0.2.1a 只接 TAB3,所以選 8/10-bit 時 "OG3K<rate>" 查不到,原廠的錯誤
 * 退回給出 &DAT_c0be5b50 = TAB3 第 0 筆 = **UHD30**。
 * 見 notes/OG3K_8BIT_10BIT_FALLS_BACK_TO_UHD.md。
 *
 * 掃我們自己的格式表,鍵相符就:
 *   1. 把該幀率的時序寫進 donor 的時序記錄
 *   2. 把位元深度碼鎖存給 og3kcanvas(它要據此寫平面格式碼)
 *   3. 回傳這一筆的前 16 bytes 當作 picker entry
 * 沒相符就跳回原廠迴圈。
 *
 * 每筆 48 bytes:
 *   +0x00  5                 entry[0]
 *   +0x04  profile           entry[1]
 *   +0x08  donor mode        entry[2]
 *   +0x0C  key ptr (= 本筆 +0x14)   entry[3]
 *   +0x10  donor 時序記錄位址
 *   +0x14  key 字串 16 bytes
 *   +0x24  要寫進 時序+0x04 的字 (hmax | tail<<16)
 *   +0x28  要寫進 時序+0x08 的字 (vmax | x<<16)
 *   +0x2C  引擎格率(float bits)—— 原廠在同一個 picker slot 上宣告的
 *          畫布 +0x030。WITH_ENGFPS 關閉時這裡放的是整數 nominal fps class
 *          (只供驗證/清單)。
 * key 第一個字為 0 表示表尾。比對前 8 bytes。
 * ========================================================================== */

.equ TABLE, OGA(0xC0731000)
.equ HITS,      OGA(0xC0730700)
.equ TAB1,      0xC0BE5810          @ eRawBitType 4 =  8-bit
.equ TAB2,      0xC0BE59B0          @ eRawBitType 3 = 10-bit
.equ TAB3,      0xC0BE5B50          @ eRawBitType 0 = 12-bit
.equ BITLATCH,  OGA(0xC0731C14)          @ og3kcanvas 讀這裡選平面格式碼
#ifdef TARGET_ENGFPS
.equ FPSLATCH,  TARGET_ENGFPS        @ og3kcanvas 讀這裡寫畫布 +0x030
#endif
#ifdef TARGET_MATCH
/* picker 是否同意。名字不能叫 MATCH —— og3kfps.S 已經有一個同名巨集。 */
.equ PICKOK,    TARGET_MATCH         @ og3kout/aspect/aspect2 讀這裡
.equ LABEL,     TARGET_LABEL         @ 本目標的標籤四個位元組("OG3K"/"OG2K")
#endif
.equ BD12,      0
.equ BD10,      3
.equ BD8,       4
.equ BACK,  0xC043CCFC

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
    /* r5 帶位元深度碼。**不可以借 r1** —— r1 是原廠 lookup 的 table 參數,
     * 而 pass 會跳回原廠函式的第二條指令繼續執行。2026-09-15 回歸:
     * v0.2.2a 借了 r1,於是任何「進了我們的表但鍵不符」的查詢(也就是
     * 每一次非 OG3K 的 CinemaDNG 查詢)都會讓原廠 lookup 從位址 0 開始掃。 */
    push    {r3, r4, r5, r6, ip, lr}
    /* 三張表都要接,並且記下是哪一張 —— 那就是這次錄影的位元深度。
     * r1(table)比對完就不需要原值了,拿它把位元深度碼帶到 hit。
     * 不在這三張裡的一律完整走原廠,不能拿到 p83/mode98。 */
    LDA     ip, TAB3
    cmp     r1, ip
    moveq   r5, #BD12
    beq     search
    LDA     ip, TAB2
    cmp     r1, ip
    moveq   r5, #BD10
    beq     search
    LDA     ip, TAB1
    cmp     r1, ip
    bne     pass
    mov     r5, #BD8
search:
    LDA     ip, TABLE

loop:
    ldr     r3, [ip, #0x14]
    cmp     r3, #0
    beq     tailend                     @ 表尾
    ldr     r4, [r2]
    cmp     r3, r4
    bne     next
    ldr     r3, [ip, #0x18]
    ldr     r4, [r2, #4]
    cmp     r3, r4
    beq     hit
next:
    add     ip, ip, #48
    b       loop

hit:
    /* 位元深度鎖存。只有命中 OG3K 才寫,所以不會被別的查詢污染;
     * 下面那個 dmb 會一併把它發布出去。
     * DNG 的 BitsPerSample 由 FUN_c06a5290 用 FUN_c02da870(eRawBitType)
     * 算,不看 profile —— 所以 og3kcanvas 把 +0x084 對齊 eRawBitType 之後,
     * 標籤與資料就自動一致。 */
    LDA     r4, BITLATCH
    str     r5, [r4]
#ifdef TARGET_MATCH
    LDA     r4, PICKOK                  @ picker 同意:顯示鏈可以走 3:2
    mov     r3, #1
    str     r3, [r4]
#endif
#ifdef TARGET_ENGFPS
    /* 引擎格率鎖存。p83/p13 這類 donor 原廠帶的 +0x030 與我們實際在錄的
     * 格率無關(p83 = 18.0 的照片連拍率),而訊號處理引擎的組態 +0x10 就是
     * 它 —— FUN_c01caba0 的 `fps < 30` 分支、FUN_c01cec08 的 >99 閘門、
     * FUN_c01d11e8 的 timeout 全看這一個字。表裡放的是原廠在同一個 picker
     * slot 上宣告的值,所以引擎看到的與原廠一致。 */
    LDA     r4, FPSLATCH
    ldr     r3, [ip, #0x2C]
    str     r3, [r4]
#endif
    ldr     r3, [ip, #0x10]             @ donor 時序記錄

    /* mode98 的兩個 timing words 是一組。遮蔽 IRQ/FIQ，讓同 CPU 的 reader
     * 只能看到舊 tuple 或新 tuple；精確 tuple 驗證也讓跨核的混合讀取
     * fail-open。r2 已不再需要，拿來保存原 CPSR。 */
    mrs     r2, cpsr
    orr     r1, r2, #0xC0
    msr     cpsr_c, r1
    ldr     r4, [ip, #0x24]
    str     r4, [r3, #4]                @ hmax | tail
    ldr     r4, [ip, #0x28]
    str     r4, [r3, #8]                @ vmax
    dmb     ish
    mrs     r1, cpsr
    bic     r1, r1, #0xC0
    and     r2, r2, #0xC0
    orr     r1, r1, r2
    msr     cpsr_c, r1

    LDA     r4, HITS
    ldr     r3, [r4]
    add     r3, r3, #1
    str     r3, [r4]
    mov     r0, ip
    pop     {r3, r4, r5, r6, ip, lr}
    bx      lr

tailend:
#ifdef TARGET_MATCH
    /* 掃完整張表都沒命中。若請求的鍵**開頭四個位元組就是我們的標籤**,
     * 那就是「選了本目標 + 表裡沒有的格率」—— 唯一的例子是 119.88
     * (OG3K120 物理上不可能)。原廠會退回 TAB3[0] = UHD30,而只看 FLAG 的
     * og3kout/aspect/aspect2 會把顯示強制成 3:2 -> 畫面拉長、檔案是 UHD。
     *
     * 清掉 PICKOK,讓那三個 hook 退場 -> 顯示跟著 picker 走 16:9,
     * 行為等同原廠 UHD。r2 一路沒被寫過,仍是鍵指標。 */
    LDA     r4, LABEL
    ldr     r3, [r2]
    cmp     r3, r4
    bne     pass
    LDA     r4, PICKOK
    mov     r3, #0
    str     r3, [r4]
#endif
pass:
    pop     {r3, r4, r5, r6, ip, lr}
#ifdef OG_CHAIN
    OG_PASS                     @ Loader v3: the layer below, or og_replay
.global og_replay
og_replay:
#endif
    push    {r4, r5, r6, r7, r10, r11, lr}   @ 位移的原指令
    LDA     ip, BACK
    bx      ip
