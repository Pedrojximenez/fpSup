.syntax unified
.arm
.text
#include "og_pic.inc"
/* ============================================================================
 * imx410_fmt — picker hook 的動態版。掛在 FUN_c043ccf8 進入點 0xC043CCF8。
 * ============================================================================
 *   r0 = obj   r1 = table   r2 = key
 *
 * 與 fmttable.S 的差別只有一件事:**沒有靜態格式表**。
 * fmttable 掃一張八到十列、由載入器寫死的表;這裡呼叫 og3krecipe 依七個軸
 * 當場算出唯一那一列,再把它組成 picker 要的 16-byte 表項。
 *
 * fmttable.S 原封不動留著 —— 它是 OG3K/OG2K/OG6K/HSW 四個出貨目標的承重牆。
 *
 * 前四個位元組識別 "CUST";格率尾碼與原廠呼叫端的 eRawBitType 同步到
 * AXIS 後才重算。14-bit 與 12-bit 共用 TAB3,不能只看表指標反推位深。
 *
 * 查不到 mode 時**不放行給原廠**。原廠查不到會退回 TAB3[0] = UHD30,而
 * 2026-09-27 實測那會造成「畫面拉長、檔案是 UHD」。改成回傳同一張表的
 * slot 7 = FHD30,並清掉 PICKOK 讓顯示鏈跟著 picker 走 16:9。
 * 使用者 2026-09-27 的決定:「這個配置沒有 mode 對應,強制錄影就隨便用個
 * fhd 給他錄。」
 *   ⚠ v1 固定用 FHD30,不跟著選單格率走。原廠的退回同樣不跟(而且是 UHD),
 *     所以這是嚴格的改善;要跟格率得在表裡找 "FHD<suffix>",列為後續。
 *
 * ENTRY(48 bytes,RAM)—— 前 16 bytes 就是 picker 拿走的表項:
 *   +0x00  5
 *   +0x04  profile
 *   +0x08  donor mode        <- RECIPE
 *   +0x0C  key ptr (= +0x14)
 *   +0x10  donor 時序記錄位址 <- 由 RECIPE.idx 與 imager 描述子算出
 *   +0x14  key 16 bytes      <- 每次命中照抄請求的鍵
 * ========================================================================== */

#ifndef RECIPE
.equ RECIPE,   OGA(0xC0733040)
#endif
#ifndef RECIPE_CODE
.equ RECIPE_CODE, OGA(0xC0733400)        /* og3krecipe 的 entry */
#endif
#ifndef ENTRY
.equ ENTRY,    OGA(0xC0733080)
#endif
#ifndef PROFILE_ID
/* 我們宣告的 PARAM profile 的 id 放在這個 RAM 字(imx410_plan.PROFILE_ID)。
 * id 是私有的(mapping 空槽指向底列),畫布 hook 覆寫那一列 —— 見
 * IMX410_FULL_DESIGN §13 與 imx410_plan.PRIVATE_PROFILE。沒有預設值:
 * 2026-09-28 `.equ PROFILE, 13` 的預設值悄悄蓋過計畫,三次凍結。 */
#error "PROFILE_ID comes from imx410_plan"
#endif

.equ IMAGER,   0xC343B588           /* [這裡] -> 模式表描述子 */
#ifndef HITS
/* ⚠ 這個預設值只給獨立組譯用。計畫**必須**傳 HITS —— 2026-09-28 沒傳,
 * 而 0xC0730700 剛好落在 imx410_aspect2 的 payload 裡,於是每一次命中都會
 * 遞增一個活著的指令。當時還沒爆只因為 FLAG=0、一次都沒命中。 */
.equ HITS,     OGA(0xC0730700)
#endif
.equ TAB1,     0xC0BE5810           /* eRawBitType 4 =  8-bit */
.equ TAB2,     0xC0BE59B0           /* eRawBitType 3 = 10-bit */
.equ TAB3,     0xC0BE5B50           /* eRawBitType 0 = 12-bit */
.equ BITLATCH, OGA(0xC0731C14)
.equ PICKOK,   OGA(0xC0731C44)
.equ FPSLATCH, OGA(0xC0731C40)
#ifndef LABEL
.equ LABEL,    0x54535543           /* "CUST" 小端 */
#endif
.equ BD12,     0
.equ BD10,     3
.equ BD8,      4
/* ---- 選單的格率 -> AXIS ---------------------------------------------------
 * ★ picker 的鍵是「標籤 + 格率字串」,而格率字串是**選單選的那一個**
 *   (原廠字串池 0xC0BE4800:400 240 120 100 23_98 60 50 48 30 25 24)。
 *   我們一直只比對前四個位元組的標籤,後面整段丟掉 —— 於是 AXIS 的格率
 *   只能從主機改。比對尾碼就能把它接回來,**不用新增任何 hook**。
 *
 * ⚠ 行為改變:接上之後**選單說了算**。先前用 --axis-preset 設 240 而選單
 *   停在 120 時,錄出來是 240;現在會變成 120。要測 240 就得把選單也切到
 *   第十列。`WITH_RATE_FROM_MENU` 可以關掉。見 §8.10。 */
