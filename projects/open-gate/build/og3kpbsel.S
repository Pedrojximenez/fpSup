.syntax unified
.arm
.text
#include "og_pic.inc"
/* ============================================================================
 * og3kpbsel — 讓 OG3K 的片子在回放時走「照片管線」。
 * ============================================================================
 *
 * 完整推導在 notes/OG3K_PLAYBACK_PROFILE_CLASSES.md 第 9 節。摘要:
 *
 * XC_LiveViewConfiguratorW71c1 的 v3(0xC043BE68)依 *param_2 選分支,
 * mode 5 = 影片回放 → FUN_c043bc68 → 組字串鍵去查 0xC0BE4508/4548/4588,
 * 回傳一筆「表項」。
 *
 * 真正的消費端是 **v5**(0xC043C090):它拿 v3 回傳的表項,用純範圍檢查
 * (FUN_c043d058/d0d8/d1d8/d258…:`表 <= 指標 < 表+跨距`)判斷它來自哪張表,
 * 然後把配置器內部的**管線子物件偏移**選出來:
 *
 *     照片表 0xC0BE4870 / 4BD0 / 5CF0 / 5D70   → param_1 + 0x268   ← 3:2
 *     錄影表 0xC0BE5810 / 59B0 / 5B50          → param_1 + 0x460
 *     回放表 0xC0BE4508 / 4548 / 4588          → +0x514(鍵非 "UHD")
 *                                              → +0x4CC / +0x4F0(鍵是 "UHD")
 *     全部不中                                 → +0x268(並記錯誤 0x511)
 *
 * 回放顯示幾何住在這些子物件裡,**不在 PARAM 列** —— 這就是為什麼
 * 2026-09-13 改 p51 的 PARAM 畫布命中 33 次卻毫無變化。
 *
 * 而 `param_1 + 0x268` 是照片管線,也就是**已經能正確顯示 3032x2012 /
 * 3008x2000 12-bit 未壓縮 DNG 的那一條**(S 尺寸照片檢視每天都在用)。
 *
 * 所以不需要新增任何 profile、表項或 PARAM 列:遇到 3008x2000 的片子時,
 * 讓 v3 回傳**照片檢視表現成的那一筆**:
 *
 *     0xC0BE5D20 = 0xC0BE5CF0 + 3*16 = {1, 43, 98, "12BLOW"}
 *
 * 它落在 0xC0BE5CF0..+0x80 之內,所以 v5 的 FUN_c043d0d8 會回 1,
 * 走 +0x268,而且**不會**觸發錯誤記錄。一個原廠位元都不動。
 *
 * 用 p43(檢視,張數 0)而不是 p83(拍攝,張數 3):我們要顯示一個檔案,
 * 不需要擷取緩衝。
 *
 * 守衛完全自我判斷,不靠旗標:mode 必須是 5,且 param_2+0x08/+0x0C 必須是
 * 3008x2000(那是 v1 發射器比對的同一對欄位,PBFLAG 實測為 1 已證明
 * 回放時這一對確實是 3008x2000)。
 *
 * 之前 og3kpb.S 失敗是因為掛錯位置 —— 掛在 FUN_c0437af8(緩衝尺寸查詢),
 * 不是管線選擇器。
 *
 * Hook:0xC043BE68,B,位移指令是 push {r4, r5, r6, lr}。
 * ========================================================================== */

/* 回傳哪一筆表項 = 選哪一條管線,而 v5 只用位址範圍認表,所以這是一個
 * **可以列舉的旋鈕**。做成從 RAM 讀,換候選時一個 mem set 就好,不用重載。
 * 0 = 不介入(完全原廠行為)。
 *
 * v5 的檢查順序與對應的管線(表有重疊,先中先贏):
 *   0xC0BE4870/4990/4BD0            → +0x268  照片
 *   0xC0BE4C50/5050                 → +0x340/3D0/3F4/43C
 *   0xC0BE4D50/5150                 → 同上(type 3)
 *   0xC0BE5450 (跨距 0x300)         → 鍵=="DCI4K" ? +0x560 : +0x538  ← WithRaw
 *   0xC0BE5610 (跨距 0x200,與上重疊) → 鍵前3=="UHD" ? +0x4A8 : +0x484
 *   0xC0BE5810/59B0/5B50            → +0x460  錄影
 *   0xC0BE4508/4548/4588            → 回放(原廠行為)
 *
 * 候選(柵格寬正好 3032 的用 ★):
 *   0xC0BE5D20  {1, p43,  98, "12BLOW"}  柵格 2024x1341  → +0x268   已試:有結構但斑點
 *   0xC0BE5690  {4, p331,106, "FHD30"}   柵格 3032x1708 ★→ +0x538   WithRaw
 *   0xC0BE5BC0  {5, p175,106, "FHD30"}   柵格 1936x1090  → +0x460   錄影管線
 */
#ifndef TARGET_AW
#define TARGET_AW 3008
#define TARGET_AH 2000
#endif

.equ ENT,    OGA(0xC0732390)         /* 要回傳的表項指標(0 = 不介入) */
.equ BACK,   0xC043BE6C
.equ LOG,    OGA(0xC0732380)         /* +0 命中次數  +4 mode 5 的總次數 */

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
    push    {r2, r3, ip, lr}

    ldr     r3, [r1]                    @ *param_2 = mode
    cmp     r3, #5                      @ 5 = 影片回放
    bne     pass

    LDA     ip, LOG
    ldr     r3, [ip, #4]
    add     r3, r3, #1
    str     r3, [ip, #4]

    /* 2026-09-15:原本寫死 3008x2000(OG3K 的 DNG 裁切),改吃目標參數。
     * 與 og3kname 的 PBFLAG 判定必須用同一對數字。 */
    ldr     r3, [r1, #0x08]             @ v1 比對的同一對尺寸欄位
    movw    r2, #TARGET_AW
    cmp     r3, r2
    bne     pass
    ldr     r3, [r1, #0x0C]
    movw    r2, #TARGET_AH
    cmp     r3, r2
    bne     pass

    ldr     r3, [ip]                    @ 命中計次
    add     r3, r3, #1
    str     r3, [ip]

    LDA     r2, ENT
    ldr     r2, [r2]
    cmp     r2, #0
    beq     pass                        @ 0 = 不介入
    mov     r0, r2
    pop     {r2, r3, ip, lr}
    bx      lr

pass:
    pop     {r2, r3, ip, lr}
#ifdef OG_CHAIN
    OG_PASS                     @ Loader v3: the layer below, or og_replay
.global og_replay
og_replay:
#endif
    push    {r4, r5, r6, lr}            @ 位移指令
    LDA     ip, BACK
    bx      ip
