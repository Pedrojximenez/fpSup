.syntax unified
.arm
.text
#include "og_pic.inc"
/* OG_ENUM: the resolution value this target stores (OG3K 4, OG2K 7; uishare/ui/enums.py). */
#ifndef OG_ENUM
#define OG_ENUM 4
#endif
/* ============================================================================
 * og3ksel — 讓 OG3K 成為真正的第三個選項。
 * ============================================================================
 * 掛在解析度 setter C005C020 進入點,原指令 push {r4,r5,r6,lr}。
 *   r0 = obj   r1 = enum   r2 = flag
 *
 * 選單第三列產生 enum 4,但 MenuItemMovieRecSize 只有 {2→FHD, 3→UHD} 兩筆,
 * enum 4 查不到就落回 FHD 那一對尺寸。所以在 setter 當下依 enum 改寫那一對:
 *
 *   enum 4  →  旗標 = 1
 *   其餘    →  旗標 = 0
 *
 * v2:不再改 MenuItemMovieRecSize —— 實測 enum 4 查不到尺寸時是「保持原值」,
 * 不是落回 enum 2 那一筆,所以從 UHD 切過來會留著 3840×2160。改由
 * og3kname 直接接管解析度名,完全不依賴尺寸。
 * 命中計數在 0xC0731C00,最後一次的 enum 在 +0x04。
 * ========================================================================== */

.equ PAIR,  0xC074222C          /* MenuItemMovieRecSize enum2 的 寬/高 */
.equ LOG,   OGA(0xC0731C00)
.equ FLAG,  OGA(0xC0731C08)          /* 1 = OG3K 生效,畫布 hook 看這個 */
.equ GTAB,  OGA(0xC0732100)          /* 分組表,見下方說明 */
/* 2026-09-21:FLAG 的意思收緊成「選了本目標 **而且** 錄影格式是 CinemaDNG」。
 * MOV 不走 CinemaDNG picker,只看 FLAG 的那組 hook 若仍開著,按錄影會
 * 硬凍結 —— OG3K 與 OG2K 都實測確認。見 og3kfmt.S 與
 * notes/FLAG_AND_PICKER_DISAGREE.md §38。 */
.equ FMTLATCH, OGA(0xC0731C20)       /* 0 = CinemaDNG,由 og3kfmt / og3krestore 寫;開機值 UNKNOWN(非 0 → 不生效) */
/* 使用者上次選的是不是本目標。XC_CommonSaveData +0x290,跨電源循環,
 * 而且**不需要任何存檔命令**(PERSISTENT_STORE_COMMONSAVE.md)。
 * 開機時由 og3krestore 讀回並還原。 */
.equ OGSAVE,   0xC30754CC
/* donor 感測器模式的 timing record;離開本模式時要還原成原廠。
 * 由 og3k_plan 的 DEFINES 提供;沒定義時是 OG3K 的 mode98。 */