#ifndef RATESTR
.equ RATESTR,  OGA(0xC0730160)           /* 11 筆 x 8 bytes,NUL 補滿 */
#endif
.equ RATE_COUNT, 11
.equ A_RATE,   1*4
.equ FHD30_SLOT, 7                  /* 三張表的 slot 7 都是 FHD30 */
.equ BACK,     0xC043CCFC

/* RECIPE 字位移 */
.equ R_VALID,  9*4
.equ R_MODE,   10*4
.equ R_IDX,    11*4
.equ R_TW0,    12*4
.equ R_TW1,    13*4
.equ R_EFPS,   19*4

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
    push    {r3, r4, r5, r6, r7, r8, ip, lr}   @ 偶數個 —— 維持 8-byte 對齊
    /* r1(table)、r2(key)要活過 og3krecipe 的呼叫。og3krecipe 會 push/pop
     * r4-r11,所以那一段是安全的;r0-r3 與 r12 不是。 */
    mov     r4, r1                      @ table
    mov     r6, r2                      @ key

    LDA     ip, TAB3
    cmp     r4, ip
    moveq   r5, #BD12
    beq     haveitab
    LDA     ip, TAB2
    cmp     r4, ip
    moveq   r5, #BD10
    beq     haveitab
    LDA     ip, TAB1
    cmp     r4, ip
    bne     pass
    mov     r5, #BD8
haveitab:

    /* 鍵的前四個位元組是不是我們的標籤 */
    LDA     ip, LABEL
    ldr     r3, [r6]
    cmp     r3, ip
    bne     pass

#ifdef WITH_BIT_FROM_MENU
    /* 只在 FUN_c043b828 的三個已核對呼叫點讀原廠 config。
     * 原廠 r6 是 config;entry 保存的 r6 在 sp+12,現在 r6 已是 key。
     * 直接呼叫 picker 的其他使用者不保證 r6 的語意,絕不能解參考它。
     * 不新增 hook、不做跨次讀取;同一次呼叫的 enum 與表必須相符。 */
    LDA     ip, 0xC043B8D8             @ TAB1: BL C043CCF8 的返回點
    cmp     lr, ip
    beq     bs_read
    add     ip, ip, #0x30              @ TAB2: C043B908
    cmp     lr, ip
    beq     bs_read
    add     ip, ip, #0x24              @ TAB3: C043B92C (12 或 14)
    cmp     lr, ip
    bne     bs_done
bs_read:
    ldr     r3, [sp, #12]
#ifdef BIT14
    /* imx410_bit14:原廠設定只存 12-bit,14 只在記憶體記號 BIT14。CUSTOM 鍵 +
     * TAB3 + config 說 12 + 記號 -> 把這次 config 的 eRawBitType 改成 1,
     * 之後的錄影描述子(BitsPerSample、平面)跟著 config 走。設定區不動。 */
    ldr     ip, [r3, #0x20]
    cmp     ip, #0
    cmpeq   r5, #BD12
    bne     1f
    LDA     ip, BIT14
    ldr     ip, [ip]
    cmp     ip, #1
    moveq   ip, #1
    streq   ip, [r3, #0x20]
1:
#endif
    ldr     r3, [r3, #0x20]            @ eRawBitType,本次原廠 config
    cmp     r3, #1                     @ 14-bit 的表仍是 TAB3
    cmpeq   r5, #BD12
    beq     bs_fourteen
    cmp     r3, r5                     @ 其餘必須與 table 一致
    bne     bs_done
    mov     r0, #12
    cmp     r3, #BD8
    moveq   r0, #8
    cmp     r3, #BD10
    moveq   r0, #10
    b       bs_store
bs_fourteen:
    mov     r0, #14
bs_store:
    mov     r5, r3                     @ BITLATCH 保留真正 enum (14 = 1)
    LDA     ip, AXIS
    ldr     r1, [ip]
    cmp     r1, r0
    strne   r0, [ip]                   @ A_BIT = 0;重算前同步
bs_done:
#endif

#ifdef WITH_RATE_FROM_MENU
    /* ---- 鍵的尾碼 -> AXIS 的格率索引 ------------------------------------
     * 逐位元組比,兩邊同時到 NUL 才算命中。對不到就不動 AXIS(沿用主機值),
     * 所以這一段是 fail-open 的。**必須在 og3krecipe 之前** —— 它是看 AXIS
     * 有沒有變才決定要不要重算的。 */
    LDA     r0, RATESTR
    mov     r8, #0
rs_next:
    cmp     r8, #RATE_COUNT
    bhs     rs_done
    add     r1, r6, #4                  @ 鍵的尾碼
    mov     r3, #0
rs_byte:
    ldrb    r2, [r0, r3]
    ldrb    ip, [r1, r3]
    cmp     r2, ip
    bne     rs_miss
    cmp     r2, #0                      @ 兩邊都到 NUL -> 命中
    beq     rs_hit
    add     r3, r3, #1
    cmp     r3, #8
    blo     rs_byte
rs_miss:
    add     r0, r0, #8
    add     r8, r8, #1
    b       rs_next
rs_hit:
#ifdef RATE240
    /* ⛔ 第一守則:原廠只存 119.88("120");使用者選了第十列 239.76 時,
     * 只有記憶體記號 RATE240 知道。120 + 記號 -> 240(索引 9)。 */
    cmp     r8, #8
    bne     1f
    LDA     r1, RATE240
    ldr     r1, [r1]
    cmp     r1, #0
    movne   r8, #9
1:
#endif
    LDA     r1, AXIS
    ldr     r2, [r1, #A_RATE]
    cmp     r2, r8
    strne   r8, [r1, #A_RATE]           @ 只在真的不同時寫,不要白白觸發重算
rs_done:
#endif

    /* 依七個軸重算(AXIS 沒變的話它自己會立刻返回) */
    LDA     ip, RECIPE_CODE
    blx     ip

    LDA     r7, RECIPE
    ldr     r3, [r7, #R_VALID]
    cmp     r3, #0
    beq     fallback

/* ---- 命中 ---------------------------------------------------------------- */
    LDA     r3, BITLATCH
    str     r5, [r3]
    LDA     r3, PICKOK
    mov     ip, #1
    str     ip, [r3]
    LDA     r3, FPSLATCH
    ldr     ip, [r7, #R_EFPS]
    str     ip, [r3]

    /* 組 ENTRY */
    LDA     r1, ENTRY
    mov     ip, #5
    str     ip, [r1]
    /* USER 搬遷會壓縮 RECIPE 與 PROFILE_ID 之間的空洞，不能沿用舊位址差。 */
    LDA     ip, PROFILE_ID
    ldr     ip, [ip]                           @ 我們宣告的私有 profile id
    str     ip, [r1, #4]
    ldr     ip, [r7, #R_MODE]
    str     ip, [r1, #8]
    add     ip, r1, #0x14
    str     ip, [r1, #0xC]

    /* donor 時序記錄 = timing 基底 + idx * 0x20。基底從 imager 描述子拿,
     * 不寫死 —— 表被搬走也跟得上(IMX410_FULL_DESIGN §14)。 */
    LDA     r3, IMAGER
    ldr     r3, [r3]
    ldr     r3, [r3]                    @ +0x00 = 時序表基底
    ldr     ip, [r7, #R_IDX]
    add     r3, r3, ip, lsl #5
    str     r3, [r1, #0x10]

    /* 鍵照抄 16 bytes 到 +0x14,讓表項自我一致(picker 不會再比一次,
     * 但除錯與 og3k_verify 對照時有用)。 */
    mov     ip, #0
1:  ldr     r0, [r6, ip]
    add     r2, r1, #0x14
    str     r0, [r2, ip]
    add     ip, ip, #4
    cmp     ip, #16
    blo     1b

    /* 時序兩個字是一組。遮蔽 IRQ/FIQ,讓同 CPU 的 reader 只看得到舊 tuple
     * 或新 tuple。抄 fmttable.S 的做法,它已經實機跑過。 */
    mrs     r2, cpsr
    orr     r0, r2, #0xC0
    msr     cpsr_c, r0
    ldr     r0, [r7, #R_TW0]
    str     r0, [r3, #4]
    ldr     r0, [r7, #R_TW1]
    str     r0, [r3, #8]
    dmb     ish
    mrs     r0, cpsr
    bic     r0, r0, #0xC0
    and     r2, r2, #0xC0
    orr     r0, r0, r2
    msr     cpsr_c, r0

    LDA     r3, HITS
    ldr     r0, [r3]
    add     r0, r0, #1
    str     r0, [r3]
    mov     r0, r1                      @ 回傳 ENTRY
    pop     {r3, r4, r5, r6, r7, r8, ip, lr}
    bx      lr

/* ---- 沒有 mode 對應:給原廠 FHD30,不要 UHD30 --------------------------- */
fallback:
    LDA     r3, PICKOK
    mov     ip, #0
    str     ip, [r3]                    @ 顯示鏈退場 -> 跟著 picker 走 16:9
    add     r0, r4, #(FHD30_SLOT * 16)
    pop     {r3, r4, r5, r6, r7, r8, ip, lr}
    bx      lr

pass:
    pop     {r3, r4, r5, r6, r7, r8, ip, lr}
    push    {r4, r5, r6, r7, r10, r11, lr}   @ 位移的原指令
    LDA     ip, BACK
    bx      ip