#ifndef TARGET_MODE_TIMING
#define TARGET_MODE_TIMING 0xC0B59540
#define TARGET_MODE_W0     0x01BD01BD  /* mode98 stock hmax=445, tail=445 */
#define TARGET_MODE_W1     0x0004082E  /* mode98 stock vmax=2094, x=4 */
#endif
.equ DONOR_TIMING, TARGET_MODE_TIMING
.equ DONOR_W0,     TARGET_MODE_W0
.equ DONOR_W1,     TARGET_MODE_W1
.equ BACK,  0xC005C024

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
    push    {r2, r3, r4, r5, r6, r7, ip, lr}

    LDA     ip, LOG                     @ 記一下,方便回讀確認
    ldr     r3, [ip]
    add     r3, r3, #1
    str     r3, [ip]
    str     r1, [ip, #4]

#ifdef TARGET_FMT_GUARD
    /* 使用者的選擇本身,與錄影格式無關 —— 這是跨電源循環要記住的東西,
     * 所以先寫,再去算「現在生不生效」。 */
    cmp     r1, #OG_ENUM
    moveq   r4, #1
    movne   r4, #0
    LDA     ip, OGSAVE
#ifdef OG_SAVE_ENUM
    /* Loader v3, OG3K and OG2K stacked: OGSAVE holds the OG enum the user chose
     * (0 = none), shared by every OG layer.  Chosen -> mine; otherwise clear it
     * only while it still says mine (another layer may have just written its own). */
    ldr     r3, [ip]
    cmp     r4, #0
    movne   r3, #OG_ENUM
    bne     1f
    cmp     r3, #OG_ENUM
    moveq   r3, #0
1:  str     r3, [ip]
#else
    str     r4, [ip]
#endif

    /* 生效還要求錄影格式是 CinemaDNG。格式不對就當成沒選中,
     * 整段交易會走「離開」那一條:撤旗標、還原 donor 時序、分組欄位歸位。 */
    mov     r5, r4
    cmp     r5, #0
    beq     decided
    LDA     ip, FMTLATCH
    ldr     r3, [ip]
    cmp     r3, #0
    movne   r5, #0
decided:
#else
    cmp     r1, #OG_ENUM
    moveq   r5, #1
    movne   r5, #0
#endif

    /* FLAG、共用 timing tuple 與分組欄位是一個解析度切換 transaction。
     * 離開 OG3K 時先撤旗標再還原 mode98；進入時先把資料準備好，最後才
     * 發布 FLAG=1。遮蔽 IRQ/FIQ，避免同 CPU reader 看見半組 timing。 */
    mrs     r6, cpsr
    orr     r7, r6, #0xC0
    msr     cpsr_c, r7
#ifdef OG_GTAB_SHARED
    /* r7 = how many leading (shared) GTAB groups to skip; 0 = write them all.
     * Only "leaving for another OG" below sets it. */
    mov     r7, #0
#endif
    cmp     r5, #0
    bne     groups
#ifdef OG_CHAIN
    /* Loader v3, OG3K and OG2K stacked: leaving is undoing what *this* layer
     * did.  Not active -> write nothing (the timing, the shared preview
     * heights): another layer may be the one just selected. */
    LDA     ip, FLAG
    ldr     r3, [ip]
    cmp     r3, #0
    beq     gdone
#endif
    LDA     ip, FLAG
    mov     r3, #0
    str     r3, [ip]
    dmb     ish
#ifdef TARGET_DYN_DONOR
    /* 全功能版:donor 是**變動的**,還原的對象由配方決定,不是編譯期常數。
     * 原廠時序存在 RECIPE 的 R_SAVE0/R_SAVE1(og3krecipe 在 imx410_fmt 覆寫
     * 之前讀下來的)。不還原的話,配方借過 mode 106 之後切回原廠 FHD30
     * 就拿到我們的時序。
     *
     * 順便把快照第一個字作廢 -> 下次進來一定重算 -> 重新存一次原廠時序。
     * **不能清 valid** —— og3krecipe 比的是快照不是 valid,清了它會讓
     * imx410_fmt 永遠走 FHD fallback。 */
    LDA     ip, TARGET_DYN_DONOR        @ = RECIPE 的位址
    ldr     r3, [ip, #9*4]              @ R_VALID
    cmp     r3, #0
    beq     8f
    ldr     r3, [ip, #11*4]             @ R_IDX
    cmp     r3, #70
    bhs     8f
    ldr     r7, [ip, #21*4]             @ R_SAVE0
    cmp     r7, #0
    beq     8f
    ldr     r2, [ip, #22*4]             @ R_SAVE1
    mvn     lr, #0
    str     lr, [ip]                    @ 快照作廢
    LDA     ip, TARGET_DYN_IMAGER
    ldr     ip, [ip]
    ldr     ip, [ip]                    @ 時序表基底
    add     ip, ip, r3, lsl #5
    str     r7, [ip, #4]
    str     r2, [ip, #8]
8:
    dmb     ish
#else
    LDA     ip, DONOR_TIMING
    LDA     r3, DONOR_W0
    str     r3, [ip, #4]
    LDA     r3, DONOR_W1
    str     r3, [ip, #8]
    dmb     ish
#endif

    /* LCD 預覽的可見高。實測引擎匯出組態 C31DF564+0x30 為
     *   可見 2000x1125   來源 2016x1344
     * 來源本來就是 3:2 全高,是「可見」這一步把它裁成 16:9。長寬比 hook 與
     * 主輸出模板已讓下游變成 3:2,若這裡仍是 1125,那張 16:9 就會被非等比
     * 撐滿 3:2 的框 —— 就是縱向拉高的來源。
     * 改成 1334:邊距 2016-2000=16、1344-1334=10,與原廠邊距同構。
     * 實測引擎組態會在 1334 與 1125 之間來回跳,而 profile 5 的表值一直是
     * 1334 —— 因為 1125 來自別的 profile。搜索全表發現同樣是 2016x1344 來源
     * 的「+1C = 1」兄弟共六個:5、210、227、257、258、259,可見全是 2000x1125;
     * 而「+1C = 2」的那些(1、41、42、81、82…)可見都是 2000x1334。
     * 待機用 profile 5,半按與錄影切到別的兄弟,所以六個都要補。
     *
     * 這些 profile 為所有模式共用,所以必須跟著旗標還原,不能一次寫死。
     * 位址表由 og3k_load.py 裝在 0xC0732100。 */
    /* 分組表 @0xC0732100(由 og3k_load / AutoRun 填):
     *     +0x00  群組數
     *     每組:  筆數, 選中時的值, 未選時的值, 之後是該組的位址
     *
     *   群組 0  六個預覽 profile 的 PARAM+0x28    1125 → 1334
     *   群組 1  八個 OG3K profile 的 RWZM 四欄    0x640 → 0x400(unity)
     *
     * RWZM 那組是 open gate 的關鍵:1600 = 1.5625x 的實質縮小會把 producer
     * 的有效區釘在 1936 寬,錄出來就只有左上一塊有畫面。八個格率用八個不同
     * 的 profile,所以三十二欄都要補 —— 舊 AutoRun 只補了 profile 175 那四欄。
     *
     * 這些 profile 是 FHD 共用的,所以一定要跟著旗標還原,不能寫死。 */
#ifdef OG_SAVE_ENUM
    /* Leaving, and another OG layer was just chosen (OGSAVE = its enum): that
     * layer owns the shared preview heights now -- above us it has already
     * written them, below us it is about to.  Restoring them here would undo it.
     * (The only GTAB group under OG_CHAIN is the shared one; og3k_plan checks.) */
    LDA     ip, OGSAVE
    ldr     r3, [ip]
    cmp     r3, #0
    cmpne   r3, #OG_ENUM
#ifdef OG_GTAB_SHARED
    /* 2026-10-07: GTAB also carries this layer's private groups (the video
     * clamp of its donor modes, og3k_plan.CLAMP_*).  Those must go back even
     * when another OG takes over; only the shared groups are skipped. */
    movne   r7, #OG_GTAB_SHARED
#else
    bne     gdone
#endif
#endif
groups:
    LDA     ip, GTAB
    ldr     r4, [ip], #4                @ 群組數
gloop:
    cmp     r4, #0
    beq     gdone
    ldr     r2, [ip], #4                @ 這組的筆數
    ldr     r3, [ip], #4                @ 選中時的值
    ldr     lr, [ip], #4                @ 未選時的值
    cmp     r5, #0
    moveq   r3, lr
eloop:
    cmp     r2, #0
    beq     gnext
    ldr     lr, [ip], #4
#ifdef OG_GTAB_SHARED
    cmp     r7, #0                      @ a shared group being skipped: walk past it
    streq   r3, [lr]
#else
    str     r3, [lr]
#endif
    sub     r2, r2, #1
    b       eloop
gnext:
#ifdef OG_GTAB_SHARED
    cmp     r7, #0
    subne   r7, r7, #1
#endif
    sub     r4, r4, #1
    b       gloop
gdone:
    dmb     ish
    cmp     r5, #0
    beq     published
    LDA     ip, FLAG
    mov     r3, #1
    str     r3, [ip]                    @ 最後才讓其他 hooks 看見 OG3K
    dmb     ish
published:
    mrs     r7, cpsr
    bic     r7, r7, #0xC0
    and     r6, r6, #0xC0
    orr     r7, r7, r6
    msr     cpsr_c, r7

    pop     {r2, r3, r4, r5, r6, r7, ip, lr}
#ifdef OG_CHAIN
    OG_PASS                     @ Loader v3: the layer below, or og_replay
.global og_replay
og_replay:
#endif
    push    {r4, r5, r6, lr}            @ 位移的原指令
    LDA     ip, BACK
    bx      ip
